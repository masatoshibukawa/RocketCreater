"""Start the project-local ComfyUI on loopback, with cloud nodes disabled."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

from bootstrap import COMFY, PYTHON, ROOT, RUNTIME, local_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8188)
    parser.add_argument("--background", action="store_true")
    options = parser.parse_args()
    directories = {"user": RUNTIME / "user", "input": RUNTIME / "inputs", "output": ROOT / "outputs"}
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)
    arguments = [str(PYTHON), "-u", str(COMFY / "main.py"), "--listen", "127.0.0.1", "--port", str(options.port), "--disable-auto-launch", "--offline", "--disable-all-custom-nodes", "--disable-metadata", "--reserve-vram", "2"]
    for name, directory in directories.items():
        arguments.extend([f"--{name}-directory", str(directory)])
    environment = local_environment()
    environment.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "PYTHONUTF8": "1"})
    if not options.background:
        subprocess.run(arguments, cwd=COMFY, env=environment, check=True)
        return
    address = f"http://127.0.0.1:{options.port}"
    try:
        urllib.request.urlopen(address + "/system_stats", timeout=2).close()
    except urllib.error.URLError:
        pass
    else:
        raise RuntimeError(f"Port {options.port} already serves ComfyUI; verify its identity before reuse")
    log_path = RUNTIME / "server.log"
    with log_path.open("ab") as log:
        process = subprocess.Popen(arguments, cwd=COMFY, env=environment, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    (RUNTIME / "server.json").write_text(json.dumps({"pid": process.pid, "url": address}, indent=2) + "\n")
    for _ in range(90):
        if process.poll() is not None:
            raise RuntimeError(f"ComfyUI exited with {process.returncode}; inspect runtime/server.log")
        try:
            with urllib.request.urlopen(address + "/system_stats", timeout=2) as response:
                stats = json.load(response)
            print(json.dumps({"pid": process.pid, "url": address, "devices": [item["name"] for item in stats["devices"]]}))
            return
        except urllib.error.URLError:
            time.sleep(0.5)
    raise RuntimeError("Startup was not confirmed within 45 seconds; inspect runtime/server.log")


if __name__ == "__main__":
    main()
