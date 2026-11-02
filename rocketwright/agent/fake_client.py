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
    "DEMO_DESIGNS",
    "DEMO_REQUIREMENTS",
    "DemoScript",
    "FakeAnthropicClient",
    "FakeParsedMessage",
    "FakeStream",
    "ReviewScriptItem",
    "ScriptItem",
    "build_demo_reviews",
    "build_demo_script",
    "make_message",
    "text_block",
    "thinking_block",
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

_FINS = {
    "count": 4,
    "root_chord_m": 0.10,
    "tip_chord_m": 0.05,
    "span_m": 0.035,
    "sweep_m": 0.03,
    "thickness_m": 0.003,
}

# The FIRST design of every tier is meant to fail so the demo shows "read the failure reason,
# fix the cause"; the following ones pass. Every tier is judged by its real physics model
# (bottle: physics.water, amateur: physics.solid, commercial/heavy: physics.multistage).
#
# Bottle/amateur numbers came from scripts/tune_suborbital_demo.py (real physics, scenario env):
#   * bottle attempt 1: 1.5 L, 40 % water, 500 kPa, no parachute -> apogee ~36 m and a 20 m/s
#     ballistic descent; fails "add a parachute" / "recovery required" / apogee > 33 m.
#   * bottle attempt 2: 0.5 m parachute, 1.5 L at 400 kPa -> ~30 m, 3.1 m/s -> pass.
#   * bottle attempt 3: 0.5 m parachute, 2 L at 350 kPa -> ~29.5 m, 3.3 m/s -> pass.
#   (re-tuned for water.DEFAULT_CD 0.8 / AIR_IMPULSE_EFFICIENCY 0.25, calibrated 2026-11-02)
#   * amateur attempt 1: dummy_I200 on a 1 kg payload with a 0.6 m chute -> apogee ~1.1 km and a
#     9.5 m/s descent; fails "larger parachute" and "apogee below target".
#   * amateur attempt 2: dummy_J420 in a 60 mm airframe with a 1.2 m chute -> ~1.94 km, 5.4 m/s.
#   * amateur attempt 3: dummy_J420 in a heavier 54 mm airframe -> ~1.99 km, 5.7 m/s, 46 kJPY.
#   (re-tuned for solid.DEFAULT_CD 0.75, calibrated 2026-11-02; a 66 mm airframe no longer
#   reaches 1.8 km on a J420 with this Cd)
#
# Commercial numbers came from scripts/tune_demo_design.py (real physics, scenario env, Earth
# rotation on as the orbit-goal dispatch does; coast-and-circularize insertion):
#   * attempt 1: Electron-class, 9 x rutherford + 1 500 kg upper stage -> the upper stage burns
#     out before the insertion cutoff (apogee reached but the orbit never closes), fails
#     "perigee below target 400 km" (under-fuelled upper stage).
#   * attempt 2: +1 000 kg upper-stage propellant, re-tuned kick (14 s / 5.0 deg, inside a
#     +-2 s / +-0.5 deg passing window) -> 400 km circularized, Monte-Carlo success 0.87.
#   * attempt 3: 10 engines and a 3 500 kg upper stage with a later/larger kick (39 s / 14 deg)
#     -> 400 km circularized with more propellant margin, Monte-Carlo success 0.78.
# A merlin_1d first stage is too strong for a 150 kg payload under the 2e9 JPY budget (liftoff
# TWR > 3 and max-Q far above 60 kPa), hence the Rutherford-class vehicle.
_COMMERCIAL_STAGE_TEMPLATE = {"structural_fraction": 0.08, "engine_id": "rutherford"}


def _commercial(
    prop1_kg: float, engines1: int, prop2_kg: float, pitch_start_s: float, pitch_deg: float
) -> dict[str, Any]:
    return {
        "tier": "commercial",
        "stages": [
            {
                **_COMMERCIAL_STAGE_TEMPLATE,
                "propellant_mass_kg": prop1_kg,
                "engine_count": engines1,
            },
            {
                "propellant_mass_kg": prop2_kg,
                "structural_fraction": 0.10,
                "engine_id": "rutherford",
                "engine_count": 1,
            },
        ],
        "boosters": [],
        "fairing_mass_kg": 50,
        "payload_mass_kg": 150,
        "pitch_start_s": pitch_start_s,
        "initial_pitch_deg": pitch_deg,
    }


_AMATEUR_BASE = {
    "tier": "amateur",
    "body_diameter_m": 0.054,
    "body_length_m": 0.9,
    "nose_shape": "ogive",
    "nose_length_m": 0.15,
    "fins": _FINS,
    "motor_id": "dummy_J420",
    "dry_mass_kg": 1.6,
    "payload_mass_kg": 1.0,
    "parachute_diameter_m": 1.2,
    "deploy_delay_s": 1.0,
}

_BOTTLE_BASE = {
    "tier": "bottle",
    "bottle_volume_m3": 0.0015,
    "water_fill_frac": 0.4,
    "initial_gauge_pressure_pa": 400000,
    "nozzle_diameter_m": 0.022,
    "dry_mass_kg": 0.12,
    "payload_mass_kg": 0.06,
    "has_fins": True,
    "has_parachute": True,
    "parachute_diameter_m": 0.5,
}

DEMO_DESIGNS: dict[str, list[dict[str, Any]]] = {
    "bottle": [
        {  # fails: no parachute (20 m/s ballistic descent) and 500 kPa overshoots 30 m
            **_BOTTLE_BASE,
            "initial_gauge_pressure_pa": 500000,
            "has_parachute": False,
            "parachute_diameter_m": None,
        },
        _BOTTLE_BASE,
        {
            **_BOTTLE_BASE,
            "bottle_volume_m3": 0.002,
            "dry_mass_kg": 0.14,
            "initial_gauge_pressure_pa": 350000,
        },
    ],
    "amateur": [
        {  # fails: motor too small for 2 km (~1.1 km) and 0.6 m chute descends at 9.5 m/s
            **_AMATEUR_BASE,
            "motor_id": "dummy_I200",
            "dry_mass_kg": 1.0,
            "parachute_diameter_m": 0.6,
        },
        {
            **_AMATEUR_BASE,
            "body_diameter_m": 0.060,
            "body_length_m": 1.0,
            "nose_length_m": 0.18,
            "fins": {**_FINS, "span_m": 0.045},
            "dry_mass_kg": 1.3,
        },
        _AMATEUR_BASE,
    ],
    "commercial": [
        _commercial(9250, 9, 1500, 12.0, 4.0),  # fails: upper stage burns out, no orbit
        _commercial(9250, 9, 2500, 14.0, 5.0),
        _commercial(9250, 10, 3500, 39.0, 14.0),
    ],
    "heavy": [
        # Catalog ids only (no heavy demo scenario yet). Attempt 1: a 10 t Centaur-class upper
        # stage burns out before the insertion cutoff -> fails "perigee below target 500 km";
        # attempt 2: 25 t upper stage with a 30 s / 12 deg kick -> 500 x ~1,360 km with ~7.8 t
        # of propellant left, Monte-Carlo success 0.98 (checked 2026-11-02, rotation on).
        {
            "tier": "heavy",
            "stages": [
                {
                    "propellant_mass_kg": 280000,
                    "structural_fraction": 0.07,
                    "engine_id": "rd_180",
                    "engine_count": 1,
                },
                {
                    "propellant_mass_kg": 10000,
                    "structural_fraction": 0.09,
                    "engine_id": "rl10",
                    "engine_count": 1,
                },
            ],
            "boosters": [{"booster_id": "gem_63", "count": 2}],
            "fairing_mass_kg": 2500,
            "payload_mass_kg": 5000,
            "pitch_start_s": 12,
            "initial_pitch_deg": 4,
        },
        {
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
        },
    ],
}


def _final_from_results(
    tier: str,
    designs: list[dict[str, Any]],
    sim_ids: list[str],
    dispersion_ids: dict[int, str] | None = None,
):
    """Script item that composes the final JSON from the simulate_design results in history.
    Only passing designs are reported (CLAUDE.md section 1); if none passed, all attempts are
    listed with passed=false so the user still sees what was tried. `dispersion_ids` maps a
    design index to the run_dispersion tool_use id whose success_rate it quotes."""
    dispersion_ids = dispersion_ids or {}

    def build(history: list[dict[str, Any]]) -> Message:
        results = tool_results_from_history(history)
        out_designs = []
        for i, (design, sim_id) in enumerate(zip(designs, sim_ids, strict=True)):
            sim = results.get(sim_id, {})
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
        physics = f"real {model} physics"
        final = {
            "designs": passing or out_designs,
            "summary": (
                f"Tier {tier}: the first attempt failed, its failure reason was read and the "
                f"cause fixed; {len(passing)} of {len(out_designs)} designs passed "
                f"({physics}). Attempts that failed: {n_failed}."
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
    """classify -> search_catalog -> simulate_design (first attempt, fails) -> simulate_design
    x(N-1) in one turn (corrected designs) -> run_dispersion on the first passing design
    (index 1, n=100) -> final JSON quoting its success_rate. With `reviews=True` the returned
    DemoScript also carries `build_demo_reviews()` for the fake client's reviewer calls;
    `dispersion=False` drops the run_dispersion turn (loop-mechanics tests)."""
    requirement = {**DEMO_REQUIREMENTS[tier], "text": requirement_text}
    designs = DEMO_DESIGNS[tier]
    sim_ids = [f"toolu_sim_{i + 1}" for i in range(len(designs))]
    dispersion_index = 1  # the first design meant to pass (see DEMO_DESIGNS)
    dispersion_ids = {dispersion_index: "toolu_disp_1"} if dispersion else {}

    def simulate(sim_id: str, design: dict[str, Any]):
        return tool_use_block(
            sim_id,
            "simulate_design",
            {
                "design": design,
                "env": env,
                "seed": seed,
                "requirement": requirement,
                "tune_pitch": False,  # the demo uses pre-tuned numbers (see DEMO_DESIGNS)
            },
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
                    text_block("Looking up the catalog for this tier."),
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
                    thinking_block("Proposing an initial design and simulating it."),
                    simulate(sim_ids[0], designs[0]),
                ],
                stop_reason="tool_use",
            ),
            make_message(
                [
                    thinking_block(
                        "The first attempt failed. Reading failure_reasons and fixing the cause "
                        "(not the symptom): adjusting the design variable it points at, then "
                        "simulating the corrected candidates."
                    ),
                    *[
                        simulate(sim_id, d)
                        for sim_id, d in zip(sim_ids[1:], designs[1:], strict=True)
                    ],
                ],
                stop_reason="tool_use",
            ),
            *(
                [
                    make_message(
                        [
                            thinking_block(
                                "A corrected design passed. Running the Monte-Carlo dispersion "
                                "on it (n=100, same seed) to quote a success rate instead of "
                                "guessing one."
                            ),
                            tool_use_block(
                                dispersion_ids[dispersion_index],
                                "run_dispersion",
                                {
                                    "design": designs[dispersion_index],
                                    "env": env,
                                    "n": 100,
                                    "seed": seed if seed is not None else 0,
                                    "requirement": requirement,
                                },
                            ),
                        ],
                        stop_reason="tool_use",
                    )
                ]
                if dispersion
                else []
            ),
            _final_from_results(tier, designs, sim_ids, dispersion_ids),
        ]
    )
    if reviews:
        script.reviews = build_demo_reviews()
    return script
