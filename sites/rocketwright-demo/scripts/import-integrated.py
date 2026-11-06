"""Import the existing integrated UI and verified saved demo; never run a tool or write its state."""
import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--project", required=True)
parser.add_argument("--media", type=Path, required=True)
args = parser.parse_args()
site = Path(__file__).resolve().parents[1]
source = args.source.resolve()
revision = "3b236f19078c31dc30e5f614296558c2d0fabf6c"
app = site / "integrated-src"
paths = ["app/components/WorkbenchPanel.tsx", "app/components/RocketViewport.tsx", "app/components/AnalysisEvidence.tsx", "app/components/ReferenceLibrary.tsx", "app/lib/types.ts", "app/globals.css", "app/workbench.css", "package.json", "tsconfig.json"]
for relative in paths:
    destination = app / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_bytes(subprocess.check_output(["git", "-C", str(source), "show", f"{revision}:web/{relative}"]))
types = subprocess.check_output(["git", "-C", str(source), "show", f"{revision}:web/app/lib/workbench.ts"]).decode("utf-8")
(app / "app/lib/workbench-types.ts").write_text('import type { BottleDesign } from "./types";\n' + types[types.index("export interface WorkbenchFile"):types.index("const STORAGE_KEY")], encoding="utf-8")
sys.path.insert(0, str(source))
from rocketwright.agent.workbench import DEFAULT_WORKBENCH
from rocketwright.agent.library import ReferenceLibrary
from rocketwright.agent.manual import write_manual

directory = source / "output/workbench" / args.project
state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
assert state["active"] is None, "Choose a completed saved project."
assert len(state["history"]) == 8
public = app / "public"
assets = public / "assets"
manifest = []
files = []
for row in state["files"]:
    if row["name"].endswith(".blend"):
        continue
    origin = (directory / row["key"]).resolve()
    assert origin.is_relative_to(directory.resolve())
    digest = hashlib.sha256(origin.read_bytes()).hexdigest()
    assert digest == row["sha256"], f"Changed artifact: {row['key']}"
    destination = assets / row["key"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origin, destination)
    files.append(row | {"url": "/functional/assets/" + row["key"]})
    manifest.append({"path": "assets/" + row["key"], "sha256": digest, "bytes": origin.stat().st_size})

snapshots = []
for count in range(len(state["history"]) + 1):
    prefix = copy.deepcopy(state)
    prefix["history"] = prefix["history"][:count]
    prefix.update(active=None, error=None, files=[], proposal=None)
    prefix.pop("video_plan", None)
    prefix.pop("print_package", None)
    view = DEFAULT_WORKBENCH.view(prefix)
    if count < len(state["history"]):
        next_id = state["history"][count]["chosen"]
        view["options"] = [row for row in view["options"] if row["id"] == next_id]
        assert len(view["options"]) == 1
        view["recommendation"] = next_id
    keys = ["id", "revision", "confirmed", "recommendation", "workshop", "active", "error", "options", "files", "proposal", "design", "plan", "history"]
    snapshots.append({key: view.get(key) for key in keys})

# Reuse the integrated product's existing PDF function on the same frozen packet.
# The output goes only into this demo; the source project and its state stay untouched.
report = json.loads((directory / "production/report.json").read_text(encoding="utf-8"))
manual = write_manual(directory / "production", state | {"design_snapshot": report["design"]}, assets / "manual")
manual_hash = hashlib.sha256(manual.read_bytes()).hexdigest()
files.append({"name": manual.name, "key": "manual/" + manual.name, "kind": "manual", "sha256": manual_hash, "url": "/functional/assets/manual/" + manual.name})
manifest.append({"path": "assets/manual/" + manual.name, "sha256": manual_hash, "bytes": manual.stat().st_size, "derived_from": "production/report.json + assembly.json + build.md"})

library = ReferenceLibrary(root=source, media_root=args.media.resolve())
catalog = library.view()
for asset in catalog["assets"]:
    if not asset["url"]:
        continue
    origin = library.file(asset["id"])
    destination = assets / "library" / origin.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origin, destination)
    asset["url"] = "/functional/assets/library/" + origin.name
    manifest.append({"path": "assets/library/" + origin.name, "sha256": hashlib.sha256(origin.read_bytes()).hexdigest(), "bytes": origin.stat().st_size})

plan = copy.deepcopy(state["video_plan"])
# The existing saved LLM captions contain replacement characters. Restore readable
# display captions from the verified focus fields; retain the model/camera/settings.
plan.update(design_caption="フィンの配置と機体の構成を確認する", launch_caption="計算した飛行軌跡を再生する")
plan.pop("reason", None)
payload = dict(source_commit=revision, source_project=args.project, replay=True, snapshots=snapshots,
               files=files, print_package=state["print_package"], video_plan=plan,
               library=catalog, references=library.references(limit=200), assets=manifest)
(public / "demo-data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"snapshots": len(snapshots), "artifacts": len(files), "library_available": sum(bool(a["url"]) for a in catalog["assets"]), "total_asset_bytes": sum(a["bytes"] for a in manifest)}))
