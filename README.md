# RocketWright

Describe a mission in plain language ("lift 1 kg to 2 km and recover it", "put a 150 kg satellite
into a 400 km orbit") and RocketWright classifies it into one of four tiers, lets Claude propose
designs using that tier's physics model and parts catalog, launches every candidate in a
deterministic simulator (including Monte Carlo dispersion), and returns only the designs that pass,
with drawings, bill of materials, flight analysis and success rate.

Built for **Built with Claude: Japan 2026**. Everything is simulated; nothing is launched.
Licensed under MIT.

## What it does

1. Classify the request into a tier: `bottle`, `amateur`, `commercial` or `heavy`.
2. Let Claude choose and explain designs using that tier's physics model and catalog.
3. Simulate each candidate (plus an n-run dispersion with seeded noise).
4. Return only passing designs, each with drawing, BOM, flight analysis and success rate.

| Tier | Typical request | Propulsion | Physics model |
| --- | --- | --- | --- |
| `bottle` | tens of metres, land an egg intact | water + compressed air | `water` |
| `amateur` | hundreds of metres to a few km, ~1 kg payload | certified commercial solid motors (catalog) | `solid` |
| `commercial` | 100 km, small satellites to LEO | multistage (engines from catalog) | `multistage` |
| `heavy` | multi-tonne payloads to LEO / GTO | multistage + strap-on boosters | `multistage` |

## Principles

- **Claude thinks, chooses and explains; code produces every number.** Each figure shown to the
  user comes from a tool call and carries that call's id as provenance. The final explanation is
  checked in code for numbers with no source.
- **Deterministic.** Every random process takes a seed; same input + seed gives the same result.
  The demo scripts in `scenarios/` are regression tests.
- **Ship end to end first.** Simplified physics is marked with `# SIMPLIFICATION:` in code and
  listed below.
- **No unsourced data.** Catalog values, tier boundaries and reference values carry a `source` URL
  or `provisional: true` (awaiting human confirmation, listed below).

## Repository layout

```
rocketwright/        Python package (backend)
  schema.py          pydantic models: Requirement, Env, Design (tier-discriminated), SimResult, DispersionResult
  classify.py        rule-based tier classification
  guard.py           out-of-scope request detection
  physics/           atmosphere, water, solid, multistage, stability, recovery
  dispersion.py      Monte Carlo runner shared by all models
  cost.py            BOM roll-up (bottle/amateur) or mass-based estimate (commercial/heavy)
  catalog/           parts.yaml, motors/*.eng, engines.yaml (every entry sourced or provisional)
  drawing.py         SVG side view with dimensions
  report.py          Markdown/JSON report and BOM CSV
  agent/             Claude tool definitions, design loop, reviewers, system prompt
api/main.py          FastAPI; streams agent progress over SSE
web/                 Next.js (App Router, TypeScript) frontend
config/tiers.yaml    tier boundaries (sourced or provisional)
config/models.yaml   Claude model ids, effort, attempt budget, reviewer settings
scenarios/           fixed demo scripts used as regression tests
scripts/             run_scenario.py (demo runner) and tuning helpers
tests/               pytest
```

## Getting started

Backend (Python 3.11+, managed with [uv](https://docs.astral.sh/uv/)):

```bash
uv python install 3.12
uv sync --group dev
uv run pytest
uv run ruff check .
uv run uvicorn api.main:app --reload   # GET /health
```

Agent calls need `ANTHROPIC_API_KEY`; copy `.env.example` to `.env`.

Frontend (Node >= 18.18; the scaffold was written by hand and has not been built yet in this
environment):

```bash
cd web && npm install && npm run dev
```

## Running the demo

Each file in `scenarios/` is a fixed demo script (request text, seed, expected tier). The runner
prints one line per agent event and exits non-zero when the classified tier differs from the
expectation or the loop ends in error.

```bash
# No network, no API key: scripted fake client with scripted reviewer answers.
uv run python scripts/run_scenario.py scenarios/demo_commercial.yaml --dummy

# Live: real Claude API (ANTHROPIC_API_KEY must be set; see .env.example).
uv run python scripts/run_scenario.py scenarios/demo_commercial.yaml
```

`scenarios/demo_amateur.yaml` and `scenarios/demo_bottle.yaml` work the same way. The same runs
are executed by `tests/test_scenarios.py` with the dummy client.

Models and the reviewer fan-out are configured in `config/models.yaml`:

- `design_model` (`claude-opus-5-5`, adaptive thinking, `effort: high`) makes the design
  decisions; `light_model` (`claude-haiku-5-5`) does light work.
- `max_attempts` (40) caps `simulate_design` calls; `max_turns` (80) caps API round trips.
- `reviewers`: four per-aspect reviewers (stability / recovery / cost / safety) run in parallel on
  every passing candidate (`enabled`, `model`, `effort`, `max_tokens`,
  `max_rounds_per_candidate`). Their verdicts are streamed as a `review` event; major/blocker
  findings are fed back to the designer, and a blocker moves the design out of the final passing
  list (a `warning` event of kind `review_gate` says so). Findings that cite numbers absent from
  the tool results are dropped in code.

## Status

| Phase | Dates | Done when |
| --- | --- | --- |
| 1 | 11/2–11/3 | schema, classify, guard, minimal multistage with tests; agent completes a loop on dummy physics |
| 2 | 11/4–11/5 | solid + stability + recovery; agent + UI work end to end for commercial and amateur |
| 3 | 11/6–11/7 | water, dispersion for all tiers, reviewers, drawing and BOM export |
| 4 | 11/8 | feature freeze; scenario regression tests, UI polish, README |
| 5 | 11/9–11/10 | demo video, summary, submission |

Current: phase 4 (feature freeze). All four tiers run on their real physics models (`water`,
`solid`, `multistage`); dispersion, reviewers, drawings, reports and BOM export are wired in.
`uv run python scripts/check_scenarios.py` runs every scenario with the fake client and checks
the final JSON (passing design, provenance, review and dispersion events, cited tool ids).

## Simplifications

Each entry mirrors a `# SIMPLIFICATION:` comment in the code (`grep -rn SIMPLIFICATION rocketwright/`).

`physics/atmosphere.py`:

- Above 86 km the temperature is held constant and pressure/density decay exponentially; the
  real USSA76 thermosphere rises to ~1000 K.
- The molar mass of air is held at its sea-level value (USSA76 lets it drop above 86 km).
- The temperature offset does not re-integrate the hydrostatic pressure profile.

`physics/multistage.py`:

- Spherical Earth with the mean radius; central gravity only (no J2).
- Fairing jettison at a fixed altitude (110 km) instead of a free-molecular-heating limit.
- Vehicle diameter is estimated from total propellant mass (`d = 0.05 m * m_prop^(1/3)`).
- Drag coefficient is a small Mach table for a slender launcher, not vehicle-specific.
- Engine mass is assumed to be part of the structural fraction (a warning is raised when the
  fraction cannot even cover the engines).
- All strap-on boosters are jettisoned together when the shortest-burning one is empty; leftover
  propellant is dropped with them, and boosters that outlast stage 1 are dropped with stage 1.
- Upper stages ignite immediately at separation (no coast, no ullage).
- With Earth rotation on, the in-plane component of the co-rotating atmosphere is
  `omega * cos(latitude)`, as if the trajectory plane were the equator.
- Speed of sound comes from the same atmosphere model with no hypersonic subtleties.
- The pitch kick is instantaneous and rotates the air-relative velocity vector; afterwards the
  thrust follows the velocity (zero angle of attack, open-loop gravity turn). This makes the
  reachable orbit very sensitive to `pitch_start_s` / `initial_pitch_deg` (a tenth of a degree can
  move the perigee by tens of km) and favours elliptical insertions; `tune_pitch_program`
  (scipy) searches the two parameters.
- For the ideal delta-v budget the fairing is dropped after the first phase.
- Payload margin holds the simulated losses fixed and inverts the ideal rocket equation against the
  circular speed at the reference perigee.

`physics/stability.py` (Barrowman, used by `solid`):

- Barrowman's fin normal-force coefficient is used as is for 3-8 fins; his derivation assumes at
  most two fins are effective in any plane (OpenRocket applies a reduction for 5+ fins).
- A constant-diameter body tube contributes no normal force (Barrowman).
- The CG is a lumped-mass estimate: the airframe dry mass is spread uniformly along the overall
  length (CG at mid-length), the payload is a point mass at the base of the nose cone unless a
  station is given, and the motor is a point mass at the centre of its case flush with the aft end.

`physics/solid.py` (amateur):

- One constant drag coefficient (`DEFAULT_CD = 0.5`) on the body frontal area for a slender finned
  hobby rocket at zero angle of attack.
- Constant `g` along the whole flight.
- On the rail only the along-rail (vertical) air speed counts; the rail is vertical (`Env` has no
  launch-angle field); after rail departure the flight is a point mass at zero angle of attack
  whose body axis follows the air-relative velocity.
- The parachute opens at apogee + `deploy_delay_s` regardless of the motor's ejection-charge
  timing (`deploy_delay_s` is measured **from apogee**, not from burnout; the schema comment and
  the model agree).

`physics/water.py` (bottle):

- One constant drag coefficient (`DEFAULT_CD = 0.5`) on the bottle cross-section for a finned
  bottle flying nose first; a bottle without fins tumbles, modelled as a doubled drag coefficient
  (`TUMBLING_DRAG_FACTOR = 2.0`).
- The air-blowdown phase after the water is spent is one instantaneous impulse along the body
  axis equal to `AIR_IMPULSE_EFFICIENCY = 0.5` times `sqrt(2 m_air W_isentropic)`.
- The bottle diameter is estimated from the volume (a 1.5 L PET bottle is about 90 mm across,
  scaled with the cube root of the volume).
- The air inside the bottle is at ambient temperature before launch.
- Rail / angle-of-attack simplifications as in `solid.py` (vertical launcher, zero angle of attack).
- The parachute opens exactly at apogee.

`physics/recovery.py` (parachute descent, shared by `solid` and `water`):

- Flat-sheet / hemispherical hobby parachute `Cd = 1.5` (a cross-type chute is ~0.8).
- The descent is at the terminal speed computed with the air density at the mid-point of the
  descent; opening transients and the density change along the way are ignored. The rocket drifts
  with the full wind vector for the whole descent (wind constant with altitude).

`cost.py`:

- Flat placeholder prices (all provisional, see below); the strap-on booster mass is a placeholder
  constant until the catalog carries it.

`drawing.py` (SVG side views):

- A bottle is drawn as a cylinder with a fixed length/diameter ratio (3.5) plus a nose of 0.8 d
  and a neck of 0.3 d.
- The amateur motor-mount length comes from the motor catalog; a placeholder fraction of the body
  length (0.2) is used when the motor cannot be loaded. The fin drawn is a representative size
  (0.8 d span) when a design only says `has_fins`.
- Each multistage stage is a cylinder whose diameter follows the `multistage` rule above and whose
  length comes from the propellant mass at a bulk density of 1000 kg/m3; the fairing is 2.5
  diameters long; boosters are 0.4 x diameter cylinders 0.6 x the stage-1 length when the booster
  catalog is unavailable. The sketches are concept-level, not manufacturing drawings.

`report.py`:

- When the catalog does not carry a part, the dry mass of a bottle/amateur airframe is split across
  BOM rows by fixed fractions (bottle 45/10/25/20 % for bottle/nozzle/fins/parachute; amateur
  15/45/25/10 % for nose/body/fins/parachute; provisional).
- Every report carries a note that physics and cost are simplified and points here.

## Values to confirm / 要確認の値

Every item below is `provisional: true` in the repository (or a hard-coded constant without a
source) and needs a human decision or a source.

`config/tiers.yaml`:

| Tier | Key | Placeholder |
| --- | --- | --- |
| bottle | target_altitude_max | 100 m |
| bottle | payload_mass_max | 0.2 kg |
| bottle | budget_min | 1,000 JPY |
| amateur | target_altitude_max | 5,000 m (depends on club / legal practice in Japan) |
| amateur | payload_mass_max | 5 kg |
| amateur | budget_min | 30,000 JPY |
| commercial | target_altitude_min | 100 km (Karman line; could cite FAI) |
| commercial | target_altitude_max | 2,000 km |
| commercial | payload_mass_max | 1,000 kg |
| commercial | budget_min | 1e9 JPY (most arbitrary; drives the budget-conflict demo) |
| heavy | target_altitude_max | unbounded |
| heavy | payload_mass_max | unbounded |
| heavy | budget_min | 5e9 JPY |

`cost.py` (`COST_CONSTANTS`, all JPY, all provisional):

| Key | Placeholder |
| --- | --- |
| bottle_base_jpy | 1,500 (bottle, nozzle, fins, launcher) |
| bottle_parachute_jpy | 800 |
| amateur_airframe_jpy_per_kg | 12,000 |
| amateur_fin_jpy | 500 per fin |
| amateur_motor_jpy | 8,000 (flat, mid-power reload) |
| amateur_parachute_jpy_per_m2 | 6,000 |
| amateur_electronics_jpy | 10,000 (altimeter + deploy) |
| commercial_jpy_per_kg_liftoff | 80,000 |
| heavy_jpy_per_kg_liftoff | 25,000 |
| booster_mass_kg_placeholder | 20,000 kg per strap-on |

Pass/fail thresholds (`PASS_THRESHOLDS` in `physics/solid.py` and `physics/water.py`):

| Model | Rule | Value |
| --- | --- | --- |
| solid | minimum rail-exit speed | 15 m/s (common club guideline) |
| solid | static stability margin | 1.5 to 4.0 cal (above 4.0 is a warning only) |
| solid, water | maximum descent speed | 6 m/s (water: 10 m/s for an empty bottle without payload) |
| solid | parachute deployment speed | 40 m/s, warning only |
| solid, water | apogee tolerance when a target is given | +-10 % |
| water | maximum initial gauge pressure | 1,000 kPa (PET bottle safety cap) |

Dispersion sigmas (`dispersion.py` `DISPERSION_SPEC`, all provisional; one standard
deviation, applied per sample with the run's seed):

| Tier | Quantity | Sigma |
| --- | --- | --- |
| bottle | initial gauge pressure | 5 % (relative) |
| bottle | wind speed / direction | 1.0 m/s / 20 deg |
| amateur | motor thrust (total impulse) | 5 % (relative) |
| amateur | dry mass | 3 % (relative) |
| amateur | wind speed / direction | 1.5 m/s / 30 deg |
| amateur | parachute deploy delay | 0.5 s (clipped at 0) |
| commercial, heavy | engine Isp | 1 % (relative) |
| commercial, heavy | engine thrust | 2 % (relative) |
| commercial, heavy | stage structural fraction | 5 % (relative) |

The success rates shown in the demo (`run_dispersion` with n=100) are computed from these
sigmas at run time and are not stored anywhere; they change when the sigmas do. Note that the
open-loop gravity turn of `multistage` makes the commercial success rate very sensitive to these
sigmas (the demo design passes nominally but most perturbed samples fall short of the target
perigee), which is a consequence of the no-guidance simplification above.

Physics constants without a source:

- `solid.DEFAULT_CD = 0.5` and `water.DEFAULT_CD = 0.5` (body drag), `water.TUMBLING_DRAG_FACTOR
  = 2.0` (bottle without fins).
- `recovery.DEFAULT_PARACHUTE_CD = 1.5` (hobby parachute).
- `water.AIR_IMPULSE_EFFICIENCY = 0.5` (air-blowdown impulse fraction).
- Bottle diameter rule: 90 mm for 1.5 L, scaled with the cube root of the volume
  (`water.bottle_diameter_m`; the drawing uses a separate aspect ratio of 3.5).
- `deploy_delay_s` semantics: the delay is counted **from apogee** (parachute opens at apogee +
  delay); it is not the motor's ejection-charge delay after burnout. Confirm this is the intended
  meaning for the amateur demo.

Catalog (`rocketwright/catalog/`):

- `motors/*.eng`: all five thrust curves (`dummy_F32`, `dummy_G80`, `dummy_H128`, `dummy_I200`,
  `dummy_J420`) are **synthetic trapezoids** written for this repository, not real motors. Every
  `solid` result carries a warning until licensed curves (with source and license) replace them.
- `parts.yaml`: all 17 items (bottles, nozzles, nose cones, body tubes, fins and fin stock,
  motor mounts, parachutes) carry representative hobby-shop masses and JPY prices, all
  provisional.
- `engines.yaml`: `merlin_1d_vacuum`, `rl10` (RL10C-1), `le_9`, `rutherford`, `gem_63` and
  `ariane5_eap` are provisional (numbers read from public pages but not yet confirmed); the other
  entries carry a source.

Wording that a human should review:

- `report.py` `CHECKLIST`: the "Checklist of items to confirm (not legal advice)" is generic on
  purpose (site permission, weather limits, range safety, insurance; motor certification and
  airspace for amateur; launch licence, range agreement, spectrum and export control for
  commercial/heavy). RocketWright does not decide on permits or legality (CLAUDE.md section 4).
- `agent/prompts.py` cost reviewer: severity `major` is defined as "the cost is within about a
  tenth of the budget" and `blocker` only when `cost_jpy` is above the budget; reviewers must
  describe thresholds in words rather than numbers. Confirm the one-tenth margin rule.

Schema decisions not spelled out in `CLAUDE.md`:

- `Env` defaults are all zero (no real launch site). Demo scenarios must set latitude, altitude and wind.
- `AmateurDesign.dry_mass_kg` (airframe without motor and payload) was added; `solid.py` needs it.
- `AmateurDesign.deploy_delay_s` is the delay after apogee (see above).
- `Env.rail_length_m` (default 1.5 m) was added for launcher-departure speed in `solid`/`water`.
- Metric keys must end with one of the suffixes in `rocketwright.schema.UNIT_SUFFIXES`.

## 日本語概要

自然文で要求（高度か軌道か、積載質量、回収の要否、予算）を伝えると、規模を4段階
（ペットボトル／アマチュア／企業級／重工級）に分類し、その段階の物理モデルと部品カタログを使って
Claude が設計案を作り、シミュレータで仮想打ち上げ（シード付きの多数回試行を含む）して検証し、
合格した設計案だけを図面・部品表・飛行解析・成功率つきで返す Web アプリです。
実機は打ち上げません。すべてシミュレーション上で完結します。

- 数値はすべてコード（ツール関数）が出し、Claude は考える・選ぶ・説明するだけです。
- 乱数は必ずシードを受け取り、同じ入力なら同じ結果を返します。
- 出典のない数値は `provisional: true` を付け、上の「要確認の値」に列挙しています。
- 現在はフェーズ4（機能凍結）：4段階すべてが実物理モデル（`water` / `solid` / `multistage`）で動き、
  多数回試行、観点別レビュアー（安定性・回収・費用・安全）、図面・レポート・部品表の出力まで繋がっています。
- デモは `uv run python scripts/run_scenario.py scenarios/demo_commercial.yaml --dummy`
  （API キー不要）で再現できます。`--dummy` を外すと実際の Claude API を使います
  （`ANTHROPIC_API_KEY` が必要）。

セットアップは上記 Getting started を参照してください。ライセンスは MIT です。
