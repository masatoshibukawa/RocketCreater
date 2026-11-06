# Catalog data

Every entry in `parts.yaml`, `engines.yaml` and `motors/*.eng` must carry either a `source` URL
(and a `license` for bundled thrust curves) or `provisional: true`. Provisional entries are
placeholders awaiting human confirmation and are listed in the top-level README under
要確認の値.

## Bottle design search pool

`search_catalog(tier="bottle", kind="parts", query=null)` returns the three
shelves in [bottle_variables.yaml](bottle_variables.yaml). A part-name query narrows the
response to matching component groups and the methods and scores relevant to their inputs.

| Shelf in the response | Contents |
| --- | --- |
| `variable_definitions` | Bottle, nozzle, fins, parachute, airframe/payload masses and operating point. A `catalog_choice` supplies part dimensions to `design_inputs`. Mission values stay fixed. `derived` values are computed. `reserved` geometry needs a suitable model before exploration. |
| `analysis_methods` | Executable tool names with their arguments, applicable design inputs, assumptions and comparison conditions. |
| `evaluation_functions` | Each score specifies its role, units, direction and a path in a method's result. A conditional score is absent when inapplicable. |

For an altitude miss, compare operating points using `water_fill_frac` and
`initial_gauge_pressure_pa` with `simulate_design`. Read `metrics.apogee_band_excess_m` in
metres and use `metrics.apogee_m` to distinguish undershoot from overshoot. If that range
is exhausted, try another catalog nozzle on the same bottle. For two nominal passes,
`run_dispersion` can compare success rates under identical environment, seed and sample
count. Choosing an objective for a trial always leaves the full nominal acceptance check in place.

### Literature and future simulators

[Literature contracts](bottle_literature.yaml) connect the local [reference index](../../文献/README.md)
to candidate methods. `search_catalog` returns these in `planned.analysis_methods` and
`planned.evaluation_functions`. Each method specifies its variables, other required inputs,
output fields and validation procedure. Its evaluation functions name the outputs they use.
Source IDs resolve through the returned `references` dictionary even without the local PDFs.

For example, a fin query exposes the D09 CAD variants and the R03 aerodynamic test method.
PN1 and PN3 support a count comparison at the same nominal profile. PN1 and PN2 also change
the adapter clearance and positioning. Use dimensions measured on finished geometry.
A parachute query distinguishes release from full inflation. P09 identifies a release
mechanism, while timing and reliability still need measurements on the assembled vehicle.

For a height benchmark, use R14 Table 2 as measured data, convert absolute to gauge
pressure, and preserve the run IDs and measurement uncertainties. A benchmark residual
evaluates the simulator. Mission altitude acceptance still uses the requested target.
