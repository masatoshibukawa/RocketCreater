"""Generate a short Wan2.2 image-to-video sample through the local ComfyUI API."""

import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import uuid

from bootstrap import ROOT, RUNTIME

POSITIVE = "A cinematic inspection shot inside a clean industrial spacecraft assembly hangar. Two tall open carbon-fiber payload fairing halves stand behind a central metallic upper-stage truss and its dark engine nozzles. The camera makes a slow smooth lateral dolly to the left with subtle natural parallax, keeping the entire assembly centered. All hardware is stationary and rigid, with stable geometry and unchanged proportions. Realistic cool overhead lighting, fine brushed-metal reflections, carbon-fiber surface detail, restrained cinematic contrast, sharp technical product cinematography. A single continuous shot."
NEGATIVE = "text, subtitles, logos, watermark, people, flames, smoke, explosion, spacecraft launch, opening or closing fairings, moving hardware, bending metal, changing geometry, morphing, duplicate engines, flicker, jitter, camera shake, abrupt cuts, oversaturated colors, low quality, blurry details"


def api(address, endpoint, data=None):
    request = urllib.request.Request(address + endpoint, data=json.dumps(data).encode() if data is not None else None, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def workflow(filename, width, height, frames, steps, seed):
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_ti2v_5B_fp16.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}},
        "4": {"class_type": "LoadImage", "inputs": {"image": filename}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": POSITIVE}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": NEGATIVE}},
        "7": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["3", 0], "width": width, "height": height, "length": frames, "batch_size": 1, "start_image": ["4", 0]}},
        "8": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
        "9": {"class_type": "KSampler", "inputs": {"model": ["8", 0], "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["7", 0], "seed": seed, "steps": steps, "cfg": 5.0, "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1.0}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}},
        "11": {"class_type": "CreateVideo", "inputs": {"images": ["10", 0], "fps": 24.0}},
        "12": {"class_type": "SaveVideo", "inputs": {"video": ["11", 0], "filename_prefix": "rocketwright_wan22", "format": "mp4", "codec": "h264"}},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=ROOT.parent / "Test project/renders/frames/frame_0170.png")
    parser.add_argument("--width", type=int, default=832)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--frames", type=int, default=49)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20261104)
    parser.add_argument("--port", type=int, default=8188)
    options = parser.parse_args()
    if options.width % 32 or options.height % 32 or (options.frames - 1) % 4:
        parser.error("Width/height must be multiples of 32; frames must be 4n+1")
    from PIL import Image
    image_path = RUNTIME / "inputs" / "rocketwright_fairing.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(options.image) as image:
        image.convert("RGB").save(image_path)
    prompt = workflow(image_path.name, options.width, options.height, options.frames, options.steps, options.seed)
    (ROOT / "workflow-api.json").write_text(json.dumps(prompt, indent=2) + "\n", encoding="utf-8")
    address = f"http://127.0.0.1:{options.port}"
    info = api(address, "/object_info")
    missing = sorted({node["class_type"] for node in prompt.values()} - set(info))
    if missing:
        raise RuntimeError(f"Missing nodes: {missing}")
    started = time.monotonic()
    response = api(address, "/prompt", {"prompt": prompt, "client_id": str(uuid.uuid4())})
    prompt_id = response["prompt_id"]
    print(f"Queued {prompt_id}", flush=True)
    report = {"prompt_id": prompt_id, "input": "../Test project/renders/frames/frame_0170.png" if options.image == parser.get_default("image") else options.image.name, "input_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(), "width": options.width, "height": options.height, "frames": options.frames, "fps": 24, "steps": options.steps, "seed": options.seed, "cfg": 5, "sampler": "uni_pc", "scheduler": "simple", "shift": 8, "audio": "none", "workflow": "workflow-api.json"}
    (ROOT / "generation-request.json").write_text(json.dumps(report, indent=2) + "\n")
    while time.monotonic() - started < 3600:
        history = api(address, f"/history/{prompt_id}")
        if prompt_id in history:
            result = history[prompt_id]
            report.update({"elapsed_seconds": round(time.monotonic() - started, 2), "status": result["status"], "outputs": result.get("outputs", {})})
            (RUNTIME / "generation-history.json").write_text(json.dumps(result, indent=2) + "\n")
            (ROOT / "generation-result.json").write_text(json.dumps(report, indent=2) + "\n")
            if result["status"]["status_str"] != "success":
                raise RuntimeError("Generation failed; inspect runtime/generation-history.json")
            print(json.dumps(report, indent=2), flush=True)
            return
        time.sleep(5)
        elapsed = time.monotonic() - started
        if int(elapsed) % 30 < 5:
            print(f"Generating: {elapsed:.0f}s", flush=True)
    raise TimeoutError("No completion after one hour; inspect the running job before retrying")


if __name__ == "__main__":
    main()
