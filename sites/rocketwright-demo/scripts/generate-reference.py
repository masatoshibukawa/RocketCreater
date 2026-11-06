"""Generate browser parity fixtures from the committed Python model, without cloud calls."""
import hashlib
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root))

from rocketwright.physics.water import simulate
from rocketwright.schema import BottleDesign, Env

base = dict(target=20, volume=1.5, fill=35, pressure=330, dryMass=180, payload=60, nozzle=9, parachute=0.6, budget=3000)
cases = [
    ("standard", {}),
    ("two_litres", dict(volume=2, fill=30, dryMass=220)),
    ("low_fill", dict(fill=15, pressure=250)),
    ("high_fill", dict(fill=75, pressure=150)),
    ("does_not_lift", dict(volume=3, fill=80, pressure=50, nozzle=5, dryMass=500, payload=200)),
    ("light_payload", dict(payload=0, dryMass=80, pressure=400, nozzle=12)),
    ("small_chute", dict(parachute=0.3, payload=200)),
]
rows = []
for name, overrides in cases:
    i = base | overrides
    d = BottleDesign(bottle_volume_m3=i["volume"] / 1000, water_fill_frac=i["fill"] / 100,
                     initial_gauge_pressure_pa=i["pressure"] * 1000, nozzle_diameter_m=i["nozzle"] / 1000,
                     dry_mass_kg=i["dryMass"] / 1000, payload_mass_kg=i["payload"] / 1000,
                     has_fins=True, has_parachute=True, parachute_diameter_m=i["parachute"])
    result = simulate(d, Env(rail_length_m=1.5), target_apogee_m=i["target"])
    rows.append(dict(name=name, input=i, metrics=result.metrics))
sources = {str(p.relative_to(root)).replace("\\", "/"): hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
           for p in [root / "rocketwright/physics" / (name + ".py") for name in ("water", "recovery", "atmosphere")]}
destination = Path(__file__).resolve().parents[1] / "tests/python-reference.json"
destination.parent.mkdir(exist_ok=True)
destination.write_text(json.dumps(dict(sources=sources, cases=rows), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Generated {len(rows)} Python reference cases.")
