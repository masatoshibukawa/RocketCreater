"""Download optional local models used by the realism experiments."""

import argparse
import json
from pathlib import Path
import shutil

from bootstrap import COMFY, ROOT, download, read_json

GROUPS = {
    "photo": [
        ("Comfy-Org/flux2-klein", "split_files/diffusion_models/flux-2-klein-4b.safetensors"),
        ("Comfy-Org/flux2-klein", "split_files/text_encoders/qwen_3_4b.safetensors"),
        ("Comfy-Org/flux2-dev", "split_files/vae/flux2-vae.safetensors"),
    ],
    "wan14b": [
        ("Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"),
        ("Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"),
        ("Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "split_files/vae/wan_2.1_vae.safetensors"),
    ],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", nargs="+", choices=GROUPS, default=["photo", "wan14b"])
    options = parser.parse_args()
    metadata = {}
    records = []
    for group in options.groups:
        for repository, remote_path in GROUPS[group]:
            if repository not in metadata:
                metadata[repository] = read_json(f"https://huggingface.co/api/models/{repository}?blobs=true")
            info = metadata[repository]
            item = next(item for item in info["siblings"] if item["rfilename"] == remote_path)
            records.append({"group": group, "repository": repository, "revision": info["sha"], "path": remote_path, "bytes": item["lfs"]["size"], "sha256": item["lfs"]["sha256"]})
    needed = sum(item["bytes"] for item in records if not (COMFY / "models" / Path(item["path"]).relative_to("split_files")).exists())
    free = shutil.disk_usage(ROOT).free
    print(f"Download: {needed / 1e9:.2f} GB; free: {free / 1e9:.2f} GB", flush=True)
    if free < needed + 15 * 2**30:
        raise RuntimeError("Insufficient free disk space with 15 GiB working margin")
    for item in records:
        destination = COMFY / "models" / Path(item["path"]).relative_to("split_files")
        download(f"https://huggingface.co/{item['repository']}/resolve/{item['revision']}/{item['path']}", destination, item["sha256"], item["bytes"])
    manifest = ROOT / "quality-models.json"
    previous = json.loads(manifest.read_text()) if manifest.exists() else []
    keys = {(item["repository"], item["path"]) for item in records}
    records += [item for item in previous if (item["repository"], item["path"]) not in keys]
    manifest.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print("Optional model hashes verified", flush=True)


if __name__ == "__main__":
    main()
