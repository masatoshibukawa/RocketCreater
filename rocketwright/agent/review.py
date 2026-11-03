"""Per-aspect reviewers (CLAUDE.md section 8, phase 3): stability, recovery, cost, safety.

Each reviewer is one structured-output call on the light model
(`client.messages.parse(..., output_format=ReviewVerdict, output_config={"effort": "low"})`,
adaptive thinking left at its default, no tools, no forced tool_choice). The four run
concurrently with asyncio.gather under a Semaphore(4); results come back in ASPECTS order.

Reviewers judge and point; they never produce numbers. `sanitize_verdict` drops every finding
or suggestion that mentions a number absent from the tool results (provenance check), and an
API failure of one reviewer becomes a "minor" verdict instead of failing the design loop.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import anthropic
from pydantic import BaseModel, Field, ValidationError

from rocketwright.agent.prompts import REVIEWER_PROMPTS
from rocketwright.agent.provenance import find_unsourced_numbers

if TYPE_CHECKING:  # pragma: no cover - import cycle guard (loop imports review)
    from rocketwright.agent.loop import AgentConfig

__all__ = [
    "ASPECTS",
    "Aspect",
    "ReviewRun",
    "ReviewVerdict",
    "Severity",
    "needs_redesign",
    "review_candidate",
    "review_candidate_detailed",
    "review_feedback_message",
    "reviewer_request",
    "sanitize_verdict",
]

ASPECTS: tuple[str, ...] = ("stability", "recovery", "cost", "safety")
Aspect = Literal["stability", "recovery", "cost", "safety"]
Severity = Literal["ok", "minor", "major", "blocker"]
SEVERITY_ORDER: dict[str, int] = {"ok": 0, "minor": 1, "major": 2, "blocker": 3}

REVIEWER_MAX_TOKENS = 4096
_MAX_CONCURRENT_REVIEWERS = 4
_UNAVAILABLE_PREFIX = "reviewer unavailable: "


class ReviewVerdict(BaseModel):
    """Structured output of one reviewer (also the schema sent to the API)."""

    aspect: Aspect
    severity: Severity
    findings: list[str] = Field(default_factory=list)
    suggested_changes: list[str] = Field(default_factory=list)


def needs_redesign(verdict: ReviewVerdict) -> bool:
    return SEVERITY_ORDER[verdict.severity] >= SEVERITY_ORDER["major"]


@dataclass(frozen=True)
class ReviewRun:
    """Sanitised verdicts (ASPECTS order) plus the texts the provenance check removed."""

    verdicts: list[ReviewVerdict]
    dropped: dict[str, list[str]] = field(default_factory=dict)  # aspect -> removed texts


# --------------------------------------------------------------------------- request shape


def _slim(sim_result: dict[str, Any]) -> dict[str, Any]:
    slim = dict(sim_result)
    if isinstance(slim.get("trace"), list):
        slim["trace_point_count"] = len(slim.pop("trace"))
    return slim


def reviewer_request(
    aspect: str,
    config: AgentConfig,
    candidate: dict[str, Any],
    sim_result: dict[str, Any],
    requirement_text: str,
    extra_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Keyword arguments of the `messages.parse` call for one reviewer (kept separate so tests
    and the fake client can inspect the exact API shape)."""
    rc = config.reviewers
    user_text = "\n\n".join(
        [
            f"Review aspect: {aspect}",
            f"Candidate source_id: {candidate.get('source_id')}",
            "User requirement (verbatim):\n" + requirement_text.strip(),
            "Candidate design (tool input):\n"
            + json.dumps(candidate.get("design"), ensure_ascii=False),
            "Simulation result (tool output, cite its numbers only):\n"
            + json.dumps(_slim(sim_result), ensure_ascii=False),
        ]
        + (
            ["Additional context:\n" + json.dumps(extra_context, ensure_ascii=False)]
            if extra_context
            else []
        )
    )
    return {
        "model": rc.model or config.light_model,
        "max_tokens": rc.max_tokens,
        "system": REVIEWER_PROMPTS[aspect],
        "messages": [{"role": "user", "content": user_text}],
        "output_config": {"effort": rc.effort},
        "output_format": ReviewVerdict,
    }


def _verdict_from_response(aspect: str, response: Any) -> ReviewVerdict:
    parsed = getattr(response, "parsed_output", None)
    if isinstance(parsed, ReviewVerdict):
        verdict = parsed
    elif isinstance(parsed, BaseModel):
        verdict = ReviewVerdict.model_validate(parsed.model_dump())
    else:
        text = next(
            (b.text for b in getattr(response, "content", []) if getattr(b, "type", "") == "text"),
            "",
        )
        verdict = ReviewVerdict.model_validate(json.loads(text))
    if verdict.aspect != aspect:  # the model is told its aspect; never trust a swapped one
        verdict = verdict.model_copy(update={"aspect": aspect})
    return verdict


def _fallback(aspect: str, reason: str) -> ReviewVerdict:
    return ReviewVerdict(
        aspect=aspect,  # type: ignore[arg-type]
        severity="minor",
        findings=[_UNAVAILABLE_PREFIX + reason],
        suggested_changes=[],
    )


# --------------------------------------------------------------------------- provenance


def sanitize_verdict(
    verdict: ReviewVerdict, sources: list[dict[str, Any]]
) -> tuple[ReviewVerdict, list[str]]:
    """Drop findings / suggested changes that cite numbers absent from `sources` (tool results
    and the inputs the reviewer was shown). Returns the clean verdict and the dropped texts;
    a one-line note (with no numbers above ten) replaces the dropped findings so the designer
    still learns that the reviewer tried to say more."""
    dropped: list[str] = []
    findings = [f for f in verdict.findings if not _unsourced(f, sources, dropped)]
    n_dropped_findings = len(dropped)
    suggestions = [s for s in verdict.suggested_changes if not _unsourced(s, sources, dropped)]
    if n_dropped_findings == 1:
        findings.append("[1 finding dropped: it cited numbers absent from the tool results]")
    elif n_dropped_findings:
        findings.append(
            f"[{n_dropped_findings} findings dropped: they cited numbers absent from the tool "
            "results]"
        )
    clean = verdict.model_copy(update={"findings": findings, "suggested_changes": suggestions})
    return clean, dropped


def _unsourced(text: str, sources: list[dict[str, Any]], dropped: list[str]) -> bool:
    if find_unsourced_numbers(text, sources):
        dropped.append(text)
        return True
    return False


# --------------------------------------------------------------------------- run


async def review_candidate_detailed(
    client: Any,
    config: AgentConfig,
    candidate: dict[str, Any],
    sim_result: dict[str, Any],
    requirement_text: str,
    *,
    extra_context: dict[str, Any] | None = None,
) -> ReviewRun:
    """Run the four reviewers concurrently on one passing candidate. Never raises for an API
    error of a single reviewer (fallback verdict, severity "minor"). Verdicts come back in
    ASPECTS order, provenance-sanitised; the removed texts are reported per aspect."""
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_REVIEWERS)
    sources: list[dict[str, Any]] = [sim_result]
    if isinstance(candidate.get("design"), dict):
        sources.append(candidate["design"])
    if extra_context:
        sources.append(extra_context)

    async def one(aspect: str) -> tuple[ReviewVerdict, list[str]]:
        request = reviewer_request(
            aspect, config, candidate, sim_result, requirement_text, extra_context
        )
        async with semaphore:
            try:
                response = await client.messages.parse(**request)
                verdict = _verdict_from_response(aspect, response)
            except anthropic.APIError as exc:
                return _fallback(aspect, f"{type(exc).__name__}: {exc}"), []
            except (ValidationError, ValueError, StopIteration) as exc:
                return _fallback(aspect, f"unparseable verdict ({type(exc).__name__}: {exc})"), []
        return sanitize_verdict(verdict, sources)

    outcomes = await asyncio.gather(*(one(a) for a in ASPECTS))
    return ReviewRun(
        verdicts=[v for v, _ in outcomes],
        dropped={v.aspect: d for v, d in outcomes if d},
    )


async def review_candidate(
    client: Any,
    config: AgentConfig,
    candidate: dict[str, Any],
    sim_result: dict[str, Any],
    requirement_text: str,
    *,
    extra_context: dict[str, Any] | None = None,
) -> list[ReviewVerdict]:
    """`review_candidate_detailed` without the dropped texts."""
    run = await review_candidate_detailed(
        client, config, candidate, sim_result, requirement_text, extra_context=extra_context
    )
    return run.verdicts


# --------------------------------------------------------------------------- feedback


def review_feedback_message(verdicts: list[ReviewVerdict], *, source_id: str) -> str:
    """Compact user-turn text for the design agent; empty when every verdict is "ok"."""
    items = [v for v in verdicts if v.severity != "ok"]
    if not items:
        return ""
    lines = [f"Reviewer findings for candidate {source_id}:"]
    for v in items:
        findings = "; ".join(v.findings) if v.findings else "(no detail given)"
        line = f"- [{v.aspect}/{v.severity}] {findings}"
        if v.suggested_changes:
            line += "; suggested: " + "; ".join(v.suggested_changes)
        lines.append(line)
    if any(needs_redesign(v) for v in items):
        lines.append(
            "Address every blocker and major finding by re-designing and re-simulating "
            "(design_stage / design_from_parts for bottle and amateur, simulate_design for "
            "commercial and heavy) before the final answer, or explain in the final answer why "
            "you did not. A candidate with a blocker will not be reported as passing."
        )
    else:
        lines.append(
            "Minor findings only: no re-design required, but mention them in the explanation."
        )
    return "\n".join(lines)
