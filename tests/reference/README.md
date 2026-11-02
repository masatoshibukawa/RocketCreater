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

# OpenRocket reference flights for `tests/test_solid.py`

`test_openrocket_reference_flight` loads every `openrocket_*.yaml` file in this directory, runs
`rocketwright.physics.solid.simulate` on the design it describes and compares the listed metrics
with the OpenRocket values to within `tolerance_frac` (default 15 %). With no file present the
test is skipped: a human must build the same vehicle in OpenRocket (https://openrocket.info/) and
export the numbers. Use a motor whose `.eng` file is bundled under `rocketwright/catalog/motors/`
(the synthetic `dummy_*` curves can be imported into OpenRocket as custom motors) so that both
tools fly the same thrust curve.

## Expected YAML format

```yaml
source: "OpenRocket 23.09, file sim/demo_amateur.ork, simulation 'calm day'"  # required
notes: "optional: launch rod length, wind model, drag options used"
tolerance_frac: 0.15                 # optional, relative tolerance per metric
env:                                 # rocketwright.schema.Env (same site as the OpenRocket sim)
  launch_altitude_m: 300
  wind_speed_mps: 0.0
  rail_length_m: 1.5
design:                              # rocketwright.schema.AmateurDesign
  tier: amateur
  body_diameter_m: 0.054
  body_length_m: 0.9                 # tube only; overall length = nose_length_m + body_length_m
  nose_shape: ogive
  nose_length_m: 0.15
  fins: {count: 4, root_chord_m: 0.10, tip_chord_m: 0.05, span_m: 0.05, sweep_m: 0.03}
  motor_id: dummy_G80
  dry_mass_kg: 0.5                   # airframe without motor and payload
  payload_mass_kg: 0.2
  parachute_diameter_m: 0.9
  deploy_delay_s: 1.0                # the model deploys at apogee + delay (see solid.py)
expected:                            # any subset of SimResult.metrics keys
  apogee_m: 550
  max_speed_mps: 120
  rail_exit_speed_mps: 17
  stability_margin_cal: 2.9
  descent_speed_mps: 3.7
```
