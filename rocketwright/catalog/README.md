# Catalog data

Every entry in `parts.yaml`, `engines.yaml` and `motors/*.eng` must carry either a `source` URL
(and a `license` for bundled thrust curves) or `provisional: true`. Provisional entries are
placeholders awaiting human confirmation and are listed in the top-level README under
要確認の値.

## parts.yaml (v2)

Format: `PARTS_SCHEMA.md`. Top-level keys:

| key | meaning |
| --- | --- |
| `version: 2` | format version |
| `price_jpy_basis` | one line stating how `price_jpy` was derived (currently USD x 150, fixed, provisional) |
| `parts` | the v2 list (one map per part, `kind`/`tier` from the schema table) |
| `items` | YAML alias (`*parts`) of the same list, kept so the v1 readers (`agent/tools.py` `_load_yaml_list(..., "items")`, `report.py` `_load_catalog_parts`) keep working. New code must read `parts`. |

Conventions used when the catalog was rebuilt (2026-11-03):

- `source` is the page the dimensions or mass were taken from; further pages are quoted in `notes`.
  A part with a `source` is **also** `provisional: true` whenever one of its numbers is derived
  (e.g. a body-tube mass computed from ID/OD/length and a paper density) or assumed (packed
  parachute diameter, ring/hook masses). The derivation is always written in `notes`.
- No Japanese retailer quoting these parts in JPY was found, so every `price_jpy` is a converted
  USD retail price (per single unit, pack price divided by pack count) and is provisional.
- Estes tube/nose-cone/parachute geometry and masses come from Estes product pages plus the public
  OpenRocket component database (`Estes-legacy.orc`, `LocPrecision-legacy.orc` in
  github.com/openrocket/openrocket). Estes publishes no part masses; tube masses are computed with
  the OpenRocket spiral-kraft density (849 kg/m3), which reproduces LOC's published 7.8 oz for its
  3.0 in tube within 3 %.
- Bottle-tier pressure limits follow the JAXA Space Education Center water-rocket manual
  (carbonated-drink bottles only; never above 7 atm, 4-5 atm recommended -> `max_gauge_pressure_pa`
  500 kPa on bottles, 600-700 kPa on launchers as the hard limit).
- Ids are stable and lowercase; BOM keyword matching in `report.py` relies on ids containing
  `tube`, `nose`, `fin`, `parachute`, `bottle`, `nozzle`, `shock`/`recovery`, so keep those words.

Fields beyond the schema table that readers may use (documented in `PARTS_SCHEMA.md`):
`fits_tube_ids` (list, on `motor_mount`), `motor_diameter_m: 0.013` (mini motors), and the
top-level `price_jpy_basis`.

## motors/*.eng

RASP format. Header comment lines that the loader (`physics/solid.py`) reads: `; source:`,
`; license:`, `; provisional:`. Informational lines added for the catalog readers:
`; diameter_m`, `; length_m`, `; delays: a,b,c`, `; propellant_mass_kg`, `; total_mass_kg`,
`; price_jpy` (converted, provisional). The RASP data line still carries the authoritative
diameter / length / delays / masses that `load_motor` parses.

All bundled curves are **synthetic** (a 5-point shape whose integral, peak and burn time match the
cited manufacturer or NAR/TRA certification summary); none copies a measured curve, so every file
is `provisional: true`. `dummy_*.eng` are placeholders used by the tests.

| file | basis |
| --- | --- |
| `estes_A8`, `estes_B6`, `estes_C6`, `estes_D12`, `estes_E12` | Estes product pages |
| `aerotech_F32T` | NAR S&T certification sheet (via thrustcurve.org) |
| `aerotech_G80T` | thrustcurve.org summary, NAR data sheet |
| `aerotech_H128W`, `aerotech_I200W` | thrustcurve.org summary (TRA certified); high-power, flag in the checklist |
| `aerotech_H180W`, `aerotech_I161W`, `aerotech_I284W`, `aerotech_J350W`, `aerotech_J415W` (RMS reloads), `aerotech_I205W`, `aerotech_I140W`, `aerotech_I280DM`, `aerotech_J435WS`, `aerotech_J250W` (DMS single-use) | thrustcurve.org summaries (TRA certified); burn time = total impulse / published average thrust; high-power |

Prices: every real motor file carries `; price_jpy:` (AeroTech order form rev 03/26/25,
https://cdn.shopify.com/s/files/1/0615/7592/1878/files/Model_and_HP_03.26.25.pdf, at 150 JPY/USD;
Estes pages); reload kits also carry `; hardware:` / `; hardware_price_jpy:` (the reusable RMS case,
billed once). The design chain offers `dummy_*` only when no certified motor passes.

`estes_A8`: the published 2.50 N-s over 0.80 s gives an average thrust of ~3.1 N, so the "8"
in its designation is not the average thrust (Estes' historical rating). `tests/test_solid.py`
exempts this one motor from its label-vs-average-thrust check (`_LABEL_IS_NOT_AVERAGE_THRUST`)
instead of faking the curve; the integral, peak and burn time still match the Estes page.
