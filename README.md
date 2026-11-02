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
  agent/             Claude tool definitions, design loop, system prompt
api/main.py          FastAPI; streams agent progress over SSE
web/                 Next.js (App Router, TypeScript) frontend
config/tiers.yaml    tier boundaries (sourced or provisional)
scenarios/           fixed demo scripts used as regression tests
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

## Status

| Phase | Dates | Done when |
| --- | --- | --- |
| 1 | 11/2–11/3 | schema, classify, guard, minimal multistage with tests; agent completes a loop on dummy physics |
| 2 | 11/4–11/5 | solid + stability + recovery; agent + UI work end to end for commercial and amateur |
| 3 | 11/6–11/7 | water, dispersion for all tiers, reviewers, drawing and BOM export |
| 4 | 11/8 | feature freeze; scenario regression tests, UI polish, README |
| 5 | 11/9–11/10 | demo video, summary, submission |

Current: phase 1 (scaffold complete).

## Simplifications

Each entry mirrors a `# SIMPLIFICATION:` comment in the code (`grep -rn SIMPLIFICATION rocketwright/`).

Physics status per tier:

- `commercial` / `heavy` use the real `physics/multistage.py` model through the agent tools.
- `bottle` and `amateur` are still **dummy physics** (`rocketwright/agent/tools.py`, closed-form
  placeholders tagged `DUMMY PHYSICS` in every result) until phase 3 wires in `physics/water.py`
  and `physics/solid.py`. Monte-Carlo dispersion is a dummy spread around the nominal result for
  every tier until phase 3.

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

`cost.py`:

- Flat placeholder prices (all provisional); booster mass is a placeholder constant.

## Values to confirm / 要確認の値

Every item below is `provisional: true` in the repository and needs a human decision or a source.

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

Schema decisions not spelled out in `CLAUDE.md`:

- `Env` defaults are all zero (no real launch site). Demo scenarios must set latitude, altitude and wind.
- `AmateurDesign.dry_mass_kg` (airframe without motor and payload) was added; `solid.py` needs it.
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

セットアップは上記 Getting started を参照してください。ライセンスは MIT です。
