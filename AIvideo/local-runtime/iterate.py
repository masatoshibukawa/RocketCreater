"""Run bounded, resumable local generation experiments without overwriting takes."""

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.error

from bootstrap import ROOT, RUNTIME
from generate import api
from quality_workflows import photo_graph, video_graph

RECORDS = ROOT / "experiments"
OUTPUTS = ROOT / "outputs" / "experiments"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def validate(config):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", config["id"]):
        raise ValueError("Experiment id must be a short lowercase slug")
    if config["backend"] not in {"import", "photo", "wan5b", "wan14b"}:
        raise ValueError("Unknown backend")
    if config["backend"] != "import":
        alignment = 16 if config["backend"] == "wan14b" else 32
        if config["width"] % alignment or config["height"] % alignment or min(config["width"], config["height"]) < 64:
            raise ValueError(f"Dimensions must be positive multiples of {alignment}")
        if config["backend"] != "photo" and ((config["frames"] - 1) % 4 or config["frames"] < 5 or config["fps"] <= 0):
            raise ValueError("Video requires 4n+1 frames and positive fps")
        if config["backend"] == "wan14b" and not 0 < config.get("split_step", config["steps"] // 2) < config["steps"]:
            raise ValueError("Invalid high/low noise sampler split")


def action_for(record, fingerprint):
    if not record:
        return "submit"
    if record["fingerprint"] != fingerprint:
        raise ValueError("Configuration or input changed: use a new experiment id")
    if record["status"] == "completed":
        return "skip"
    if record["status"] == "submitted":
        return "resume"
    raise ValueError("Failed or ambiguous take is preserved: inspect it and use a new id")


def source_path(value):
    source = (ROOT / value).resolve()
    if not source.is_relative_to(ROOT.parent.resolve()) or not source.is_file():
        raise ValueError(f"Input must be an existing file within AIvideo: {value}")
    return source


def saved_path(result, node_id):
    item = result["outputs"][node_id]["images"][0]
    path = (ROOT / "outputs" / item["subfolder"] / item["filename"]).resolve()
    if item["type"] != "output" or not path.is_relative_to((ROOT / "outputs").resolve()):
        raise ValueError("Unexpected server output location")
    return path


def measure_video(source, destination, config):
    import av
    import imageio_ffmpeg
    import numpy as np
    from PIL import Image, ImageDraw
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-map", "0:v:0", "-c", "copy", "-map_metadata", "-1", "-metadata", "title=RocketWright Local Video Experiment", "-metadata", "comment=AI-generated concept visualization; no engineering validation", "-movflags", "+faststart", str(destination)], check=True)
    sheet = Image.new("RGB", (1152, 480), "#101820")
    draw = ImageDraw.Draw(sheet)
    with av.open(str(destination)) as container:
        stream = container.streams.video[0]
        fps, width, height = float(stream.average_rate), stream.width, stream.height
        expected = config.get("frames", stream.frames)
        selected = sorted({0, expected // 5, expected * 2 // 5, expected * 3 // 5, expected * 4 // 5, expected - 1})
        means, differences, previous, count = [], [], None, 0
        for index, frame in enumerate(container.decode(stream)):
            image = frame.to_image().convert("RGB")
            small = np.asarray(image.resize((192, 108)), dtype=np.float32)
            means.append(float(small.mean()))
            if previous is not None:
                differences.append(float(np.abs(previous - small).mean()))
            previous = small
            if index in selected:
                slot = selected.index(index)
                x, y = slot % 3 * 384, slot // 3 * 240
                thumb = image.copy()
                thumb.thumbnail((384, 216))
                sheet.paste(thumb, (x + (384 - thumb.width) // 2, y))
                draw.text((x + 8, y + 221), f"{index / fps:.2f}s / frame {index+1}", fill="white")
            if index == 0:
                image.save(destination.parent / "poster.jpg", quality=95)
            count += 1
        metadata = dict(container.metadata)
    if config["backend"] != "import" and (count != config["frames"] or (width, height) != (config["width"], config["height"]) or abs(fps - config["fps"]) > 0.01):
        raise ValueError("Decoded output does not match requested dimensions, fps, or frame count")
    if not count or max(means) < 2:
        raise ValueError("Empty or black output")
    sheet.save(destination.parent / "contact.jpg", quality=94)
    return {"width": width, "height": height, "frames": count, "fps": fps, "seconds": count / fps, "full_decode": True, "mean_frame_change": round(float(np.mean(differences)), 4) if differences else 0, "metadata": metadata, "note": "Frame change is a motion/consistency diagnostic, not a realism score."}


def model_records(graph):
    files = {value for item in graph.values() for key, value in item["inputs"].items() if key in {"unet_name", "clip_name", "vae_name"}}
    records = []
    installation = json.loads((ROOT / "installation.json").read_text())
    for item in installation["models"]:
        if item["file"] in files:
            records.append({"file": item["file"], "sha256": item["sha256"]})
    optional = ROOT / "quality-models.json"
    if optional.exists():
        for item in json.loads(optional.read_text()):
            if Path(item["path"]).name in files:
                records.append({"file": Path(item["path"]).name, "sha256": item["sha256"]})
    return sorted(records, key=lambda item: item["file"])


def run_one(config, address, timeout=1800):
    validate(config)
    identifier = config["id"]
    media = OUTPUTS / identifier
    record_path = RECORDS / identifier / "record.json"
    source = source_path(config["source"]) if config.get("source") else None
    source_hash = digest(source) if source else None
    filename = f"iteration-{identifier}-{source_hash[:12]}{source.suffix.lower()}" if source else None
    prefix = f"experiments/{identifier}/raw"
    graph = photo_graph(config, prefix) if config["backend"] == "photo" else video_graph(config, filename, prefix) if config["backend"] != "import" else {}
    models = model_records(graph) if graph else []
    fingerprint = hashlib.sha256(json.dumps({"config": config, "source_sha256": source_hash, "graph": graph, "models": models}, sort_keys=True).encode()).hexdigest()
    record = json.loads(record_path.read_text(encoding="utf-8")) if record_path.exists() else None
    action = action_for(record, fingerprint)
    if action == "skip":
        output = ROOT / record["output"]
        if not output.exists() or digest(output) != record["output_sha256"]:
            raise ValueError(f"Completed output is missing or modified: {identifier}")
        print(f"SKIP {identifier}: completed output verified", flush=True)
        return False
    media.mkdir(parents=True, exist_ok=True)
    if action == "submit":
        record = {"id": identifier, "fingerprint": fingerprint, "config": config, "input_sha256": source_hash, "models": models, "created_utc": datetime.now(timezone.utc).isoformat(), "status": "prepared"}
        if config["backend"] != "import":
            queue = api(address, "/queue")
            if queue["queue_running"] or queue["queue_pending"]:
                raise RuntimeError("ComfyUI queue is busy; leave other jobs intact and try later")
            info = api(address, "/object_info")
            missing = {item["class_type"] for item in graph.values()} - set(info)
            if missing:
                raise ValueError(f"Missing nodes: {sorted(missing)}")
            if source:
                shutil.copyfile(source, RUNTIME / "inputs" / filename)
            write_json(record_path.parent / "workflow.json", graph)
            write_json(record_path, record)
            try:
                response = api(address, "/prompt", {"prompt": graph, "client_id": "rocketwright-iterations"})
            except urllib.error.HTTPError as error:
                record.update(status="failed", error=error.read().decode("utf-8", errors="replace"))
                write_json(record_path, record)
                raise
            record.update(status="submitted", prompt_id=response["prompt_id"])
            write_json(record_path, record)
            print(f"SUBMIT {identifier}: {record['prompt_id']}", flush=True)
    started, peak, next_report = time.monotonic(), 0, 0
    if config["backend"] != "import":
        while time.monotonic() - started < timeout:
            history = api(address, "/history/" + record["prompt_id"])
            if record["prompt_id"] in history:
                result = history[record["prompt_id"]]
                if result["status"]["status_str"] != "success":
                    record.update(status="failed", error="Server execution failed; raw history preserved under runtime")
                    write_json(RUNTIME / f"history-{identifier}.json", result)
                    write_json(record_path, record)
                    raise RuntimeError(f"Generation failed: {identifier}")
                timestamps = {item[0]: item[1].get("timestamp") for item in result["status"].get("messages", [])}
                begin, end = timestamps.get("execution_start"), timestamps.get("execution_success")
                record["server_seconds"] = (end - begin) / 1000 if begin and end else None
                source = saved_path(result, "13" if config["backend"] == "photo" else "12")
                break
            try:
                usage = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], text=True, timeout=4)
                peak = max(peak, int(usage.splitlines()[0]))
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
            if time.monotonic() >= next_report:
                print(f"WAIT {identifier}: {time.monotonic()-started:.0f}s", flush=True)
                next_report = time.monotonic() + 20
            time.sleep(3)
        else:
            raise TimeoutError("Job remains submitted; rerun this plan to resume polling, without resubmitting")
    if config["backend"] == "photo":
        from PIL import Image
        final = media / "image.png"
        with Image.open(source) as image:
            image.convert("RGB").save(final)
            image.convert("RGB").save(media / "poster.jpg", quality=95)
            metrics = {"width": image.width, "height": image.height}
    else:
        final = media / "video.mp4"
        metrics = measure_video(source, final, config)
    record.update(status="completed", output=final.relative_to(ROOT).as_posix(), output_sha256=digest(final), metrics=metrics, polling_session_seconds=round(time.monotonic()-started, 2), sampled_device_memory_peak_mib=peak or None, memory_note="Whole-device usage sampled every few seconds; includes other applications, may miss peaks.")
    write_json(record_path, record)
    print(f"DONE {identifier}: {record.get('server_seconds')}s", flush=True)
    return True


def gallery():
    cards = []
    for path in sorted(RECORDS.glob("*/record.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["status"] != "completed":
            continue
        identifier = record["id"]
        review_path = path.parent / "review.json"
        review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {"decision": "unreviewed"}
        config = record["config"]
        kind = "image.png" if config["backend"] == "photo" else "video.mp4"
        visual = f'<img src="{identifier}/{kind}" alt="{identifier}">' if config["backend"] == "photo" else f'<video controls loop muted playsinline preload="metadata" poster="{identifier}/poster.jpg" src="{identifier}/{kind}"></video>'
        cards.append(f'<article data-status="{html.escape(review["decision"])}"><h2>{html.escape(identifier)}</h2>{visual}<p>{html.escape(config.get("hypothesis", ""))}</p><p class="details">{html.escape(config["backend"])} · {record["metrics"]["width"]}×{record["metrics"]["height"]} · {record.get("server_seconds", "import")}s</p><strong>{html.escape(review["decision"])}</strong><p>{html.escape(review.get("notes", "Not reviewed yet"))}</p><a href="{identifier}/{kind}">Open media</a> <a href="{identifier}/contact.jpg" {"hidden" if kind == "image.png" else ""}>Contact sheet</a><details><summary>Settings</summary><pre>{html.escape(json.dumps(config,ensure_ascii=False,indent=2))}</pre></details></article>')
    document = '''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RocketWright Video Experiments</title><style>body{margin:0;background:#10151c;color:#e9eef2;font:16px system-ui}header,main{max-width:1440px;margin:auto;padding:24px}h1{font-size:32px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:24px}article{background:#1a2430;padding:20px;border-radius:12px;border:1px solid #34465a}video,img{display:block;width:100%;aspect-ratio:16/9;object-fit:contain;background:#080d12}p{line-height:1.6}.details{color:#aabac8}a{color:#80d5ed;margin-right:16px}pre{white-space:pre-wrap;overflow-wrap:anywhere}button{padding:10px;margin:4px;color:inherit;background:#24384b;border:1px solid #66849b;border-radius:6px}article[data-status="selected"]{border-color:#76e0b8}header p{max-width:900px}</style><header><h1>RocketWright Video Experiments</h1><p>無料のローカル生成を比較する。写真調の新規コンセプトは元CGと形状が異なる。数値は生成速度・デコード確認であり、写実性の自動スコアではない。動画の音声はない。</p><button onclick="filter('all')">All</button><button onclick="filter('selected')">Selected</button><button onclick="document.querySelectorAll('video').forEach(v=>{v.currentTime=0;v.play()})">Play together</button><button onclick="document.querySelectorAll('video').forEach(v=>v.pause())">Pause</button></header><main>'''+"\n".join(cards)+'''</main><script>function filter(s){document.querySelectorAll('article').forEach(a=>a.hidden=s!=='all'&&a.dataset.status!==s)}</script></html>'''
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    (OUTPUTS / "index.html").write_text(document, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=ROOT / "experiments.json")
    parser.add_argument("--only", nargs="+")
    parser.add_argument("--max-runs", type=int, default=3)
    parser.add_argument("--max-minutes", type=float, default=20)
    parser.add_argument("--port", type=int, default=8188)
    parser.add_argument("--gallery", action="store_true")
    options = parser.parse_args()
    if options.gallery:
        gallery()
        return
    plan = json.loads(options.plan.read_text(encoding="utf-8"))
    configurations = [{**plan.get("defaults", {}), **config} for config in plan["runs"]]
    identifiers = [config["id"] for config in configurations]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Duplicate experiment ids")
    if options.only and set(options.only) - set(identifiers):
        raise ValueError("Unknown experiment id")
    if options.max_runs < 1 or options.max_minutes <= 0:
        raise ValueError("Run and time limits must be positive")
    begun, completed = time.monotonic(), 0
    for config in configurations:
        if options.only and config["id"] not in options.only:
            continue
        if completed >= options.max_runs or time.monotonic() - begun > options.max_minutes * 60:
            print("Campaign limit reached; rerun to continue", flush=True)
            break
        completed += run_one(config, f"http://127.0.0.1:{options.port}")
        gallery()


if __name__ == "__main__":
    main()
