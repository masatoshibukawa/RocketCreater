# Adaptive follow-up analysis

The campaign turns observed CFD accuracy failures and fin/mission tradeoffs into
auditable choices of **target + method + evaluation**. It supplements the existing
generation and integrity pools; it does not promote their screening results to
hardware qualification.

Catalog: `rocketwright/catalog/bottle_analysis.yaml`. There are 26 variables,
7 targets, 17 methods, 9 evaluations and 23 permitted combinations. Ten methods
have campaign adapters; seven are explicitly planned. Existing thermal, contact,
stability and body FEM calculations remain in the integrity harness. Planned
entries describe additional coupling or calibration, not absence of those earlier
calculations.

## Host/planner boundary

`Search.analysis_campaign()` exposes `Campaign.options()` and `step(id, reason)`.
The host owns the catalog, input records, solver paths, requirements, capabilities,
resources and runner registry. A planner can choose only an offered ID. It cannot
provide commands, change thresholds or assert physical qualification.

Before ranking, the harness checks adapters, dependencies, input scopes, numerical
quality flags, applicability bounds, memory, remaining cost budget and attempt
limits. Every decision includes all offered and rejected IDs with reasons.
The score is a declared heuristic:

`priority + 5 * sum(clipped observed urgency) - log(1 + estimated seconds)`.

It is not a learned information-gain model. This run used the deterministic host
baseline, **not an internal LLM benchmark**. The API supports a planner choosing a
different eligible ID; evaluation of a live LLM's choices remains separate work.

Artifacts retain input/method/parameter/dependency fingerprints. A changed input
scope invalidates that result and its descendants. Hosts must update the input
scope hashes when physical inputs change; the `variables.invalidates` list is the
declared dependency map, not an automatic CAD change detector. Requirements are
part of evaluations and precision allocation; changing them requires a new
assessment. Completed execution, numerical accuracy, model applicability and
physical evidence remain separate.

The cost budget controls admission/reservation and is charged by the greater of
estimated and observed time. It is **not a hard wall-clock deadline**. Individual
solver subprocesses have timeouts. A failed action cannot consume unbounded retries.
No result from this research campaign can authorize physical launch.

## Reproduce

Use a new output directory for each campaign. Keep the existing input/CFD/flight
artifacts at their original revisions; do not overwrite them.

```powershell
python scenarios/adaptive_analysis/run.py `
  output/integrity-02/input.json output/flight-loads-01/tunnel `
  output/flight-loads-01/assessment-refined output/adaptive-01 `
  --solver <absolute-CalculiX-executable> --memory-gib 8 --budget-s 2400

python scenarios/adaptive_analysis/repair.py `
  output/integrity-02/input.json output/adaptive-01 output/adaptive-geometry-02 `
  --solver <absolute-CalculiX-executable>

python scenarios/adaptive_analysis/report.py `
  output/adaptive-01 output/adaptive-geometry-02 output/adaptive-report-01
```

`run.py` currently checks the assembly source at the sibling prototype output
used by the existing CFD run. It must have the exact recorded geometry hash.
CuPy/CUDA setup is the same as `scenarios/cfd/README.md`; on this PC the MATLAB
CUDA runtime directory also has to be on PATH. No proprietary solver is bundled.
GPU memory is a conservative host reservation, not total installed capacity.

The repair campaign imports hashed prior evidence, rather than treating old runs
as a current cache. After both thickness-only candidates miss the altitude target,
it reopens the low-layer shape pool, screens 192 combinations, and verifies the
lightest feasible screen with new geometry-specific FEM and CFD. It does not reuse
the original airframe's CFD table as qualified evidence for the modified shape.

See [RESULTS.md](RESULTS.md) and `reference-summary.json` for executed findings.

## Verification and scope

The beam screen uses tapered Euler–Bernoulli elements, consistent mass, and a
distributed root foundation retaining translation/rotation coupling. Its uniform
load solution is checked against a closed form; tapered refinement and mass/CG/
liquid-centroid invariants are tested. Large linear displacements identify cases
requiring nonlinear FEM, not quantitative accepted deformations.

Material profiles are assumed isotropic parameter scenarios, not measured paper,
printed polymer, carbon-fiber grade or laminate allowables. All temperatures and
loads retain their assumptions. Solid-fin mass replaces the original BOM group;
the old material label and material price are invalidated. New prices, joints and
manufacturing processes are not invented.

Grid differences are sensitivity measures, not guaranteed error bounds. An
observed asymptotic trend is required before using Richardson/GCI estimates.
See the [NASA grid-convergence guide](https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html)
and [verification assessment](https://www.grc.nasa.gov/www/wind/valid/tutorial/verassess.html).
The thresholds in this repository are project screening assumptions, not NASA
approval criteria.
