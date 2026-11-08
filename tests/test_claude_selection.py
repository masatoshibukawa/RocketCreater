import json
from types import SimpleNamespace

import anthropic
import pytest

from rocketwright.analysis.claude import ClaudeDirector
from rocketwright.analysis.planner import choose
from rocketwright.analysis.schema import SearchLimits


class Messages:
    def __init__(self, *, stop="end_turn", action="screen"):
        self.calls = []
        self.stop, self.action = stop, action

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            stop_reason=self.stop,
            model="contract-test-model",
            _request_id="request-1",
            usage=SimpleNamespace(input_tokens=100, output_tokens=20),
            content=[
                SimpleNamespace(
                    type="text",
                    text=json.dumps(
                        {"action": self.action, "reason": "Compare the offered simulation evidence"}
                    ),
                )
            ],
        )


def run(messages):
    director = ClaudeDirector(client=SimpleNamespace(messages=messages))
    return choose(
        {"offered": {"screen": {"score": 1}, "modes": {"score": 0}}},
        {},
        SearchLimits(planner="claude"),
        director=director,
    )


def test_claude_contract_constrains_ids_and_records_provider_usage():
    messages = Messages()
    result = run(messages)
    assert result["planner"] == "claude" and result["action"] == "screen"
    request = messages.calls[0]
    assert request["output_config"]["format"]["schema"]["properties"]["action"]["enum"] == [
        "screen",
        "modes",
    ]
    assert result["api_requests"][0]["input_tokens"] == 100
    assert "api_key" not in str(result)


@pytest.mark.parametrize("stop,action", [("max_tokens", "screen"), ("end_turn", "unknown")])
def test_claude_incomplete_or_unoffered_decisions_cannot_run(stop, action):
    messages = Messages(stop=stop, action=action)
    result = run(messages)
    assert result["action"] is None and result["planner"] == "failed"
    assert len(messages.calls) == 2 and len(result["api_requests"]) == 2


def test_missing_key_fails_without_silent_local_fallback(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = choose({"offered": {"a": {}, "b": {}}}, {}, SearchLimits(planner="claude"))
    assert result["action"] is None and "not configured" in result["errors"][0]


def test_provider_error_body_is_not_saved():
    class Failing:
        def create(self, **kwargs):
            raise anthropic.APIError("secret-should-not-leak", request=None, body={"key": "secret"})

    result = run(Failing())
    assert "secret" not in json.dumps(result)
    assert result["action"] is None
