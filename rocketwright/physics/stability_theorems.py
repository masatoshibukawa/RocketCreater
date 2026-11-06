"""Model-specific theorem checks; a sampled flight is not an asymptotic proof."""

import numpy as np
from scipy.linalg import eigh, solve_continuous_lyapunov


def lasalle_pitch(inertia, stiffness, damping):
    """Exact argument for a frozen, unforced scalar linear pitch oscillator."""
    values = np.array([inertia, stiffness, damping], dtype=float)
    if not np.isfinite(values).all() or inertia <= 0:
        raise ValueError("finite parameters and positive inertia are required")
    if stiffness < 0 or damping < 0:
        status = "unstable_linear_model"
    elif stiffness == 0:
        status = "origin_not_asymptotic: continuum_of_equilibria"
    elif damping == 0:
        status = "stable_not_asymptotic: undamped_oscillations"
    else:
        status = "globally_asymptotic_for_frozen_linear_model"
    return dict(
        status=status,
        model="I*e_ddot+c*e_dot+k*e=0; constant I,c,k; no forcing",
        origin="e=0, e_dot=0 relative to fixed air-aligned trim",
        V="(I*e_dot^2+k*e^2)/2",
        Vdot="-c*e_dot^2",
        zero_derivative_set="e_dot=0" if damping > 0 else "whole_state_space",
        largest_invariant_set="{0}" if stiffness > 0 and damping > 0 else "not_only_origin",
        compact_invariant_sublevels=bool(stiffness > 0 and damping >= 0),
        qualified_for_full_flight=False,
    )


def gronwall_bound(times, matrices, metric=None, disturbance_bound=0.0):
    """Finite-horizon bound for the explicitly piecewise-affine linear A(t) model.

    The maximum endpoint logarithmic norm bounds every matrix on each affine
    segment by convexity. This does NOT enclose the original nonlinear trajectory
    or unobserved parameter variation. Disturbance is measured in the same P norm.
    """
    t, a = np.asarray(times, float), np.asarray(matrices, float)
    if len(t) < 2 or a.shape != (len(t), 2, 2) or np.any(np.diff(t) <= 0):
        raise ValueError("ordered times and matching 2x2 matrices required")
    if not np.isfinite(a).all() or not np.isfinite(t).all() or disturbance_bound < 0:
        raise ValueError("finite inputs and nonnegative disturbance required")
    p = np.eye(2) if metric is None else np.asarray(metric, dtype=float)
    if p.shape != (2, 2) or not np.isfinite(p).all() or not np.allclose(p, p.T):
        raise ValueError("symmetric metric required")
    if np.linalg.eigvalsh(p).min() <= 0:
        raise ValueError("positive definite metric required")
    rates = np.array([eigh(x.T @ p + p @ x, p, eigvals_only=True).max() / 2 for x in a])
    interval_rates = np.maximum(rates[:-1], rates[1:])
    logs = np.r_[0.0, np.cumsum(interval_rates * np.diff(t))]
    # Homogeneous norm gain is retained as log10 even if the bound is very loose.
    additive = 0.0
    additive_history = [0.0]
    for rate, dt in zip(interval_rates, np.diff(t), strict=True):
        if disturbance_bound == 0:
            additive = 0.0
        elif rate * dt > 700 or additive > 1e300:
            raise OverflowError("disturbance bound overflow; rescale or shorten the horizon")
        else:
            integral = np.expm1(rate * dt) / rate if abs(rate) > 1e-12 else dt
            additive = np.exp(rate * dt) * additive + disturbance_bound * integral
        additive_history.append(float(additive))
    return dict(
        time_s=t.tolist(),
        metric=p.tolist(),
        endpoint_logarithmic_norm_per_s=rates.tolist(),
        interval_upper_rate_per_s=interval_rates.tolist(),
        log10_homogeneous_gain=(logs / np.log(10)).tolist(),
        additive_disturbance_bound=additive_history,
        all_intervals_contracting=bool(max(interval_rates) < 0),
        scope="finite horizon of piecewise-affine 2-state model; not nonlinear-flight proof",
    )


def barbalat_eligibility(
    *,
    infinite_horizon,
    bounded_below_V,
    nonpositive_Vdot,
    uniformly_continuous_W,
    detects_state_origin,
):
    """Explicit prerequisites for W=-Vdot -> 0; convergence of W is not e -> 0."""
    conditions = dict(
        infinite_horizon=infinite_horizon,
        bounded_below_V=bounded_below_V,
        nonpositive_Vdot=nonpositive_Vdot,
        uniformly_continuous_W=uniformly_continuous_W,
    )
    eligible = all(v is True for v in conditions.values())
    return dict(
        prerequisites=conditions,
        W_to_zero_proved=eligible,
        state_to_origin_proved=bool(eligible and detects_state_origin is True),
        missing=[k for k, v in conditions.items() if v is not True],
        extra_state_condition=detects_state_origin,
        rule="finite observed decay is not evidence of infinite-horizon uniform continuity",
    )


def flight_screen(assembly, trajectory, table, mass, cfg):
    """Air-aligned pitch reduction using CFD slope, actual modeled I, and rate damping.

    Holds velocity direction fixed, omits translational/flexible/slosh coupling.
    The actual ascent about its nonzero trajectory is not this equilibrium model.
    """
    rows, matrices, times = [], [], []
    length = assembly["dimensions_mm"]["overall"] / 1000
    omega_scale = 10.0  # z=(angle, angular_rate/(10 rad/s)); dimensionless coordinates
    for sample in trajectory["load_samples"]:
        t = sample["time_s"]
        if not trajectory["rail_exit_s"] < t < trajectory["apogee_s"]:
            continue
        speed = float(np.linalg.norm(sample["air_velocity_body_mps"]))
        if speed < table.speeds[0] or speed > table.speeds[-1]:
            continue
        _, cg, inertia = mass.properties(t)
        q = 0.5 * getattr(cfg, "air_density_kg_m3", 1.204) * speed**2
        eps = np.deg2rad(0.1)
        direction = speed * np.array([np.sin(eps), 0, np.cos(eps)])
        # evaluate's transverse moment is restoring for an air direction inclined +eps.
        # Positive air incidence is the negative of positive body-attitude error.
        stiffness = table.evaluate(direction, q, cg)["moment_nm"][1] / eps
        damping = q * table.area * length**2 / (2 * speed) * cfg.pitch_damping
        inertia_pitch = float(inertia[1])
        check = lasalle_pitch(inertia_pitch, stiffness, damping)
        rows.append(
            dict(
                time_s=t,
                stiffness_nm_rad=float(stiffness),
                damping_nm_s_rad=damping,
                inertia_kg_m2=inertia_pitch,
                **check,
            )
        )
        matrices.append(
            [[0, omega_scale], [-stiffness / inertia_pitch / omega_scale, -damping / inertia_pitch]]
        )
        times.append(t)
    if len(times) < 2:
        return dict(completed=False, reason="insufficient in-domain ascent states")
    a = np.asarray(matrices)
    metrics = [np.eye(2)]
    for x in a[[0, len(a) // 2, -1]]:
        if np.linalg.eigvals(x).real.max() < 0:
            metrics.append(solve_continuous_lyapunov(x.T, -np.eye(2)))
    bounds = [gronwall_bound(times, matrices, p) for p in metrics]
    best = min(bounds, key=lambda b: max(b["log10_homogeneous_gain"]))
    return dict(
        completed=True,
        frozen_checks=rows,
        gronwall=best,
        frozen_asymptotic_count=sum(r["status"].startswith("globally_asymptotic") for r in rows),
        analyzed_points=len(rows),
        rate_scale_rad_s=omega_scale,
        scheduled_model=dict(times=times, matrices=matrices, metric=best["metric"]),
        barbalat=barbalat_eligibility(
            infinite_horizon=False,
            bounded_below_V=None,
            nonpositive_Vdot=None,
            uniformly_continuous_W=None,
            detects_state_origin=None,
        ),
        full_flight_stability_proved=False,
        omitted=[
            "velocity-direction dynamics",
            "time-varying trim forcing",
            "mass-flux angular terms",
            "flexible/slosh modes",
            "hybrid launch and canopy events",
            "CFD/model uncertainty",
        ],
    )


def campaign(folder, problem):
    """Use the same host selection gates as other analysis methods."""
    import hashlib
    from pathlib import Path

    from rocketwright.adaptive import Campaign

    def gate(params, output, host):
        p = host.inputs["stability_problem"]
        kind = p.get("kind")
        barbalat = barbalat_eligibility(
            **p.get(
                "barbalat",
                dict(
                    infinite_horizon=False,
                    bounded_below_V=None,
                    nonpositive_Vdot=None,
                    uniformly_continuous_W=None,
                    detects_state_origin=None,
                ),
            )
        )
        return dict(
            recognized_model=kind,
            barbalat_review=barbalat,
            metrics=dict(
                lasalle_eligible=kind == "frozen_pitch" and p.get("unforced") is True,
                gronwall_eligible=kind == "piecewise_affine_pitch",
                barbalat_eligible=barbalat["W_to_zero_proved"],
            ),
        )

    runners = {
        "theorem_gate": gate,
        "lasalle": lambda p, o, h: lasalle_pitch(**h.inputs["stability_problem"]["parameters"]),
        "gronwall": lambda p, o, h: gronwall_bound(**h.inputs["stability_problem"]["parameters"]),
        "barbalat": lambda p, o, h: barbalat_eligibility(
            **h.inputs["stability_problem"]["barbalat"]
        ),
    }
    result = Campaign(
        folder,
        inputs={
            "stability_problem": problem,
            "theorem_code": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
        runners=runners,
        budget_s=30,
    )
    result.run()
    return result
