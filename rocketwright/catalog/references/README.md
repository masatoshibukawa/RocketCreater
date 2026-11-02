# Reference vehicles

One YAML file per tier (`bottle.yaml`, `amateur.yaml`, `commercial.yaml`, `heavy.yaml`), each a
list under `references:`. Loaded and validated by `rocketwright/references.py`; reproduced by
`uv run python scripts/check_references.py` and `tests/test_references.py`.

Rules (CLAUDE.md section 2):

- `sources` must be public URLs. No source, no entry.
- `provisional: true` until a human has checked every number against the source. Keep it true
  when you had to estimate a value the source does not give (say which in `notes`).
- `design` uses the ids in `rocketwright/catalog/engines.yaml` / `motors/*.eng`; add the engine or
  motor there (with its own source) rather than inventing one inline.
- `published` keys carry unit suffixes. Suborbital entries need `apogee_m`; orbital entries need
  `payload_to_orbit_kg` and `orbit_altitude_m`.
- `tolerance_frac` is the reproduction error this entry is held to (default 0.30). Raise it only
  with a reason in `notes`.

```yaml
version: 1
references:
  - id: electron                      # [a-z0-9_]+, unique across all files
    tier: commercial
    name: "Rocket Lab Electron"
    sources: ["https://en.wikipedia.org/wiki/Electron_(rocket)"]
    provisional: true
    requirement:                      # the mission this vehicle answers (rocketwright.schema.Requirement)
      goal_kind: orbit
      target_altitude_m: 500000
      payload_mass_kg: 300
    design:                           # rocketwright.schema.Design for this tier
      tier: commercial
      stages:
        - {propellant_mass_kg: 9250, structural_fraction: 0.10, engine_id: rutherford, engine_count: 9}
        - {propellant_mass_kg: 2050, structural_fraction: 0.12, engine_id: rutherford_vacuum, engine_count: 1}
      fairing_mass_kg: 50
      payload_mass_kg: 300
      pitch_start_s: 8
      initial_pitch_deg: 3
    published:                        # what the source states
      payload_to_orbit_kg: 300
      orbit_altitude_m: 500000
    env: {launch_latitude_deg: -39.26, launch_altitude_m: 10}
    tolerance_frac: 0.30
    notes: "structural fractions estimated from dry/wet masses on the page"
```
