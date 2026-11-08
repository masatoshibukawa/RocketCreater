"""Apply narration-timed red callouts to the hybrid preview."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import av
import numpy as np

from render_preview_v1 import FFMPEG, PROJECT, SAMPLE, ffmpeg, write_wav
from replace_preview_narration import loudness


def drawboxes(plan):
    last_end = 0
    filters = []
    for cue in plan["cues"]:
        start, end = cue["from_s"], cue["to_s"]
        x, y, width, height = cue["rect"]
        if not last_end <= start < end <= plan["duration_s"]:
            raise ValueError(f"Invalid or overlapping cue: {cue['label']}")
        if not (0 <= x < x+width <= plan["width"] and 0 <= y < y+height <= plan["height"]):
            raise ValueError(f"Callout exceeds the picture: {cue['label']}")
        filters.append(f"drawbox=x={x}:y={y}:w={width}:h={height}:"
                       f"color={plan['color']}:t={plan['thickness_px']}:enable='gte(t,{start})*lt(t,{end})'")
        last_end = end
    return ",".join(filters)


def retime_audio(source, plan, path):
    raw = ffmpeg("-i", source, "-map", "0:a:0", "-t", plan["duration_s"], "-ac", 1,
                 "-ar", SAMPLE, "-f", "f32le", "-", capture=True)
    original = np.frombuffer(raw, dtype="<f4")
    samples = plan["duration_s"]*SAMPLE
    if len(original) != samples or not np.isfinite(original).all():
        raise ValueError("Source audio does not cover the full edit")
    revised = original.copy()
    parts = []
    source_end = 0
    target_end = 0
    for move in plan["audio_moves"]:
        a, b = (round(second*SAMPLE) for second in move["source_s"])
        dst = round(move["target_s"]*SAMPLE)
        if not (source_end <= a < b <= samples and target_end <= dst < dst+b-a <= samples):
            raise ValueError(f"Invalid or overlapping audio move: {move['label']}")
        parts.append((dst, original[a:b].copy(), move["label"]))
        revised[a:b] = 0
        source_end, target_end = b, dst+b-a
    for dst, clip, label in parts:
        region = revised[dst:dst+len(clip)]
        if float(np.max(np.abs(region))) > .025:
            raise ValueError(f"Audio move would overwrite an audible section: {label}")
        fade = min(round(.015*SAMPLE), len(clip)//2)
        ramp = np.linspace(0, 1, fade, dtype=np.float32)
        clip[:fade] *= ramp
        clip[-fade:] *= ramp[::-1]
        region[:] = clip
    write_wav(path, revised)


def validate(path, plan):
    with av.open(str(path)) as container:
        video, audio = container.streams.video[0], container.streams.audio[0]
        if (container.duration != plan["duration_s"]*av.time_base
                or video.frames != plan["duration_s"]*plan["fps"]
                or (video.width, video.height) != (plan["width"], plan["height"])
                or video.average_rate != plan["fps"] or audio.rate != SAMPLE):
            raise ValueError("Unexpected preview duration or format")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--plan", type=Path, default=PROJECT/"hybrid-v2-focus.json")
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        raise ValueError("Use a separate path for the revised preview")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    validate(args.source, plan)
    filters = drawboxes(plan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="focus-", dir=args.output.parent) as directory:
        wav = Path(directory)/"retimed.wav"
        result = Path(directory)/"focus.mp4"
        retime_audio(args.source, plan, wav)
        ffmpeg("-i", args.source, "-i", wav, "-map", "0:v:0", "-map", "1:a:0", "-vf", filters,
               "-c:v", "libx264", "-preset", "veryfast", "-crf", 16, "-pix_fmt", "yuv420p", "-threads", 5,
               "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
               "-metadata", "title=RocketWright — Product Demo", "-metadata:s:a:0", "language=jpn", result)
        subprocess.run([FFMPEG, "-v", "error", "-xerror", "-i", str(result), "-f", "null", "-"], check=True)
        validate(result, plan)
        metrics = loudness(result)
        peak = float(metrics["input_tp"])
        if peak >= -.8:
            raise ValueError("Output true peak is too high")
        result.replace(args.output)
    report = dict(duration_s=plan["duration_s"], frame_count=plan["duration_s"]*plan["fps"],
                  cue_count=len(plan["cues"]), audio_move_count=len(plan["audio_moves"]),
                  integrated_lufs=float(metrics["input_i"]), true_peak_dbtp=peak, full_decode="passed",
                  source_sha256=sha256(args.source.read_bytes()).hexdigest(),
                  sha256=sha256(args.output.read_bytes()).hexdigest())
    args.output.with_suffix(".verification.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
