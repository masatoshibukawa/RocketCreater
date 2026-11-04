"""Search the fixed demo egg mission. Run with python -m rocketwright.bottle_search --help."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from anthropic import APIError

from rocketwright.bottle_assembly import Workshop, assembly, catalog
from rocketwright.bottle_candidates import (
    CONFIRMATION_SEED,
    ENV,
    FILL_PCT,
    NOZZLE_MM,
    PRESSURE_KPA,
    REQUIREMENT,
    SELECTION_SEED,
    component_screen,
    design_at,
    flight_tool,
    starts,
)
from rocketwright.bottle_packet import write_packet
from rocketwright.drawing import render_side_view_svg
from rocketwright.physics.water import PASS_THRESHOLDS

SHELF = {
    "component": ("low", "nozzle and canopy", "thrust/weight and steady descent", "feasibility"),
    "flight": (
        "middle",
        "assembled airframe",
        "simulate_design",
        "rail exit, altitude and descent",
    ),
    "screen": ("high", "mission in wind and pressure variation", "run_dispersion", "pass fraction"),
    "confirm": ("high", "locked design", "independent run_dispersion", "pass fraction"),
}
SAMPLES = {"screen": (24, SELECTION_SEED), "confirm": (64, CONFIRMATION_SEED)}
PASS_RATE = 0.80  # Predeclared experimental proxy, not a measured recovery reliability.
TARGET = REQUIREMENT.target_altitude_m


@dataclass(frozen=True)
class Action:
    method: str
    start: str
    nozzle_mm: int
    pressure_kpa: int
    fill_pct: int
    variant: str = ""

    @property
    def id(self):
        base = f"{self.method}/{self.start}/{self.nozzle_mm}/{self.pressure_kpa}/{self.fill_pct}"
        return f"{base}/{self.variant}" if self.variant else base

    def change(self, **kwargs):
        return Action(**(asdict(self) | kwargs))


class Search:
    def __init__(self, mode="mixed", workshop=None):
        records = starts()
        keys = {"mixed": records, "references": ("D02", "D01"), "new": ("new",)}[mode]
        self.records = {key: records[key] for key in keys}
        self.history = []
        self.results = {}
        self.workshop = workshop
        if workshop is not None:
            workshop.check_ids(records)

    def design(self, action):
        design = design_at(
            self.records[action.start], action.nozzle_mm, action.pressure_kpa, action.fill_pct
        )
        if self.workshop is None:
            return design
        plan = self.plan(action, design)
        return design.model_copy(
            update={
                "dry_mass_kg": plan["dry_mass_g"] / 1000,
                "axial_drag_coefficient": plan["axial_cd"],
            }
        )

    def plan(self, action, design):
        return assembly(design, action.start, action.nozzle_mm, action.variant, self.workshop)

    def options(self):
        options = {}
        if any(a.method == "confirm" for a in self.results):
            return options

        def offer(action):
            if self.workshop is not None:
                if (
                    action.pressure_kpa > self.workshop.pressure_ceiling_kpa
                    or action.nozzle_mm not in self.workshop.nozzle_options_mm
                ):
                    return
                kit = catalog()[0]["variants"][action.variant]
                if {kit["fin"], kit["pad"]} & self.workshop.unavailable:
                    return
            if action not in self.results:
                options[action.id] = action

        for key, record in self.records.items():
            nozzle = record["initial_nozzle_mm"]
            if self.workshop is None:
                offer(Action("component", key, nozzle, 300, 35))
                continue
            initial = [p for p in PRESSURE_KPA if p <= self.workshop.pressure_ceiling_kpa]
            if initial:
                if nozzle not in self.workshop.nozzle_options_mm:
                    nozzle = self.workshop.nozzle_options_mm[0]
                for v in ("carton_plain", "carton_damped", "pp_damped"):
                    offer(
                        Action(
                            "component",
                            key,
                            nozzle,
                            min(initial, key=lambda p: abs(p - 300)),
                            35,
                            v,
                        )
                    )
        for action, result in self.results.items():
            if action.method == "component" and result["eligible"]:
                offer(action.change(method="flight"))
            if action.method == "component" and self.workshop is not None:
                if not result["checks"]["mount_settles"] and action.variant == "carton_plain":
                    offer(action.change(variant="carton_damped"))
                if not result["checks"]["static_restoring_dry_and_wet"]:
                    variants = {"carton_damped": "carton_wide", "pp_damped": "pp_wide"}
                    if action.variant in variants:
                        offer(action.change(variant=variants[action.variant]))
                    if action.fill_pct > min(FILL_PCT):
                        offer(action.change(fill_pct=min(FILL_PCT)))
            if action.method == "screen" and result["success_rate"] >= PASS_RATE:
                offer(action.change(method="confirm"))
            if action.method != "flight":
                continue
            if result["success"]:
                offer(action.change(method="screen"))
            apogee = result["apogee_m"]
            # Limit reproposals to tested or adjacent regimes; nearest-to-target estimate
            # is only a suggestion. The ODE must validate every new operating point.
            direction = 1 if apogee < TARGET else -1
            pressures = [p for p in PRESSURE_KPA if (p - action.pressure_kpa) * direction > 0]
            if self.workshop is not None:
                pressures = [p for p in pressures if p <= self.workshop.pressure_ceiling_kpa]
            if pressures:
                for p in (
                    min(pressures, key=lambda p: abs(p - action.pressure_kpa)),
                    min(
                        pressures,
                        key=lambda p: abs(p - action.pressure_kpa * TARGET / max(apogee, 1)),
                    ),
                ):
                    offer(action.change(method="component", pressure_kpa=p))
            for fill in FILL_PCT:
                if fill != action.fill_pct:
                    offer(action.change(method="component", fill_pct=fill))
            # A hardware change becomes available after operating-point evidence, or when
            # the pressure boundary prevents another step in the desired direction.
            family_runs = sum(
                a.method == "flight"
                and a.start == action.start
                and a.nozzle_mm == action.nozzle_mm
                and a.variant == action.variant
                for a in self.results
            )
            if not result["success"] and (family_runs >= 2 or not pressures):
                for nozzle in NOZZLE_MM:
                    if nozzle != action.nozzle_mm:
                        offer(action.change(method="component", nozzle_mm=nozzle))
        return options

    def step(self, action_id, reason):
        options = self.options()
        if action_id not in options or not isinstance(reason, str) or not reason.strip():
            raise ValueError("choose a listed ID and give a reason")
        action = options[action_id]
        design = self.design(action)
        if action.method == "component":
            result = component_screen(design)
            if self.workshop is not None:
                plan = self.plan(action, design)
                result.update(
                    {
                        k: plan[k]
                        for k in (
                            "key",
                            "dry_mass_g",
                            "cp_mm",
                            "wet_cg_mm",
                            "mount_bound",
                            "pitch_rate_per_s",
                            "checks",
                            "estimated_outlay_jpy",
                            "unavailable",
                        )
                    }
                )
                result["eligible"] = (
                    result["eligible"]
                    and all(plan["checks"].values())
                    and plan["estimated_outlay_jpy"] <= REQUIREMENT.budget_jpy
                )
        elif action.method == "flight":
            flight = flight_tool("simulate_design", design, action.id)
            result = {
                "success": flight["success"],
                "failures": flight["failure_reasons"],
                "cost_jpy": flight["cost_jpy"],
                **{
                    k: flight["metrics"][k]
                    for k in (
                        "apogee_m",
                        "descent_speed_mps",
                        "rail_exit_speed_mps",
                        "landing_distance_m",
                    )
                },
            }
            if self.workshop is not None:
                corners = []
                for ratio in (0.85, 1.15):
                    corner = design.model_copy(
                        update={"axial_drag_coefficient": design.axial_drag_coefficient * ratio}
                    )
                    check = flight_tool("simulate_design", corner, f"{action.id}/cd/{ratio}")
                    corners.append(
                        {
                            "cd": corner.axial_drag_coefficient,
                            "altitude_m": check["metrics"]["apogee_m"],
                            "passed": check["success"],
                        }
                    )
                result["cd_checks"] = corners
                if not all(point["passed"] for point in corners):
                    result["success"] = False
                    result["failures"] = [*result["failures"], "assembled Cd bracket"]
        else:
            n, seed = SAMPLES[action.method]
            if self.workshop is not None:
                seed = {"screen": 4701, "confirm": 77131}[action.method]
            spread = flight_tool("run_dispersion", design, action.id, n=n, seed=seed)
            result = {
                "n": n,
                "seed": seed,
                "success_rate": spread["success_rate"],
                "passes": round(n * spread["success_rate"]),
                "failure_counts": spread["failure_counts"],
                "apogee_m": spread["quantiles"]["apogee_m"],
                "descent_speed_mps": spread["quantiles"]["descent_speed_mps"],
            }
        self.results[action] = result
        self.history.append(
            {
                "offered": list(options),
                "chosen": action.id,
                "reason": reason,
                "analysis": SHELF[action.method],
                "result": result,
            }
        )
        return action, result


def baseline_choice(search, options):
    """Deterministic comparator for experiments without an external decision maker."""
    for method in ("confirm", "screen", "flight"):
        eligible = [a for a in options.values() if a.method == method]
        if eligible:
            choice = eligible[0]
            return choice.id, f"Advance an eligible {method}."
    fresh = [a for a in options.values() if not any(r.start == a.start for r in search.results)]
    if fresh:
        return fresh[0].id, "Inspect a previously untested starting architecture."
    flights = [(a, v["apogee_m"]) for a, v in search.results.items() if a.method == "flight"]
    if not flights:
        return next(iter(options)), "Screen an available assembly."

    def score(candidate):
        matched = [
            (a, h)
            for a, h in flights
            if a.start == candidate.start
            and a.variant == candidate.variant
            and a.nozzle_mm == candidate.nozzle_mm
            and a.fill_pct == candidate.fill_pct
        ]
        if not matched:
            return float("inf")
        a, h = min(matched, key=lambda pair: abs(pair[0].pressure_kpa - candidate.pressure_kpa))
        return abs(h * candidate.pressure_kpa / a.pressure_kpa - TARGET)

    return min(options.values(), key=score).id, "Test the operating point estimated nearest target."


def model_choice(client, model, search, options):
    """The model picks an ID. Numerical inputs and acceptance stay in the harness."""
    context = {
        "mission": REQUIREMENT.model_dump(mode="json"),
        "starting_records": search.records,
        "analysis_pool": SHELF,
        "eligible": list(options),
        "screening_pass_rate": PASS_RATE,
        "history": [{k: row[k] for k in ("chosen", "reason", "result")} for row in search.history],
    }
    if search.workshop is not None:
        context["materials"] = catalog()[0]["variants"]
        context["workshop"] = search.workshop.model_dump(mode="json")
        context["build_checks"] = "Material mass, egg fit, wet and dry stability, mount settling."
    tool = {
        "name": "choose_analysis",
        "description": "Select one currently eligible analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "enum": list(options)},
                "reason": {"type": "string"},
            },
            "required": ["id", "reason"],
        },
    }
    message = client.messages.create(
        model=model,
        max_tokens=2048,
        tools=[tool],
        system=(
            "Use choose_analysis once. Compare literature starts and an independent start "
            "when offered. Diagnose misses using history; prefer matched comparisons. "
            "Confirm one screened design only when ready to freeze it."
        ),
        messages=[{"role": "user", "content": json.dumps(context)}],
    )
    for block in message.content:
        if block.type == "tool_use" and block.name == tool["name"]:
            return block.input["id"], block.input["reason"]
    raise ValueError("model did not select an analysis")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--starts", choices=("mixed", "references", "new"), default="mixed")
    parser.add_argument("--output", type=Path, required=True, help="new directory for this run")
    parser.add_argument("--max-actions", type=int, default=32)
    parser.add_argument(
        "--workshop",
        type=Path,
        help="resource exclusions, operating limits and bench records (JSON)",
    )
    parser.add_argument(
        "--protocol",
        choices=("assembly", "legacy"),
        help="default: assembly; old replay IDs select legacy",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--interactive", action="store_true", help="read one JSON choice per line")
    group.add_argument("--model", metavar="MODEL_ID", help="select actions using the Anthropic API")
    group.add_argument(
        "--replay", type=Path, help="replay choices.json against freshly computed menus"
    )
    args = parser.parse_args()
    if args.max_actions < 1:
        parser.error("--max-actions must be positive")
    choices = json.loads(args.replay.read_text(encoding="utf-8")) if args.replay else None
    client = None
    if args.model:
        from anthropic import Anthropic

        client = Anthropic()
    legacy_replay = bool(choices) and choices[0]["id"].count("/") == 4
    protocol = args.protocol or ("legacy" if legacy_replay else "assembly")
    if args.workshop and protocol == "legacy":
        parser.error("--workshop requires the assembly protocol")
    workshop = (
        (Workshop.model_validate_json(args.workshop.read_bytes()) if args.workshop else Workshop())
        if protocol == "assembly"
        else None
    )
    search = Search(args.starts, workshop)
    args.output.mkdir(parents=True, exist_ok=False)
    status = "budget_exhausted"
    selected = None
    for i in range(args.max_actions):
        options = search.options()
        if not options:
            status = "no_eligible_combination"
            break
        try:
            if args.interactive:
                print(json.dumps({"next": i + 1, "eligible": list(options)}), flush=True)
                decision = json.loads(input())
                key, reason = decision["id"], decision["reason"]
            elif choices is not None:
                key, reason = choices[i]["id"], choices[i]["reason"]
            elif client is not None:
                key, reason = model_choice(client, args.model, search, options)
            else:
                key, reason = baseline_choice(search, options)
            action, result = search.step(key, reason)
        except (
            ValueError,
            EOFError,
            KeyError,
            IndexError,
            TypeError,
            RuntimeError,
            APIError,
        ) as exc:
            status = f"stopped_at_action_{i + 1}: {type(exc).__name__}"
            print(status, flush=True)
            break
        print(json.dumps({"chosen": key, "result": result}), flush=True)
        if action.method == "confirm":
            if choices is not None and len(choices) != i + 1:
                status = "invalid_replay_after_confirmation"
                break
            selected = action
            status = "proxy_pass" if result["success_rate"] >= PASS_RATE else "holdout_failed"
            break

    def write(name, data):
        (args.output / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    write("choices.json", [{"id": h["chosen"], "reason": h["reason"]} for h in search.history])
    write(
        "run.json",
        {
            "status": status,
            "protocol": protocol,
            "workshop": workshop.model_dump(mode="json") if workshop is not None else None,
            "starts": search.records,
            "method_pool": SHELF,
            "chooser": args.model
            or (
                "replay"
                if choices is not None
                else "interactive"
                if args.interactive
                else "baseline"
            ),
            "mission": REQUIREMENT.model_dump(mode="json"),
            "bottle_volume_m3": 0.0015,
            "environment": ENV.model_dump(mode="json"),
            "thresholds": PASS_THRESHOLDS,
            "min_sample_pass_rate": PASS_RATE,
            "max_actions": args.max_actions,
            "unevaluated": [
                "actual opening",
                "egg fracture and mount loads",
                "6DOF attitude and spin",
            ],
            "history": search.history,
        },
    )
    if selected:
        design = search.design(selected)
        write("design.json", design.model_dump(mode="json"))
        (args.output / "vehicle.svg").write_text(render_side_view_svg(design), encoding="utf-8")
        if workshop is not None and status == "proxy_pass":
            write_packet(args.output, design, search.plan(selected, design), search.history)
    print(status)
    return 0 if status == "proxy_pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
