"""Persistent, revision-checked human checkpoints around the existing bottle harness.

Run in one API process. Atomic snapshots remain readable while a worker runs a tool.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from rocketwright import aero
from rocketwright.agent.local_runtime import LocalDirector
from rocketwright.bottle_assembly import Workshop
from rocketwright.bottle_candidates import PRESSURE_KPA, REQUIREMENT, flight_tool
from rocketwright.bottle_packet import write_packet
from rocketwright.bottle_search import PASS_RATE, TARGET, Action, Search, baseline_choice
from rocketwright.geometry import assembled_shape
from rocketwright.report import export_bom_csv, export_report_json, export_report_markdown
from rocketwright.schema import SimResult

ROOT = Path(__file__).resolve().parents[2]
AERO_BACKEND_ENV = "ROCKETWRIGHT_AERO_BACKEND"
STEPS = {
    "component": "構成・重心・振動",
    "flight": "飛行・抗力の範囲",
    "screen": "条件を変えた試行",
    "confirm": "採用案の独立確認",
}
SKILLS = {
    "analysis": ["UI/bottle-pool/selection.html"],
    "print": [
        "3d model/3d-model-skills/categories/3d-model-preparation/SKILL.md",
        "3d model/3d-model-skills/categories/3d-model-records/SKILL.md",
    ],
    "video": [
        "AIvideo/skills/video-production/video-llm-direction/SKILL.md",
        "AIvideo/skills/video-production/video-sf-vfx/SKILL.md",
    ],
}


class Conflict(ValueError):
    pass


class StepChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=2000)


def engine_version() -> str:
    """Invalidate saved numerical evidence if its implementation or inputs change."""
    digest = hashlib.sha256()
    package = ROOT / "rocketwright"
    files = sorted((package / "physics").glob("*.py"))
    files += [
        package / name
        for name in (
            "schema.py",
            "cost.py",
            "dispersion.py",
            "bottle_assembly.py",
            "bottle_candidates.py",
            "bottle_search.py",
            "bottle_print.py",
            "bottle_packet.py",
            "drawing.py",
            "report.py",
            "agent/tools.py",
        )
    ]
    files += sorted((ROOT / "rocketwright/catalog").rglob("*.yaml"))
    files += sorted((ROOT / "rocketwright/catalog").rglob("*.eng"))
    for file in files:
        digest.update(file.relative_to(ROOT).as_posix().encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()


class Workbench:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(os.getenv("ROCKETWRIGHT_WORKSPACE", ROOT / "output/workbench"))
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def directory(self, project_id: str) -> Path:
        if len(project_id) != 32 or any(c not in "0123456789abcdef" for c in project_id):
            raise KeyError("Unknown project")
        return self.root / project_id

    def _write(self, state: dict):
        path = self.directory(state["id"]) / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
        temp.replace(path)

    def load(self, project_id: str) -> dict:
        try:
            return json.loads(
                (self.directory(project_id) / "state.json").read_text(encoding="utf-8")
            )
        except FileNotFoundError as exc:
            raise KeyError("Unknown project") from exc

    def create(self, workshop: Workshop | None = None) -> dict:
        if workshop is None:
            workshop = Workshop.model_validate_json(
                (ROOT / "scenarios/bottle_empty_workshop.json").read_text(encoding="utf-8")
            )
        Search("references", workshop)  # Validate registered resource/construction ids.
        state = {
            "id": uuid.uuid4().hex,
            "revision": 0,
            "engine_version": engine_version(),
            "created_at": time.time(),
            "workshop": workshop.model_dump(mode="json"),
            "history": [],
            "active": None,
            "error": None,
            "files": [],
            "proposal": None,
            "aero_loop": None,
        }
        self._write(state)
        return self.view(state)

    def search(self, state: dict) -> Search:
        if state["engine_version"] != engine_version():
            raise Conflict("Analysis code or catalog changed. Create a new project to recalculate.")
        search = Search("references", Workshop.model_validate(state["workshop"]))
        for row in state["history"]:
            action = Action(**row["action"])
            search.results[action] = row["result"]
            search.history.append({k: v for k, v in row.items() if k != "action"})
        return search

    def view(self, state: dict) -> dict:
        search = self.search(state)
        options = search.options()
        recommendation = baseline_choice(search, options)[0] if options else None
        recipe = json.loads((ROOT / "scenarios/bottle_prototype_choices.json").read_text())
        history_ids = [row["chosen"] for row in state["history"]]
        if history_ids == [row["id"] for row in recipe[: len(history_ids)]] and len(
            history_ids
        ) < len(recipe):
            next_id = recipe[len(history_ids)]["id"]
            if next_id in options:
                recommendation = next_id
        last = next(reversed(search.results), None) if search.results else None
        plan = search.plan(last, search.design(last)) if last else None
        confirmed = any(
            a.method == "confirm" and r["success_rate"] >= PASS_RATE
            for a, r in search.results.items()
        )
        return state | {
            "requirement": REQUIREMENT.model_dump(mode="json"),
            "options": [
                {
                    "id": a.id,
                    "method": a.method,
                    "label": STEPS[a.method],
                    "architecture": a.start,
                    "variant": a.variant,
                    "pressure_kpa": a.pressure_kpa,
                    "fill_pct": a.fill_pct,
                }
                for a in options.values()
            ],
            "recommendation": recommendation,
            "confirmed": confirmed,
            "design": search.design(last).model_dump(mode="json") if last else None,
            "plan": plan,
            "aero_loop": state.get("aero_loop"),  # absent from projects saved before it existed
            "aero_images": self.aero_images(state),
            "skills": SKILLS,
            "eta_seconds": None,
        }

    def get(self, project_id: str) -> dict:
        state = self.load(project_id)
        if state["active"] and project_id not in self._locks:
            # A prior process stopped after saving its running checkpoint.
            state["active"] = None
            state["error"] = "Previous operation was interrupted. Review before retrying."
            state["revision"] += 1
            self._write(state)
        return self.view(state)

    def _run(self, project_id: str, revision: int, operation: str, worker, *, started_event=None):
        with self._guard:
            lock = self._locks.setdefault(project_id, threading.Lock())
        if not lock.acquire(blocking=False):
            raise Conflict("Another operation is running for this project")
        try:
            state = self.load(project_id)
            self.search(state)
            if revision != state["revision"]:
                raise Conflict("Project revision changed. Reload before continuing.")
            state["active"] = {"name": operation, "started_at": time.time()}
            state["error"] = None
            self._write(state)
            if started_event is not None:
                started_event.set()
            started = time.monotonic()
            try:
                worker(state)
            except Exception as exc:
                state["error"] = str(exc)
                raise
            finally:
                state["active"] = None
                state["last_elapsed_seconds"] = round(time.monotonic() - started, 3)
                state["revision"] += 1
                self._write(state)
            return self.view(state)
        finally:
            lock.release()

    def step(self, project_id: str, revision: int, choice: StepChoice) -> dict:
        def worker(state):
            search = self.search(state)
            action, _ = search.step(choice.id, choice.reason)
            from dataclasses import asdict

            state["history"].append(search.history[-1] | {"action": asdict(action)})
            state["proposal"] = None

        return self._run(project_id, revision, choice.id, worker)

    def propose(self, project_id: str, revision: int, director: LocalDirector | None = None):
        def worker(state):
            search = self.search(state)
            options = search.options()
            if not options:
                raise Conflict("No further eligible analysis")
            schema = StepChoice.model_json_schema()
            schema["properties"]["id"]["enum"] = list(options)
            context = {
                "requirement": REQUIREMENT.model_dump(mode="json"),
                "eligible": list(options),
                "history": search.history,
                "workshop": state["workshop"],
            }
            data, model = (director or LocalDirector()).generate(
                context,
                schema,
                "Choose one eligible analysis ID and explain in Japanese why its evidence is "
                "needed. Do not invent results. Return JSON only. A human executes the choice.",
            )
            choice = StepChoice.model_validate(data)
            if choice.id not in options:
                raise Conflict("Model chose an ineligible analysis")
            state["proposal"] = choice.model_dump() | {"model": model}

        return self._run(project_id, revision, "local_llm_proposal", worker)

    def register_files(self, state: dict, directory: Path, kind: str):
        base = self.directory(state["id"])
        for path in sorted(directory.iterdir()):
            if not path.is_file():
                continue
            key = path.relative_to(base).as_posix()
            state["files"].append(
                {
                    "name": path.name,
                    "key": key,
                    "kind": kind,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "url": f"/workbench/projects/{state['id']}/files/{key}",
                }
            )

    def _confirmed(self, search: Search) -> list[Action]:
        return [
            a
            for a, r in search.results.items()
            if a.method == "confirm" and r["success_rate"] >= PASS_RATE
        ]

    def export(self, project_id: str, revision: int):
        def worker(state):
            search = self.search(state)
            confirmed = self._confirmed(search)
            if not confirmed:
                raise Conflict("Confirm an eligible design before exporting production files")
            if state["files"]:
                raise Conflict("Outputs already exist for this frozen design")
            action = confirmed[-1]
            design = search.design(action)
            plan = search.plan(action, design)
            directory = self.directory(project_id) / "production"
            directory.mkdir(parents=True, exist_ok=True)
            write_packet(directory, design, plan, search.history, search.workshop)
            result = SimResult.model_validate(
                flight_tool("simulate_design", design, action.id, env=search.env)
            )
            source = {"simulation": action.id, "confirmation": search.history[-1]["chosen"]}
            report = export_report_json(design, result, requirement=REQUIREMENT, sources=source)
            (directory / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (directory / "report.md").write_text(
                export_report_markdown(design, result, requirement=REQUIREMENT, sources=source),
                encoding="utf-8",
            )
            (directory / "bom.csv").write_text(export_bom_csv(design), encoding="utf-8")
            (directory / "trace.json").write_text(
                json.dumps([p.model_dump(mode="json") for p in result.trace]), encoding="utf-8"
            )
            self.register_files(state, directory, "production")

        return self._run(project_id, revision, "export_production", worker)

    def print_package(self, project_id: str, revision: int):
        def worker(state):
            from rocketwright.manufacturing import PrintGeometry, PrintRequest, prepare
            from rocketwright.schema import BottleDesign

            if any(f["kind"] == "manufacturing" for f in state["files"]):
                raise Conflict("A print package already exists for this frozen design")
            try:
                report = json.loads(
                    self.file(project_id, "production/report.json").read_text(encoding="utf-8")
                )
                assembly = json.loads(
                    self.file(project_id, "production/assembly.json").read_text(encoding="utf-8")
                )
            except KeyError as exc:
                raise Conflict("Export the confirmed production design before slicing") from exc
            request = PrintRequest(
                design=BottleDesign.model_validate(report["design"]),
                geometry=PrintGeometry.from_plan(assembly["dimensions_mm"]),
            )
            directory = self.directory(project_id) / f"manufacturing-r{revision}"
            manifest = prepare(request, directory)
            self.register_files(state, directory, "manufacturing")
            state["files"] = [
                f
                for f in state["files"]
                if not (f["kind"] == "manufacturing" and f["name"].endswith(".log"))
            ]
            state["print_package"] = manifest

        return self._run(project_id, revision, "prepare_print_package", worker)

    def aero_loop(self, project_id: str, revision: int):
        """Flight/CFD loop on the confirmed design, stored beside it in `aero_loop`: a CFD-based
        alternative to read. History, the frozen design and production files stay as they are."""

        backend = os.getenv(AERO_BACKEND_ENV, "auto")
        if backend not in aero.BACKEND_NAMES:
            raise ValueError(f"{AERO_BACKEND_ENV} must be one of {aero.BACKEND_NAMES}")

        def worker(state):
            search = self.search(state)
            confirmed = self._confirmed(search)
            if not confirmed:
                raise Conflict("Confirm an eligible design before running the aero loop")
            action = confirmed[-1]
            design = search.design(action)
            plan = search.plan(action, design)
            ceiling = search.workshop.pressure_ceiling_kpa
            result = aero.run_aero_loop(
                design,
                search.env,
                target_apogee_m=TARGET,
                pressures_kpa=[p for p in PRESSURE_KPA if p <= ceiling],
                backend=backend,
                shape=assembled_shape(plan["dimensions_mm"]),
                cg_from_nose_m=plan["wet_cg_mm"] / 1000,  # least stable: water loaded
            )
            confirmation = search.results[action]
            n, seed = confirmation["n"], confirmation["seed"]
            spread = flight_tool(
                "run_dispersion",
                result.final_design,
                f"{action.id}/aero-loop",
                n=n,
                seed=seed,
                env=search.env,
            )
            state["aero_loop"] = result.model_dump(mode="json") | {
                "source_action": action.id,
                "backend_requested": backend,
                "target_apogee_m": TARGET,
                "cg_from_nose_m": plan["wet_cg_mm"] / 1000,
                "baseline": {
                    "pressure_kpa": design.initial_gauge_pressure_pa / 1000,
                    "cd": design.axial_drag_coefficient,
                    "success_rate": confirmation["success_rate"],
                },
                "dispersion": {
                    "n": n,
                    "seed": seed,
                    "success_rate": spread["success_rate"],
                    "passes": round(n * spread["success_rate"]),
                    "failure_counts": spread["failure_counts"],
                    "apogee_m": spread["quantiles"]["apogee_m"],
                    "descent_speed_mps": spread["quantiles"]["descent_speed_mps"],
                },
            }

        return self._run(project_id, revision, "aero_loop", worker)

    def trajectory(self, project_id: str) -> dict:
        """Time series of the current design, recomputed by the same simulation tool. Read-only:
        nothing is added to the history, so it needs no revision."""
        state = self.load(project_id)
        search = self.search(state)
        last = next(reversed(search.results), None)
        if last is None:
            raise Conflict("Run an analysis step before requesting the trajectory")
        design = search.design(last)
        result = flight_tool("simulate_design", design, last.id, env=search.env)
        return {
            "source_action": last.id,
            "design": design.model_dump(mode="json"),
            "trace": result["trace"],
            "metrics": result["metrics"],
            "warnings": result["warnings"],
        }

    def aero_images(self, state: dict) -> list[dict]:
        """Flow pictures of the last aero loop; the analytic backends leave none."""
        artifacts = (state.get("aero_loop") or {}).get("artifacts_dir")
        return [
            image | {"url": f"/workbench/projects/{state['id']}/aero-images/{image['name']}"}
            for image in aero.flow_images(artifacts)
        ]

    def aero_image(self, project_id: str, name: str) -> Path:
        """One `flow/*.png` of the project's aero loop, and nothing else in that directory."""
        artifacts = (self.load(project_id).get("aero_loop") or {}).get("artifacts_dir")
        return aero.flow_image_path(artifacts, name)

    def manual(self, project_id: str, revision: int):
        def worker(state):
            from rocketwright.agent.manual import write_manual

            if any(f["kind"] == "manual" for f in state["files"]):
                raise Conflict("The frozen assembly PDF already exists")
            keys = {f["key"] for f in state["files"] if f["kind"] == "production"}
            required = {"production/assembly.json", "production/build.md", "production/report.json"}
            if not required <= keys:
                raise Conflict("Export the confirmed production packet before generating its PDF")
            for key in required:
                self.file(project_id, key)  # Validate the frozen sources before rendering.
            directory = self.directory(project_id)
            report = json.loads((directory / "production/report.json").read_text(encoding="utf-8"))
            write_manual(
                directory / "production",
                state | {"design_snapshot": report["design"]},
                directory / "manual",
            )
            self.register_files(state, directory / "manual", "manual")

        return self._run(project_id, revision, "assembly_pdf", worker)

    def file(self, project_id: str, key: str) -> Path:
        state = self.load(project_id)
        record = next((f for f in state["files"] if f["key"] == key), None)
        if record is None:
            raise KeyError("Unknown artifact")
        base = self.directory(project_id).resolve()
        path = (base / key).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            raise KeyError("Unknown artifact")
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise Conflict("Artifact changed since verification")
        return path


DEFAULT_WORKBENCH = Workbench()
