"""The consultation director on the Claude API (fake client, no network)."""

from types import SimpleNamespace

import pytest

from rocketwright.agent import claude_director
from rocketwright.agent.claude_director import ClaudeDirector, intake_director
from rocketwright.agent.local_runtime import LocalDirector, LocalRuntimeError


class FakeMessages:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=self.content)


def _client(content):
    return SimpleNamespace(messages=FakeMessages(content))


def test_the_answer_is_the_forced_tool_call_input():
    client = _client([SimpleNamespace(type="tool_use", input={"target_altitude_m": 20})])
    director = ClaudeDirector(client=client, model="claude-haiku-5-5")

    data, model = director.generate({"request": "20 m"}, {"type": "object"}, "抽出して")

    assert data == {"target_altitude_m": 20}
    assert model == "claude-haiku-5-5"
    call = client.messages.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": "answer"}
    assert call["tools"][0]["input_schema"] == {"type": "object"}


def test_no_tool_call_is_an_error():
    director = ClaudeDirector(client=_client([SimpleNamespace(type="text", text="no")]))

    with pytest.raises(LocalRuntimeError):
        director.generate({}, {"type": "object"}, "")


def test_the_paid_switch_picks_claude_and_otherwise_gemma(monkeypatch):
    monkeypatch.setenv("ROCKETWRIGHT_ENABLE_CLOUD_DESIGN", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    assert isinstance(intake_director(), ClaudeDirector)

    monkeypatch.delenv("ROCKETWRIGHT_ENABLE_CLOUD_DESIGN")
    assert isinstance(claude_director.intake_director(), LocalDirector)
