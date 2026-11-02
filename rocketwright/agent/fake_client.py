"""Scripted stand-in for anthropic.AsyncAnthropic, shared by tests and `scripts/run_scenario.py
--dummy`. No network, no API key.

A script is a list of items; each item is either a prebuilt `anthropic.types.Message` or a
callable `(messages_history) -> Message` that can look at the tool results sent so far (used to
compose a final answer whose numbers really come from tool results).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from anthropic.types import Message, TextBlock, ThinkingBlock, ToolUseBlock, Usage

__all__ = [
    "DEMO_DESIGNS",
    "DEMO_REQUIREMENTS",
    "FakeAnthropicClient",
    "FakeStream",
    "ScriptItem",
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


class _FakeMessages:
    def __init__(self, script: list[ScriptItem], calls: list[dict[str, Any]]) -> None:
        self._script = list(script)
        self._index = 0
        self.calls = calls

    def stream(self, **kwargs: Any) -> FakeStream:
        self.calls.append(kwargs)
        if self._index >= len(self._script):
            raise RuntimeError("fake script exhausted: the loop made more calls than scripted")
        item = self._script[self._index]
        self._index += 1
        message = item(list(kwargs.get("messages", []))) if callable(item) else item
        return FakeStream(message)


class FakeAnthropicClient:
    """Duck-types the `messages.stream` surface used by rocketwright.agent.loop."""

    def __init__(self, script: list[ScriptItem]) -> None:
        self.calls: list[dict[str, Any]] = []
        self.messages = _FakeMessages(script, self.calls)


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
        "target_altitude_m": 25,
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
    "root_chord_m": 0.12,
    "tip_chord_m": 0.06,
    "span_m": 0.07,
    "sweep_m": 0.03,
    "thickness_m": 0.003,
}

# The FIRST design of every tier is meant to fail so the demo shows "read the failure reason,
# fix the cause"; the following ones pass. Bottle/amateur are judged by the dummy physics until
# phase 3; commercial/heavy by the real multistage model.
#
# Commercial numbers came from scripts/tune_demo_design.py (real physics, scenario env):
#   * attempt 1: Electron-class, 9 x rutherford + 2 500 kg upper stage -> perigee ~290 km,
#     fails "perigee below target 400 km" (under-fuelled upper stage, too little burn time).
#   * attempt 2: +1 000 kg upper-stage propellant, 10 engines, re-tuned pitch program
#     (25.5 s / 7.95 deg sits inside the +-0.5 s / +-0.2 deg passing window) -> ~475 x 670 km.
#   * attempt 3: slightly lighter first stage, later/larger kick (37.5 s / 13.55 deg) -> ~440 x
#     540 km, a more circular insertion.
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
    "motor_id": "dummy-J700",
    "dry_mass_kg": 1.5,
    "payload_mass_kg": 1.0,
    "parachute_diameter_m": 1.2,
    "deploy_delay_s": 5.0,
}

DEMO_DESIGNS: dict[str, list[dict[str, Any]]] = {
    "bottle": [
        {  # fails: apogee short of the 25 m target (dummy)
            "tier": "bottle",
            "bottle_volume_m3": 0.0015,
            "water_fill_frac": 0.4,
            "initial_gauge_pressure_pa": 500000,
            "nozzle_diameter_m": 0.022,
            "dry_mass_kg": 0.12,
            "payload_mass_kg": 0.06,
            "has_fins": True,
            "has_parachute": True,
            "parachute_diameter_m": 0.4,
        },
        {
            "tier": "bottle",
            "bottle_volume_m3": 0.002,
            "water_fill_frac": 0.35,
            "initial_gauge_pressure_pa": 600000,
            "nozzle_diameter_m": 0.022,
            "dry_mass_kg": 0.14,
            "payload_mass_kg": 0.06,
            "has_fins": True,
            "has_parachute": True,
            "parachute_diameter_m": 0.5,
        },
    ],
    "amateur": [
        {**_AMATEUR_BASE, "parachute_diameter_m": 0.6},  # fails: descent too fast (dummy)
        _AMATEUR_BASE,
        {
            "tier": "amateur",
            "body_diameter_m": 0.066,
            "body_length_m": 1.1,
            "nose_shape": "ogive",
            "nose_length_m": 0.2,
            "fins": {**_FINS, "span_m": 0.09},
            "motor_id": "dummy-J700",
            "dry_mass_kg": 1.4,
            "payload_mass_kg": 1.0,
            "parachute_diameter_m": 1.1,
            "deploy_delay_s": 6.0,
        },
    ],
    "commercial": [
        _commercial(9250, 9, 2500, 12.0, 4.0),  # fails: perigee ~290 km < 400 km
        _commercial(9250, 10, 3500, 25.5, 7.95),
        _commercial(9000, 10, 3500, 37.5, 13.55),
    ],
    "heavy": [
        # Catalog ids only; not tuned (no heavy demo scenario yet).
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
            "boosters": [{"booster_id": "gem_63", "count": 4}],
            "fairing_mass_kg": 2500,
            "payload_mass_kg": 5000,
            "pitch_start_s": 14,
            "initial_pitch_deg": 5,
        },
    ],
}


def _final_from_results(tier: str, designs: list[dict[str, Any]], sim_ids: list[str]):
    """Script item that composes the final JSON from the simulate_design results in history.
    Only passing designs are reported (CLAUDE.md section 1); if none passed, all attempts are
    listed with passed=false so the user still sees what was tried."""

    def build(history: list[dict[str, Any]]) -> Message:
        results = tool_results_from_history(history)
        out_designs = []
        for design, sim_id in zip(designs, sim_ids, strict=True):
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
            out_designs.append(
                {
                    "design": design,
                    "metrics": metrics,
                    "passed": bool(sim.get("success")),
                    "cost_jpy": cost,
                    "success_rate": None,
                    "sources": {**{k: sim_id for k in metrics}, "cost_jpy": sim_id},
                    "explanation": explanation,
                }
            )
        passing = [d for d in out_designs if d["passed"]]
        n_failed = len(out_designs) - len(passing)
        physics = "real multistage physics" if tier in ("commercial", "heavy") else "dummy physics"
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


def build_demo_script(
    tier: str, requirement_text: str, env: dict[str, Any], seed: int | None
) -> list[ScriptItem]:
    """classify -> search_catalog -> simulate_design (first attempt, fails) -> simulate_design
    x(N-1) in one turn (corrected designs) -> final JSON."""
    requirement = {**DEMO_REQUIREMENTS[tier], "text": requirement_text}
    designs = DEMO_DESIGNS[tier]
    sim_ids = [f"toolu_sim_{i + 1}" for i in range(len(designs))]

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

    return [
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
                    "toolu_search", "search_catalog", {"tier": tier, "query": None, "kind": "all"}
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
                *[simulate(sim_id, d) for sim_id, d in zip(sim_ids[1:], designs[1:], strict=True)],
            ],
            stop_reason="tool_use",
        ),
        _final_from_results(tier, designs, sim_ids),
    ]
