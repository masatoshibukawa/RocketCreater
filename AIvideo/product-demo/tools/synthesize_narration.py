"""Generate local narration trials; keep raw takes and measured generation records."""
from __future__ import annotations

import argparse
from hashlib import sha256
import io
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request
import wave

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def request(base, path, query=None, body=None, method="GET"):
    url = base.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=240) as res:
        return res.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=["qwen-design", "aivis"], required=True)
    parser.add_argument("--config", type=Path, default=PROJECT / "narration-candidates.json")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:10139")
    parser.add_argument("--candidate")
    parser.add_argument("--full-plan", type=Path)
    args = parser.parse_args()
    args.out = args.out.resolve()
    config = read(args.config)
    candidates = [c for c in config["candidates"] if c["engine"] == args.engine
                  and (not args.candidate or c["id"] == args.candidate)]
    if not candidates:
        raise ValueError("No matching candidate")
    if args.full_plan and (len(candidates) != 1 or args.engine == "qwen-design"):
        raise ValueError("Full narration requires one stable Aivis voice; design trials are not a fixed speaker")
    args.out.mkdir(parents=True, exist_ok=True)
    load_start = time.perf_counter()
    if args.engine == "qwen-design":
        import numpy as np
        import soundfile as sf
        import torch
        from qwen_tts import Qwen3TTSModel
        if not args.model:
            raise ValueError("--model must point to the downloaded official VoiceDesign snapshot")
        torch.set_num_threads(8)
        model = Qwen3TTSModel.from_pretrained(str(args.model.resolve()), device_map="cuda:0",
                    dtype=torch.bfloat16, attn_implementation="sdpa", local_files_only=True)
        engine_version = __import__("importlib.metadata", fromlist=["version"]).version("qwen-tts")
        speakers = []
    else:
        engine_version = json.loads(request(args.base_url, "/version"))
        speakers = json.loads(request(args.base_url, "/speakers"))
    load_s = time.perf_counter() - load_start
    jobs = ([dict(id=f"{i:02d}", text=s.get("speech", s["caption"]), available_s=s["end_s"]-s["start_s"]-.55)
             for i, s in enumerate(read(args.full_plan)["shots"]) if s["caption"]]
            if args.full_plan else [dict(id="comparison", text=config["sample_text"])])
    records = []
    for candidate in candidates:
        if args.engine == "aivis":
            speaker = next(s for s in speakers if s["name"] == candidate["speaker_name"])
            style = next(s for s in speaker["styles"] if s["name"] == candidate["style_name"])
        for job in jobs:
            dest = args.out / candidate["id"] / f"{job['id']}.wav"
            dest.parent.mkdir(parents=True, exist_ok=True)
            start = time.perf_counter()
            params = dict(candidate.get("parameters", {}))
            if args.engine == "qwen-design":
                torch.manual_seed(candidate["seed"])
                wavs, sr = model.generate_voice_design(text=job["text"], language="Japanese",
                    instruct=candidate["instruct"], **config["qwen_generation"])
                signal = np.asarray(wavs[0])
                if not np.isfinite(signal).all() or np.max(np.abs(signal)) < .01:
                    raise ValueError("Invalid generated waveform")
                sf.write(dest, signal, sr, subtype="PCM_16")
                duration = len(signal)/sr
            else:
                query = json.loads(request(args.base_url, "/audio_query",
                    {"speaker":style["id"], "text":job["text"]}, method="POST"))
                query.update(params)
                blob = request(args.base_url, "/synthesis", {"speaker":style["id"]}, query, "POST")
                with wave.open(io.BytesIO(blob)) as take:
                    duration = take.getnframes()/take.getframerate()
                if args.full_plan and duration > job["available_s"]:
                    # Preserve content and re-synthesize with a modest native speech-rate correction.
                    correction = min(1.28, duration/job["available_s"])
                    query["speedScale"] *= correction
                    blob = request(args.base_url, "/synthesis", {"speaker":style["id"]}, query, "POST")
                    params["speedScale"] = query["speedScale"]
                    with wave.open(io.BytesIO(blob)) as take:
                        duration = take.getnframes()/take.getframerate()
                dest.write_bytes(blob)
                params["speaker_id"] = style["id"]
            elapsed = time.perf_counter() - start
            record = dict(candidate=candidate["id"], case=job["id"], text=job["text"],
                          engine=args.engine, engine_version=engine_version, parameters=params,
                          load_s=round(load_s, 3), synthesis_s=round(elapsed, 3),
                          duration_s=round(duration, 3), rtf=round(elapsed/duration, 3),
                          sha256=sha256(dest.read_bytes()).hexdigest(), path=dest.relative_to(ROOT).as_posix())
            if args.engine == "qwen-design":
                record.update(instruct=candidate["instruct"], seed=candidate["seed"],
                              generation=config["qwen_generation"])
            records.append(record)
            (args.out / "generation.json").write_text(json.dumps(records, ensure_ascii=False, indent=2)+"\n",
                                                      encoding="utf-8")
            print(f"{candidate['id']} {job['id']}: {duration:.2f}s, generation {elapsed:.2f}s", flush=True)


if __name__ == "__main__":
    main()
