# Reference vehicles for `tests/test_multistage.py`

`test_reference_vehicle_payload_order_of_magnitude` loads every `*.yaml` / `*.yml` file in this
directory and checks that the multistage model reproduces the vehicle's published LEO capability
to within an order of magnitude (positive perigee at the stated payload, and
`|payload_margin_kg| < payload_to_leo_kg`). With no data file present the test is skipped.

Every file must have a public `source` URL (CLAUDE.md section 2, principle 4). Do not add a
vehicle whose numbers you cannot trace to a public page.

## Expected YAML format

```yaml
vehicle: "Falcon 9 Block 5"                     # display name
source: "https://en.wikipedia.org/wiki/Falcon_9"  # public page the numbers come from
payload_to_leo_kg: 22800                         # published LEO capability (expendable)
orbit_altitude_m: 200000                         # perigee altitude used as the target
notes: "optional free text (which variant, reference orbit, inclination ...)"
design:                                          # a rocketwright.schema.MultistageDesign
  tier: commercial                               # or heavy (boosters allowed)
  stages:                                        # index 0 burns first
    - propellant_mass_kg: 411000
      structural_fraction: 0.05                  # structure / (structure + propellant)
      engine_id: merlin_1d                       # id from rocketwright/catalog/engines.yaml
      engine_count: 9
    - propellant_mass_kg: 107500
      structural_fraction: 0.04
      engine_id: merlin_1d_vacuum
      engine_count: 1
  boosters: []                                   # heavy only: [{booster_id: gem_63, count: 4}]
  fairing_mass_kg: 1900
  payload_mass_kg: 0                             # overwritten by payload_to_leo_kg
  pitch_start_s: 10                              # starting guess; the test tunes the program
  initial_pitch_deg: 5
```

The test replaces `payload_mass_kg` with `payload_to_leo_kg`, tunes the pitch program with
`multistage.tune_pitch_program`, and simulates with `target_perigee_m = orbit_altitude_m`.
