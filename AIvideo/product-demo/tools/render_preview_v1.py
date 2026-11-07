"""Build the 175-second product-demo preview from the local storyboard and evidence."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import wave

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]
MEDIA = ROOT / "output/media/product-demo"
EDIT = MEDIA / "edit/preview-v1"
AUDIO = MEDIA / "audio/preview-v1"
OUT = MEDIA / "generated/preview-v1"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
PLAN = PROJECT / "preview-v1.json"
FONT_DIR = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
W, H = 1920, 1080
FPS, SAMPLE = 30, 48_000
INK, MUTED, GREEN = "#f3fbff", "#bfd3df", "#79f7c0"
DARK = (7, 15, 25)
PRINTER_RECT = (460, 125, 1000, 750)


def config(path):
    return json.loads(path.read_text(encoding="utf-8"))


def ffmpeg(*args, capture=False):
    return subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *map(str, args)],
        check=True, stdout=subprocess.PIPE if capture else None,
    ).stdout


def wrap(draw, text, face, width):
    # Keep Latin words intact when possible; Japanese can wrap between characters.
    import re
    tokens = re.findall(r"[A-Za-z0-9.+%/−-]+|.", text)
    lines, line = [], ""
    for token in tokens:
        if line and draw.textlength(line + token, font=face) > width:
            lines.append(line.rstrip())
            line = ""
        line += token.lstrip() if not line else token
    return lines + [line.rstrip()] if line else lines


def face(size, bold=False):
    return ImageFont.truetype(str(FONT_DIR / ("YuGothB.ttc" if bold else "meiryo.ttc")), size)


def multiline(draw, xy, content, size, width, color=INK, bold=False, max_lines=2):
    font = face(size, bold)
    lines = wrap(draw, content, font, width)
    if len(lines) > max_lines:
        raise ValueError(f"Text exceeds {max_lines} lines at size {size}: {content}")
    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=font, fill=color, anchor="lt")
        y += int(size * 1.26)


def label(draw, xy, content, size=25, color=MUTED, bold=False):
    draw.text(xy, content, font=face(size, bold), fill=color, anchor="lt")


def card(draw, box, title, detail, heading=30, body=34):
    x, y, w, h = box
    draw.rounded_rectangle((x, y, x+w, y+h), 14, fill=(6, 17, 27, 226), outline=(68, 126, 126, 235), width=2)
    draw.line((x+2, y+21, x+2, y+h-21), fill=GREEN, width=4)
    multiline(draw, (x+24, y+17), title, heading, w-48, GREEN, True, 1)
    multiline(draw, (x+24, y+59), detail, body, w-48, INK, False, 2)


def load_art(path):
    with Image.open(path) as art:
        return ImageOps.exif_transpose(art).convert("RGB")


def plates(shot, artwork, index, duration):
    layout = shot["layout"]
    canvas = Image.new("RGB", (W, H), DARK)
    overlay = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(overlay)

    if layout in {"hero", "crew", "grid"}:
        canvas = ImageOps.fit(load_art(artwork), (W, H), Image.Resampling.LANCZOS)
        xs = np.linspace(0, 1, W)[None, :]
        ys = np.linspace(0, 1, H)[:, None]
        if layout == "grid":
            alpha = 150 + 58 * np.maximum(0, (ys - .55) / .45) + np.zeros_like(xs)
        elif layout == "crew":
            alpha = 88 * np.maximum(0, 1 - ys * 5) + 170 * np.maximum(0, (ys - .60) / .4) + np.zeros_like(xs)
        else:
            alpha = np.maximum(157 * (1-xs)**1.7, 152 * ys**4)
        tint = Image.new("RGB", (W, H), DARK)
        canvas = Image.composite(tint, canvas, Image.fromarray(alpha.astype(np.uint8)))
    elif layout == "side":
        x, y, w, h = 746, 166, 1088, 697
        border = ImageDraw.Draw(canvas)
        border.rounded_rectangle((x, y, x+w, y+h), 16, fill=(10, 22, 36), outline=(43, 80, 97), width=2)
        still = ImageOps.contain(load_art(artwork), (w-24, h-24), Image.Resampling.LANCZOS)
        canvas.paste(still, (x+(w-still.width)//2, y+(h-still.height)//2))
    elif layout == "print":
        x, y, w, h = PRINTER_RECT
        d.rectangle((x-2, y-2, x+w+1, y+h+1), outline=GREEN, width=2)
    else:
        raise ValueError(layout)

    d.rounded_rectangle((75, 48, 474, 96), 9, fill=(5, 14, 23, 218))
    label(d, (91, 61), "ROCKETWRIGHT   /   構成プレビュー", 21, INK, True)
    phase = ("背景と意義" if index < 5 else "チーム" if index < 7 else
             "解析の仕組み" if index < 11 else "解析記録" if index < 19 else
             "実写と試作" if index < 22 else "開発と展望")
    d.rounded_rectangle((1510, 48, 1844, 96), 9, fill=(5, 14, 23, 218))
    label(d, (1532, 60), f"{index+1:02d}   /   {phase}", 22, GREEN, True)

    if layout == "print":
        multiline(d, (84, 222), shot["title"], 43, 335, max_lines=3, bold=True)
        label(d, (88, 170), "LIVE FOOTAGE", 23, GREEN, True)
        multiline(d, (1492, 755), shot["badge"], 23, 340, GREEN)
    elif layout == "crew":
        multiline(d, (86, 137), shot["title"], 57, 1720, bold=True)
        for i, (title, detail) in enumerate(shot["cards"]):
            card(d, (170 + 875*i, 713, 705, 126), title, detail, 38, 28)
    elif layout == "hero":
        y = 420 if index != 7 else 640
        label(d, (88, y-61), "MISSION CONTROL   /   DESIGN SYSTEM", 25, GREEN, True)
        multiline(d, (84, y), shot["title"], 85, 1650, bold=True)
        if shot["cards"]:
            title, detail = shot["cards"][0]
            label(d, (90, y+125), title, 37, GREEN, True)
            label(d, (90, y+184), detail, 31)
    elif layout == "side":
        multiline(d, (84, 182), shot["title"], 54, 635, bold=True)
        for i, (title, detail) in enumerate(shot["cards"]):
            card(d, (85, 349+165*i, 615, 144), title, detail, 31, 32)
    else:
        multiline(d, (84, 184), shot["title"], 66, 1730, bold=True)
        cards = shot["cards"]
        n = len(cards)
        w = 540 if n == 3 else 330
        gap = 27
        x = (W-n*w-(n-1)*gap)//2
        for i, (title, detail) in enumerate(cards):
            card(d, (x+(w+gap)*i, 482, w, 180), title, detail, 31, 33 if n == 3 else 31)
            if n == 3 and i < 2:
                label(d, (x+(w+gap)*i+w+2, 551), "›", 27, GREEN, True)
    badge = shot.get("badge") or ("構成イメージ" if isinstance(shot["asset"], int) else "")
    if badge and layout != "print":
        badge_w = int(d.textlength(badge, font=face(23))) + 33
        d.rounded_rectangle((84, 867, 84+badge_w, 907), 7, fill=(5, 16, 27, 228))
        label(d, (100, 876), badge, 23, GREEN)
    if shot["caption"]:
        d.rounded_rectangle((84, 917, 1836, 1023), 13, fill=(3, 11, 19, 242))
        font = face(32)
        lines = wrap(d, shot["caption"], font, 1670)
        if len(lines) > 2:
            raise ValueError(f"Too many subtitle lines: {shot['caption']}")
        for i, line in enumerate(lines):
            d.text((W//2, 951 - 19*(len(lines)-1) + i*41), line, font=font, fill=INK, anchor="mt")
    d.line((84, 1048, 1836, 1048), fill="#26434e", width=3)
    d.line((84, 1048, 84 + int(1752 * shot["end_s"] / duration), 1048), fill=GREEN, width=3)
    return canvas, overlay


def render_shot(index, shot, path, duration):
    n = (shot["end_s"] - shot["start_s"]) * FPS
    canvas, overlay = plates(shot, path, index, duration)
    overlay_path = EDIT / f"{index:02d}-overlay.png"
    overlay.save(overlay_path)
    out = EDIT / f"{index:02d}.mp4"
    if shot["layout"] == "print":
        x, y, w, h = PRINTER_RECT
        inputs = ["-i", path]
        chain = f"scale={w}:{h}:flags=lanczos,setsar=1,pad={W}:{H}:{x}:{y}:color=0x070f19,fps={FPS}"
    else:
        canvas_path = EDIT / f"{index:02d}-base.png"
        canvas.save(canvas_path)
        inputs = ["-i", canvas_path]
        motion = (shot["layout"] in {"hero", "grid"} and shot["asset"] != 6)
        if motion:
            chain = (f"scale=3840:2160,zoompan=z='1+0.045*on/{n-1}':x='iw/2-iw/zoom/2':"
                     f"y='ih/2-ih/zoom/2':d={n}:s={W}x{H}:fps={FPS}")
        else:
            chain = f"loop=loop=-1:size=1:start=0,setpts=N/({FPS}*TB),fps={FPS}"
    filters = f"[0:v]{chain}[base];[base][1:v]overlay,format=yuv420p[v]"
    if index == 0:
        filters += f";[v]fade=in:0:9[f]"
    elif shot["end_s"] == duration:
        filters += f";[v]fade=out:{n-18}:18[f]"
    ffmpeg(*inputs, "-i", overlay_path, "-filter_complex_threads", 2, "-filter_complex", filters,
           "-map", "[f]" if filters.endswith("[f]") else "[v]", "-frames:v", n, "-an",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", 18, "-threads", 3,
           "-pix_fmt", "yuv420p", "-r", FPS, out)
    print(f"Rendered {index+1:02d}: {shot['start_s']}–{shot['end_s']} s", flush=True)
    return out


def write_wav(path, signal):
    with wave.open(str(path), "wb") as handle:
        handle.setparams((1, 2, SAMPLE, 0, "NONE", "not compressed"))
        handle.writeframes((np.clip(signal, -1, 1) * 32767).astype("<i2").tobytes())


def srt_stamp(seconds):
    return f"{seconds//3600:02d}:{(seconds//60)%60:02d}:{seconds%60:02d},000"


def score_bed(duration):
    """Original chord bed shared by the preview and audio-only revisions."""
    bed = np.zeros(duration*SAMPLE, dtype=np.float32)
    chords = [(0, 50, (55, 82.41, 110)), (50, 66, (65.41, 98, 130.81)),
              (66, 100, (55, 82.41, 130.81)), (100, 150, (49, 73.42, 110)),
              (150, 162, (65.41, 98, 130.81)), (162, duration, (55, 82.41, 164.81))]
    for start, end, notes in chords:
        t = np.arange((end-start)*SAMPLE)/SAMPLE
        fade = np.minimum(np.clip(t/1.6, 0, 1), np.clip((end-start-t)/1.5, 0, 1))
        section = np.zeros_like(t)
        for j, hz in enumerate(notes):
            section += np.sin(2*np.pi*hz*t + .28*np.sin(2*np.pi*.16*t + j)) * (0.012 - j*.002)
            section += .003 * np.sin(2*np.pi*(hz*2.005)*t + j)
        bed[start*SAMPLE:end*SAMPLE] = section * fade * (0.86 + 0.14*np.cos(2*np.pi*.21*t))
    return bed


def mix_audio(shots, duration):
    takes = AUDIO / "takes"
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(PROJECT / "tools/preview_voice.ps1"), "-Plan", str(PLAN),
                    "-OutputDirectory", str(takes)], check=True)
    speech = np.zeros(duration*SAMPLE, dtype=np.float32)
    subtitle_entries = []
    activity = np.zeros(duration*SAMPLE, dtype=np.float32)
    for i, shot in enumerate(shots):
        if not shot["caption"]:
            continue
        path = takes / f"{i:02d}.wav"
        with wave.open(str(path), "rb") as voice:
            length = voice.getnframes() / voice.getframerate()
        available = shot["end_s"] - shot["start_s"] - .55
        speed = max(1, length/available)
        if speed > 1.25:
            raise ValueError(f"Shorten narration for shot {i+1}: {length:.2f}s into {available:.2f}s")
        raw = ffmpeg("-i", path, "-af", f"highpass=f=85,atempo={speed:.4f}", "-ar", SAMPLE,
                     "-ac", 1, "-f", "s16le", "-", capture=True)
        sample = np.frombuffer(raw, dtype="<i2").astype(np.float32)[:round(available*SAMPLE)]
        peak = float(np.max(np.abs(sample)))
        if peak == 0:
            raise ValueError(f"Silent narration for shot {i+1}")
        sample *= .73 / peak
        fade = min(720, len(sample)//2)
        sample[:fade] *= np.linspace(0, 1, fade)
        sample[-fade:] *= np.linspace(1, 0, fade)
        start = round((shot["start_s"]+.30)*SAMPLE)
        end = start+len(sample)
        speech[start:end] = sample
        activity[max(0, start-SAMPLE//8):min(len(activity), end+SAMPLE//6)] = 1
        subtitle_entries.append(
            f"{len(subtitle_entries)+1}\n{srt_stamp(shot['start_s'])} --> {srt_stamp(shot['end_s'])}\n{shot['caption']}")
    bed = score_bed(duration)
    write_wav(AUDIO / "narration.wav", speech)
    write_wav(AUDIO / "mix.wav", speech + bed*(1-.58*activity))
    (OUT / "rocketwright-preview-v1.ja.srt").write_text("\n\n".join(subtitle_entries)+"\n", encoding="utf-8")


def main():
    plan = config(PLAN)
    duration, shots = plan["duration_s"], plan["shots"]
    assert (plan["width"], plan["height"], plan["fps"]) == (W, H, FPS)
    assert shots[0]["start_s"] == 0 and shots[-1]["end_s"] == duration
    assert all(a["end_s"] == b["start_s"] for a, b in zip(shots, shots[1:]))
    for directory in (EDIT, AUDIO, OUT):
        directory.mkdir(parents=True, exist_ok=True)
    sources = {i: ROOT / scene["image"] for i, scene in enumerate(config(PROJECT / "nine-frame-plan.json")["scenes"], 1)}
    trim = config(PROJECT / "print-insert-5s-verification.json")
    sources["printer"] = ROOT / trim["output"]
    if sha256(sources["printer"].read_bytes()).hexdigest() != trim["sha256"]:
        raise ValueError("Printer excerpt differs from the verified source")
    sources["stage6"] = EDIT / "stage6.png"
    sources["stage6"].write_bytes(subprocess.check_output(
        ["git", "show", f"{plan['source_commit']}:scenarios/adaptive_design/local-learned-stage6.png"], cwd=ROOT))
    mix_audio(shots, duration)
    with ThreadPoolExecutor(max_workers=2) as pool:
        segments = list(pool.map(lambda pair: render_shot(pair[0], pair[1], sources[pair[1]["asset"]], duration),
                                 enumerate(shots)))
    concat = EDIT / "shots.ffconcat"
    concat.write_text("ffconcat version 1.0\n" + "".join(f"file {path.name}\n" for path in segments), encoding="utf-8")
    result = OUT / "rocketwright-preview-v1.mp4"
    ffmpeg("-f", "concat", "-safe", 1, "-i", concat, "-i", AUDIO / "mix.wav",
           "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
           "-metadata", "title=RocketWright — Preview v1", "-metadata:s:a:0", "language=jpn",
           "-movflags", "+faststart", result)
    print(result, flush=True)


if __name__ == "__main__":
    main()
