"""Composite a timed HUD and original audio over the rendered concept scene."""

import argparse
import array
import json
import math
import random
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "python"))

import imageio_ffmpeg
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFont

WIDTH, HEIGHT, FPS, FRAMES = 1280, 720, 30, 310
CYAN = (157, 231, 249)
GREEN = (58, 238, 196)
VIGNETTE = None


def font(size, bold=False):
    path = Path("C:/Windows/Fonts") / ("arialbd.ttf" if bold else "arial.ttf")
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default(size=size)


def smooth(value):
    value = max(0, min(1, value))
    return value * value * (3 - 2 * value)


def grade(image):
    global VIGNETTE
    if VIGNETTE is None:
        pixels = bytearray()
        for y in range(HEIGHT):
            for x in range(WIDTH):
                radius = ((x - WIDTH / 2) / (WIDTH * 0.7)) ** 2 + ((y - HEIGHT / 2) / (HEIGHT * 0.8)) ** 2
                pixels.append(round(255 * max(0.72, 1 - 0.23 * radius)))
        VIGNETTE = Image.frombytes("L", (WIDTH, HEIGHT), bytes(pixels)).convert("RGB")
    image = ImageEnhance.Color(image).enhance(0.68)
    image = ImageEnhance.Contrast(image).enhance(1.08)
    image = ImageEnhance.Brightness(image).enhance(0.88)
    return ImageChops.multiply(image, VIGNETTE)


def panel(draw, rect, title=None):
    x, y, w, h = rect
    draw.rounded_rectangle((x, y, x + w, y + h), radius=4, fill=(12, 39, 52, 103), outline=(*CYAN, 165), width=1)
    if title:
        draw.text((x + 14, y + 12), title, font=font(24), fill=(226, 248, 255, 240))


def wire_fairing(draw, rect, alpha=220):
    x, y, w, h = rect
    center_x = x + w / 2
    base = y + h * 0.93
    for side in [-1, 1]:
        for strand in range(5):
            points = []
            theta = math.pi * strand / 4
            for i in range(45):
                z = i / 44
                r = (1 - max(0, (z - 0.33) / 0.67) ** 2) * w * 0.16
                px = center_x + side * w * (0.22 - 0.06 * z) + r * math.cos(theta)
                py = base - z * h * 0.88 - math.sin(theta) * r * 0.16
                points.append((px, py))
            draw.line(points, fill=(84, 210, 252, alpha), width=1)
        for level in [0, 0.25, 0.5, 0.75]:
            r = (1 - max(0, (level - 0.33) / 0.67) ** 2) * w * 0.16
            cx = center_x + side * w * (0.22 - 0.06 * level)
            py = base - level * h * 0.88
            draw.arc((cx - r, py - r * 0.16, cx + r, py + r * 0.16), 180, 360, fill=(84, 210, 252, alpha), width=1)
    stage_y = base - h * 0.40
    draw.ellipse((center_x - w * 0.10, stage_y, center_x + w * 0.10, stage_y + h * 0.055), outline=(*CYAN, alpha))
    for side in [-1, 1]:
        draw.line((center_x + side * w * 0.10, stage_y + 3, center_x - side * w * 0.14, base - h * 0.12), fill=(*CYAN, alpha))
        draw.line((center_x + side * w * 0.06, base - h * 0.23, center_x + side * w * 0.10, base), fill=(*CYAN, alpha))


def vehicle(draw, x, y, w, h):
    mid = x + w / 2
    outline = [(mid, y), (mid - 9, y + 32), (mid - 11, y + h - 25), (mid - 17, y + h - 6), (mid - 8, y + h - 6), (mid + 8, y + h - 6), (mid + 17, y + h - 6), (mid + 11, y + h - 25), (mid + 9, y + 32), (mid, y)]
    draw.line(outline, fill=(*CYAN, 220), width=2)
    for p in [0.17, 0.35, 0.72, 0.88]:
        yy = y + h * p
        draw.line((mid - 10, yy, mid + 10, yy), fill=(*CYAN, 170))
    for shift in [0, 5, 10]:
        draw.ellipse((x + 5 - shift, y + h - 7 - shift / 3, x + w - 5 + shift, y + h + shift / 3), outline=(*CYAN, 100))


def overlay(time):
    image = Image.new("RGBA", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    margin, cut = 25, 16
    draw.line([(margin + cut, margin), (WIDTH - margin - cut, margin), (WIDTH - margin, margin + cut), (WIDTH - margin, HEIGHT - margin - cut), (WIDTH - margin - cut, HEIGHT - margin), (margin + cut, HEIGHT - margin), (margin, HEIGHT - margin - cut), (margin, margin + cut), (margin + cut, margin)], fill=(*CYAN, 140), width=1)
    draw.text((45, 43), "ROCKETWRIGHT", font=font(27), fill=(228, 247, 255, 245))
    draw.text((47, 75), "MISSION DESIGN / VISUAL STUDY", font=font(10), fill=(*CYAN, 220))
    if time > 0.6:
        panel(draw, (48, 103, 315, 189), "Payload Fairing")
        for label, value, yy in [("TYPE", "CLAMSHELL / TWO HALVES", 165), ("LOOK", "CARBON COMPOSITE", 198), ("ROLE", "PAYLOAD ENCLOSURE", 231)]:
            draw.text((63, yy), label, font=font(12), fill=(213, 232, 241, 210))
            draw.text((134, yy), value, font=font(12), fill=(*CYAN, 230))
        draw.text((134, 251), "CONCEPT GEOMETRY", font=font(11), fill=(191, 218, 232, 205))
    if time > 1.1:
        panel(draw, (902, 101, 330, 217), "Render Layers")
        draw.text((918, 141), "CONCEPT VIEW ACTIVE", font=font(15), fill=(*GREEN, 235))
        values = [0.89, 0.76, 0.94, 0.82, 0.92]
        for i, name in enumerate(["GEOMETRY", "MATERIALS", "LIGHTING", "CAMERA", "OVERLAYS"]):
            yy = 177 + i * 24
            draw.text((918, yy), name, font=font(11), fill=(211, 237, 247, 210))
            draw.rectangle((1061, yy + 3, 1198, yy + 9), fill=(33, 90, 100, 140))
            progress = smooth((time - 1.25 - i * 0.10) / 0.75)
            draw.rectangle((1061, yy + 3, 1061 + 137 * values[i] * progress, yy + 9), fill=(*GREEN, 230))
    if time > 0.85:
        panel(draw, (493, 26, 252, 180))
        wire_fairing(draw, (502, 34, 234, 163))
        panel(draw, (903, 504, 329, 182))
        wire_fairing(draw, (911, 517, 205, 159))
        draw.text((1120, 572), "FAIRING", font=font(12), fill=(*CYAN, 235))
        draw.text((1120, 593), "OPEN VIEW", font=font(11), fill=(*CYAN, 215))
        draw.text((1120, 614), "CONCEPT", font=font(11), fill=(*CYAN, 210))
        panel(draw, (60, 386, 120, 294))
        vehicle(draw, 82, 405, 76, 255)
    draw.text((369, 686), "CONCEPT VISUALIZATION / NOT A FLIGHT RESULT", font=font(10), fill=(*CYAN, 165))
    reveal = smooth((time - 0.23) / 0.65)
    if reveal < 1:
        image.putalpha(image.getchannel("A").point(lambda value: int(value * reveal)))
    return image


def original_audio(path, seconds=10.43):
    rate = 48000
    rng = random.Random(42)
    samples = array.array("h")
    filtered = 0.0
    for i in range(round(rate * seconds)):
        t = i / rate
        filtered = filtered * 0.94 + rng.uniform(-1, 1) * 0.06
        fade = smooth(t / 0.45) * (1 - smooth((t - 8.15) / 1.15))
        drone = 0.038 * math.sin(math.tau * 49 * t) + 0.022 * math.sin(math.tau * 98.2 * t)
        air = 0.16 * filtered
        chime = 0
        for event, pitch in [(0.62, 740), (1.12, 990), (1.5, 1190), (4.4, 520)]:
            dt = t - event
            if 0 <= dt < 0.35:
                chime += math.sin(math.tau * pitch * dt) * math.exp(-dt * 20) * 0.045
        value = max(-0.8, min(0.8, (drone + air + chime) * fade * 3.2))
        pan = 0.04 * math.sin(t * 0.8)
        samples.extend((int(value * (1 - pan) * 32767), int(value * (1 + pan) * 32767)))
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(samples.tobytes())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--poster", type=int)
    args = parser.parse_args()
    output = ROOT / "renders"
    output.mkdir(exist_ok=True)
    if args.poster:
        background = Image.open(output / f"preview_{args.poster:04d}.png").convert("RGB").resize((WIDTH, HEIGHT))
        composed = Image.alpha_composite(grade(background).convert("RGBA"), overlay((args.poster - 1) / FPS))
        path = output / "rocketwright_fairing_poster.png"
        composed.convert("RGB").save(path)
        print(path.name)
        return
    original_audio(output / "original_sound.wav")
    process = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "warning", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS), "-i", "-", "-i", str(output / "original_sound.wav"), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-t", "10.43", "-map_metadata", "-1", "-metadata", "title=RocketWright Fairing Concept", "-metadata", "comment=Concept visualization; not a flight or structural result", "-movflags", "+faststart", str(output / "rocketwright_fairing.mp4")], stdin=subprocess.PIPE)
    poster_frame = 170
    last = None
    for frame in range(1, FRAMES + 1):
        t = (frame - 1) / FPS
        if frame <= 263:
            background = Image.open(output / "frames" / f"frame_{frame:04d}.png").convert("RGB")
            last = background
        else:
            background = last.copy()
        background = grade(background)
        composed = Image.alpha_composite(background.convert("RGBA"), overlay(t)).convert("RGB")
        visibility = smooth(t / 0.5) * (1 - smooth((t - 8.33) / 0.5))
        composed = ImageEnhance.Brightness(composed).enhance(visibility)
        if frame == poster_frame:
            composed.save(output / "rocketwright_fairing_poster.png")
        process.stdin.write(composed.tobytes())
    process.stdin.close()
    if process.wait() != 0:
        raise SystemExit("Video encoder failed")
    print("Encoded rocketwright_fairing.mp4")


if __name__ == "__main__":
    main()
