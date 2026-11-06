"""A traceable laminate/printed-shoe proposal; typical properties are not allowables."""

import copy
import json
from pathlib import Path

import numpy as np
import yaml

from rocketwright.physics.bottle_integrity.schema import AnalysisConfig, Material
from rocketwright.physics.stability import trapezoidal_fin_force
from rocketwright.schema import BottleDesign, FinSet


def polygon_moments(points):
    """Area, centroid and raw second moments of a counter-clockwise polygon."""
    p = np.asarray(points, dtype=float)
    x, y = p.T
    u, v = np.roll(p, -1, axis=0).T
    cross = x * v - u * y
    area = cross.sum() / 2
    if area <= 0:
        raise ValueError("polygon must have positive area")
    mean = np.array([((x + u) * cross).sum(), ((y + v) * cross).sum()]) / (6 * area)
    second = np.array(
        [((x * x + x * u + u * u) * cross).sum(), ((y * y + y * v + v * v) * cross).sum()]
    ) / (12 * area)
    return area, mean, second


def build(packet, specification=None):
    spec = specification or yaml.safe_load(
        (Path(__file__).parents[1] / "catalog/bottle_concrete_fin.yaml").read_text(encoding="utf-8")
    )
    f, mount = spec["fin"], spec["mount"]
    original = packet["assembly"]
    assembly = copy.deepcopy(original)
    design = BottleDesign(**packet["design"])
    cfg = AnalysisConfig(**packet["config"])
    g = assembly["dimensions_mm"]
    g.update(
        fin_span=f["free_span_mm"],
        fin_root=f["root_chord_mm"],
        fin_tip=f["tip_chord_mm"],
        fin_sweep=f["sweep_mm"],
        fin_tab=f["captured_tab_mm"],
        fin_root_offset=f["root_offset_mm"],
        fin_shoe_width=mount["shoe_total_width_mm"],
        fin_thickness=f["thickness_mm"],
    )
    cr, ct, span, sweep, tab, thick = (
        g[k] / 1000
        for k in ("fin_root", "fin_tip", "fin_span", "fin_sweep", "fin_tab", "fin_thickness")
    )
    start = (g["overall"] - g["fin_tail_inset"] - g["fin_root"]) / 1000
    offset = g["fin_root_offset"] / 1000
    radius = g["body_diameter"] / 2000
    points = [(0, -tab), (cr, -tab), (cr, 0), (sweep + ct, span), (sweep, span), (0, 0)]
    area, mean, second = polygon_moments(points)
    fin_mass = 4 * area * thick * f["density_kg_m3"]
    radial2 = second[1] + 2 * (radius + offset) * mean[1] + (radius + offset) ** 2
    transverse = fin_mass * (second[0] - mean[0] ** 2 + radial2 / 2 + thick**2 / 24)
    fin = next(b for b in assembly["bill"] if b["id"] == "carton_fin")
    fin.update(
        name=f"{f['manufacturer']} {f['grade']} 1.0 mm / 4枚",
        mass_g=1000 * fin_mass,
        station_mm=1000 * (start + mean[0]),
        quantity="4 cut plates, captured tabs included",
        allowance_jpy=None,
        basis=f["source"],
        material_status=f["thickness_status"],
        local_inertia_kg_m2=[transverse, transverse, fin_mass * (radial2 + thick**2 / 12)],
    )
    # Outer shoe volume less the actual captured laminate. Bolt holes are not deducted;
    # this is a stated solid-volume upper estimate, not a slicer or scale measurement.
    width = mount["shoe_total_width_mm"] / 1000
    volume = 4 * cr * (offset * width - tab * thick)
    shoe_mass = volume * mount["density_kg_m3"]
    assembly["bill"] += [
        dict(
            id="fin_shoes",
            name="Prusament PETG / eight jaw halves",
            mass_g=1000 * shoe_mass,
            station_mm=1000 * (start + cr / 2),
            quantity="8",
            allowance_jpy=None,
            basis="solid envelope minus laminate slot; holes/fillets not deducted",
        ),
        dict(
            id="fin_fasteners",
            name=mount["fastener"],
            mass_g=mount["fastener_group_mass_assumed_g"],
            station_mm=1000 * (start + cr / 2),
            quantity="8 sets",
            allowance_jpy=None,
            basis="unweighed hardware allowance",
        ),
        dict(
            id="fin_straps",
            name=mount["straps"],
            mass_g=mount["strap_group_mass_assumed_g"],
            station_mm=1000 * (start + cr / 2),
            quantity="2",
            allowance_jpy=None,
            basis="unweighed hardware allowance",
        ),
    ]
    old_dry = design.dry_mass_kg
    payload = design.payload_mass_kg
    water = 1000 * design.bottle_volume_m3 * design.water_fill_frac
    payload_moment = (old_dry + payload) * original["loaded_cg_mm"] - old_dry * original[
        "dry_cg_mm"
    ]
    water_moment = (old_dry + payload + water) * original["wet_cg_mm"] - (
        old_dry + payload
    ) * original["loaded_cg_mm"]
    dry = sum(b["mass_g"] for b in assembly["bill"]) / 1000
    moment = sum(b["mass_g"] / 1000 * b["station_mm"] for b in assembly["bill"])
    assembly.update(
        key=spec["id"],
        variant="laminate_external_shoe",
        dry_mass_g=1000 * dry,
        estimated_dry_mass_g=1000 * dry,
        dry_cg_mm=moment / dry,
        loaded_cg_mm=(moment + payload_moment) / (dry + payload),
        wet_cg_mm=(moment + payload_moment + water_moment) / (dry + payload + water),
        cost_status="purchase quotation and printed mass pending",
        physical_status="proposal_only",
    )
    # This slope/CP is only a beam-screen load model. Flight uses the new CFD table.
    cn, cp = trapezoidal_fin_force(
        2 * (radius + offset),
        FinSet(count=4, root_chord_m=cr, tip_chord_m=ct, span_m=span, sweep_m=sweep),
        start,
    )
    cn *= ((radius + offset) / radius) ** 2
    assembly["fin_set_CNalpha_per_rad"] = cn
    assembly["cp_mm"] = (2 * g["nose_length"] * 2 / 3 + cn * cp * 1000) / (2 + cn)
    for stale in ("holdout", "checks", "mode_hz", "mount_bound", "pitch_rate_per_s"):
        assembly.pop(stale, None)
    assembly["checks"] = {"previous_evidence_invalidated": True, "physical_qualification": False}
    assembly["inertia_scope"] = (
        "exact laminate polygon moments; other BOM local inertias remain surrogates"
    )
    jaw = mount["jaw_thickness_mm"] / 1000
    # Two opposed cantilever jaws in parallel. Full-width, solid, warm E assumption.
    k = 2 * 3 * mount["young_warm_assumption_pa"] * (cr * jaw**3 / 12) / tab**3
    cfg.fin_root_k_n_m = k
    cfg.fin_thickness_m = thick
    cfg.fin_material = Material(
        young_pa=f["young_pa"],
        density=f["density_kg_m3"],
        poisson=f["poisson_assumption"],
        cte=1e-5,
        warm_ratio=f["warm_stiffness_multiplier_assumption"],
        warm_c=45,
        evidence_id="Iten-Resiten-G10FR4-2019-typical-3.175mm",  # not an allowable
    )
    cfg.flight.cant_deg = 0
    return {
        "design": design.model_copy(update={"dry_mass_kg": dry}).model_dump(),
        "assembly": assembly,
        "config": cfg.model_dump(),
        "specification": spec,
        "joint_model": {
            "warm_root_k_n_m": k,
            "scope": "two-jaw beam surrogate; no bolt/contact/strap qualification",
        },
        "fin_polygon_mm": (np.array(points) * 1000).tolist(),
    }


def write_candidate(packet, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    candidate = build(packet)
    for name, value in (
        ("input", candidate),
        ("assembly", candidate["assembly"]),
        ("design", candidate["design"]),
    ):
        (folder / f"{name}.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return candidate
