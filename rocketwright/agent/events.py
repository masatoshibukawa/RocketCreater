"""Progress events yielded by the design loop and streamed to the UI over SSE."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["AgentEvent", "EventType"]

EventType = Literal[
    "thinking", "text", "tool_call", "tool_result", "candidate", "final", "error", "question"
]


class AgentEvent(BaseModel):
    """One step of the loop. `attempt` is the number of simulate_design calls made so far;
    `t_s` is seconds since the loop started."""

    model_config = ConfigDict(frozen=True)

    type: EventType
    attempt: int = Field(ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)
    t_s: float = Field(ge=0)
