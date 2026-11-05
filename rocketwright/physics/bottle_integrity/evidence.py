"""Specimen evidence contracts and fit/holdout checks; examples never become real evidence."""

import hashlib
from pathlib import Path

import numpy as np
from pydantic import Field

from .schema import Strict


class EvidenceRecord(Strict):
    id: str = Field(min_length=1)
    article: str = Field(min_length=1)
    component: str = Field(min_length=1)
    method: str = Field(min_length=1)
    source_file: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    measured: bool
    temperature_c: float
    specimen_count: int = Field(ge=1)
    orientation: str
    manufacturing: str
    reviewed_by: str | None = None
    applicable_min: float
    applicable_max: float


REQUIRED = {
    "geometry": "article dimensions, wall thickness map, attachment and print orientation",
    "material": "direction/temperature dependent stress-strain, failure and creep observations",
    "mount": "pad compression, damping, contact area and payload fracture load",
    "joint": "bond/fastener pull-out and support compliance",
    "pressure": "manufacturer applicability and approved qualified pressure-retention evidence",
    "thrust": "time-resolved thrust, pressure and temperature including residual air",
    "aerodynamics": "independent force/moment measurements across Reynolds number and incidence",
    "inertia": "wet/dry CG and principal inertias",
    "thermal": "conductivity, heat capacity, expansion and interface conductance",
    "modes": "assembled modes and damping with attachment compliance",
    "recovery": "deployment timing, inflation loads, attachment strength and landing tests",
    "operations": "launcher restraint/release, recovery area and operational review",
}


def audit(records, root: Path):
    root = Path(root).resolve()
    accepted = []
    rejected = []
    for raw in records:
        record = EvidenceRecord.model_validate(raw)
        source = (root / record.source_file).resolve()
        reasons = []
        if not source.is_relative_to(root):
            reasons.append("source_outside_evidence_directory")
        elif not source.is_file():
            reasons.append("source_missing")
        elif hashlib.sha256(source.read_bytes()).hexdigest() != record.source_sha256:
            reasons.append("source_hash_mismatch")
        if not record.measured:
            reasons.append("synthetic_or_assumed")
        if not record.reviewed_by:
            reasons.append("applicability_review_missing")
        if record.applicable_max <= record.applicable_min:
            reasons.append("invalid_coverage")
        if reasons:
            rejected.append({"id": record.id, "reasons": reasons})
        else:
            accepted.append(record.model_dump())
    covered = {r["component"] for r in accepted}
    return {
        "records": accepted,
        "rejected": rejected,
        "missing": [k for k in REQUIRED if k not in covered],
        "qualification": "requires_article_specific_review; manifest alone does not qualify",
    }


def fit_curve(x, force, *, degree=1, holdout=None):
    """Fit measured stiffness laws without silently reusing fitting data as validation."""
    x = np.asarray(x, dtype=float)
    force = np.asarray(force, dtype=float)
    if x.ndim != 1 or x.shape != force.shape or len(x) < degree + 2 or degree not in (1, 2, 3):
        raise ValueError("Need paired measurements with enough independent points")
    if not np.isfinite(x).all() or not np.isfinite(force).all() or np.ptp(x) <= 0:
        raise ValueError("Nonfinite or degenerate measurements")
    coefficients = np.polynomial.polynomial.polyfit(x, force, degree)
    error = np.polynomial.polynomial.polyval(x, coefficients) - force
    result = {
        "coefficients_ascending": coefficients.tolist(),
        "fit_rmse": float(np.sqrt(np.mean(error**2))),
        "coverage": [float(min(x)), float(max(x))],
        "validated": False,
    }
    if holdout is not None:
        hx, hy = np.asarray(holdout, dtype=float).T
        if len(hx) < 2 or not np.isfinite(holdout).all():
            raise ValueError("Invalid independent holdout measurements")
        residual = np.polynomial.polynomial.polyval(hx, coefficients) - hy
        result["holdout_rmse"] = float(np.sqrt(np.mean(residual**2)))
        result["holdout_within_coverage"] = bool(np.all((hx >= min(x)) & (hx <= max(x))))
    return result
