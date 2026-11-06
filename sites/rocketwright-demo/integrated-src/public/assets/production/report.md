# RocketWright design report — ペットボトル (bottle)

## Requirement

| Item | Value |
| --- | --- |
| Goal | altitude |
| Target altitude / perigee | 20.00 m |
| Payload mass | 60 g |
| Budget | 3,000 円 |
| Recovery required | yes |

## Design variables

| Variable | Value |
| --- | --- |
| bottle_volume_m3 | 1.50 L |
| water_fill_frac | 25 % |
| initial_gauge_pressure_pa | 325 kPa |
| nozzle_diameter_m | 9 mm |
| dry_mass_kg | 153 g |
| payload_mass_kg | 60 g |
| has_fins | yes |
| axial_drag_coefficient | 0.828 |
| has_parachute | yes |
| parachute_diameter_m | 595 mm |

## Key metrics

| Metric | Value | SI value | Source (tool call id) |
| --- | --- | --- | --- |
| apogee_m | 19.46 m | 19.4596976335308 | confirm/D02/9/325/25/carton_wide |
| apogee_time_s | 2.1 s | 2.0532095816215215 | confirm/D02/9/325/25/carton_wide |
| max_speed_mps | 20.7 m/s | 20.688107450219437 | confirm/D02/9/325/25/carton_wide |
| max_accel_mps2 | 104.33 m/s2 | 104.33255941844295 | confirm/D02/9/325/25/carton_wide |
| peak_thrust_n | 41 N | 41.35121330287565 | confirm/D02/9/325/25/carton_wide |
| thrust_phase_duration_s | 0.3 s | 0.26829789815502514 | confirm/D02/9/325/25/carton_wide |
| water_exhausted_speed_mps | 19.0 m/s | 18.952292042718376 | confirm/D02/9/325/25/carton_wide |
| water_impulse_ns | 9 N·s | 8.540673932728712 | confirm/D02/9/325/25/carton_wide |
| air_impulse_ns | 0 N·s | 0.44532781902935503 | confirm/D02/9/325/25/carton_wide |
| rail_exit_speed_mps | 14.5 m/s | 14.520647270497207 | confirm/D02/9/325/25/carton_wide |
| descent_speed_mps | 2.9 m/s | 2.8618084152518937 | confirm/D02/9/325/25/carton_wide |
| landing_east_m | 12.69 m | 12.688334728899441 | confirm/D02/9/325/25/carton_wide |
| landing_north_m | 0 mm | 2.330809276838535e-15 | confirm/D02/9/325/25/carton_wide |
| landing_distance_m | 12.69 m | 12.688334728899441 | confirm/D02/9/325/25/carton_wide |
| flight_time_s | 8.9 s | 8.85300006718342 | confirm/D02/9/325/25/carton_wide |
| liftoff_mass_kg | 588 g | 0.5877873 | confirm/D02/9/325/25/carton_wide |
| water_mass_kg | 375 g | 0.375 | confirm/D02/9/325/25/carton_wide |
| cost_jpy | 2,300 円 | 2300.0 | confirm/D02/9/325/25/carton_wide |

## Verdict

**PASS** (simulate_design `confirm/D02/9/325/25/carton_wide`)

Warnings:

- stability: Barrowman estimate on representative fins; CG is estimated, not measured
- stability: margin -0.30 cal with water loaded: the vehicle does not restore itself at liftoff

## Checklist of items to confirm (not legal advice)

This is a checklist of topics to confirm with the responsible authority or club; RocketWright does not decide on permits or legality.

- [ ] Launch site: permission of the land owner / site operator and a safety area sized from the landing dispersion in this report
- [ ] Weather limits (wind, visibility) and a go/no-go rule agreed before launch day
- [ ] Range safety: spectator distance, recovery crew, first-aid, fire precautions
- [ ] Insurance or club coverage applicable to the activity
- [ ] Pressure limit of the bottle and the launcher release mechanism (never exceed the rated pressure; use water only, no gas other than air)
- [ ] Eye protection for the launch crew; nobody downrange during pressurisation

## Notes

- Physics and cost models are deliberately simplified; every `SIMPLIFICATION` is listed in the repository README together with the provisional values awaiting human confirmation.
