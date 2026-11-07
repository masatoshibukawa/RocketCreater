"""Replace only the v1 audio, fitting each take without cutting off speech."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import wave

import av
import numpy as np

from render_preview_v1 import FFMPEG, OUT, PLAN, SAMPLE, config, ffmpeg, score_bed, write_wav

TARGET = "I=-16:TP=-1.5:LRA=11"


def loudness(path):
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path), "-map", "0:a:0",
                        "-af", f"loudnorm={TARGET}:print_format=json", "-f", "null", "-"],
                       check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return json.loads(re.findall(r"\{[^{}]*\}", r.stderr)[-1])


def stamp(sample):
    ms = round(sample * 1000 / SAMPLE)
    return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}"


def active_region(signal):
    frame = SAMPLE//100
    n = len(signal)//frame
    rms = np.sqrt(np.mean(signal[:n*frame].reshape(-1, frame)**2, axis=1))
    good = np.flatnonzero(rms > max(.0015, np.max(rms)*.035))
    if not len(good):
        raise ValueError("No active speech detected")
    return good[0]*frame, (good[-1]+1)*frame


def load_take(path, available):
    with wave.open(str(path), "rb") as wf:
        original = wf.getnframes()/wf.getframerate()
    speed = max(1, (original+.016)/available)
    if speed > 1.16:
        raise ValueError(f"{path.name}: {original:.2f}s exceeds {available:.2f}s. Re-synthesize at a suitable pace.")
    af = "highpass=f=68"
    if speed > 1.0:
        af += f",atempo={speed:.6f}"
    data = ffmpeg("-i", path, "-af", af, "-ac", 1, "-ar", SAMPLE, "-f", "f32le", "-", capture=True)
    signal = np.frombuffer(data, dtype="<f4").copy()
    if len(signal) > round(available*SAMPLE):
        raise ValueError(f"{path.name}: fitted audio still exceeds the slot; no samples were cut")
    a, b = active_region(signal)
    rms = float(np.sqrt(np.mean(signal[a:b]**2)))
    peak = float(np.max(np.abs(signal)))
    signal *= min(.105 / rms, .73 / peak, 3)
    edge = min(480, len(signal)//2)
    signal[:edge] *= np.linspace(0, 1, edge)
    signal[-edge:] *= np.linspace(1, 0, edge)
    return signal, original, speed, a, b


def video_hash(path):
    return ffmpeg("-i", path, "-map", "0:v:0", "-c:v", "copy",
                  "-f", "hash", "-hash", "sha256", "-", capture=True).decode("ascii").strip()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--takes", type=Path, required=True)
    p.add_argument("--source", type=Path, default=OUT/"rocketwright-preview-v1.mp4")
    p.add_argument("--output", type=Path, default=OUT/"rocketwright-preview-v1-narrated.mp4")
    p.add_argument("--plan", type=Path, default=PLAN)
    args = p.parse_args()
    if args.source.resolve() == args.output.resolve():
        raise ValueError("Choose a separate path for the narration revision")
    duration = config(args.plan)["duration_s"]
    shots = config(args.plan)["shots"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    base = args.output.with_suffix("")
    dry = np.zeros(duration*SAMPLE, dtype=np.float32)
    duck = np.ones_like(dry)
    cues, report = [], []
    for i, shot in enumerate(shots):
        if not shot["caption"]:
            continue
        start = round((shot["start_s"] + .30)*SAMPLE)
        limit = shot["end_s"] - .25
        path = args.takes / f"{i:02d}.wav"
        sample, raw_s, speed, first, last = load_take(path, limit-start/SAMPLE)
        end = start+len(sample)
        dry[start:end] = sample
        d1 = max(0, start+first-round(.10*SAMPLE))
        d2 = min(len(dry), start+last+round(.22*SAMPLE))
        duck[d1:start+first] = np.linspace(1,.38,start+first-d1)
        duck[start+first:start+last] = .38
        duck[start+last:d2] = np.linspace(.38,1,d2-(start+last))
        cue_start, cue_end = start+first, min(round(limit*SAMPLE),start+last+round(.14*SAMPLE))
        cues.append(f"{len(cues)+1}\n{stamp(cue_start)} --> {stamp(cue_end)}\n{shot['caption']}")
        report.append(dict(shot=i+1, input_seconds=round(raw_s,3), speed=round(speed,4),
                           start_s=round(start/SAMPLE,3), end_s=round(end/SAMPLE,3),
                           speech_start_s=round(cue_start/SAMPLE,3), subtitle_end_s=round(cue_end/SAMPLE,3),
                           sha256=sha256(path.read_bytes()).hexdigest()))
    voice = base.with_suffix(".narration.wav")
    premix = base.with_suffix(".premix.wav")
    mix = base.with_suffix(".mix.wav")
    write_wav(voice, dry)
    write_wav(premix, dry + score_bed(duration)*duck*1.20)
    m = loudness(premix)
    fields = dict(measured_I=m["input_i"], measured_TP=m["input_tp"], measured_LRA=m["input_lra"],
                  measured_thresh=m["input_thresh"], offset=m["target_offset"])
    norm = f"loudnorm={TARGET}:linear=true:" + ":".join(f"{k}={v}" for k,v in fields.items())
    ffmpeg("-i",premix,"-af",norm,"-ar",SAMPLE,"-ac",1,"-c:a","pcm_s16le",mix)
    ffmpeg("-i",args.source,"-i",mix,"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac","-b:a","160k",
           "-map_metadata","-1","-metadata","title=RocketWright — Preview v1 Narrated",
           "-metadata:s:a:0","language=jpn","-movflags","+faststart",args.output)
    original_hash, revised_hash = video_hash(args.source), video_hash(args.output)
    if original_hash != revised_hash:
        raise ValueError("Video stream changed during audio replacement")
    with av.open(str(args.output)) as c:
        v, a = c.streams.video[0], c.streams.audio[0]
        if c.duration != duration*av.time_base or v.frames != duration*30 or a.rate != SAMPLE:
            raise ValueError("Unexpected output duration, frame count, or sample rate")
        dimensions = [v.width, v.height]
    actual = loudness(args.output)
    if float(actual["input_tp"]) > -1.0:
        raise ValueError("Final audio true peak exceeds -1 dBTP")
    base.with_suffix(".ja.srt").write_text("\n\n".join(cues)+"\n",encoding="utf-8")
    verification = dict(duration_s=duration, video_frames=duration*30, dimensions=dimensions,
                        audio_sample_rate=SAMPLE, video_stream_sha256=original_hash.split("=")[-1],
                        same_video_stream=True, output_sha256=sha256(args.output.read_bytes()).hexdigest(),
                        integrated_lufs=float(actual["input_i"]), true_peak_dbtp=float(actual["input_tp"]),
                        speech_take_count=len(report), manual_listening="not_performed", shots=report)
    base.with_suffix(".verification.json").write_text(json.dumps(verification,indent=2)+"\n",encoding="utf-8")
    print(f"{args.output}: {duration}s, {len(report)} takes, {actual['input_i']} LUFS, {actual['input_tp']} dBTP")


if __name__ == "__main__":
    main()
