"""Design exploration loop over the Claude API (manual tool-use loop, streaming helper).

`run_design_loop()` is an async generator of AgentEvent:
  guard check -> [error] | (thinking | text | tool_call | tool_result | candidate | review)* ->
  [warning] final | question | error

Attempts: a `simulate_design` call (commercial/heavy, or a geometric design), a
`design_from_parts` call (bottle/amateur: parts -> buildability -> sim) or an `auto_design` call
(bottle/amateur: the staged chain's baseline build, judged like design_from_parts) is one
attempt (ATTEMPT_TOOLS); a design_from_parts result stopped by a buildability error has
`sim: null` and is a failed attempt with no candidate. A passing part-space attempt's candidate
carries `build`, `bill` and `origin` (the tool name). `design_stage` is exploration: one stage's
ranked candidates, not an attempt and no candidate event (the UI reads its candidates from the
tool_result).

Phase 3 reviewers (review.py): every passing attempt result (a candidate) is reviewed
once by the four per-aspect reviewers; their verdicts are emitted as a `review` event, and
major/blocker findings are appended as a text block AFTER the tool_result blocks of the same
user message (the API requires tool_result blocks to lead the user turn). A blocker removes the
design from the final passing list (`_apply_review_gate`).

Reference seeds (references.py): when a `find_reference_designs` result carries a seed whose
`sim` passed, a `candidate` event is emitted for it (source_id = that tool_use id, payload
`seeded_from` = reference id) so the UI shows it as attempt 0. The seed is free: it is not a
simulate_design call, so it is not counted as an attempt and not reviewed; the agent adopts
it by simulating it (that call is attempt 1 and is reviewed as usual).

Facts baked in (anthropic SDK 1.x, claude-haiku-5-5 and the other adaptive-thinking models):
  * thinking = {"type": "adaptive", "display": "summarized"}; never `budget_tokens`;
  * depth via output_config={"effort": ...}; no forced tool_choice (prompt steers instead);
  * `client.messages.stream(...)` + `await stream.get_final_message()`;
  * all tool_results of one assistant turn go back in ONE user message;
  * stop reasons handled: end_turn, tool_use, max_tokens, refusal (stop_details), pause_turn.
The SDK reads ANTHROPIC_API_KEY itself; this module never touches or logs it.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal

import anthropic
import yaml
from pydantic import BaseModel, ConfigDict, Field

from rocketwright.agent.constraints import UserConstraints, constrain, read_constraints
from rocketwright.agent.events import AgentEvent
from rocketwright.agent.final_check import split_checked_designs
from rocketwright.agent.prompts import system_prompt
from rocketwright.agent.provenance import find_unsourced_numbers
from rocketwright.agent.review import (
    SEVERITY_ORDER,
    ReviewVerdict,
    needs_redesign,
    review_candidate_detailed,
    review_feedback_message,
)
from rocketwright.agent.tools import execute_tool, get_tool_definitions
from rocketwright.guard import (
    TIER_LIMIT,
    GuardResult,
    check_bottle_limit,
    check_scope,
    requirement_in_reach,
    tier_limit_refusal,
)
from rocketwright.schema import Env, Tier

__all__ = ["AgentConfig", "ReviewerConfig", "models_config_path", "run_design_loop"]

ATTEMPT_TOOL = "simulate_design"
# design_from_parts / auto_design are the bottle/amateur attempts: a build resolved, checked and
# simulated (auto_design: the build the staged chain chose). All three count against the attempt
# budget and yield candidates when their sim passes.
PART_ATTEMPT_TOOLS = ("design_from_parts", "auto_design")
ATTEMPT_TOOLS = (ATTEMPT_TOOL, *PART_ATTEMPT_TOOLS)
REFERENCE_TOOL = "find_reference_designs"
CLASSIFY_TOOL = "classify_requirement"
CANNOT_DO = "できません"
FINAL_KEY = '"designs"'
_BROKEN_FINAL_FEEDBACK = (
    "The final answer is not valid JSON, so nothing could be read from it. Send it again as a "
    "single valid JSON object: escape every double quote and line break inside a string, and "
    "add no text before or after the object."
)
_TRACE_KEY = "trace"
_ATTEMPT_NAMES = "simulate_design / design_from_parts / auto_design calls"


def models_config_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "config" / "models.yaml"


Effort = Literal["low", "medium", "high", "xhigh", "max"]


class ReviewerConfig(BaseModel):
    """`reviewers:` block of config/models.yaml (per-aspect reviewers, review.py)."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    model: str | None = None  # None -> AgentConfig.light_model
    effort: Effort = "low"
    max_tokens: int = Field(default=4096, gt=0)
    max_rounds_per_candidate: int = Field(default=1, ge=0)  # 0 disables; a source_id is never
    # reviewed more than this many times (1 = once)


class AgentConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed_tiers: tuple[Tier, ...] = (Tier.BOTTLE,)
    design_model: str = "claude-haiku-5-5"
    light_model: str = "claude-haiku-5-5"
    effort: Effort = "low"
    thinking_display: str = "summarized"
    max_tokens: int = Field(default=16000, gt=0)
    max_attempts: int = Field(default=8, ge=1)
    max_turns: int = Field(default=24, ge=1)
    reviewers: ReviewerConfig = Field(default_factory=ReviewerConfig)

    @property
    def bottle_only(self) -> bool:
        return self.allowed_tiers == (Tier.BOTTLE,)

    @property
    def reviewers_enabled(self) -> bool:
        return self.reviewers.enabled and self.reviewers.max_rounds_per_candidate > 0

    @classmethod
    def load(cls, path: Path | None = None) -> AgentConfig:
        with (path or models_config_path()).open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)


# --------------------------------------------------------------------------- helpers


def _refusal_payload(guard: GuardResult) -> dict[str, Any]:
    return {
        "kind": "out_of_scope",
        "category": guard.category,
        "reason": guard.reason,
        "suggestion": guard.suggestion,
    }


def _final_check_feedback(mismatches: list[dict[str, Any]]) -> str:
    lines = [
        f"- designs[{found['index']}]: {'; '.join(found['problems'])}" for found in mismatches
    ]
    return (
        "The final answer disagrees with the tool results it cites:\n"
        + "\n".join(lines)
        + "\nCopy the numbers, the pass/fail and the source ids from the tool results and send "
        "the corrected final JSON. A design that still disagrees is removed."
    )


def _tier_refusal(
    tool: str, tool_input: dict[str, Any], result: dict[str, Any], cfg: AgentConfig
) -> GuardResult | None:
    """The refusal when classify_requirement puts the normalised request out of reach. The text
    screen only sees what is plainly written; the model reads the rest."""
    if tool != CLASSIFY_TOOL or "error" in result:
        return None
    requirement = tool_input.get("requirement") or {}
    required = str(result.get("required_tier"))
    in_reach = not cfg.bottle_only or requirement_in_reach(requirement)
    if required in cfg.allowed_tiers and in_reach:
        return None
    return tier_limit_refusal(requirement, required)


def _parse_final_json(text: str) -> dict[str, Any] | None:
    s = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    for candidate in (s, s[s.find("{") : s.rfind("}") + 1] if "{" in s and "}" in s else ""):
        if not candidate:
            continue
        try:
            # strict=False: the light model leaves bare line breaks inside its strings.
            parsed = json.loads(candidate, strict=False)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _explanation_text(result: dict[str, Any]) -> str:
    parts: list[str] = [str(result.get("summary", ""))]
    for d in result.get("designs", []) or []:
        if isinstance(d, dict):
            parts.append(str(d.get("explanation", "")))
    return "\n".join(parts)


def _without_trace(result: dict[str, Any]) -> dict[str, Any]:
    if _TRACE_KEY in result and isinstance(result[_TRACE_KEY], list):
        slim = dict(result)
        slim["trace_point_count"] = len(slim.pop(_TRACE_KEY))
        return slim
    return result


def _strip_sim_traces(node: Any) -> Any:
    """Copy of `node` where every nested `sim` object has its time-series trace replaced by
    `trace_point_count` (design_from_parts / auto_design `sim`, find_reference_designs
    `seed.sim`, any candidate or feasibility entry that carries one)."""
    if isinstance(node, list):
        return [_strip_sim_traces(v) for v in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for k, v in node.items():
        if k == "sim" and isinstance(v, dict):
            out[k] = _without_trace(_strip_sim_traces(v))
        else:
            out[k] = _strip_sim_traces(v)
    return out


def _for_model(result: dict[str, Any]) -> dict[str, Any]:
    """Tool result as sent to the model: the simulation traces are dropped (the UI gets them
    via the tool_result event): the top-level one (simulate_design) and every nested `sim`
    (design_from_parts, auto_design, the find_reference_designs seed). auto_design's own
    `trace` (its per-stage decisions, a list of dicts without a time axis) is kept."""
    trace = result.get(_TRACE_KEY)
    is_stage_trace = isinstance(trace, list) and any(
        isinstance(p, dict) and "stage" in p for p in trace
    )
    return _strip_sim_traces(result if is_stage_trace else _without_trace(result))


def attempt_outcome(
    name: str, tool_input: dict[str, Any], result: dict[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """(sim result, design) of an attempt tool result. simulate_design: the result itself and
    the input design (or the tuned one); design_from_parts / auto_design: the embedded `sim`
    (None when a buildability error stopped the simulation) and the resolved `design`."""
    if name in PART_ATTEMPT_TOOLS:
        sim = result.get("sim")
        return (sim if isinstance(sim, dict) else None), result.get("design")
    return result, result.get("tuned_design") or tool_input.get("design")


def _seed_candidate(tool_use_id: str, result: dict[str, Any]) -> dict[str, Any] | None:
    """The candidate payload for a find_reference_designs result whose seed sim passed, else
    None. The seed is free: it is not a simulate_design call, so it does not count as an
    attempt and is not reviewed (the agent re-simulates it to adopt it)."""
    seed = result.get("seed")
    if not isinstance(seed, dict):
        return None
    sim = seed.get("sim")
    if not isinstance(sim, dict) or not sim.get("success") or not seed.get("design"):
        return None
    return {
        "source_id": tool_use_id,
        "design": seed["design"],
        "metrics": sim.get("metrics", {}),
        "cost_jpy": sim.get("cost_jpy"),
        "seeded_from": seed.get("reference_id"),
    }


_JAPANESE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
# The light model drifted into English in open_questions when the system prompt alone asked.
_REPLY_IN_JAPANESE = (
    "This request is in Japanese: write summary, explanation, open_questions and every "
    "question in Japanese."
)


def _initial_user_message(
    text: str,
    env: Env | None,
    seed: int | None,
    legal_note: str | None,
    held: UserConstraints,
) -> str:
    lines = [text.strip()]
    if env is not None:
        lines.append(
            "Launch environment (pass as `env` to simulate_design / run_dispersion): "
            + json.dumps(env.model_dump(mode="json"), ensure_ascii=False)
        )
    if seed is not None:
        lines.append(f"Use seed {seed} for every simulate_design and run_dispersion call.")
    if legal_note:
        lines.append(f"Note from the scope guard: {legal_note}")
    if held.bottle_id:
        lines.append(
            f"The user asked for a {held.said} bottle: the tools keep {held.bottle_id} for "
            "every design and turn away any other bottle."
        )
    if _JAPANESE.search(text):
        lines.append(_REPLY_IN_JAPANESE)
    return "\n\n".join(lines)


_ASKING_ENDING = re.compile(r"(ください|でしょうか|ますか|ですか|教えて)[。.！!\s]*$")


def _looks_like_question(text: str) -> bool:
    """A reply that is not the final JSON and asks the user for something. Japanese requests
    often end without a question mark ("目標の高度を教えてください。")."""
    return "?" in text or "？" in text or bool(_ASKING_ENDING.search(text.strip()))


def _design_source_ids(design: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    sources = design.get("sources")
    if isinstance(sources, dict):
        ids.update(str(v) for v in sources.values())
    if design.get("source_id"):
        ids.add(str(design["source_id"]))
    return ids


def _apply_review_gate(
    final_result: dict[str, Any], blocked: dict[str, list[str]]
) -> tuple[dict[str, Any], list[str]]:
    """Move every design that cites a review-blocked source_id out of `designs` into
    `rejected_by_review` (passed=False, review_blocked=True, review_findings). Pure: returns a
    new dict and the moved source ids; unchanged input is returned as is."""
    designs = final_result.get("designs")
    if not blocked or not isinstance(designs, list):
        return final_result, []
    kept: list[Any] = []
    rejected: list[dict[str, Any]] = []
    moved: list[str] = []
    for d in designs:
        hit = sorted(_design_source_ids(d) & set(blocked)) if isinstance(d, dict) else []
        if not hit:
            kept.append(d)
            continue
        findings = [f for sid in hit for f in blocked[sid]]
        rejected.append({**d, "passed": False, "review_blocked": True, "review_findings": findings})
        moved.extend(hit)
    if not rejected:
        return final_result, []
    gated = {**final_result, "designs": kept}
    gated["rejected_by_review"] = list(final_result.get("rejected_by_review") or []) + rejected
    return gated, moved


def _max_severity(verdicts: list[ReviewVerdict]) -> str:
    return max((v.severity for v in verdicts), key=lambda s: SEVERITY_ORDER[s], default="ok")


# --------------------------------------------------------------------------- loop


async def run_design_loop(
    requirement_text: str,
    *,
    client: anthropic.AsyncAnthropic | None = None,
    config: AgentConfig | None = None,
    env: Env | dict[str, Any] | None = None,
    seed: int | None = None,
) -> AsyncIterator[AgentEvent]:
    cfg = config or AgentConfig.load()
    t0 = time.monotonic()
    attempts = 0

    def ev(kind: str, payload: dict[str, Any]) -> AgentEvent:
        return AgentEvent(type=kind, attempt=attempts, payload=payload, t_s=time.monotonic() - t0)  # type: ignore[arg-type]

    # 1. scope guard before anything reaches the model
    guard = check_scope(requirement_text)
    if guard.allowed and cfg.bottle_only:
        limit = check_bottle_limit(requirement_text)
        guard = guard if limit.allowed else limit
    if not guard.allowed:
        yield ev("error", _refusal_payload(guard))
        return
    legal_note = guard.suggestion if guard.category == "legal_approval" else None

    env_model = Env.model_validate(env) if isinstance(env, dict) else env
    held = read_constraints(requirement_text)
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": _initial_user_message(
                requirement_text, env_model, seed, legal_note, held
            ),
        }
    ]
    tools = get_tool_definitions(cfg.allowed_tiers)
    tool_results_log: list[dict[str, Any]] = []
    budget_exhausted_told = False
    final_corrected = False  # the model gets one chance to fix a final that fails the check
    review_rounds: dict[str, int] = {}  # source_id -> times reviewed (never above the cap)
    review_blocked: dict[str, list[str]] = {}  # source_id -> blocker findings

    api = client if client is not None else anthropic.AsyncAnthropic()

    for _turn in range(cfg.max_turns):
        try:
            async with api.messages.stream(
                model=cfg.design_model,
                max_tokens=cfg.max_tokens,
                # Tools and system prompt are about 29k tokens and identical on every turn.
                system=[
                    {
                        "type": "text",
                        "text": system_prompt(cfg.bottle_only),
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=tools,
                messages=messages,
                thinking={"type": "adaptive", "display": cfg.thinking_display},
                output_config={"effort": cfg.effort},
            ) as stream:
                response = await stream.get_final_message()
        except anthropic.APIError as exc:
            yield ev("error", {"kind": "api_error", "error": f"{type(exc).__name__}: {exc}"})
            return

        # 2. surface the assistant turn
        tool_uses: list[Any] = []
        text_parts: list[str] = []
        for block in response.content:
            btype = getattr(block, "type", None)
            if btype == "thinking":
                summary = getattr(block, "thinking", "") or ""
                if summary:
                    yield ev("thinking", {"summary": summary})
            elif btype == "text":
                text_parts.append(block.text)
                yield ev("text", {"text": block.text})
            elif btype == "tool_use":
                tool_uses.append(block)
                yield ev("tool_call", {"id": block.id, "name": block.name, "input": block.input})

        stop = response.stop_reason
        if stop == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue
        if stop == "refusal":
            details = getattr(response, "stop_details", None)
            yield ev(
                "error",
                {
                    "kind": "refusal",
                    "stop_reason": stop,
                    "stop_details": details.model_dump()
                    if hasattr(details, "model_dump")
                    else details,
                },
            )
            return
        if stop == "max_tokens":
            yield ev(
                "error",
                {
                    "kind": "truncated",
                    "stop_reason": stop,
                    "detail": "assistant turn hit max_tokens"
                    + (" with a tool call in flight" if tool_uses else ""),
                    "text": "".join(text_parts),
                },
            )
            return

        # 3. no tool calls -> final answer (or a clarifying question)
        if not tool_uses:
            text = "".join(text_parts)
            parsed = _parse_final_json(text)
            if parsed is None:
                if FINAL_KEY in text and not final_corrected:
                    final_corrected = True
                    messages.append({"role": "assistant", "content": response.content})
                    messages.append({"role": "user", "content": _BROKEN_FINAL_FEEDBACK})
                    continue
                if text.lstrip().startswith(CANNOT_DO):
                    refusal = GuardResult(False, TIER_LIMIT, text.strip(), "")
                    yield ev("error", _refusal_payload(refusal))
                elif _looks_like_question(text):
                    yield ev("question", {"text": text})
                else:
                    yield ev(
                        "final",
                        {"result": None, "raw_text": text, "parse_error": "not a JSON object"},
                    )
                return
            checked, mismatches = split_checked_designs(parsed, tool_results_log)
            if mismatches and not final_corrected:
                final_corrected = True
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": _final_check_feedback(mismatches)})
                continue
            if mismatches:
                yield ev(
                    "warning",
                    {
                        "kind": "final_check",
                        "detail": "designs that disagree with the tool results they cite were "
                        "moved from `designs` to `rejected_by_check` in the final result",
                        "rejected": mismatches,
                    },
                )
            violations = find_unsourced_numbers(_explanation_text(checked), tool_results_log)
            parsed, rejected_ids = _apply_review_gate(checked, review_blocked)
            if rejected_ids:
                yield ev(
                    "warning",
                    {
                        "kind": "review_gate",
                        "detail": "designs with a reviewer blocker were moved from `designs` "
                        "to `rejected_by_review` in the final result",
                        "rejected_ids": rejected_ids,
                    },
                )
            yield ev(
                "final",
                {
                    "result": parsed,
                    "provenance_violations": violations,
                    "review_blocked_ids": sorted(review_blocked),
                    "attempts": attempts,
                    "stop_reason": stop,
                },
            )
            return

        # 4. run every tool of this turn, return all results in ONE user message
        messages.append({"role": "assistant", "content": response.content})
        results_content: list[dict[str, Any]] = []
        feedback_texts: list[str] = []
        for tu in tool_uses:
            tool_input = tu.input if isinstance(tu.input, dict) else {}
            tool_input, broken = constrain(tu.name, tool_input, held)
            result: dict[str, Any]
            if broken is not None:
                result = {"error": broken, "source_id": tu.id}
            elif tu.name in ATTEMPT_TOOLS:
                if attempts >= cfg.max_attempts:
                    result = {
                        "error": f"attempt budget exhausted ({cfg.max_attempts} "
                        f"{_ATTEMPT_NAMES}); produce the final answer now",
                        "source_id": tu.id,
                    }
                else:
                    attempts += 1
                    result = execute_tool(tu.name, tool_input, tu.id)
            else:
                result = execute_tool(tu.name, tool_input, tu.id)
            is_error = "error" in result
            if not is_error:
                tool_results_log.append(result)
            yield ev(
                "tool_result",
                {"id": tu.id, "name": tu.name, "is_error": is_error, "result": result},
            )
            refusal = _tier_refusal(tu.name, tool_input, result, cfg)
            if refusal is not None:
                yield ev("error", _refusal_payload(refusal))
                return
            if tu.name == REFERENCE_TOOL and not is_error:
                seed_candidate = _seed_candidate(tu.id, result)
                if seed_candidate is not None:
                    yield ev("candidate", seed_candidate)  # attempt 0: free, not reviewed
            sim, design = attempt_outcome(tu.name, tool_input, result)
            if tu.name in ATTEMPT_TOOLS and not is_error and sim and sim.get("success"):
                candidate = {
                    "source_id": tu.id,
                    # simulate_design: the input design (the tuned one with tune_pitch);
                    # design_from_parts / auto_design: the resolved design, plus the parts and
                    # the bill
                    "design": design,
                    "metrics": sim.get("metrics", {}),
                    "cost_jpy": sim.get("cost_jpy"),
                    "origin": tu.name,
                }
                if tu.name in PART_ATTEMPT_TOOLS:
                    candidate["build"] = result.get("build")
                    candidate["bill"] = result.get("bill")
                yield ev("candidate", candidate)
                # 4b. per-aspect reviewers, once per candidate (review.py)
                if (
                    cfg.reviewers_enabled
                    and review_rounds.get(tu.id, 0) < cfg.reviewers.max_rounds_per_candidate
                ):
                    review_rounds[tu.id] = review_rounds.get(tu.id, 0) + 1
                    run = await review_candidate_detailed(
                        api,
                        cfg,
                        candidate,
                        _for_model(sim),  # the sim result (part-space tools: their `sim`)
                        requirement_text,
                        extra_context={
                            "requirement": tool_input.get("requirement"),
                            **(
                                {"build": result.get("build"), "bill": result.get("bill")}
                                if tu.name in PART_ATTEMPT_TOOLS
                                else {}
                            ),
                        },
                    )
                    verdicts = run.verdicts
                    feedback = review_feedback_message(verdicts, source_id=tu.id)
                    blockers = [v for v in verdicts if v.severity == "blocker"]
                    if blockers:
                        review_blocked[tu.id] = [f for v in blockers for f in v.findings]
                    if any(needs_redesign(v) for v in verdicts):
                        feedback_texts.append(feedback)
                    yield ev(
                        "review",
                        {
                            "source_id": tu.id,
                            "verdicts": [v.model_dump() for v in verdicts],
                            "max_severity": _max_severity(verdicts),
                            "blocked": bool(blockers),
                            "feedback": feedback or None,
                            "dropped": run.dropped,  # aspect -> texts with unsourced numbers
                        },
                    )
            block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": json.dumps(_for_model(result), ensure_ascii=False),
            }
            if is_error:
                block["is_error"] = True
            results_content.append(block)

        # text blocks go AFTER every tool_result block of the user turn (API ordering rule)
        for text in feedback_texts:
            results_content.append({"type": "text", "text": text})
        if attempts >= cfg.max_attempts and not budget_exhausted_told:
            budget_exhausted_told = True
            results_content.append(
                {
                    "type": "text",
                    "text": f"Attempt budget reached ({attempts}/{cfg.max_attempts} "
                    f"{_ATTEMPT_NAMES}). Do not simulate again; write the final JSON answer "
                    "now from the results you already have.",
                }
            )
        messages.append({"role": "user", "content": results_content})

    yield ev("error", {"kind": "max_turns", "detail": f"exceeded {cfg.max_turns} API turns"})
