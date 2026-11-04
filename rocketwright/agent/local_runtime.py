"""Bounded loopback JSON clients. Model output never becomes executable code."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class LocalRuntimeError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LocalRuntimeError("Local runtime redirects are disabled")


class LocalJSON:
    def __init__(self, address: str, timeout: float = 120):
        parsed = urlsplit(address)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("Runtime address must be an HTTP loopback origin")
        self.address = address.rstrip("/")
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, endpoint: str, data: dict | None = None, *, timeout=None) -> Any:
        body = None if data is None else json.dumps(data).encode("utf-8")
        request = urllib.request.Request(
            self.address + endpoint, body, {"Content-Type": "application/json"}
        )
        try:
            with self.opener.open(request, timeout=timeout or self.timeout) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise LocalRuntimeError("Runtime response exceeds the JSON size limit")
            return json.loads(raw)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise LocalRuntimeError(f"Local runtime request failed: {type(exc).__name__}") from exc


class LocalDirector:
    def __init__(self):
        connection_path = (
            Path(__file__).resolve().parents[2] / "AIvideo/local-director/runtime/connection.json"
        )
        connection = json.loads(connection_path.read_text()) if connection_path.is_file() else {}
        self.model = os.getenv("ROCKETWRIGHT_LOCAL_MODEL") or connection.get("model")
        self.api = LocalJSON(
            os.getenv("ROCKETWRIGHT_OLLAMA_URL")
            or connection.get("url")
            or "http://127.0.0.1:11434"
        )

    def models(self) -> list[str]:
        rows = self.api.request("/api/tags", timeout=3).get("models", [])
        # Reject cloud aliases and remote-backed entries even on a loopback server.
        return [
            row["name"]
            for row in rows
            if isinstance(row.get("name"), str)
            and "cloud" not in row["name"].lower()
            and not row.get("remote_host")
            and not row.get("remote_model")
        ]

    def generate(self, context: dict, schema: dict, instructions: str) -> tuple[dict, str]:
        models = self.models()
        model = self.model
        if model is None:
            model = next((m for m in models if m.lower().startswith("gemma")), None)
        if model not in models:
            raise LocalRuntimeError(
                "No configured local model; start Ollama with an installed model"
            )
        result = self.api.request(
            "/api/chat",
            {
                "model": model,
                "stream": False,
                "think": False,
                "format": schema,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
                ],
                "options": {"temperature": 0, "num_predict": 1800},
                "keep_alive": 0,
            },
        )
        try:
            return json.loads(result["message"]["content"]), model
        except (KeyError, TypeError, ValueError) as exc:
            raise LocalRuntimeError("Local model did not return a JSON object") from exc
