"""Generate v1 speech with one fixed, original synthesized voice reference."""
from __future__ import annotations

import argparse
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import time

import numpy as np
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

from synthesize_narration import PROJECT, ROOT, read


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--settings", type=Path, default=PROJECT/"narration-v1-voice.json")
    p.add_argument("--plan", type=Path, default=PROJECT/"preview-v1.json")
    p.add_argument("--shot", type=int, action="append", help="Zero-based shot index; repeat to regenerate a subset")
    args = p.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    settings = read(args.settings)
    ref = settings["reference"]
    source = ROOT/ref["source"]
    if sha256(source.read_bytes()).hexdigest() != ref["sha256"]:
        raise ValueError("The selected comparison reference has changed")
    ref_samples, ref_rate = sf.read(source, dtype="float32")
    ref_samples = ref_samples[:round(ref["stop_s"]*ref_rate)]
    if not len(ref_samples) or not np.isfinite(ref_samples).all():
        raise ValueError("Invalid reference audio")
    sf.write(out/"voice-reference.wav", ref_samples, ref_rate, subtype="PCM_16")
    load_begin = time.perf_counter()
    torch.set_num_threads(8)
    model = Qwen3TTSModel.from_pretrained(str(args.model.resolve()), device_map="cuda:0",
                dtype=torch.bfloat16, attn_implementation="sdpa", local_files_only=True)
    voice_prompt = model.create_voice_clone_prompt(ref_audio=(ref_samples, ref_rate), ref_text=ref["text"],
                                                  x_vector_only_mode=False)
    load_s = time.perf_counter()-load_begin
    jobs = [(i, settings["speech_overrides"].get(str(i), s.get("speech",s["caption"])))
            for i, s in enumerate(read(args.plan)["shots"])
            if s["caption"] and (not args.shot or i in args.shot)]
    if not jobs:
        raise ValueError("No matching voiced shots")
    record_path = out/"generation.json"
    records = {r["case"]:r for r in read(record_path)} if args.shot and record_path.exists() else {}
    step = settings["batch_size"]
    for j in range(0,len(jobs),step):
        batch = jobs[j:j+step]
        seed = settings["seed"] + batch[0][0]
        torch.manual_seed(seed)
        began = time.perf_counter()
        wavs, sr = model.generate_voice_clone(text=[t for _,t in batch], language="Japanese",
                    voice_clone_prompt=voice_prompt*len(batch), **settings["generation"])
        elapsed = time.perf_counter()-began
        if len(wavs) != len(batch):
            raise ValueError("The returned voice batch does not match the input")
        seconds = sum(len(y) for y in wavs)/sr
        for (i,text), signal in zip(batch, wavs):
            if not np.isfinite(signal).all() or np.max(np.abs(signal))<.01:
                raise ValueError(f"Invalid audio at shot {i}")
            case = f"{i:02d}"
            dest = out/f"{case}.wav"
            sf.write(dest,signal,sr,subtype="PCM_16")
            records[case] = dict(candidate=settings["voice_id"],case=case,text=text,
                engine="qwen-base",engine_version=version("qwen-tts"),load_s=round(load_s,3),
                duration_s=round(len(signal)/sr,3),synthesis_s=None,rtf=None,batch_size=len(batch),
                batch_elapsed_s=round(elapsed,3),batch_rtf=round(elapsed/seconds,3),seed=seed,
                generation=settings["generation"],sha256=sha256(dest.read_bytes()).hexdigest(),
                path=dest.relative_to(ROOT).as_posix())
            print(f"Shot {i+1:02d}: {len(signal)/sr:.2f}s, batch {elapsed:.2f}s",flush=True)
        record_path.write_text(json.dumps([records[k] for k in sorted(records)],ensure_ascii=False,indent=2)+"\n",
                               encoding="utf-8")


if __name__ == "__main__":
    main()
