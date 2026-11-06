"""Bounded Claude Messages adapter. Credentials and endpoint stay outside saved evidence."""

import json
import os
from types import SimpleNamespace

import anthropic


class ClaudeSelectionError(ValueError):
    pass


class ClaudeDirector:
    def __init__(self, *, client=None, model=None, max_tokens=1200):
        self.model = model or os.getenv("ROCKETWRIGHT_CLAUDE_MODEL", "claude-sonnet-5-5")
        # Do not save or echo API keys, request headers or raw exception responses.
        if client is None and not os.getenv("ANTHROPIC_API_KEY"):
            raise ClaudeSelectionError("ANTHROPIC_API_KEY is not configured")
        self.client = client or anthropic.Anthropic(max_retries=0)
        self.api = SimpleNamespace(timeout=90)
        self.max_tokens = max_tokens
        self.last_usage = {}

    def generate(self, context, schema, instructions):
        self.last_usage = {}
        # String length constraints are enforced by the host; the provider supports
        # object shape, required properties and enum-constrained action IDs.
        wire = json.loads(json.dumps(schema))
        for field in wire.get("properties", {}).values():
            field.pop("minLength", None)
            field.pop("maxLength", None)
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=instructions,
                messages=[{"role": "user", "content": json.dumps(context, ensure_ascii=False)}],
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": wire}},
                timeout=self.api.timeout,
            )
        except anthropic.APIError as error:
            # Provider errors can contain credentials or echoed inputs. Record a
            # classification/status only; retries are bounded by the host planner.
            raise ClaudeSelectionError(
                f"Claude request failed: {type(error).__name__}; "
                f"status={getattr(error, 'status_code', None)}"
            ) from None
        self.last_usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "request_id": getattr(response, "_request_id", None),
            "stop_reason": response.stop_reason,
        }
        if response.stop_reason != "end_turn":
            raise ClaudeSelectionError("Claude did not finish a complete decision")
        texts = [block.text for block in response.content if block.type == "text"]
        if len(texts) != 1:
            raise ClaudeSelectionError("Claude returned no unique JSON decision")
        try:
            result = json.loads(texts[0])
        except (TypeError, ValueError):
            raise ClaudeSelectionError("Claude returned invalid decision JSON") from None
        return result, response.model
