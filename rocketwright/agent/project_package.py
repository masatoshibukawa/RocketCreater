"""Portable production source and provenance, excluding credentials and machine paths."""

import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")


def environment(root):
    from rocketwright.manufacturing import tools

    packages = {}
    for name in (
        "numpy",
        "scipy",
        "pydantic",
        "PyYAML",
        "fastapi",
        "uvicorn",
        "anthropic",
        "reportlab",
        "Pillow",
        "imageio-ffmpeg",
    ):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            # The existing media adapter may use isolated, already-installed packages.
            libraries = (
                Path(__import__("os").getenv("ROCKETWRIGHT_MEDIA_ROOT", root / "AIvideo"))
                / "Test project/tools/python"
            )
            distributions = {
                d.metadata["Name"].casefold().replace("_", "-"): d.version
                for d in importlib.metadata.distributions(path=[str(libraries)])
            }
            packages[name] = distributions.get(name.casefold().replace("_", "-"))
    binaries = {}
    for key, path in tools().items():
        binaries[key] = dict(
            name=path.name,
            present=path.is_file(),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        )
    return dict(
        python=platform.python_version(),
        platform=platform.system(),
        architecture=platform.machine(),
        packages=packages,
        tools=binaries,
        external_tools_bundled=False,
    )


def add_reproduction(z, store, state, root):
    """Only fixed project source selectors, never a path supplied by a model or import."""
    source = {}
    for folder in ("rocketwright", "api", "scenarios/cfd"):
        for path in (root / folder).rglob("*"):
            if (
                path.is_file()
                and path.suffix in {".py", ".yaml", ".json", ".eng", ".cu", ".cuh", ".md"}
                and "__pycache__" not in path.parts
            ):
                source[path.relative_to(root).as_posix()] = path
    for name in (
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "scripts/build_print_parts.py",
        "scripts/check_ultimaker_slice.py",
        "scripts/compose_workbench_video.py",
        "scripts/render_workbench_scene.py",
        "scripts/render_checkpoint.py",
        "scripts/video_scene_templates.py",
        "scripts/airframe_visuals.py",
        "scripts/reproduce_design_package.py",
        "scripts/verify_design_package.py",
        "3d model/prototypes/pet-rocket-coke-2l/build.py",
        "3d model/prototypes/pet-rocket-coke-2l/parameters.json",
    ):
        source[name] = root / name
    for path in (root / "AIvideo/pet-rocket/realism").iterdir():
        if path.is_file() and path.suffix in {".py", ".json", ".md"}:
            source[path.relative_to(root).as_posix()] = path
    if state.get("airframe_template"):
        for path in (root / "rocketwright/catalog/airframes/reference").iterdir():
            if path.is_file() and path.suffix in {".stl", ".step", ".scad", ".txt"}:
                source[path.relative_to(root).as_posix()] = path
    if any(r["kind"] in {"photographic_video", "photographic_preview"} for r in state["files"]):
        from rocketwright.agent.video_appearance import asset_files

        _, pairs = asset_files()
        for row, path in pairs:
            source["AIvideo/pet-rocket/realism/" + row["file"]] = path
    rows = []
    for name, path in sorted(source.items()):
        if path.is_symlink() or not path.is_file() or ".." in Path(name).parts:
            raise ValueError("Missing or indirect reproduction source: " + name)
        key = "source/" + name
        z.write(path, key)
        rows.append(
            dict(
                key=key,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                version=state["version"],
            )
        )
    env = environment(root)
    if (
        any(
            r["kind"] in {"video", "photographic_video", "photographic_preview"}
            for r in state["files"]
        )
        and not env["packages"]["imageio-ffmpeg"]
    ):
        raise ValueError(
            "Set ROCKETWRIGHT_MEDIA_ROOT to installed media libraries "
            "before packaging video reproduction"
        )
    directory = store.directory(state["id"])
    geometry = json.loads((directory / "cad/geometry-check.json").read_text(encoding="utf-8"))
    styles = [
        style
        for style, kind in (("engineering", "video"), ("photographic", "photographic_video"))
        if any(r["kind"] == kind for r in state["files"])
    ]
    expectation = dict(
        spec=state["spec"],
        source_project_id=state["id"],
        source_version=state["version"],
        geometry={
            key: {
                k: v
                for k, v in row.items()
                if k in {"volume_mm3", "triangles", "non_manifold_edges", "boundary_edges"}
            }
            for key, row in geometry.items()
        },
        metrics=state["analysis"]["result"]["metrics"],
        input_sha256=state["analysis"]["input_sha256"],
        print_required=any(r["kind"] == "print" for r in state["files"]),
        video_styles=styles,
        video_outputs=[
            dict(style=style, quality=quality)
            for style, quality, kind in (
                ("engineering", "final", "video"),
                ("photographic", "final", "photographic_video"),
                ("photographic", "preview", "photographic_preview"),
            )
            if any(r["kind"] == kind for r in state["files"])
        ],
        airframe_template=state.get("airframe_template"),
        adopted_scope=state.get("adoption_scope", "prototype_screening"),
        adaptive_required=bool(state.get("adaptive")),
    )
    if state.get("adaptive"):
        expectation["adaptive_configuration"] = {
            k: state["adaptive"][k] for k in ("precision", "limits")
        }
        expectation["adaptive_configuration"]["runtime"] = {
            k: v
            for k, v in state["adaptive"]["runtime"].items()
            if k not in {"calculix", "cfd_python"}
        }
    history = dict(
        operations=state["history"],
        intake=state.get("intake", []),
        observations=state.get("observations", []),
        versions=[
            dict(
                version=v["version"],
                spec=v["spec"],
                adopted=v["adopted"],
                metrics=v["analysis"]["result"]["metrics"] if v.get("analysis") else None,
            )
            for v in state["versions"]
        ],
    )
    if state.get("adaptive"):
        history["adaptive"] = {
            k: state["adaptive"].get(k)
            for k in ("precision", "limits", "status", "decisions", "revisions", "quality_pending")
        }
    requirements = (
        "\n".join(f"{name}=={version}" for name, version in env["packages"].items() if version)
        + "\n"
    )
    values = {
        "reproduction/input.json": expectation,
        "reproduction/environment.json": env,
        "reproduction/history.json": history,
        "reproduction/source-manifest.json": list(rows),
    }
    for key, value in values.items():
        blob = encoded(value)
        z.writestr(key, blob)
        rows.append(
            dict(key=key, sha256=hashlib.sha256(blob).hexdigest(), version=state["version"])
        )
    # Source manifest deliberately describes source files only, avoiding self-referential hashes.
    key = "reproduction/requirements.txt"
    blob = requirements.encode()
    z.writestr(key, blob)
    rows.append(dict(key=key, sha256=hashlib.sha256(blob).hexdigest(), version=state["version"]))
    z.write(root / "scripts/reproduce_design_package.py", "scripts/reproduce_package.py")
    rows.append(
        dict(
            key="scripts/reproduce_package.py",
            sha256=hashlib.sha256(
                (root / "scripts/reproduce_design_package.py").read_bytes()
            ).hexdigest(),
            version=state["version"],
        )
    )
    return rows
