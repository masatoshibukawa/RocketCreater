"""Persistent free-design revisions with one geometry and a bounded local production harness."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rocketwright.agent.project_assembly import STEP_IDS, Observation, assembly_assessment
from rocketwright.agent.project_equipment import Equipment, procurement_summary
from rocketwright.agent.project_jobs import cancel_path, file_lock, locked, progress, resource_lease
from rocketwright.agent.project_requirements import assess_requirements, validate_requirements
from rocketwright.agent.workbench import Conflict
from rocketwright.analysis.schema import MOUNTS, STOCKS, Assumptions
from rocketwright.geometry import airframe
from rocketwright.manufacturing import (
    PrintGeometry,
    PrintRequest,
    fingerprint,
    prepare,
    prepare_geometry,
)
from rocketwright.physics import water
from rocketwright.schema import BottleDesign, Env, Requirement

ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    temp.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def implementation_fingerprint():
    files = [
        "rocketwright/schema.py",
        "rocketwright/manufacturing.py",
        "rocketwright/physics/water.py",
        "rocketwright/geometry.py",
        "rocketwright/agent/project_requirements.py",
        "rocketwright/agent/project_equipment.py",
        "rocketwright/agent/project_assembly.py",
        "rocketwright/analysis/schema.py",
        "scripts/build_print_parts.py",
        "3d model/prototypes/pet-rocket-coke-2l/build.py",
        "3d model/prototypes/pet-rocket-coke-2l/parameters.json",
    ]
    return fingerprint({p: sha(ROOT / p) for p in files})


class DesignSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: str = Field(default="ペトロケの試作", min_length=1, max_length=100)
    design: BottleDesign
    geometry: PrintGeometry
    requirement: Requirement | None = None
    env: Env = Field(default_factory=Env)
    other_dry_mass_g: float = Field(gt=0, le=2000)
    measured_printed_mass_g: float | None = Field(default=None, gt=0, le=1000)
    material: str = Field(
        default="UltiMaker Tough PLA Gray", pattern="^(UltiMaker Tough PLA Gray|Prusament PETG)$"
    )
    assumptions: Assumptions = Field(default_factory=Assumptions)
    equipment: Equipment = Field(default_factory=Equipment)
    altitude_rule: Literal["band_10pct", "minimum"] = "band_10pct"

    @model_validator(mode="after")
    def physical_envelope(self):
        cylinder = math.pi * (self.geometry.body_diameter_mm / 2000) ** 2
        cylinder *= self.geometry.body_height_mm / 1000
        if self.design.bottle_volume_m3 > cylinder * 1.02:
            raise ValueError("容量が入力したボトル外形の最大体積を超えています。")
        if self.design.nozzle_diameter_m > self.geometry.body_diameter_mm / 1000:
            raise ValueError("ノズル径がボトル胴径を超えています。")
        if self.requirement and self.requirement.goal_kind.value != "altitude":
            raise ValueError("この製作フローは高度を指定するペトロケ用です。")
        validate_requirements(self)
        return self


class DesignProjects:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(
            os.getenv("ROCKETWRIGHT_DESIGN_ROOT", ROOT / "output/design-projects")
        )
        self.locks: dict[str, threading.Lock] = {}
        self.guard = threading.Lock()
        self.session = uuid.uuid4().hex

    def base(self, project_id):
        if not re.fullmatch(r"[a-f0-9]{32}", project_id):
            raise KeyError("Unknown design project")
        return self.root / project_id

    def directory(self, project_id):
        state = self.load(project_id)
        return self.base(project_id) / f"v{state['version']}"

    def load(self, project_id):
        try:
            return json.loads((self.base(project_id) / "state.json").read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise KeyError("Unknown design project") from exc

    def _write(self, state):
        state["updated_at"] = time.time()
        write_json(self.base(state["id"]) / "state.json", state)
        write_json(self.base(state["id"]) / f"v{state['version']}/snapshot.json", state)

    def get(self, project_id):
        state = self.load(project_id)
        if state["analysis"] and "cad_sha256" not in state["analysis"]:
            # Earlier saved records already carry the original CAD hashes in their registry.
            state["analysis"]["cad_sha256"] = {
                f["name"]: f["sha256"] for f in state["files"] if f["kind"] == "cad"
            }
        if not state["adopted"]:
            state["files"] = [
                f
                for f in state["files"]
                if f["name"].endswith((".png", ".json")) or f["name"] == "analysis-envelope-m.stl"
            ]
        active = state["active"]
        abandoned = (
            active
            and active.get("owner") != self.session
            and not locked(self.base(project_id) / "operation.lock")
            and not (active.get("phase") == "queued" and time.time() - active["started_at"] < 30)
        )
        if abandoned:
            state["active"] = None
            state["error"] = "前回の処理は中断されました。保存済みの入力から再試行できます。"
            state["revision"] += 1
            self._write(state)
        elif active:
            state["active"]["progress"] = progress(self, project_id, active)
        return state

    def list(self):
        rows = []
        for path in self.root.glob("*/state.json"):
            try:
                state = self.get(path.parent.name)
                rows.append(
                    {k: state[k] for k in ("id", "name", "version", "revision", "updated_at")}
                )
            except (KeyError, ValueError, OSError):
                continue
        return sorted(rows, key=lambda x: x["updated_at"], reverse=True)[:100]

    def create(self, spec: DesignSpec):
        spec = DesignSpec.model_validate(spec.model_dump())
        state = dict(
            id=uuid.uuid4().hex,
            name=spec.name,
            revision=0,
            version=1,
            spec=spec.model_dump(mode="json"),
            active=None,
            error=None,
            analysis=None,
            adopted=False,
            files=[],
            history=[],
            versions=[],
            video_plan=None,
            photographic_video_plan=None,
            adaptive=None,
            observations=[],
            created_at=time.time(),
        )
        self._write(state)
        return state

    def _run(self, project_id, revision, operation, worker, *, started_event=None):
        with self.guard:
            lock = self.locks.setdefault(project_id, threading.Lock())
        if not lock.acquire(blocking=False):
            raise Conflict("別の処理を実行中です。完了後に再試行してください。")
        process_lock = None
        process_locked = False
        try:
            process_lock = file_lock(self.base(project_id) / "operation.lock")
            process_lock.__enter__()
            process_locked = True
            state = self.get(project_id)
            reservation = state.get("active") or {}
            own_job = reservation.get("id") == os.getenv("ROCKETWRIGHT_JOB_ID") and reservation.get(
                "id"
            )
            if state["revision"] != revision or (state["active"] and not own_job):
                raise Conflict("設計版が更新されました。最新の状態を読み直してください。")
            state["active"] = {
                **reservation,
                **dict(
                    id=reservation.get("id") or uuid.uuid4().hex,
                    name=operation,
                    phase="running",
                    started_at=reservation.get("started_at", time.time()),
                    owner=self.session,
                ),
            }
            state["error"] = None
            self._write(state)
            if started_event:
                started_event.set()
            try:
                worker(state)
                state["history"].append(
                    dict(operation=operation, version=state["version"], at=time.time())
                )
            except Exception as exc:
                state["error"] = str(exc)
                raise
            finally:
                state.setdefault("jobs", []).append(
                    {**state["active"], "finished_at": time.time(), "error": state["error"]}
                )
                state["jobs"] = state["jobs"][-50:]
                state["active"] = None
                state["revision"] += 1
                self._write(state)
            return state
        finally:
            if process_locked:
                process_lock.__exit__(None, None, None)
            lock.release()

    def cancel(self, project_id, revision):
        state = self.get(project_id)
        if state["revision"] != revision or not state["active"]:
            raise Conflict("現在の処理がありません。")
        cancel_path(self, project_id, state["active"]["id"]).parent.mkdir(exist_ok=True)
        cancel_path(self, project_id, state["active"]["id"]).touch()
        return self.get(project_id)

    def edit(self, project_id, revision, spec: DesignSpec):
        spec = DesignSpec.model_validate(spec.model_dump())

        def worker(state):
            self.new_version(state, spec)

        return self._run(project_id, revision, "edit", worker)

    def new_version(self, state, spec: DesignSpec):
        """Called under the project operation lock by human edits and host redesigns."""
        spec = DesignSpec.model_validate(spec.model_dump())
        from rocketwright.agent.project_revisions import reuse_previous_cad

        old = {k: state[k] for k in ("version", "spec", "analysis")}
        self._write(state)
        state["versions"].append(
            dict(
                version=state["version"],
                adopted=state["adopted"],
                spec=state["spec"],
                analysis=state["analysis"],
            )
        )
        state.update(
            version=state["version"] + 1,
            name=spec.name,
            spec=spec.model_dump(mode="json"),
            analysis=None,
            adopted=False,
            files=[],
            video_plan=None,
            photographic_video_plan=None,
            observations=[],
            cad_reuse=None,
        )
        reuse_previous_cad(self, state, old, state["spec"])
        if state.get("adaptive"):
            state["adaptive"].update(status="running", accepted_spec_hash=None)

    def adaptive_step(self, project_id, revision, *, started_event=None):
        from rocketwright.analysis.service import Harness

        return Harness(self).step(project_id, revision, started_event=started_event)

    def adaptive_run(self, project_id, revision, *, started_event=None):
        from rocketwright.analysis.service import Harness

        return Harness(self).run(project_id, revision, started_event=started_event)

    def restore(self, project_id, revision, version):
        state = self.get(project_id)
        old = next((v for v in state["versions"] if v["version"] == version), None)
        if old is None:
            raise KeyError("保存された版がありません")
        return self.edit(project_id, revision, DesignSpec.model_validate(old["spec"]))

    def compare(self, project_id, version):
        from rocketwright.agent.project_revisions import difference

        state = self.get(project_id)
        if not 1 <= version < state["version"]:
            raise ValueError("比較する旧版がありません。")
        old = json.loads(
            (self.base(project_id) / f"v{version}/snapshot.json").read_text(encoding="utf-8")
        )
        result = difference(old["spec"], state["spec"])
        a, b = old.get("analysis"), state.get("analysis")
        delta = {}
        if a and b:
            for key in ("apogee_m", "descent_speed_mps", "max_speed_mps"):
                if key in a["result"]["metrics"] and key in b["result"]["metrics"]:
                    delta[key] = b["result"]["metrics"][key] - a["result"]["metrics"][key]
        return dict(from_version=version, to_version=state["version"], **result, result_delta=delta)

    def register_files(self, state, directory, kind):
        base = self.base(state["id"]) / f"v{state['version']}"
        for path in sorted(directory.iterdir()):
            if (
                not path.is_file()
                or path.suffix
                not in {
                    ".json",
                    ".csv",
                    ".md",
                    ".pdf",
                    ".svg",
                    ".stl",
                    ".3mf",
                    ".ufp",
                    ".gcode",
                    ".png",
                    ".mp4",
                    ".zip",
                    ".py",
                }
                or path.name in {"render.log", "job.json", "snapshot.json"}
            ):
                continue
            key = path.relative_to(base).as_posix()
            state["files"] = [f for f in state["files"] if f["key"] != key]
            state["files"].append(
                dict(
                    name=path.name,
                    key=key,
                    kind=kind,
                    sha256=sha(path),
                    version=state["version"],
                    url=f"/design-projects/{state['id']}/v{state['version']}/files/{key}",
                )
            )

    def file(self, project_id, key, version=None):
        state = self.get(project_id)
        version = state["version"] if version is None else version
        if version < 1 or version > state["version"]:
            raise KeyError("Unknown design version")
        if version != state["version"]:
            state = json.loads(
                (self.base(project_id) / f"v{version}/snapshot.json").read_text(encoding="utf-8")
            )
        row = next((r for r in state["files"] if r["key"] == key), None)
        if (
            not state["adopted"]
            and Path(key).suffix in {".stl", ".3mf", ".ufp", ".gcode"}
            and key != "cad/analysis-envelope-m.stl"
        ):
            raise KeyError("採用前の製作データは配信しません")
        base = (self.base(project_id) / f"v{version}").resolve()
        path = (base / key).resolve()
        if not row or not path.is_relative_to(base) or path.is_symlink() or not path.is_file():
            raise KeyError("登録済みの成果物ではありません")
        if sha(path) != row["sha256"]:
            raise Conflict("検査後にファイルが変わりました。再生成が必要です。")
        return path

    def analyse(self, project_id, revision, *, started_event=None):
        def worker(state):
            if state["adopted"]:
                raise Conflict("採用版は保持します。編集して新しい版で再解析してください。")
            state.update(analysis=None, files=[], video_plan=None, photographic_video_plan=None)
            spec = DesignSpec.model_validate(state["spec"])
            directory = self.directory(project_id)
            cad_dir = directory / "cad"
            reuse = state.get("cad_reuse")
            valid_reuse = bool(
                reuse
                and reuse["geometry_sha256"] == fingerprint(spec.geometry.model_dump())
                and all(
                    (cad_dir / name).is_file() and sha(cad_dir / name) == expected
                    for name, expected in reuse["cad_sha256"].items()
                )
            )
            # Failed/interrupted runs may leave partial CAD; keep it for inspection.
            if cad_dir.exists() and not valid_reuse:
                cad_dir.rename(directory / ("cad-incomplete-" + uuid.uuid4().hex[:8]))
            design = spec.design.model_copy(update={"geometry": spec.geometry})
            if valid_reuse:
                geometry = json.loads((cad_dir / "geometry-check.json").read_text(encoding="utf-8"))
            else:
                with resource_lease(self, state, "renderer"):
                    _, geometry = prepare_geometry(PrintRequest(design=design), cad_dir)
            printed = sum(
                r["volume_mm3"]
                * STOCKS[spec.material]["density"]
                * 1e-6
                * (spec.geometry.fin_count if name == "fin" else 1)
                for name, r in geometry.items()
                if name != "fit-ring"
            )
            mass = spec.measured_printed_mass_g or printed
            design = design.model_copy(
                update={
                    "dry_mass_kg": (
                        spec.other_dry_mass_g
                        + mass
                        + MOUNTS[spec.assumptions.mount]["additional_mass_g"]
                    )
                    / 1000
                }
            )
            target = (
                spec.requirement.target_altitude_m
                if spec.requirement and spec.altitude_rule == "band_10pct"
                else None
            )
            result = water.simulate(design, spec.env, target_apogee_m=target)
            if (
                spec.requirement
                and spec.altitude_rule == "minimum"
                and result.metrics["apogee_m"] < spec.requirement.target_altitude_m
            ):
                result = result.model_copy(
                    update={
                        "success": False,
                        "failure_reasons": [
                            *result.failure_reasons,
                            "要求した最低高度に達していません。",
                        ],
                    }
                )
            frame = airframe(design)
            (cad_dir / "analysis-envelope-m.stl").write_bytes(frame.stl_bytes())
            state["analysis"] = dict(
                input_sha256=fingerprint(state["spec"]),
                implementation_sha256=implementation_fingerprint(),
                geometry_sha256=fingerprint(spec.geometry.model_dump()),
                design=design.model_dump(mode="json"),
                result=result.model_dump(mode="json"),
                requirements=assess_requirements(spec, result),
                printed_solid_mass_g=printed,
                printed_mass_used_g=mass,
                mass_basis="measured" if spec.measured_printed_mass_g else "solid_CAD_estimate",
                cad_sha256={p.name: sha(p) for p in cad_dir.iterdir() if p.is_file()},
                limitations=[
                    "抗力係数は仮定値。CFD格子収束・強度・実機の合格を示しません。",
                    "推定質量はCADの一様固体。充填後の実測質量で再解析してください。",
                    "解析の外形は取付部・穴・丸みを省略した寸法付き包絡です。",
                ],
            )
            state["adopted"] = False
            self.register_files(state, cad_dir, "cad")
            # Inspection previews are available before adoption; manufacturing meshes are not.
            state["files"] = [
                f
                for f in state["files"]
                if f["name"].endswith((".png", ".json")) or f["name"] == "analysis-envelope-m.stl"
            ]

        return self._run(project_id, revision, "analyse", worker, started_event=started_event)

    def require_adopted(self, state):
        analysis = state["analysis"]
        if (
            not state["adopted"]
            or not analysis
            or analysis["input_sha256"] != fingerprint(state["spec"])
            or analysis["implementation_sha256"] != implementation_fingerprint()
        ):
            raise Conflict("この版を再解析してから採用してください。")

    def adopt(self, project_id, revision):
        def worker(state):
            if state.get("adaptive"):
                from rocketwright.analysis import policy
                from rocketwright.analysis.service import Harness, code_hash

                adaptive = state["adaptive"]
                harness = Harness(self)
                campaign, spec, _, _ = harness._campaign(state)
                confirmation = harness.data(campaign, "confirm")
                if (
                    adaptive["status"] != "model_criteria_met"
                    or adaptive["accepted_spec_hash"] != policy.identity(spec)
                    or adaptive.get("accepted_code_hash") != code_hash()
                    or not confirmation
                    or not confirmation["metrics"]["criteria_met"]
                ):
                    raise Conflict(
                        "階層解析のこの版の確認が未達です。基本解析だけでは採用できません。"
                    )
            a = state["analysis"]
            if (
                not a
                or a["input_sha256"] != fingerprint(state["spec"])
                or not a["result"]["success"]
            ):
                raise Conflict("この版の計算条件を満たす解析が必要です。")
            if a["implementation_sha256"] != implementation_fingerprint():
                raise Conflict("解析コードが更新されました。再解析が必要です。")
            for name, expected in a.get("cad_sha256", {}).items():
                if sha(self.directory(project_id) / "cad" / name) != expected:
                    raise Conflict("解析後にCADが変わりました。再解析が必要です。")
            for row in state["files"]:
                self.file(project_id, row["key"])
            directory = self.directory(project_id) / "production"
            directory.mkdir(exist_ok=True)
            design = a["design"]
            g = DesignSpec.model_validate(state["spec"]).geometry
            dims = dict(
                body_diameter=g.body_diameter_mm,
                overall=g.overall_mm,
                nose_length=g.nose_length_mm,
                egg_bay_length=0,
                canopy_bay_length=0,
                bottle_length=g.body_height_mm,
                fin_root=g.fin_root_mm,
                fin_tip=g.fin_tip_mm,
                fin_span=g.fin_span_mm,
                fin_sweep=g.fin_sweep_mm,
                fin_tail_inset=g.fin_tail_inset_mm,
                fin_count=g.fin_count,
                fin_thickness=g.fin_thickness_mm,
            )
            write_json(
                directory / "assembly.json", dict(dimensions_mm=dims, key=f"v{state['version']}")
            )
            write_json(
                directory / "report.json",
                dict(
                    design=design,
                    sim_source_id=f"{state['id']}:v{state['version']}",
                    analysis=a,
                    spec=state["spec"],
                ),
            )
            write_json(directory / "trace.json", a["result"]["trace"])
            steps = assembly_steps(state)
            write_json(
                directory / "assembly-access.json",
                assembly_assessment(DesignSpec.model_validate(state["spec"])),
            )
            write_json(directory / "steps.json", steps)
            (directory / "instructions.md").write_text(
                "\n\n".join(
                    f"{i + 1}. {s['title']}\n{s['instruction']}" for i, s in enumerate(steps)
                ),
                encoding="utf-8",
            )
            write_json(directory / "design.json", dict(schema_version=1, spec=state["spec"]))
            write_json(directory / "equipment.json", state["spec"]["equipment"])
            write_json(
                directory / "procurement.json",
                procurement_summary(DesignSpec.model_validate(state["spec"])),
            )
            with (directory / "bom.csv").open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["part", "quantity", "material", "dimension_basis"])
                writer.writerows(
                    [
                        [
                            "fin",
                            g.fin_count if design["has_fins"] else 0,
                            state["spec"]["material"],
                            "CAD",
                        ],
                        ["nose", 1, state["spec"]["material"], "CAD"],
                        [
                            "bottle",
                            1,
                            "市販PET・無加工",
                            "実測" if g.dimensions_measured else "仮定",
                        ],
                    ]
                )
            state["adopted"] = True
            state["adoption_scope"] = "prototype_screening"
            self.register_files(state, self.directory(project_id) / "cad", "cad")
            self.register_files(state, directory, "production")

        return self._run(project_id, revision, "adopt", worker)

    def observe(self, project_id, revision, observation: Observation):
        observation = Observation.model_validate(observation.model_dump())

        def worker(state):
            self.require_adopted(state)
            state.setdefault("observations", []).append(
                dict(
                    **observation.model_dump(),
                    version=state["version"],
                    at=time.time(),
                    input_sha256=state["analysis"]["input_sha256"],
                )
            )
            directory = self.directory(project_id) / "observations"
            write_json(directory / "observations.json", state["observations"])
            state["files"] = [r for r in state["files"] if r["kind"] not in {"manual", "package"}]
            self.register_files(state, directory, "observations")

        return self._run(project_id, revision, "observe", worker)

    def manual(self, project_id, revision):
        def worker(state):
            from rocketwright.agent.project_manual import write_project_manual

            self.require_adopted(state)
            steps = json.loads(
                self.file(project_id, "production/steps.json").read_text(encoding="utf-8")
            )
            output = self.directory(project_id) / "manual"
            output.mkdir(exist_ok=True)
            write_project_manual(state, steps, output / "assembly.pdf")
            self.register_files(state, output, "manual")

        return self._run(project_id, revision, "assembly_pdf", worker)

    def print_package(self, project_id, revision, *, started_event=None):
        def worker(state):
            self.require_adopted(state)
            if state["spec"]["material"] != "UltiMaker Tough PLA Gray":
                raise Conflict("PETG用の印刷プロファイルは未登録です。PLA設定へ流用しません。")
            for row in state["files"]:
                self.file(project_id, row["key"])
            output = self.directory(project_id) / ("print-" + uuid.uuid4().hex[:8])
            with resource_lease(self, state, "renderer"), resource_lease(self, state, "slicer"):
                manifest = prepare(
                    PrintRequest(
                        design=BottleDesign.model_validate(state["analysis"]["design"]),
                        printer=state["spec"]
                        .get("equipment", {})
                        .get("printer_profile", "s5-gray-aa04"),
                    ),
                    output,
                )
            # Regeneration must reproduce the exact CAD volumes that supplied the mass model.
            original = json.loads(self.file(project_id, "cad/geometry-check.json").read_text())
            actual = json.loads((output / "geometry-check.json").read_text())
            if any(
                abs(original[k]["volume_mm3"] - actual[k]["volume_mm3"]) > 0.01 for k in original
            ):
                raise Conflict("スライス元の形状が解析時のCADと一致しません。")
            manifest["design_version"] = state["version"]
            write_json(
                output / "design-binding.json",
                dict(
                    version=state["version"],
                    input_sha256=state["analysis"]["input_sha256"],
                    geometry_sha256=state["analysis"]["geometry_sha256"],
                ),
            )
            self.register_files(state, output, "print")

        return self._run(project_id, revision, "slicing", worker, started_event=started_event)

    def archive(self, project_id, revision):
        def worker(state):
            self.require_adopted(state)
            output = self.directory(project_id) / "package"
            output.mkdir(exist_ok=True)
            rows = [r for r in state["files"] if r["kind"] != "package"]
            for row in rows:
                self.file(project_id, row["key"])
            missing = [
                kind
                for kind in ("manual", "print", "video", "photographic_video")
                if not any(r["kind"] == kind for r in rows)
            ]
            readme = (
                f"# {state['name']} / "
                f"v{state['version']}\n\n採用版の試作データです。実機・"
                f"飛行は未検証。\n"
                f"\n未生成: {', '.join(missing) or 'なし'}\n\n"
                "production/design.json → report.json → steps.json "
                "の順で確認してください。\n"
                "scripts/verify_package.py はファイル整合だけを読み取り検査します。"
                "\n"
            )
            readme += (
                "\n印刷用STLの*-mmと3MFはmm単位。UFP/G-codeはS5/Gray/AA0.4専用です。\n"
                "analysis-envelope-m.stlはm単位の解析包絡で、印刷用ではありません。\n"
                "試着リングは寸法確認用で、機体の印刷部品質量には含めません。\n"
            )
            manifest = dict(
                schema_version=1,
                project_id=state["id"],
                version=state["version"],
                missing=missing,
                physical_print_verified=False,
                files=rows,
            )
            with zipfile.ZipFile(output / "design-package.zip", "w", zipfile.ZIP_DEFLATED) as z:
                for row in rows:
                    z.write(self.file(project_id, row["key"]), row["key"])
                z.writestr("README.md", readme)
                z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                z.write(ROOT / "scripts/verify_design_package.py", "scripts/verify_package.py")
            self.register_files(state, output, "package")

        return self._run(project_id, revision, "archive", worker)


def assembly_steps(state):
    spec = DesignSpec.model_validate(state["spec"])
    g = spec.geometry
    steps = [
        dict(
            title="部品と版を照合",
            instruction=f"v{state['version']}の部品表とCADを照合。"
            f"胴径{g.body_diameter_mm:g} mm・"
            f"高さ{g.body_height_mm:g} mmの市販ボトルを無加工で使います。"
            f"実寸未確認なら試着リングから確認してください。",
        ),
        dict(
            title="印刷部品を仕上げる",
            instruction=f"{spec.material}のノーズ1個と"
            f"フィン{g.fin_count if spec.design.has_fins else 0}枚。"
            f"冷却後に除去ブリムを外し、割れ・変形・穴周囲を確認。"
            f"軟質先端キャップと固定材の選定は現物確認が必要です。",
        ),
        dict(
            title="フィンを等間隔に仮固定",
            instruction=f"ノズル側を0 mmとし、フィン後端を{g.fin_tail_inset_mm:g} "
            f"mmの位置へ。"
            f"{g.fin_count}枚を{360 / g.fin_count:g}度等配し、"
            f"翼根{g.fin_root_mm:g}・翼端{g.fin_tip_mm:g}・"
            f"張出し{g.fin_span_mm:g} mmを照合。"
            f"固定用スロットに適合する結束材を選び、"
            f"ボトルを傷付けないことを確認します。"
            if spec.design.has_fins
            else "この版はフィンなし。翼の取付工程はありません。",
        ),
        dict(
            title="ノーズを仮合わせ",
            instruction=f"ノーズ基部は{g.nose_base_mm:g} mm、全長は{g.overall_mm:g} mm。"
            f"差込み・保持と取外し、"
            f"軟質キャップを現物で確認。接着や締結の強さは未評価なので、"
            f"根拠のない設定値で固定しないでください。",
        ),
        dict(
            title="搭載物と回収を確認",
            instruction=f"搭載物{spec.design.payload_mass_kg * 1000:g} g。"
            + (
                "回収傘と搭載物の保持・展開経路は、"
                "この印刷形状では設計していません。別途確定し、"
                "地上試験を記録してください。"
                if spec.design.has_parachute
                else "回収方法と落下時の扱いを確認してください。"
            ),
        ),
        dict(
            title="実測を設計へ戻す",
            instruction="完成部品の質量、嵌合、取付保持、重心を測定・記録します。"
            "印刷部品の実測質量を編集画面に入力し、新しい版で再解析します。"
            "この手順書は加圧・"
            "打上げ許可を示しません。",
        ),
    ]
    for key, step in zip(STEP_IDS, steps, strict=True):
        step.update(
            id=key,
            tools=spec.equipment.tools,
            operator=spec.equipment.operator,
            observation="unconfirmed",
            reverse="仮固定を逆順に外し、傷・亀裂・変形があれば交換して再検討する。",
        )
    return steps


def queue_operation(store, project_id, revision, method):
    if method not in {"analyse", "print_package", "adaptive_step", "adaptive_run"}:
        raise ValueError("Unknown production operation")
    from rocketwright.agent.project_jobs import queue

    return queue(store, project_id, revision, method)


DEFAULT_PROJECTS = DesignProjects()
