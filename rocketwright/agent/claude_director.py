"""The intake director on the Claude API, with the same `generate` call as LocalDirector.

The consultation panel asks a director to fill a JSON schema from a request. With the paid
design enabled (ROCKETWRIGHT_ENABLE_CLOUD_DESIGN=1 and ANTHROPIC_API_KEY set), Claude fills it
through one forced tool call, so the answer always has the schema's shape; otherwise the local
Gemma runtime stays in use.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from typing import Any

import anthropic

from rocketwright.agent.local_runtime import LocalDirector, LocalRuntimeError

__all__ = ["ClaudeDirector", "cloud_enabled", "intake_director"]

ANSWER_TOOL = "answer"
MAX_TOKENS = 2000


def cloud_enabled() -> bool:
    return os.getenv("ROCKETWRIGHT_ENABLE_CLOUD_DESIGN") == "1" and bool(
        os.getenv("ANTHROPIC_API_KEY")
    )


class ClaudeDirector:
    def __init__(self, *, client: Any = None, model: str | None = None) -> None:
        from rocketwright.agent.loop import AgentConfig

        self.model = model or AgentConfig.load().light_model
        self.client = client
        self.api = SimpleNamespace(timeout=90.0)  # callers set the timeout here, as on LocalJSON

    def generate(self, context: dict, schema: dict, instructions: str) -> tuple[dict, str]:
        client = self.client or anthropic.Anthropic(timeout=self.api.timeout, max_retries=1)
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=instructions,
                messages=[{"role": "user", "content": json.dumps(context, ensure_ascii=False)}],
                tools=[
                    {
                        "name": ANSWER_TOOL,
                        "description": "Return the extracted fields.",
                        "input_schema": schema,
                    }
                ],
                tool_choice={"type": "tool", "name": ANSWER_TOOL},
            )
        except anthropic.APIError as exc:
            raise LocalRuntimeError(f"Claude request failed: {type(exc).__name__}") from exc
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and isinstance(block.input, dict):
                return block.input, self.model
        raise LocalRuntimeError("Claude did not return the requested JSON")


def intake_director() -> ClaudeDirector | LocalDirector:
    return ClaudeDirector() if cloud_enabled() else LocalDirector()
