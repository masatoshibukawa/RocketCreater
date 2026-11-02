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
from typing import Any

from anthropic.types import Message, TextBlock, ThinkingBlock, ToolUseBlock, Usage

__all__ = [
    "DEMO_PASSING_INDEX",
    "DEMO_REQUIREMENTS",
    "DEMO_TUNE",
    "DEMO_VARIANTS",
    "DemoScript",
    "FakeAnthropicClient",
    "FakeParsedMessage",
    "FakeStream",
    "ReviewScriptItem",
    "ScriptItem",
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


# --------------------------------------------------------------------------- demo script

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

# The demo story of every tier (CLAUDE.md section 8, reference-based workflow):
#   classify -> derive_requirements + search_catalog -> find_reference_designs (seed=true) ->
#   simulate_design on the seed (attempt 1) -> corrected / cheaper variants (attempts 2..N, one
#   turn) -> run_dispersion on the first passing attempt -> final JSON citing the reference id
#   and the derive tool id. The seed design is read from the find_reference_designs tool
#   result at run time, so the script never hard-codes a scaled vehicle; DEMO_VARIANTS maps
#   that seed to each attempt. Every tier is judged by its real physics model (bottle:
#   physics.water, amateur: physics.solid, commercial/heavy: physics.multistage).
#
# Numbers below were checked on 2026-11-02 with the scenario envs/seeds (scripts/run_scenario.py):
#   * bottle: seed = Apte 2 L bottle scaled to 30 m (376 kPa, 0.31 m chute) -> the seed sim
#     passes (32.2 m, 4.8 m/s), attempt 0. Attempt 1 fits it in the 1.5 L bottle the user has
#     -> 29.7 m, pass (Monte-Carlo 0.99). Attempt 2 moves halfway to the 695 kPa the derive
#     formula asks for (500 kPa) -> 36.5 m, fails +/-10 %: the simulation wins over the formula
#     (its provisional energy efficiency is pessimistic for this bottle). Attempt 3: 400 kPa
#     -> 31.1 m, pass.
#   * amateur: seed = Estes Alpha III scaled to 1 kg / 2 km (dummy_J420, 60 mm, 196 g dry,
#     1.79 m chute) -> 2208 m, fails +/-10 % (about a tenth hot). Attempt 1 simulates it as is.
#     Attempt 2 fixes the cause (too little drag and mass for the J motor): 66 mm airframe,
#     500 g dry mass, 1.0 m chute -> 1935 m, 5.4 m/s, 3.2 cal, pass (Monte-Carlo 0.94).
#     Attempt 3: same with a 1.2 m chute -> 4.5 m/s, pass.
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
    "bottle": [
        lambda seed: {**seed, "bottle_volume_m3": 0.0015},
        lambda seed: {**seed, "bottle_volume_m3": 0.0015, "initial_gauge_pressure_pa": 500000},
        lambda seed: {**seed, "bottle_volume_m3": 0.0015, "initial_gauge_pressure_pa": 400000},
    ],
    "amateur": [
        lambda seed: dict(seed),
        lambda seed: {
            **seed,
            "body_diameter_m": 0.066,
            "dry_mass_kg": 0.5,
            "parachute_diameter_m": 1.0,
        },
        lambda seed: {
            **seed,
            "body_diameter_m": 0.066,
            "dry_mass_kg": 0.5,
            "parachute_diameter_m": 1.2,
        },
    ],
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

# 0-based index (into DEMO_VARIANTS[tier]) of the first attempt meant to pass: it gets the
# run_dispersion call and its success rate is quoted in the final answer.
DEMO_PASSING_INDEX: dict[str, int] = {"bottle": 0, "amateur": 1, "commercial": 0, "heavy": 1}

# find_reference_designs `tune` per tier (orbit goals only; heavy stays untuned: see above)
DEMO_TUNE: dict[str, bool] = {"bottle": False, "amateur": False, "commercial": True, "heavy": False}

# Narration of the simulate turns (thinking blocks), per tier: (attempt 1, attempts 2..N).
_DEMO_NARRATION: dict[str, tuple[str, str]] = {
    "bottle": (
        "The seed scaled from the Apte 2 L bottle passed its own simulation (attempt 0). The "
        "user has a 1.5 L bottle, so attempt 1 keeps the seed's pressure and parachute in the "
        "1.5 L bottle.",
        "Attempt 1 passed. The derived gauge pressure (energy formula) is far above the seed's, "
        "so attempt 2 moves halfway towards it to see which is right; attempt 3 is a small "
        "pressure increase on the seed for margin.",
    ),
    "amateur": (
        "The seed scaled from the Estes Alpha III missed the +/-10 % apogee window (about a "
        "tenth too high). Attempt 1 simulates it as is with the scenario seed to confirm.",
        "Attempt 1 failed on apogee (too hot). The cause: the scaled airframe is lighter and "
        "slimmer than the derived 1.8 kg liftoff estimate assumed, so the J motor overshoots. "
        "Fix: a 66 mm airframe with a 500 g dry mass and a 1.0 m chute (attempt 2), and the "
        "same with a 1.2 m chute for a softer landing (attempt 3).",
    ),
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

_DISPERSION_ID = "toolu_disp_1"
_REFERENCE_ID = "toolu_ref"
_DERIVE_ID = "toolu_derive"


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


def _seed_design_from_history(history: list[dict[str, Any]]) -> dict[str, Any]:
    ref = tool_results_from_history(history).get(_REFERENCE_ID) or {}
    seed = ref.get("seed") or {}
    design = seed.get("design")
    if not isinstance(design, dict):
        raise RuntimeError(
            "demo script: find_reference_designs returned no seed design "
            f"(note={ref.get('note')!r}, error={ref.get('error')!r})"
        )
    return design


def demo_designs(
    tier: str, env: dict[str, Any] | None = None, requirement_text: str = ""
) -> list[dict[str, Any]]:
    """The designs the demo script simulates for `tier`, attempt order, computed the way the
    script does (seed from the find_reference_designs tool, then DEMO_VARIANTS). For tests that
    need a concrete demo design; commercial costs a few seconds (tune=true)."""
    from rocketwright.agent.tools import execute_tool

    requirement = {**DEMO_REQUIREMENTS[tier], "text": requirement_text}
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
        raise RuntimeError(f"no seed design for tier {tier!r}: {out.get('note') or out}")
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


_DEMO_STORY: dict[str, str] = {
    "bottle": (
        "The seed passed as attempt 0; attempt 1 fitted it into the user's 1.5 L bottle and "
        "passed. Attempt 2 moved towards the derived pressure and overshot the apogee window: "
        "the simulation is trusted over the formula, whose provisional energy-efficiency "
        "constant lumps nozzle and drag losses and is pessimistic for this bottle. Attempt 3 "
        "passed with a slightly higher pressure."
    ),
    "amateur": (
        "The seed flew about a tenth too high (attempt 1 failed on apogee): the simulation is "
        "trusted over the derived impulse, whose drag factor assumes a heavier, draggier "
        "airframe than the scaled one. Attempts 2 and 3 widened the airframe and added dry "
        "mass (the cause), and passed."
    ),
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


def _final_from_results(
    tier: str,
    sim_ids: list[str],
    dispersion_ids: dict[int, str] | None = None,
):
    """Script item that composes the final JSON from the tool results in history: the designs
    come from the simulate_design tool_use inputs, the metrics/cost from their results. Only
    passing designs are reported (CLAUDE.md section 1); if none passed, all attempts are
    listed with passed=false so the user still sees what was tried. `dispersion_ids` maps an
    attempt index to the run_dispersion tool_use id whose success_rate it quotes. The final
    cites `reference_id` (find_reference_designs) and `derived_targets` (derive_requirements)
    and quotes two derived numbers, so the provenance check must find them in the results."""
    dispersion_ids = dispersion_ids or {}

    def build(history: list[dict[str, Any]]) -> Message:
        results = tool_results_from_history(history)
        inputs = tool_inputs_from_history(history)
        out_designs = []
        for i, sim_id in enumerate(sim_ids):
            sim = results.get(sim_id, {})
            design = sim.get("tuned_design") or (inputs.get(sim_id) or {}).get("design")
            metrics = sim.get("metrics", {})
            cost = sim.get("cost_jpy")
            key = "perigee_m" if "perigee_m" in metrics else "apogee_m"
            verdict = (
                "passed"
                if sim.get("success")
                else "failed: " + "; ".join(sim.get("failure_reasons", []))
            )
            explanation = f"{key} = {metrics.get(key)} m, cost {cost} JPY ({verdict})"
            sources = {**{k: sim_id for k in metrics}, "cost_jpy": sim_id}
            success_rate = None
            disp_id = dispersion_ids.get(i)
            disp = results.get(disp_id, {}) if disp_id else {}
            if isinstance(disp.get("success_rate"), (int, float)):
                success_rate = disp["success_rate"]
                sources["success_rate"] = disp_id
                explanation += (
                    f"; Monte-Carlo success_rate = {success_rate} over n = {disp.get('n')} "
                    f"perturbed flights"
                )
            out_designs.append(
                {
                    "design": design,
                    "metrics": metrics,
                    "passed": bool(sim.get("success")),
                    "cost_jpy": cost,
                    "success_rate": success_rate,
                    "sources": sources,
                    "explanation": explanation,
                }
            )
        passing = [d for d in out_designs if d["passed"]]
        n_failed = len(out_designs) - len(passing)
        model = {"bottle": "water", "amateur": "solid"}.get(tier, "multistage")
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
                f"passed (real {model} physics); failed attempts: {n_failed}."
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
    """The simulate_design result embedded in a reviewer request (review.reviewer_request)."""
    content = kwargs["messages"][0]["content"]
    marker = "simulate_design result (tool output, cite its numbers only):\n"
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


def build_demo_script(
    tier: str,
    requirement_text: str,
    env: dict[str, Any],
    seed: int | None,
    *,
    reviews: bool = False,
    dispersion: bool = True,
) -> list[ScriptItem]:
    """classify -> derive_requirements + search_catalog (one turn) -> find_reference_designs
    (seed=true) -> simulate_design on the seed-based attempt 1 -> simulate_design x(N-1) in one
    turn (DEMO_VARIANTS) -> run_dispersion on the first passing attempt (DEMO_PASSING_INDEX,
    n=100) -> final JSON quoting its success_rate, the reference id and the derive tool id.
    With `reviews=True` the returned DemoScript also carries `build_demo_reviews()` for the
    fake client's reviewer calls; `dispersion=False` drops the run_dispersion turn
    (loop-mechanics tests)."""
    requirement = {**DEMO_REQUIREMENTS[tier], "text": requirement_text}
    variants = DEMO_VARIANTS[tier]
    sim_ids = [f"toolu_sim_{i + 1}" for i in range(len(variants))]
    dispersion_index = DEMO_PASSING_INDEX[tier]
    dispersion_ids = {dispersion_index: _DISPERSION_ID} if dispersion else {}
    narration_first, narration_rest = _DEMO_NARRATION[tier]

    def simulate(sim_id: str, design: dict[str, Any]):
        return tool_use_block(
            sim_id,
            "simulate_design",
            {
                "design": design,
                "env": env,
                "seed": seed,
                "requirement": requirement,
                "tune_pitch": False,  # the seed's pitch program is already tuned (DEMO_TUNE)
            },
        )

    def first_attempt(history: list[dict[str, Any]]) -> Message:
        design = variants[0](_seed_design_from_history(history))
        return make_message(
            [thinking_block(narration_first), simulate(sim_ids[0], design)],
            stop_reason="tool_use",
        )

    def later_attempts(history: list[dict[str, Any]]) -> Message:
        seed_design = _seed_design_from_history(history)
        return make_message(
            [
                thinking_block(narration_rest),
                *[
                    simulate(sim_id, variant(seed_design))
                    for sim_id, variant in zip(sim_ids[1:], variants[1:], strict=True)
                ],
            ],
            stop_reason="tool_use",
        )

    def dispersion_turn(history: list[dict[str, Any]]) -> Message:
        design = variants[dispersion_index](_seed_design_from_history(history))
        return make_message(
            [
                thinking_block(
                    "A design passed. Running the Monte-Carlo dispersion on it (n=100, same "
                    "seed) to quote a success rate instead of guessing one."
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
                    },
                ),
            ],
            stop_reason="tool_use",
        )

    script = DemoScript(
        [
            make_message(
                [
                    thinking_block(f"Normalising the request; it looks like the {tier} tier."),
                    tool_use_block(
                        "toolu_classify", "classify_requirement", {"requirement": requirement}
                    ),
                ],
                stop_reason="tool_use",
            ),
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
    if reviews:
        script.reviews = build_demo_reviews()
    return script
