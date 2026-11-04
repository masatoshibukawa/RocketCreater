"""Reuse an installed Ollama and its existing models; never download or copy weights."""

import argparse
import json
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "runtime"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--assets",
        type=Path,
        required=True,
        help="Existing directory containing ollama/ and ollama-models/",
    )
    parser.add_argument("--model", default="gemma4:12b")
    parser.add_argument("--port", type=int, default=11436)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9_-]+:[a-z0-9_.-]+", args.model):
        parser.error("Supply an installed local model:tag")
    assets = args.assets.resolve()
    executable = assets / "ollama/ollama.exe"
    family, tag = args.model.split(":")
    manifest = assets / f"ollama-models/manifests/registry.ollama.ai/library/{family}/{tag}"
    if not executable.is_file() or not manifest.is_file():
        parser.error("The executable or selected local model manifest was not found")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    address = f"http://127.0.0.1:{args.port}"
    try:
        opener.open(address + "/api/version", timeout=2).close()
    except OSError:
        pass
    else:
        raise RuntimeError("Port already serves Ollama; verify its owner before reuse")
    env = os.environ.copy()
    env.update(
        OLLAMA_HOST=f"127.0.0.1:{args.port}",
        OLLAMA_MODELS=str(assets / "ollama-models"),
        OLLAMA_NO_CLOUD="1",
        OLLAMA_NOPRUNE="1",
        OLLAMA_NUM_PARALLEL="1",
        OLLAMA_MAX_LOADED_MODELS="1",
        OLLAMA_CONTEXT_LENGTH="8192",
        OLLAMA_KEEP_ALIVE="0",
        OLLAMA_GPU_OVERHEAD="1073741824",
        OLLAMA_FLASH_ATTENTION="1",
        OLLAMA_KV_CACHE_TYPE="q8_0",
        OLLAMA_DEBUG_LOG_REQUESTS="false",
        OLLAMA_NOHISTORY="1",
    )
    with (RUNTIME / "ollama.log").open("ab") as log:
        process = subprocess.Popen(
            [str(executable), "serve"],
            cwd=RUNTIME,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError("Ollama exited; inspect runtime/ollama.log")
        try:
            with opener.open(address + "/api/tags", timeout=2) as response:
                tags = json.load(response)
            if args.model not in {row["name"] for row in tags["models"]}:
                raise RuntimeError("Selected model is not served; no download will be attempted")
            connection = {
                "url": address,
                "model": args.model,
                "pid": process.pid,
                "source": "existing local model store",
                "cloud": False,
            }
            (RUNTIME / "connection.json").write_text(json.dumps(connection, indent=2))
            print(json.dumps(connection), flush=True)
            return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("Ollama startup was not confirmed")


if __name__ == "__main__":
    main()
