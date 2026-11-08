"""Replace the final two shots and narration in the local focus cut."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import av
import numpy as np

import render_preview_v1 as preview
from replace_preview_narration import load_take, loudness


def assemble_audio(source, shots, duration, takes, output):
    sample_rate = preview.SAMPLE
    start = shots[0]["start_s"]
    data = preview.ffmpeg("-i", source, "-map", "0:a:0", "-t", start, "-ac", 1,
                          "-ar", sample_rate, "-f", "f32le", "-", capture=True)
    prefix = np.frombuffer(data, dtype="<f4")
    if len(prefix) != start*sample_rate:
        raise ValueError("The source audio does not reach the closing")
    mix = np.zeros(duration*sample_rate, dtype=np.float32)
    mix[:len(prefix)] = prefix
    fade = round(.06*sample_rate)
    mix[len(prefix)-fade:len(prefix)] *= np.linspace(1, 0, fade, dtype=np.float32)
    mix[len(prefix):] = preview.score_bed(duration)[len(prefix):]*.62
    end_fade = round(.40*sample_rate)
    mix[-end_fade:] *= np.linspace(1, 0, end_fade, dtype=np.float32)
    for index, shot in enumerate(shots):
        slot = shot["end_s"]-shot["start_s"]
        voice, _, _, _, _ = load_take(takes/f"{index:02d}.wav", slot-.65)
        begin = round((shot["start_s"]+.27)*sample_rate)
        mix[begin:begin+len(voice)] += voice*1.30
    tail = mix[len(prefix):]
    tail *= .69 / max(.69, float(np.max(np.abs(tail))))
    preview.write_wav(output, mix)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--artwork", type=Path, required=True)
    parser.add_argument("--takes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan", type=Path, default=preview.PROJECT/"hybrid-v2-closing.json")
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        raise ValueError("Use a separate path for the revised closing")
    plan = preview.config(args.plan)
    start, duration, shots = plan["replace_from_s"], plan["duration_s"], plan["shots"]
    if not (shots[0]["start_s"] == start and shots[-1]["end_s"] == duration <= 180
            and all(a["end_s"] == b["start_s"] for a, b in zip(shots, shots[1:]))):
        raise ValueError("Closing shots must cover the end of the video within three minutes")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="closing-", dir=args.output.parent) as directory:
        work = Path(directory)
        audio = work/"mix.wav"
        assemble_audio(args.source, shots, duration, args.takes, audio)
        preview.EDIT = work
        prefix = work/"prefix.mp4"
        preview.ffmpeg("-i", args.source, "-map", "0:v:0", "-frames:v", start*preview.FPS, "-an",
                       "-c:v", "libx264", "-preset", "veryfast", "-crf", 16, "-threads", 5,
                       "-pix_fmt", "yuv420p", "-r", preview.FPS, prefix)
        segments = [preview.render_shot(23+i, shot, args.artwork, duration) for i, shot in enumerate(shots)]
        concat = work/"shots.ffconcat"
        concat.write_text("ffconcat version 1.0\n"+"".join(f"file {p.name}\n" for p in [prefix,*segments]),
                          encoding="utf-8")
        result = work/"closing.mp4"
        preview.ffmpeg("-f", "concat", "-safe", 1, "-i", concat, "-i", audio,
                       "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                       "-metadata", "title=RocketWright — Product Demo", "-metadata:s:a:0", "language=jpn",
                       "-movflags", "+faststart", result)
        subprocess.run([preview.FFMPEG, "-v", "error", "-xerror", "-i", str(result), "-f", "null", "-"], check=True)
        with av.open(str(result)) as container:
            video, audio_stream = container.streams.video[0], container.streams.audio[0]
            if (container.duration != duration*av.time_base or video.frames != duration*preview.FPS
                    or (video.width, video.height) != (preview.W, preview.H) or audio_stream.rate != preview.SAMPLE):
                raise ValueError("Unexpected rendered duration or stream format")
        sound = loudness(result)
        if float(sound["input_tp"]) >= -.8:
            raise ValueError("The closing mix exceeds the peak limit")
        result.replace(args.output)
    report = {
        "duration_s": duration, "video_frames": duration*preview.FPS, "closing_from_s": start,
        "integrated_lufs": float(sound["input_i"]), "true_peak_dbtp": float(sound["input_tp"]),
        "full_decode": "passed", "sha256": sha256(args.output.read_bytes()).hexdigest(),
    }
    args.output.with_suffix(".verification.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
