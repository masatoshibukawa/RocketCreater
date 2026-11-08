"""Edit the locally supplied hybrid recording with a product-first opening."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

import av
import numpy as np
from PIL import Image, ImageDraw

from render_preview_v1 import FFMPEG, FPS, H, PROJECT, SAMPLE, W, face, ffmpeg, score_bed, write_wav
from replace_preview_narration import TARGET, load_take, loudness


def overlay_image(path, kind, first, second=""):
    if kind == "opening":
        image = Image.new("RGBA", (W, H))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((42, 45, 511, 106), radius=10, fill="#081a26", outline="#70eabb", width=2)
        draw.text((66, 62), "ROCKETWRIGHT  /  実アプリ", font=face(27, True), fill="#d1f9e9")
        draw.rectangle((0, 914, W, H), fill="#07151f")
        draw.rectangle((50, 944, 58, 1041), fill="#70eabb")
        draw.text((82, 930), first, font=face(53, True), fill="#f3fbff")
        draw.text((86, 997), second, font=face(30), fill="#c5dbe4")
    else:
        image = Image.new("RGBA", (474, 62))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((1, 1, 472, 60), radius=9, fill="#081a26", outline="#70eabb", width=2)
        draw.text((20, 16), first, font=face(27, True), fill="#e1fff1")
    image.save(path)


def role_overlay(path):
    roles = (
        ("利用者", "目的・制約を決める"),
        ("ハーネス", "実行と整合を管理"),
        ("学習予測器", "候補の見込みを出す"),
        ("Claude", "次の一手を選ぶ"),
        ("スクリプト", "数値を計算する"),
    )
    image = Image.new("RGBA", (W, H))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((1320, 57, 1881, 112), radius=10, fill="#081a26", outline="#70eabb", width=2)
    draw.text((1342, 69), "仕組みの解説  /  実画面の抜粋", font=face(26, True), fill="#d1f9e9")
    draw.rectangle((0, 838, W, H), fill="#07151f")
    draw.rectangle((42, 858, 50, 900), fill="#70eabb")
    draw.text((68, 854), "5者の分担   判断を計算へ", font=face(35, True), fill="#f3fbff")
    for index, (name, duty) in enumerate(roles):
        x = 42 + index*369
        draw.rounded_rectangle((x, 917, x+353, 1036), radius=10, fill="#0d2331", outline="#317461", width=2)
        draw.text((x+18, 930), name, font=face(30, True), fill="#82efc6")
        draw.text((x+18, 980), duty, font=face(25), fill="#f3fbff")
    image.save(path)


def edit_video(source, start, seconds, overlays, output):
    inputs = [option for path, _, _ in overlays for option in ("-i", path)]
    chain = ["[0:v]fps=30,setsar=1[base]"]
    previous = "base"
    for i, (_, position, interval) in enumerate(overlays, 1):
        condition = f":enable='gte(t,{interval[0]})*lt(t,{interval[1]})'" if interval else ""
        label = f"layer{i}"
        chain.append(f"[{previous}][{i}:v]overlay={position}:eof_action=repeat{condition}[{label}]")
        previous = label
    filters = ["-filter_complex_threads", 3, "-filter_complex", ";".join(chain),
               "-map", f"[{previous}]"] if overlays else ["-map", "0:v:0", "-vf", "fps=30,setsar=1"]
    ffmpeg("-ss", start, "-i", source, *inputs, *filters, "-t", seconds, "-an",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", 17, "-pix_fmt", "yuv420p",
           "-threads", 5, output)


def excerpt_audio(source, start, stop):
    data = ffmpeg("-ss", start, "-i", source, "-t", stop-start, "-map", "0:a:0",
                  "-ac", 1, "-ar", SAMPLE, "-f", "f32le", "-", capture=True)
    signal = np.frombuffer(data, dtype="<f4").copy()
    expected = round((stop-start)*SAMPLE)
    if abs(len(signal)-expected) > SAMPLE//20:
        raise ValueError(f"Unexpected audio length for {source.name}")
    if len(signal) < expected:
        signal = np.pad(signal, (0, expected-len(signal)))
    return signal[:expected]


def soften_edges(signal):
    n = round(.035*SAMPLE)
    ramp = np.linspace(0, 1, n, dtype=np.float32)
    signal[:n] *= ramp
    signal[-n:] *= ramp[::-1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hybrid", required=True, type=Path)
    parser.add_argument("--preview", required=True, type=Path)
    parser.add_argument("--take", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--plan", type=Path, default=PROJECT/"hybrid-v2.json")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    opening_s = plan["opening_seconds"]
    trade_start, trade_end = plan["tradeoff_source_s"]
    main_start, main_end = plan["hybrid_source_s"]
    role_start, role_end = plan["role_diagram_source_s"]
    duration = opening_s + (trade_end-trade_start) + (main_end-main_start)
    out = args.out.resolve()
    work = out/"edit"
    work.mkdir(parents=True, exist_ok=True)

    opening = work/"opening.png"
    overlay_image(opening, "opening", plan["opening_title"], plan["opening_caption"])
    trial = work/"tradeoff.png"
    overlay_image(trial, "label", "別条件の試算  /  概算高度")
    roles = work/"roles.png"
    role_overlay(roles)
    cues = []
    for index, step in enumerate(plan["app_steps"], 1):
        path = work/f"step-{index}.png"
        overlay_image(path, "label", f"{index:02d}  {step['title']}")
        cues.append((path, "1424:62", (step["start_s"]-role_end, step["end_s"]-role_end)))

    edit_video(args.hybrid, plan["opening_start_s"], opening_s, [(opening, "0:0", None)], work/"opening.mp4")
    edit_video(args.preview, trade_start, trade_end-trade_start, [(trial, "1416:100", None)], work/"tradeoff.mp4")
    edit_video(args.hybrid, main_start, role_start-main_start, [], work/"context.mp4")
    edit_video(args.hybrid, plan["role_demo_excerpt_start_s"], role_end-role_start, [(roles, "0:0", None)], work/"roles.mp4")
    edit_video(args.hybrid, role_end, main_end-role_end, cues, work/"main.mp4")
    concat = work/"shots.ffconcat"
    parts = ("opening", "tradeoff", "context", "roles", "main")
    concat.write_text("ffconcat version 1.0\n"+"".join(f"file {part}.mp4\n" for part in parts), encoding="utf-8")

    speech, raw_s, speed, _, last = load_take(args.take, opening_s-.40)
    intro = score_bed(175)[:opening_s*SAMPLE]*.33
    start = round(.20*SAMPLE)
    intro[start:start+len(speech)] += speech
    if start+last >= round((opening_s-.15)*SAMPLE):
        raise ValueError("The opening voice needs more space")
    tradeoff = excerpt_audio(args.preview, trade_start, trade_end)
    hybrid = excerpt_audio(args.hybrid, main_start, main_end)
    for audio in (intro, tradeoff, hybrid):
        soften_edges(audio)
    premix = work/"premix.wav"
    write_wav(premix, np.concatenate((intro, tradeoff, hybrid)))
    metrics = loudness(premix)
    measured = {
        "measured_I": metrics["input_i"], "measured_TP": metrics["input_tp"],
        "measured_LRA": metrics["input_lra"], "measured_thresh": metrics["input_thresh"],
        "offset": metrics["target_offset"],
    }
    norm = f"loudnorm={TARGET}:linear=true:" + ":".join(f"{key}={value}" for key, value in measured.items())
    result = out/"rocketwright-demo-hybrid-v2.mp4"
    ffmpeg("-f", "concat", "-safe", 1, "-i", concat, "-i", premix, "-map", "0:v:0", "-map", "1:a:0",
           "-c:v", "copy", "-af", norm, "-ar", SAMPLE, "-c:a", "aac", "-b:a", "160k",
           "-metadata", "title=RocketWright — Product Demo", "-metadata:s:a:0", "language=jpn",
           "-movflags", "+faststart", result)
    subprocess.run([FFMPEG, "-v", "error", "-xerror", "-i", str(result), "-f", "null", "-"], check=True)
    with av.open(str(result)) as container:
        video, audio = container.streams.video[0], container.streams.audio[0]
        if (container.duration != duration*av.time_base or video.frames != duration*FPS
                or (video.width, video.height) != (W, H) or audio.rate != SAMPLE):
            raise ValueError("Unexpected output duration or stream format")
    actual = loudness(result)
    if float(actual["input_tp"]) >= -.8:
        raise ValueError("Output peak is too high")
    report = {
        "duration_s": duration, "video_frames": duration*FPS, "resolution": [W, H], "fps": FPS,
        "audio_sample_rate_hz": SAMPLE, "integrated_lufs": float(actual["input_i"]),
        "true_peak_dbtp": float(actual["input_tp"]), "full_decode": "passed",
        "opening_source_take_s": raw_s, "opening_speed": round(speed, 4),
        "hybrid_sha256": sha256(args.hybrid.read_bytes()).hexdigest(),
        "preview_sha256": sha256(args.preview.read_bytes()).hexdigest(),
        "sha256": sha256(result.read_bytes()).hexdigest(),
    }
    (out/"verification.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
