"""Install an isolated ComfyUI and the official Wan2.2 5B model set."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import venv
import zipfile

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "runtime"
COMFY = RUNTIME / "ComfyUI"
PYTHON = RUNTIME / "venv" / "Scripts" / "python.exe"
TAG = "v0.44.0"
MODEL_REPO = "Comfy-Org/Wan_2.2_ComfyUI_Repackaged"
MODEL_FILES = {
    "split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors": "diffusion_models",
    "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors": "text_encoders",
    "split_files/vae/wan2.2_vae.safetensors": "vae",
}


def read_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "local-video-setup"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url, destination, expected_hash=None, expected_size=None):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and (expected_size is None or destination.stat().st_size == expected_size):
        if expected_hash is None or sha256(destination) == expected_hash:
            print(f"Reusing {destination.name}", flush=True)
            return
    partial = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(4):
        try:
            offset = partial.stat().st_size if partial.exists() else 0
            headers = {"User-Agent": "local-video-setup", "Accept-Encoding": "identity"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=90) as response:
                append = offset > 0 and response.status == 206
                written = offset if append else 0
                last_report = 0.0
                with partial.open("ab" if append else "wb") as target:
                    while chunk := response.read(8 * 1024 * 1024):
                        target.write(chunk)
                        written += len(chunk)
                        if time.monotonic() - last_report > 20:
                            print(f"{destination.name}: {written / 1e9:.2f} GB", flush=True)
                            last_report = time.monotonic()
            if expected_size is not None and partial.stat().st_size != expected_size:
                raise ValueError(f"Size mismatch for {destination.name}")
            if expected_hash is not None and sha256(partial) != expected_hash:
                raise ValueError(f"SHA-256 mismatch for {destination.name}; keep partial for inspection")
            partial.replace(destination)
            return
        except Exception as error:
            if attempt == 3 or isinstance(error, ValueError):
                raise
            print(f"Download retry {attempt + 1}: {error}", flush=True)
            time.sleep(3)


def run(*arguments):
    print("Running:", " ".join(map(str, arguments)), flush=True)
    subprocess.run(list(map(str, arguments)), check=True, env=local_environment())


def local_environment():
    environment = os.environ.copy()
    for key, suffix in {
        "PIP_CACHE_DIR": "cache/pip", "TORCH_HOME": "cache/torch",
        "HF_HOME": "cache/huggingface", "XDG_CACHE_HOME": "cache",
    }.items():
        environment[key] = str(RUNTIME / suffix)
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    return environment


def install():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    print(f"Available disk: {shutil.disk_usage(ROOT).free / 2**30:.1f} GiB", flush=True)
    source_record = RUNTIME / "comfy-source.json"
    if not source_record.exists():
        commit = read_json(f"https://api.github.com/repos/Comfy-Org/ComfyUI/commits/{TAG}")["sha"]
        archive = RUNTIME / "downloads" / f"ComfyUI-{TAG}.zip"
        download(f"https://api.github.com/repos/Comfy-Org/ComfyUI/zipball/{commit}", archive)
        COMFY.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                relative = Path(*Path(member.filename).parts[1:])
                destination = (COMFY / relative).resolve()
                if not destination.is_relative_to(COMFY.resolve()):
                    raise ValueError("Unsafe archive path")
                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                elif relative.parts:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(member) as source, destination.open("wb") as target:
                        shutil.copyfileobj(source, target)
        source_record.write_text(json.dumps({"tag": TAG, "commit": commit, "zip_sha256": sha256(archive)}, indent=2) + "\n")
    if not PYTHON.exists():
        venv.create(RUNTIME / "venv", with_pip=True)
    run(PYTHON, "-m", "pip", "install", "--upgrade", "pip")
    run(PYTHON, "-m", "pip", "install", "torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cu130")
    run(PYTHON, "-m", "pip", "install", "-r", COMFY / "requirements.txt", "imageio-ffmpeg")
    metadata = read_json(f"https://huggingface.co/api/models/{MODEL_REPO}?blobs=true")
    revision = metadata["sha"]
    siblings = {item["rfilename"]: item for item in metadata["siblings"]}
    models = []
    for remote_path, category in MODEL_FILES.items():
        item = siblings[remote_path]
        expected_hash = item["lfs"]["sha256"]
        expected_size = item["lfs"]["size"]
        filename = Path(remote_path).name
        download(f"https://huggingface.co/{MODEL_REPO}/resolve/{revision}/{remote_path}", COMFY / "models" / category / filename, expected_hash, expected_size)
        models.append({"file": filename, "category": category, "bytes": expected_size, "sha256": expected_hash})
    manifest = {"comfy": json.loads(source_record.read_text()), "python": sys.version.split()[0], "model_repository": MODEL_REPO, "model_revision": revision, "models": models}
    (ROOT / "installation.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with (ROOT / "requirements-lock.txt").open("w", encoding="utf-8") as target:
        subprocess.run([str(PYTHON), "-m", "pip", "freeze"], check=True, stdout=target, env=local_environment())
    run(PYTHON, "-c", "import torch; print('Torch:',torch.__version__,'CUDA:',torch.version.cuda,'available:',torch.cuda.is_available()); print(torch.cuda.get_device_name(0)); assert torch.cuda.is_available()")
    print("Installation complete", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="Download official code, packages, and models into runtime/")
    options = parser.parse_args()
    if options.install:
        install()
    else:
        parser.print_help()
