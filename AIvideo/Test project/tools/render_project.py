"""Rebuild the scene, composite the export, and run delivery checks."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender", default=shutil.which("blender") or "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")
    parser.add_argument("--samples", type=int, default=24)
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args()
    if not args.skip_render:
        if not Path(args.blender).is_file():
            parser.error("Blender not found. Supply its executable with --blender.")
        subprocess.run([args.blender, "--background", "--python", str(ROOT / "tools/build_scene.py"), "--", "--animate", "--width", "1280", "--height", "720", "--samples", str(args.samples)], check=True, cwd=ROOT)
    missing = [frame for frame in range(1, 264) if not (ROOT / "renders/frames" / f"frame_{frame:04d}.png").is_file()]
    if missing:
        parser.error(f"Missing {len(missing)} scene frames; run without --skip-render.")
    for script in ["compose_video.py", "verify_video.py"]:
        subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "tools" / script)], check=True, cwd=ROOT)


if __name__ == "__main__":
    main()
