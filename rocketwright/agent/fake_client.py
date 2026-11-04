"""Scripted stand-in for anthropic.AsyncAnthropic, shared by tests and `scripts/run_scenario.py
--dummy`. No network, no API key.

A script is a list of items; each item is either a prebuilt `anthropic.types.Message` or a
callable `(messages_history) -> Message` that can look at the tool results sent so far (used to
compose a final answer whose numbers really come from tool results).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NamedTuple

from anthropic.types import Message, TextBlock, ThinkingBlock, ToolUseBlock, Usage

__all__ = [
    "CHAIN_TIERS",
    "DEFAULT_STORY",
    "DEMO_ATTEMPT_TOOL",
    "DEMO_PASSING_INDEX",
    "DEMO_REQUIREMENTS",
    "DEMO_STORIES",
    "DEMO_TUNE",
    "DEMO_VARIANTS",
    "DemoScript",
    "DemoStory",
    "FakeAnthropicClient",
    "FakeParsedMessage",
    "FakeStream",
    "ReviewScriptItem",
    "ScriptItem",
    "attempt_outcome",
    "build_demo_reviews",
    "build_demo_script",
    "demo_designs",
    "make_message",
    "text_block",
    "thinking_block",
    "tool_inputs_from_history",
    "tool_results_from_history",
    "tool_use_block",
]

ScriptItem = Message | Callable[[list[dict[str, Any]]], Message]

# --------------------------------------------------------------------------- block builders


def text_block(text: str) -> TextBlock:
    return TextBlock(type="text", text=text)


def thinking_block(text: str) -> ThinkingBlock:
    return ThinkingBlock(type="thinking", thinking=text, signature="fake-signature")


def tool_use_block(tool_use_id: str, name: str, tool_input: dict[str, Any]) -> ToolUseBlock:
    return ToolUseBlock(type="tool_use", id=tool_use_id, name=name, input=tool_input)


def make_message(blocks: list[Any], stop_reason: str = "end_turn") -> Message:
    return Message(
        id="msg_fake",
        type="message",
        role="assistant",
        model="claude-opus-5-5",
        content=blocks,
        stop_reason=stop_reason,  # type: ignore[arg-type]
        stop_sequence=None,
        usage=Usage(input_tokens=1, output_tokens=1),
    )


# --------------------------------------------------------------------------- fake client


class FakeStream:
    """Mimics the async context manager returned by `client.messages.stream(...)`."""

    def __init__(self, message: Message) -> None:
        self._message = message

    async def __aenter__(self) -> FakeStream:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def get_final_message(self) -> Message:
        return self._message


class FakeParsedMessage:
    """Mimics the `ParsedMessage` returned by `client.messages.parse(...)` (structured output):
    `parsed_output` is the validated model, `content` holds the same JSON as a text block."""

    def __init__(self, parsed_output: Any) -> None:
        self.parsed_output = parsed_output
        self.content = [text_block(parsed_output.model_dump_json())]
        self.stop_reason = "end_turn"


# One scripted reviewer answer: a verdict (model or dict), an exception to raise from the fake
# API, or a callable receiving the `parse` kwargs (to cite numbers from the request itself).
ReviewScriptItem = Any
_REVIEW_HEADER_RE = re.compile(r"^Review aspect: (\w+)\n\nCandidate source_id: (\S+)", re.DOTALL)


class _FakeMessages:
    def __init__(
        self,
        script: list[ScriptItem],
        calls: list[dict[str, Any]],
        reviews: list[dict[str, ReviewScriptItem]] | None = None,
        parse_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        self._script = list(script)
        self._index = 0
        self.calls = calls
        # reviews[i][aspect] answers the i-th distinct candidate reviewed; missing -> "ok"
        self._reviews = list(reviews or [])
        self._review_ids: list[str] = []
        self.parse_calls = parse_calls if parse_calls is not None else []

    def stream(self, **kwargs: Any) -> FakeStream:
        self.calls.append(kwargs)
        if self._index >= len(self._script):
            raise RuntimeError("fake script exhausted: the loop made more calls than scripted")
        item = self._script[self._index]
        self._index += 1
        message = item(list(kwargs.get("messages", []))) if callable(item) else item
        return FakeStream(message)

    async def parse(self, **kwargs: Any) -> FakeParsedMessage:
        """Structured-output call used by the reviewers (rocketwright.agent.review)."""
        from rocketwright.agent.review import ReviewVerdict

        self.parse_calls.append(kwargs)
        content = kwargs.get("messages", [{}])[0].get("content", "")
        m = _REVIEW_HEADER_RE.match(content if isinstance(content, str) else "")
        aspect, source_id = (m.group(1), m.group(2)) if m else ("unknown", "unknown")
        if source_id not in self._review_ids:
            self._review_ids.append(source_id)
        index = self._review_ids.index(source_id)
        item = self._reviews[index].get(aspect) if index < len(self._reviews) else None
        if item is None:
            item = {"aspect": aspect, "severity": "ok", "findings": [], "suggested_changes": []}
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            item = item(kwargs)
        verdict = item if isinstance(item, ReviewVerdict) else ReviewVerdict.model_validate(item)
        return FakeParsedMessage(verdict)


class FakeAnthropicClient:
    """Duck-types the `messages.stream` and `messages.parse` surfaces used by
    rocketwright.agent.loop / review. `reviews` scripts the reviewer answers (see
    _FakeMessages); when omitted, a script built with `build_demo_script(..., reviews=True)`
    supplies them, else every reviewer answers "ok"."""

    def __init__(
        self, script: list[ScriptItem], reviews: list[dict[str, ReviewScriptItem]] | None = None
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.parse_calls: list[dict[str, Any]] = []
        if reviews is None:
            reviews = getattr(script, "reviews", None)
        self.messages = _FakeMessages(script, self.calls, reviews, self.parse_calls)


def tool_results_from_history(history: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """tool_use_id -> parsed tool result, from every user message in the history."""
    out: dict[str, dict[str, Any]] = {}
    for msg in history:
        if msg.get("role") != "user" or not isinstance(msg.get("content"), list):
            continue
        for block in msg["content"]:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                try:
                    out[block["tool_use_id"]] = json.loads(block["content"])
                except (TypeError, ValueError):
                    out[block["tool_use_id"]] = {"raw": block.get("content")}
    return out


# --------------------------------------------------------------------------- demo stories

DEMO_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "bottle": {
        "goal_kind": "altitude",
        "target_altitude_m": 30,
        "target_apogee_m": None,
        "payload_mass_kg": 0.06,
        "budget_jpy": 3000,
        "recovery_required": True,
        "tier_override": None,
        "text": "",
    },
    "amateur": {
        "goal_kind": "altitude",
        "target_altitude_m": 2000,
        "target_apogee_m": None,
        "payload_mass_kg": 1.0,
        "budget_jpy": 50000,
        "recovery_required": True,
        "tier_override": None,
        "text": "",
    },
    "commercial": {
        "goal_kind": "orbit",
        "target_altitude_m": 400000,
        "target_apogee_m": None,
        "payload_mass_kg": 150,
        "budget_jpy": 2.0e9,
        "recovery_required": False,
        "tier_override": None,
        "text": "",
    },
    "heavy": {
        "goal_kind": "orbit",
        "target_altitude_m": 500000,
        "target_apogee_m": None,
        "payload_mass_kg": 5000,
        "budget_jpy": 2.0e10,
        "recovery_required": False,
        "tier_override": None,
        "text": "",
    },
}

# scenarios/demo_model_rocket.yaml: 200 g to 500 m for 20,000 JPY, flown without a certification
_MODEL_ROCKET_REQUIREMENT: dict[str, Any] = {
    **DEMO_REQUIREMENTS["amateur"],
    "target_altitude_m": 500,
    "payload_mass_kg": 0.2,
    "budget_jpy": 20000,
}

# Chain-story steps (bottle / amateur). Each step looks at the design in effect and either asks
# design_stage for ONE stage (the most upstream stage that has to change; the tool redoes every
# stage after it by its default rules) or is skipped with a note:
#   ("avoid_coupler",)          body needs joined tubes -> the stage that decides the tube
#                               (mount when the motor fits more than one mount, else body_tube)
#   ("reduce_margin",)          over-stable build -> fins (the passing planform nearest 2-3 cal)
#   ("no_certification",)       high-power motor -> motor (the best passing low-power one)
#   ("prefer_part", stage, id)  the user named a part -> that stage
#   ("pressure_headroom",)      bottle: the lowest passing pressure (headroom below the cap)
ChainStep = tuple[str, ...]


@dataclass(frozen=True)
class DemoStory:
    """One scripted demo. `chain` stories (bottle / amateur) run classify -> derive (+ the
    nearest real kit as context) -> auto_design -> design_stage revisions (`steps`) ->
    design_from_parts -> run_dispersion -> final; the others are the reference-seeded stories
    of the orbital tiers (find_reference_designs seed -> simulate_design variants)."""

    name: str
    tier: str
    requirement: dict[str, Any]
    chain: bool
    steps: tuple[ChainStep, ...] = ()


DEMO_STORIES: dict[str, DemoStory] = {
    "bottle": DemoStory(
        "bottle",
        "bottle",
        DEMO_REQUIREMENTS["bottle"],
        True,
        (("prefer_part", "bottle", "pet_bottle_1p5l"), ("pressure_headroom",)),
    ),
    "amateur": DemoStory(
        "amateur",
        "amateur",
        DEMO_REQUIREMENTS["amateur"],
        True,
        (("avoid_coupler",), ("reduce_margin",)),
    ),
    "model_rocket": DemoStory(
        "model_rocket",
        "amateur",
        _MODEL_ROCKET_REQUIREMENT,
        True,
        (("no_certification",), ("avoid_coupler",)),
    ),
    "commercial": DemoStory("commercial", "commercial", DEMO_REQUIREMENTS["commercial"], False),
    "heavy": DemoStory("heavy", "heavy", DEMO_REQUIREMENTS["heavy"], False),
}
DEFAULT_STORY: dict[str, str] = {t: t for t in ("bottle", "amateur", "commercial", "heavy")}
CHAIN_TIERS: tuple[str, ...] = ("bottle", "amateur")

# Numbers of the chain stories as the tools returned them on 2026-11-03 (scenario envs/seeds;
# the script reads every value from the tool results at run time, nothing below is typed in):
#   * amateur (1 kg / 2 km / 50,000 JPY): auto_design -> J435WS (24 motors enumerated, 13
#     simulated, 1 passed) in the LOC 54 mm tube, 1,363 mm body = 2 tubes + coupler, 5.5 cal
#     (over-stable warning), Level 2 warning, 1,871 m, 33,930 JPY, pass. avoid_coupler ->
#     design_stage(mount): the 98 mm single tube (motor_mount_38mm_98) fails (948 m), so the top
#     candidate (the baseline mount) is kept. reduce_margin -> design_stage(fins): the passing
#     planform nearest 2-3 cal is the fully swept one (5.3 cal, still over-stable: the long
#     body sets the margin). design_from_parts confirms it; run_dispersion on it.
#   * bottle (30 m / egg / 3,000 JPY): auto_design -> 1.0 L bottle at 500 kPa (cap-limited),
#     29.9 m, pass. prefer_part -> design_stage(bottle): the user's 1.5 L bottle passes (364 kPa
#     solved). pressure_headroom -> design_stage(pressure): the lowest passing pressure, 350 kPa
#     (29.1 m). design_from_parts; run_dispersion.
#   * model_rocket (200 g / 500 m / 20,000 JPY, no certification): auto_design -> F32T (57 Ns,
#     no high-power warning) in an Estes BT-60, 2 tubes + coupler, 502 m, 9,340 JPY, pass.
#     no_certification: skipped (low-power motor). avoid_coupler -> design_stage(body_tube): the
#     single-tube BT-80 fails (301 m) and BT-55 is not rated for the F motor: BT-60 kept.
#     design_from_parts confirms the baseline; run_dispersion.

# --------------------------------------------------------------------------- reference stories

# The orbital tiers keep the reference-seeded story (CLAUDE.md section 8):
#   classify -> derive_requirements + search_catalog -> find_reference_designs (seed=true) ->
#   attempt 1 on the seed -> corrected / cheaper variants (attempts 2..N, one turn) ->
#   run_dispersion on the first passing attempt -> final JSON citing the reference id and the
#   derive tool id. The seed is read from the find_reference_designs tool result at run time;
#   DEMO_VARIANTS maps that seed design to each simulate_design attempt.
#   * commercial: seed = Electron scaled to 150 kg / 400 km (4 + 1 Rutherford, 4,625 + 1,025 kg
#     propellant), pitch re-tuned by tune=true (~3.5 s) -> 399.5 km circular, 37 kg margin,
#     5.1 億円, passes: attempt 0. Attempt 1 adopts it as is (Monte-Carlo 0.94). Attempt 2 tries
#     a cheaper vehicle by cutting the first stage to 4,000 kg -> perigee -1.9 km, fails.
#     Attempt 3 cuts the upper stage instead (900 kg) -> 400 x 498 km, 34 kg margin, 5.0 億円,
#     pass.
#   * heavy (no scenario file): seed = Atlas V 551 scaled to 5 t / 500 km keeps the five
#     AJ-60A boosters on a quarter-size core -> max-Q 115 kPa and an early upper-stage burnout,
#     fails (tune=false: tuning does not rescue it and costs seconds). Attempt 2: two GEM-63
#     boosters, 280 t RD-180 core, 25 t RL10 upper stage, 30 s / 12 deg kick -> 500 x 1,378 km,
#     pass (Monte-Carlo 0.97).

DesignVariant = Callable[[dict[str, Any]], dict[str, Any]]

# The attempt tool of the reference-seeded stories (bottle/amateur attempts are auto_design and
# design_from_parts, see the chain stories).
DEMO_ATTEMPT_TOOL: dict[str, str] = {"commercial": "simulate_design", "heavy": "simulate_design"}


def _with_stage(design: dict[str, Any], index: int, **changes: Any) -> dict[str, Any]:
    stages = [dict(st) for st in design["stages"]]
    stages[index] = {**stages[index], **changes}
    return {**design, "stages": stages}


_HEAVY_FIX: dict[str, Any] = {
    "tier": "heavy",
    "stages": [
        {
            "propellant_mass_kg": 280000,
            "structural_fraction": 0.07,
            "engine_id": "rd_180",
            "engine_count": 1,
        },
        {
            "propellant_mass_kg": 25000,
            "structural_fraction": 0.09,
            "engine_id": "rl10",
            "engine_count": 1,
        },
    ],
    "boosters": [{"booster_id": "gem_63", "count": 2}],
    "fairing_mass_kg": 2500,
    "payload_mass_kg": 5000,
    "pitch_start_s": 30,
    "initial_pitch_deg": 12,
}

# attempt i (1-based) = DEMO_VARIANTS[tier][i - 1](seed design from find_reference_designs)
DEMO_VARIANTS: dict[str, list[DesignVariant]] = {
    "commercial": [
        lambda seed: dict(seed),
        lambda seed: _with_stage(seed, 0, propellant_mass_kg=4000.0),
        lambda seed: _with_stage(seed, 1, propellant_mass_kg=900.0),
    ],
    "heavy": [
        lambda seed: dict(seed),
        lambda seed: dict(_HEAVY_FIX),
    ],
}

# Index of the demo design meant to pass first: reference stories index DEMO_VARIANTS (it gets
# the run_dispersion call); the chain tiers index demo_designs() (0 = the auto_design baseline).
DEMO_PASSING_INDEX: dict[str, int] = {"bottle": 0, "amateur": 0, "commercial": 0, "heavy": 1}

# find_reference_designs `tune` per tier (orbit goals only; heavy stays untuned: see above)
DEMO_TUNE: dict[str, bool] = {"bottle": False, "amateur": False, "commercial": True, "heavy": False}

# Narration of the simulate turns (thinking blocks), per tier: (attempt 1, attempts 2..N).
_DEMO_NARRATION: dict[str, tuple[str, str]] = {
    "commercial": (
        "The seed scaled from Electron (pitch program re-tuned for 400 km) reached orbit in its "
        "own simulation (attempt 0). Attempt 1 adopts it as is under the scenario seed.",
        "Attempt 1 passed with margin. To use the budget better, attempt 2 cuts the first-stage "
        "propellant; attempt 3 cuts the upper stage instead. The simulation decides which is "
        "cheaper AND still closes the orbit.",
    ),
    "heavy": (
        "The seed scaled from Atlas V 551 keeps all five AJ-60A boosters on a quarter-size "
        "core: attempt 1 simulates it as is.",
        "Attempt 1 failed: max-Q far above the limit (too much booster thrust for the core) "
        "and the upper stage burned out early. Fix the causes: two GEM-63 boosters, a larger "
        "core and a 25 t upper stage with a later kick (attempt 2).",
    ),
}

_DEMO_STORY: dict[str, str] = {
    "commercial": (
        "The re-tuned seed reached orbit (attempt 0) and was adopted as attempt 1. Attempt 2 "
        "cut the first stage to save cost and failed on perigee (the upper stage could not "
        "close the orbit); attempt 3 cut the upper stage instead and passed cheaper. The "
        "simulated delta-v losses exceed the formula's loss allowance, which is why the "
        "derived liftoff mass is optimistic."
    ),
    "heavy": (
        "The seed kept the reference's five boosters on a much smaller core and failed on "
        "max-Q and an early upper-stage burnout (attempt 1); attempt 2 fixed both causes and "
        "passed."
    ),
}

_DISPERSION_ID = "toolu_disp_1"
_REFERENCE_ID = "toolu_ref"
_DERIVE_ID = "toolu_derive"
_AUTO_ID = "toolu_auto"
_PARTS_ID = "toolu_parts"


def _stage_id(i: int) -> str:
    return f"toolu_stage_{i + 1}"


def tool_inputs_from_history(history: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """tool_use_id -> tool input, from every assistant message in the history (blocks are SDK
    objects or dicts)."""
    out: dict[str, dict[str, Any]] = {}
    for msg in history:
        if msg.get("role") != "assistant" or not isinstance(msg.get("content"), list):
            continue
        for block in msg["content"]:
            if isinstance(block, dict):
                btype, bid, binput = block.get("type"), block.get("id"), block.get("input")
            else:
                btype = getattr(block, "type", None)
                bid = getattr(block, "id", None)
                binput = getattr(block, "input", None)
            if btype == "tool_use" and bid and isinstance(binput, dict):
                out[str(bid)] = binput
    return out


def _seed_from_history(history: list[dict[str, Any]]) -> dict[str, Any]:
    """The seed design the reference-story attempts start from (find_reference_designs)."""
    ref = tool_results_from_history(history).get(_REFERENCE_ID) or {}
    value = (ref.get("seed") or {}).get("design")
    if not isinstance(value, dict):
        raise RuntimeError(
            "demo script: find_reference_designs returned no seed design "
            f"(note={ref.get('note')!r}, error={ref.get('error')!r})"
        )
    return value


def attempt_outcome(tool_name: str, result: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    """(sim result, design) of an attempt tool result: the result itself and its tuned design
    for simulate_design; the embedded `sim` ({} when a buildability error stopped it) and the
    resolved `design` for design_from_parts / auto_design."""
    if tool_name in ("design_from_parts", "auto_design"):
        sim = result.get("sim")
        return (sim if isinstance(sim, dict) else {}), result.get("design")
    return result, result.get("tuned_design")


def demo_designs(
    tier: str, env: dict[str, Any] | None = None, requirement_text: str = ""
) -> list[dict[str, Any]]:
    """Concrete demo designs of `tier` for tests. Chain tiers: [the auto_design baseline
    (design_chain, real parts)]; reference tiers: the designs the script simulates, attempt
    order (seed from find_reference_designs, then DEMO_VARIANTS; commercial costs a few
    seconds, tune=true)."""
    from rocketwright.agent.tools import execute_tool

    requirement = {**DEMO_REQUIREMENTS[tier], "text": requirement_text}
    if tier in CHAIN_TIERS:
        out = execute_tool(
            "auto_design",
            {"tier": tier, "requirement": requirement, "env": env or None},
            _AUTO_ID,
        )
        if not isinstance(out.get("design"), dict):
            raise RuntimeError(f"auto_design for {tier!r} returned no design: {out}")
        return [out["design"]]
    out = execute_tool(
        "find_reference_designs",
        {
            "requirement": requirement,
            "tier": tier,
            "k": 3,
            "seed": True,
            "tune": DEMO_TUNE[tier],
            "env": env or None,
        },
        _REFERENCE_ID,
    )
    seed = (out.get("seed") or {}).get("design")
    if not isinstance(seed, dict):
        raise RuntimeError(f"no seed for tier {tier!r}: {out.get('note') or out}")
    return [variant(seed) for variant in DEMO_VARIANTS[tier]]


def _derived_phrase(derive: dict[str, Any], tier: str) -> str:
    """Two derived numbers quoted verbatim-enough from the derive_requirements result (the
    provenance check rounds result values to the digits written)."""
    q = {
        item.get("key"): item
        for item in derive.get("quantities", [])
        if isinstance(item, dict) and item.get("key")
    }

    def val(key: str) -> float | None:
        v = (q.get(key) or {}).get("value")
        return float(v) if isinstance(v, (int, float)) else None

    if tier in ("commercial", "heavy"):
        dv, m0 = val("required_dv_mps"), val("liftoff_mass_kg")
        if dv is None or m0 is None:
            return "required delta-v and liftoff mass (see the tool result)"
        return f"required delta-v {dv:,.0f} m/s and a liftoff mass of about {m0:,.0f} kg"
    if tier == "amateur":
        impulse, chute = val("total_impulse_ns"), val("parachute_diameter_m")
        letter = (q.get("motor_class_impulse_min_ns") or {}).get("annotation") or "?"
        if impulse is None or chute is None:
            return "total impulse and parachute diameter (see the tool result)"
        return (
            f"total impulse {impulse:,.0f} Ns (motor class {letter}) and a parachute of "
            f"{chute:.2f} m"
        )
    pressure, water = val("gauge_pressure_pa"), val("water_mass_kg")
    if pressure is None or water is None:
        return "gauge pressure and water mass (see the tool result)"
    return f"gauge pressure {pressure / 1e3:.0f} kPa with {water:.3g} kg of water"


def _design_row(
    sim_id: str,
    tool_name: str,
    result: dict[str, Any],
    tool_input: dict[str, Any] | None,
    disp_id: str | None,
    results: dict[str, dict[str, Any]],
    label: str = "",
) -> dict[str, Any]:
    """One final-answer design row from an attempt result: design, metrics and cost from the
    sim, every metric cited with `sim_id`, the dispersion success rate (when `disp_id`) cited
    with the run_dispersion id. Part-space rows also carry the build and the bill rows."""
    sim, design = attempt_outcome(tool_name, result)
    if design is None:
        design = (tool_input or {}).get("design")
    metrics = sim.get("metrics", {})
    cost = sim.get("cost_jpy")
    key = "perigee_m" if "perigee_m" in metrics else "apogee_m"
    if sim.get("success"):
        verdict = "passed"
    elif sim:
        verdict = "failed: " + "; ".join(sim.get("failure_reasons", []))
    else:
        errors = [
            it.get("message", "")
            for it in result.get("issues", [])
            if isinstance(it, dict) and it.get("severity") == "error"
        ]
        verdict = "not simulated, buildability error: " + "; ".join(errors)
    explanation = f"{label}{key} = {metrics.get(key)} m, cost {cost} JPY ({verdict})"
    part_space = isinstance(result.get("build"), dict)
    if part_space:
        parts = [v for k, v in result["build"].items() if k.endswith("_id") and isinstance(v, str)]
        explanation += "; parts: " + ", ".join(parts)
    sources = {**{k: sim_id for k in metrics}, "cost_jpy": sim_id}
    success_rate = None
    disp = results.get(disp_id, {}) if disp_id else {}
    if isinstance(disp.get("success_rate"), (int, float)):
        success_rate = disp["success_rate"]
        sources["success_rate"] = disp_id
        explanation += (
            f"; Monte-Carlo success_rate = {success_rate} over n = {disp.get('n')} "
            "perturbed flights"
        )
    row: dict[str, Any] = {
        "design": design,
        "metrics": metrics,
        "passed": bool(sim.get("success")),
        "cost_jpy": cost,
        "success_rate": success_rate,
        "sources": sources,
        "explanation": explanation,
    }
    if part_space:
        row["build"] = result.get("build")
        bill = result.get("bill") or {}
        row["bill"] = [
            {k: r.get(k) for k in ("part_id", "qty", "mass_kg", "price_jpy")}
            for r in bill.get("parts", [])
            if isinstance(r, dict)
        ]
    return row


def _final_from_results(
    tier: str,
    sim_ids: list[str],
    dispersion_ids: dict[int, str] | None = None,
):
    """Reference stories: script item composing the final JSON from the tool results in
    history (designs from the simulate_design inputs or their tuned design, metrics/cost from
    the results). Only passing designs are reported (CLAUDE.md section 1); if none passed, all
    attempts are listed with passed=false. The final cites `reference_id` and `derived_targets`
    and quotes two derived numbers, so the provenance check must find them in the results."""
    dispersion_ids = dispersion_ids or {}

    def build(history: list[dict[str, Any]]) -> Message:
        results = tool_results_from_history(history)
        inputs = tool_inputs_from_history(history)
        out_designs = [
            _design_row(
                sim_id,
                DEMO_ATTEMPT_TOOL[tier],
                results.get(sim_id, {}),
                inputs.get(sim_id),
                dispersion_ids.get(i),
                results,
            )
            for i, sim_id in enumerate(sim_ids)
        ]
        passing = [d for d in out_designs if d["passed"]]
        n_failed = len(out_designs) - len(passing)
        ref = results.get(_REFERENCE_ID) or {}
        seed = ref.get("seed") or {}
        reference_id = seed.get("reference_id")
        ref_name = next(
            (r.get("name") for r in ref.get("references", []) if r.get("id") == reference_id),
            reference_id,
        )
        derive = results.get(_DERIVE_ID) or {}
        final = {
            "reference_id": reference_id,
            "derived_targets": _DERIVE_ID if derive else None,
            "designs": passing or out_designs,
            "summary": (
                f"Tier {tier}. Targets derived by formula ({_DERIVE_ID}): "
                f"{_derived_phrase(derive, tier)}. Design seeded from {ref_name} "
                f"({reference_id}, {_REFERENCE_ID}), scaled by the tool's provisional rules. "
                f"{_DEMO_STORY[tier]} {len(passing)} of {len(out_designs)} simulated designs "
                f"passed (real multistage physics); failed attempts: {n_failed}."
            ),
            "open_questions": [],
        }
        return make_message([text_block(json.dumps(final, ensure_ascii=False))])

    return build


class DemoScript(list):  # type: ignore[type-arg]
    """A script list that also carries scripted reviewer answers (`reviews`), picked up by
    `FakeAnthropicClient(script)` when no explicit `reviews=` is given."""

    reviews: list[dict[str, ReviewScriptItem]] | None = None


def _sim_result_from_review_request(kwargs: dict[str, Any]) -> dict[str, Any]:
    """The simulation result embedded in a reviewer request (review.reviewer_request)."""
    content = kwargs["messages"][0]["content"]
    marker = "Simulation result (tool output, cite its numbers only):\n"
    tail = content.split(marker, 1)[1] if marker in content else "{}"
    try:
        return json.loads(tail.split("\n\nAdditional context:", 1)[0])
    except ValueError:
        return {}


def _demo_cost_major(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Demo cost verdict: cites the candidate's own cost_jpy (a number from the tool result),
    states the threshold in words (no invented numbers; see REVIEWER_PROMPTS)."""
    cost = _sim_result_from_review_request(kwargs).get("cost_jpy")
    cited = f"cost_jpy {cost:.0f}" if isinstance(cost, (int, float)) else "cost_jpy"
    return {
        "aspect": "cost",
        "severity": "major",
        "findings": [
            f"{cited} leaves only a thin margin under the budget; price drift of the "
            "propulsion part could push it over"
        ],
        "suggested_changes": ["move to a cheaper propulsion option or drop optional parts"],
    }


def build_demo_reviews() -> list[dict[str, ReviewScriptItem]]:
    """Scripted reviewer answers for the demo: the first candidate reviewed gets a "major"
    cost finding, every later candidate (and every other aspect) is "ok"."""
    return [{"cost": _demo_cost_major}]


def _classify_turn(tier: str, requirement: dict[str, Any]) -> Message:
    return make_message(
        [
            thinking_block(f"Normalising the request; it looks like the {tier} tier."),
            tool_use_block("toolu_classify", "classify_requirement", {"requirement": requirement}),
        ],
        stop_reason="tool_use",
    )


def build_demo_script(
    tier: str,
    requirement_text: str,
    env: dict[str, Any],
    seed: int | None,
    *,
    reviews: bool = False,
    dispersion: bool = True,
    story: str | None = None,
) -> list[ScriptItem]:
    """The scripted demo of `story` (DEMO_STORIES; None = the tier's default story).

    Chain stories (bottle / amateur): classify -> derive_requirements + find_reference_designs
    (seed=false: the nearest real kit, context only) -> auto_design (attempt 1, the code's
    baseline through the fixed stage order) -> design_stage revisions, each starting at the
    most upstream stage that must change -> design_from_parts on the final build (attempt 2)
    -> run_dispersion -> final JSON. Every choice is read from the tool results at run time.

    Reference stories (commercial / heavy): classify -> derive + search_catalog ->
    find_reference_designs (seed=true) -> simulate_design attempts (DEMO_VARIANTS) ->
    run_dispersion -> final.

    With `reviews=True` the returned DemoScript also carries `build_demo_reviews()` for the
    fake client's reviewer calls; `dispersion=False` drops the run_dispersion turn
    (loop-mechanics tests)."""
    name = story or DEFAULT_STORY[tier]
    if name not in DEMO_STORIES:
        raise ValueError(f"unknown demo story {name!r}; known: {sorted(DEMO_STORIES)}")
    spec = DEMO_STORIES[name]
    if spec.tier != tier:
        raise ValueError(f"demo story {name!r} is a {spec.tier} story, not {tier}")
    requirement = {**spec.requirement, "text": requirement_text}
    if spec.chain:
        script = _chain_script(spec, requirement, env, seed, dispersion=dispersion)
    else:
        script = _reference_script(tier, requirement, env, seed, dispersion=dispersion)
    if reviews:
        script.reviews = build_demo_reviews()
    return script


def _reference_script(
    tier: str,
    requirement: dict[str, Any],
    env: dict[str, Any],
    seed: int | None,
    *,
    dispersion: bool,
) -> DemoScript:
    variants = DEMO_VARIANTS[tier]
    sim_ids = [f"toolu_sim_{i + 1}" for i in range(len(variants))]
    dispersion_index = DEMO_PASSING_INDEX[tier]
    dispersion_ids = {dispersion_index: _DISPERSION_ID} if dispersion else {}
    narration_first, narration_rest = _DEMO_NARRATION[tier]

    def simulate(sim_id: str, candidate: dict[str, Any]) -> ToolUseBlock:
        return tool_use_block(
            sim_id,
            "simulate_design",
            {
                "design": candidate,
                "env": env,
                "seed": seed,
                "requirement": requirement,
                "tune_pitch": False,  # the seed's pitch program is already tuned (DEMO_TUNE)
            },
        )

    def first_attempt(history: list[dict[str, Any]]) -> Message:
        candidate = variants[0](_seed_from_history(history))
        return make_message(
            [thinking_block(narration_first), simulate(sim_ids[0], candidate)],
            stop_reason="tool_use",
        )

    def later_attempts(history: list[dict[str, Any]]) -> Message:
        seed_value = _seed_from_history(history)
        return make_message(
            [
                thinking_block(narration_rest),
                *[
                    simulate(sim_id, variant(seed_value))
                    for sim_id, variant in zip(sim_ids[1:], variants[1:], strict=True)
                ],
            ],
            stop_reason="tool_use",
        )

    def dispersion_turn(history: list[dict[str, Any]]) -> Message:
        design = variants[dispersion_index](_seed_from_history(history))
        return _dispersion_message(
            design, env, seed, requirement, "A design passed. Running the Monte-Carlo "
        )

    return DemoScript(
        [
            _classify_turn(tier, requirement),
            make_message(
                [
                    text_block(
                        "Deriving the quantitative targets by formula and listing the catalog "
                        "for this tier."
                    ),
                    tool_use_block(
                        _DERIVE_ID,
                        "derive_requirements",
                        {
                            "requirement": requirement,
                            "tier": tier,
                            "launch_latitude_deg": env.get("launch_latitude_deg"),
                        },
                    ),
                    tool_use_block(
                        "toolu_search",
                        "search_catalog",
                        {"tier": tier, "query": None, "kind": "all"},
                    ),
                ],
                stop_reason="tool_use",
            ),
            make_message(
                [
                    thinking_block(
                        "Looking for the nearest real vehicle and seeding the design from it "
                        "(scaled by the tool's rules), with its own simulation as attempt 0."
                    ),
                    tool_use_block(
                        _REFERENCE_ID,
                        "find_reference_designs",
                        {
                            "requirement": requirement,
                            "tier": tier,
                            "k": 3,
                            "seed": True,
                            "tune": DEMO_TUNE[tier],
                            "env": env,
                        },
                    ),
                ],
                stop_reason="tool_use",
            ),
            first_attempt,
            later_attempts,
            *([dispersion_turn] if dispersion else []),
            _final_from_results(tier, sim_ids, dispersion_ids),
        ]
    )


def _dispersion_message(
    design: dict[str, Any],
    env: dict[str, Any],
    seed: int | None,
    requirement: dict[str, Any],
    lead: str,
) -> Message:
    return make_message(
        [
            thinking_block(
                lead + "dispersion on it (n=100, same seed) to quote a success rate instead "
                "of guessing one."
            ),
            tool_use_block(
                _DISPERSION_ID,
                "run_dispersion",
                {
                    "design": design,
                    "env": env,
                    "n": 100,
                    "seed": seed if seed is not None else 0,
                    "requirement": requirement,
                    "cost_jpy": None,  # geometric designs: the cost.py estimate
                },
            ),
        ],
        stop_reason="tool_use",
    )


# --------------------------------------------------------------------------- chain stories


def _issue_codes(issues: Any) -> set[str]:
    """Issue codes of a build: auto_design / design_from_parts give dicts, design_stage
    candidates "severity:code" strings."""
    out: set[str] = set()
    for it in issues or []:
        if isinstance(it, dict) and it.get("code"):
            out.add(str(it["code"]))
        elif isinstance(it, str):
            out.add(it.split(":", 1)[-1])
    return out


def _cert_level(issues: Any) -> str | None:
    """'Level 1' / 'Level 2' from a high_power_motor issue message, else None."""
    for it in issues or []:
        if isinstance(it, dict) and it.get("code") == "high_power_motor":
            m = re.search(r"Level [12]", str(it.get("message", "")))
            return m.group(0) if m else "Level 1/2"
    return None


def _funnel_text(res: dict[str, Any]) -> str:
    return (
        f"{res.get('enumerated')} enumerated, {res.get('compatible')} compatible, "
        f"{res.get('simulated')} simulated, {res.get('passed')} passed"
    )


def _cand_text(c: dict[str, Any]) -> str:
    return f"{c.get('option')}: {c.get('why')}"


def _margin(c: dict[str, Any]) -> float | None:
    v = (c.get("metrics") or {}).get("stability_margin_cal")
    return float(v) if isinstance(v, (int, float)) else None


def _clean(c: dict[str, Any]) -> bool:
    return not any(str(i).startswith("error:") for i in c.get("issues", []))


class _ChainState:
    """The design in effect while the story revises the auto_design baseline: the option per
    stage (auto_design's trace, then the adopted candidates; the stages after a changed one are
    dropped, i.e. back to their default rules) and the full build / issues / metrics."""

    def __init__(self, auto: dict[str, Any]) -> None:
        self.trace: list[dict[str, Any]] = list(auto.get("trace") or [])
        self.order: list[str] = [t["stage"] for t in self.trace]
        self.options: dict[str, str] = {t["stage"]: str(t["chosen"]) for t in self.trace}
        self.build: dict[str, Any] = dict(auto.get("build") or {})
        self.issues: set[str] = _issue_codes(auto.get("issues"))
        self.metrics: dict[str, Any] = dict((auto.get("sim") or {}).get("metrics") or {})
        self.changed: list[str] = []

    def alternatives(self, stage: str) -> list[dict[str, Any]]:
        t = next((t for t in self.trace if t["stage"] == stage), None)
        return list((t or {}).get("alternatives") or [])

    def chosen_for(self, stage: str) -> list[dict[str, str]]:
        """The upstream decisions in effect, as design_stage `chosen` (never a downstream one)."""
        idx = self.order.index(stage)
        return [
            {"stage": s, "value": self.options[s]} for s in self.order[:idx] if s in self.options
        ]

    def adopt(self, stage: str, cand: dict[str, Any] | None) -> bool:
        """Adopt `cand` for `stage`; False (nothing changes) when it is the option in effect."""
        if cand is None or self.options.get(stage) == cand.get("option"):
            return False
        idx = self.order.index(stage)
        self.options = {s: v for s, v in self.options.items() if self.order.index(s) < idx}
        self.options[stage] = str(cand["option"])
        self.build = dict(cand.get("build") or self.build)
        self.issues = _issue_codes(cand.get("issues"))
        self.metrics = dict(cand.get("metrics") or {})
        self.changed.append(stage)
        return True


# A step: need(state, auto) -> (stage, reason, k) or (None, skip note);
# pick(state, stage result) -> (candidate or None, note).
_StepNeed = tuple[str | None, str, int | None]


def _need_avoid_coupler(st: _ChainState, step: ChainStep) -> _StepNeed:
    if "body_length_stock" not in st.issues:
        return None, "The body is one stock tube: no coupler to avoid.", None
    # The tube is limited by the mount (each mount centres the motor in particular tubes): with
    # more than one mount for this motor the mount stage is the most upstream one that can
    # change the tube.
    stage = "mount" if st.alternatives("mount") else "body_tube"
    tube = st.build.get("body_tube_id")
    return (
        stage,
        f"ユーザーは継ぎ手 (coupler) を避けたい: the {tube} body needs joined tubes (build "
        f"warning body_length_stock). A wider single stock tube is decided by the {stage} "
        f"stage (it fixes which tubes fit), so the revision starts there; every stage after "
        "it is redone by its default rules.",
        None,
    )


def _pick_avoid_coupler(st: _ChainState, res: dict[str, Any]) -> tuple[Any, str]:
    cands = res.get("candidates") or []
    single = [c for c in cands if _clean(c) and "warning:body_length_stock" not in c["issues"]]
    passing = [c for c in single if c["passed"]]
    if passing:
        c = passing[0]
        return c, f"Adopted {_cand_text(c)} (one stock tube, no coupler)."
    if not cands:
        return None, "No candidate was returned: the baseline stays."
    top = cands[0]
    tried = "; ".join(
        f"{c['option']} ({(c.get('build') or {}).get('body_tube_id')}) fails: {c['why']}"
        for c in single[:2]
    )
    head = f"No single-tube option passes ({tried})." if tried else "No single-tube option."
    return top, (
        f"{head} Taking the top candidate instead, {_cand_text(top)}: the coupler stays, it is "
        "what reaching the target within the budget costs with these parts."
    )


def _need_reduce_margin(st: _ChainState, step: ChainStep) -> _StepNeed:
    if "static_margin_high" not in st.issues:
        return None, "The static margin is within the normal band.", None
    margin = st.metrics.get("stability_margin_cal")
    shown = f" ({margin:.1f} cal)" if isinstance(margin, (int, float)) else ""
    return (
        "fins",
        f"過安定{shown} (build warning static_margin_high): it would weathercock into the "
        "wind. The fins set the margin and are downstream of the settled airframe, so only "
        "the fins stage is ranked (motor, mount, tube, nose and body kept).",
        20,
    )


def _pick_reduce_margin(st: _ChainState, res: dict[str, Any]) -> tuple[Any, str]:
    cands = res.get("candidates") or []
    passing = [(i, c) for i, c in enumerate(cands) if c["passed"] and _margin(c) is not None]
    if not passing:
        return None, "No passing planform with a margin was returned: the fins stay."
    _, best = min(passing, key=lambda ic: (abs((_margin(ic[1]) or 0.0) - 2.5), ic[0]))
    current = st.metrics.get("stability_margin_cal")
    if isinstance(current, (int, float)) and (_margin(best) or 0.0) >= current:
        return None, "No passing planform lowers the margin: the fins stay."
    still = "warning:static_margin_high" in best["issues"]
    return best, (
        f"Adopted {_cand_text(best)}: the passing planform nearest the two-to-three-caliber band"
        + (
            "; still over-stable (the long body needed for the payload bay and the chute sets "
            "the margin, the fins alone cannot bring it into the band)"
            if still
            else ""
        )
        + "."
    )


def _need_no_certification(st: _ChainState, step: ChainStep) -> _StepNeed:
    motor = st.build.get("motor_id")
    if "high_power_motor" not in st.issues:
        return (
            None,
            f"資格なしで飛ばしたい: {motor} carries no high-power warning from the buildability "
            "check, so it is a model-rocket motor flown without a NAR/Tripoli certification.",
            None,
        )
    return (
        "motor",
        f"資格なしで飛ばしたい but {motor} is a high-power motor (build warning): the motor is "
        "the most upstream stage, so the whole design is redone from it.",
        20,
    )


def _pick_no_certification(st: _ChainState, res: dict[str, Any]) -> tuple[Any, str]:
    cands = res.get("candidates") or []
    low = [c for c in cands if c["passed"] and "warning:high_power_motor" not in c["issues"]]
    if low:
        return low[0], f"Adopted {_cand_text(low[0])} (low power, no certification)."
    if not cands:
        return None, "No candidate was returned: the baseline stays."
    return cands[0], (
        f"No low-power motor passes; the top candidate {_cand_text(cands[0])} needs a "
        "certification: tell the user."
    )


def _need_prefer_part(st: _ChainState, step: ChainStep) -> _StepNeed:
    stage, value = step[1], step[2]
    if st.options.get(stage) == value:
        return None, f"The baseline already uses {value}, the part the user named.", None
    return (
        stage,
        f"ユーザーの手元にある部品 {value} (named in the request) differs from the baseline "
        f"{st.options.get(stage)}: the {stage} stage is the most upstream one that changes, "
        "so the revision starts there and every later stage is redone.",
        None,
    )


def _pick_prefer_part(st: _ChainState, res: dict[str, Any], value: str) -> tuple[Any, str]:
    cands = res.get("candidates") or []
    match = next((c for c in cands if c["option"] == value), None)
    if match is not None and match["passed"]:
        return match, f"Adopted {_cand_text(match)} (the user's part)."
    if not cands:
        return None, "No candidate was returned: the baseline stays."
    why = f"fails: {match['why']}" if match is not None else "is not among the candidates"
    return cands[0], f"{value} {why}; taking the top candidate {_cand_text(cands[0])}."


def _need_pressure_headroom(st: _ChainState, step: ChainStep) -> _StepNeed:
    label = next((t["label"] for t in st.trace if t["stage"] == "pressure"), "")
    return (
        "pressure",
        f"安全のため圧力に余裕を: the baseline flew at {label}. For headroom below the bottle "
        "cap the pressure stage is ranked again (bottle, nozzle and fill kept) and the lowest "
        "passing pressure is taken.",
        None,
    )


def _pick_pressure_headroom(st: _ChainState, res: dict[str, Any]) -> tuple[Any, str]:
    passing = [c for c in res.get("candidates") or [] if c["passed"]]
    if not passing:
        return None, "No passing pressure was returned: the pressure stays."
    best = min(passing, key=lambda c: float(c["option"]))
    return best, f"Adopted {_cand_text(best)}: the lowest passing pressure, the most headroom."


def _step_need(st: _ChainState, step: ChainStep) -> _StepNeed:
    return {
        "avoid_coupler": _need_avoid_coupler,
        "reduce_margin": _need_reduce_margin,
        "no_certification": _need_no_certification,
        "prefer_part": _need_prefer_part,
        "pressure_headroom": _need_pressure_headroom,
    }[step[0]](st, step)


def _step_pick(st: _ChainState, step: ChainStep, res: dict[str, Any]) -> tuple[Any, str]:
    if step[0] == "prefer_part":
        return _pick_prefer_part(st, res, step[2])
    return {
        "avoid_coupler": _pick_avoid_coupler,
        "reduce_margin": _pick_reduce_margin,
        "no_certification": _pick_no_certification,
        "pressure_headroom": _pick_pressure_headroom,
    }[step[0]](st, res)


def _auto_narration(auto: dict[str, Any]) -> str:
    """auto_design's baseline per stage (chosen label and funnel), its verdict and warnings."""
    stages = "; ".join(
        f"{t['stage']}: {t['label']} ({t['funnel']['enumerated']} enumerated, "
        f"{t['funnel']['simulated']} simulated, {t['funnel']['passed']} passed)"
        for t in auto.get("trace") or []
    )
    sim = auto.get("sim") or {}
    verdict = (
        "it passes"
        if sim.get("success")
        else "it fails: " + "; ".join(sim.get("failure_reasons") or [])
    )
    text = f"auto_design (code baseline, fixed stage order) -> {stages}. Result: {verdict}."
    warnings = [i.get("message", "") for i in auto.get("issues") or [] if isinstance(i, dict)]
    if warnings:
        text += " Build warnings: " + " / ".join(warnings) + "."
    feas = auto.get("feasibility")
    if isinstance(feas, dict) and feas.get("verdict"):
        text += f" 予算について正直に: {feas['verdict']}."
    return text


class _ChainPlan(NamedTuple):
    """The replayed state of a chain story: the next tool call to make (None = all done) with
    its narration, the notes of every decision so far and the design in effect."""

    state: _ChainState | None
    next_call: tuple[str, str, dict[str, Any]] | None  # (tool_use id, tool name, input)
    narration: list[str]
    notes: list[str]


def _replay_chain(
    spec: DemoStory,
    results: dict[str, dict[str, Any]],
    requirement: dict[str, Any],
    env: dict[str, Any],
    seed: int | None,
    dispersion: bool,
) -> _ChainPlan:
    """Replay the story's decisions from the tool results so far (deterministic: the same
    results give the same picks) and return the next call."""
    auto = results.get(_AUTO_ID)
    if not isinstance(auto, dict) or "error" in auto or not auto.get("build"):
        return _ChainPlan(None, None, [], [])
    st = _ChainState(auto)
    fresh = [_auto_narration(auto)]  # narration since the last consumed result
    notes: list[str] = []
    for i, step in enumerate(spec.steps):
        stage, text, k = _step_need(st, step)
        if stage is None:
            fresh.append(text)
            notes.append(text)
            continue
        res = results.get(_stage_id(i))
        if res is None:
            call = {
                "tier": spec.tier,
                "requirement": requirement,
                "env": env,
                "chosen": st.chosen_for(stage),
                "stage": stage,
                "k": k,
            }
            return _ChainPlan(st, (_stage_id(i), "design_stage", call), [*fresh, text], notes)
        if "error" in res:
            note = f"design_stage({stage}) failed: {res['error']}"
        else:
            cand, pick_note = _step_pick(st, step, res)
            st.adopt(stage, cand)
            note = f"design_stage({stage}) [{_funnel_text(res)}]: {pick_note}"
        fresh = [note]
        notes.append(f"{text} {note}")
    if _PARTS_ID not in results:
        call = {"build": st.build, "env": env, "requirement": requirement, "seed": seed}
        lead = (
            "Confirming the final build with design_from_parts (attempt): "
            + (f"stages revised: {', '.join(st.changed)}" if st.changed else "baseline kept")
            + "."
        )
        return _ChainPlan(st, (_PARTS_ID, "design_from_parts", call), [*fresh, lead], notes)
    if dispersion and _DISPERSION_ID not in results:
        parts = results[_PARTS_ID]
        ok = "error" not in parts and (parts.get("sim") or {}).get("success")
        source = parts if ok else auto
        call = {
            "design": source.get("design"),
            "env": env,
            "n": 100,
            "seed": seed if seed is not None else 0,
            "requirement": requirement,
            # the budget is judged on the parts bill, as in design_from_parts
            "cost_jpy": (source.get("bill") or {}).get("cost_jpy"),
        }
        return _ChainPlan(st, (_DISPERSION_ID, "run_dispersion", call), [], notes)
    return _ChainPlan(st, None, [], notes)


def _chain_final(
    spec: DemoStory, results: dict[str, dict[str, Any]], plan: _ChainPlan
) -> dict[str, Any]:
    """Final JSON of a chain story: the auto_design baseline and the confirmed final build
    (only the final one when the build did not change), metrics and costs cited with their
    tool ids, the dispersion success rate on the design it was run on."""
    auto = results.get(_AUTO_ID) or {}
    parts = results.get(_PARTS_ID) or {}
    disp_input_design = None
    disp = results.get(_DISPERSION_ID)
    rows: list[dict[str, Any]] = []
    parts_ok = bool(parts) and "error" not in parts and isinstance(parts.get("design"), dict)
    if isinstance(disp, dict) and "error" not in disp:
        disp_input_design = (
            parts.get("design")
            if parts_ok and (parts.get("sim") or {}).get("success")
            else auto.get("design")
        )
    same_build = parts_ok and parts.get("build") == auto.get("build")
    if auto.get("design") and not same_build:
        rows.append(
            _design_row(
                _AUTO_ID,
                "auto_design",
                auto,
                None,
                _DISPERSION_ID if disp_input_design == auto.get("design") else None,
                results,
                label="auto_design baseline: ",
            )
        )
    if parts_ok:
        rows.append(
            _design_row(
                _PARTS_ID,
                "design_from_parts",
                parts,
                None,
                _DISPERSION_ID if disp_input_design == parts.get("design") else None,
                results,
                label="final build (design_from_parts): ",
            )
        )
    passing = [r for r in rows if r["passed"]]
    ref = results.get(_REFERENCE_ID) or {}
    refs = ref.get("references") or []
    reference_id = refs[0].get("id") if refs else None
    ref_name = refs[0].get("name") if refs else None
    derive = results.get(_DERIVE_ID) or {}
    trace = auto.get("trace") or []
    motor = next((t for t in trace if t["stage"] in ("motor", "bottle")), None)
    baseline = (
        f"Baseline by auto_design ({_AUTO_ID}) through the fixed stage order "
        + " -> ".join(t["stage"] for t in trace)
        + (
            f"; first stage {motor['stage']}: {motor['label']} ({motor['funnel']['enumerated']} "
            f"enumerated, {motor['funnel']['simulated']} simulated, "
            f"{motor['funnel']['passed']} passed)"
            if motor
            else ""
        )
        + "."
    )
    final_issues = parts.get("issues") if parts_ok else auto.get("issues")
    level = _cert_level(final_issues)
    cautions = []
    if level:
        cautions.append(f"the motor needs a NAR/Tripoli {level} certification (high_power_motor)")
    if "body_length_stock" in _issue_codes(final_issues):
        cautions.append("the body is joined tubes with a coupler (body_length_stock)")
    if "static_margin_high" in _issue_codes(final_issues):
        cautions.append("over-stable (static_margin_high)")
    rate = disp.get("success_rate") if isinstance(disp, dict) else None
    summary = (
        f"Tier {spec.tier}. Targets derived by formula ({_DERIVE_ID}): "
        f"{_derived_phrase(derive, spec.tier)}. {baseline} Revisions, upstream stage first: "
        + (" ".join(plan.notes) if plan.notes else "none")
        + f" Closest real kit (context, not the seed): {ref_name} "
        + f"({reference_id}, {_REFERENCE_ID})."
        + (f" Cautions for the user: {'; '.join(cautions)}." if cautions else "")
        + (
            f" Monte-Carlo success rate {rate} ({_DISPERSION_ID})."
            if isinstance(rate, (int, float))
            else ""
        )
        + f" {len(passing)} of {len(rows)} designs passed (real "
        + ("water" if spec.tier == "bottle" else "solid")
        + " physics)."
    )
    return {
        "reference_id": reference_id,
        "derived_targets": _DERIVE_ID if derive else None,
        "designs": passing or rows,
        "summary": summary,
        "open_questions": [],
    }


def _chain_script(
    spec: DemoStory,
    requirement: dict[str, Any],
    env: dict[str, Any],
    seed: int | None,
    *,
    dispersion: bool,
) -> DemoScript:
    tier = spec.tier

    def driver(history: list[dict[str, Any]]) -> Message:
        results = tool_results_from_history(history)
        plan = _replay_chain(spec, results, requirement, env, seed, dispersion)
        if plan.next_call is None:
            final = _chain_final(spec, results, plan)
            return make_message([text_block(json.dumps(final, ensure_ascii=False))])
        tool_id, name, tool_input = plan.next_call
        blocks: list[Any] = []
        if name == "run_dispersion":
            blocks.append(
                thinking_block(
                    "The final build passed. Running the Monte-Carlo dispersion on it (n=100, "
                    "same seed) to quote a success rate instead of guessing one."
                )
            )
        else:
            blocks.append(
                thinking_block(
                    f"Next: {name}"
                    + (f" at stage {tool_input['stage']}" if name == "design_stage" else "")
                    + ". Upstream stages are settled first; downstream parts are never edited "
                    "before the stage above them is."
                )
            )
            blocks.append(text_block("\n".join(plan.narration)))
        blocks.append(tool_use_block(tool_id, name, tool_input))
        return make_message(blocks, stop_reason="tool_use")

    turns: list[ScriptItem] = [
        _classify_turn(tier, requirement),
        make_message(
            [
                text_block(
                    "Deriving the quantitative targets by formula, and looking up the nearest "
                    "real kits (context: which real kit this is closest to, not a seed)."
                ),
                tool_use_block(
                    _DERIVE_ID,
                    "derive_requirements",
                    {
                        "requirement": requirement,
                        "tier": tier,
                        "launch_latitude_deg": env.get("launch_latitude_deg"),
                    },
                ),
                tool_use_block(
                    _REFERENCE_ID,
                    "find_reference_designs",
                    {
                        "requirement": requirement,
                        "tier": tier,
                        "k": 3,
                        "seed": False,
                        "tune": None,
                        "env": None,
                    },
                ),
            ],
            stop_reason="tool_use",
        ),
        make_message(
            [
                thinking_block(
                    "Baseline first: auto_design walks every stage in the fixed order and adopts "
                    "the best candidate of each (the code enumerates, checks and simulates)."
                ),
                tool_use_block(
                    _AUTO_ID, "auto_design", {"tier": tier, "requirement": requirement, "env": env}
                ),
            ],
            stop_reason="tool_use",
        ),
    ]
    # one driver turn per possible design_stage step, then design_from_parts, dispersion, final
    turns.extend([driver] * (len(spec.steps) + 3))
    return DemoScript(turns)
