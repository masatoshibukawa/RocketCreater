"""Run one independent GPU wind-tunnel case from a generated assembly.json."""

import argparse
import json
import math
import os
import time
from pathlib import Path

import numpy as np


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("assembly", type=Path)
    p.add_argument("output", type=Path, help="new directory for this case")
    p.add_argument("--shape", choices=["empty", "sphere", "flat", "recess"], default="recess")
    p.add_argument("--cells", type=int, default=16, help="cells per body diameter")
    p.add_argument("--width", type=float, default=8, help="periodic transverse width in diameters")
    p.add_argument("--upstream", type=float, default=3, help="inlet-to-nose distance in diameters")
    p.add_argument("--sphere-re", type=float, default=100, help="Reynolds number of sphere control")
    p.add_argument("--angle", type=float, default=0, help="in-plane incidence in degrees")
    p.add_argument("--cant", type=float, default=0, help="equal-handed fin cant in degrees")
    p.add_argument("--times", type=float, default=36, help="duration in D/U; average last half")
    p.add_argument("--speed", type=float, default=15, help="rocket free-stream speed, m/s")
    p.add_argument("--lattice-speed", type=float, default=0.075)
    args = p.parse_args()
    if (
        not 6 <= args.cells <= 64
        or not 5 <= args.width <= 16
        or args.times < 2
        or not 0 < args.lattice_speed < 0.1
        or not 0 < args.speed <= 35
        or not 2 <= args.upstream <= 10
        or not 1 <= args.sphere_re <= 2e5
        or max(abs(args.angle), abs(args.cant)) > 15
    ):
        p.error("unsupported geometry, time, speed or angle")
    # On Windows this can point to MATLAB's bin/win64 for NVRTC.
    dll_dir = os.environ.get("CFD_CUDA_DLL_DIR")
    dll_handle = os.add_dll_directory(dll_dir) if os.name == "nt" and dll_dir else None
    import cupy as cp

    model = json.loads(args.assembly.read_text(encoding="utf-8"))
    dims = model["dimensions_mm"]
    diameter = dims["body_diameter"]
    g = np.array(
        [
            dims[k]
            for k in (
                "overall",
                "nose_length",
                "fin_root",
                "fin_tip",
                "fin_span",
                "fin_sweep",
                "fin_tail_inset",
                "skirt_length",
            )
        ]
        + [model["loaded_cg_mm"]]
    )
    gpu_geometry = cp.asarray(
        np.r_[g / diameter, math.tan(math.radians(args.cant)), args.upstream], dtype="f"
    )
    d, speed = args.cells, args.lattice_speed
    nx, ny = round((15 + args.upstream) * d), 2 * round(args.width * d / 2)
    nz, n = ny, nx * ny * ny
    if n * 19 >= 2**31:
        p.error("grid exceeds 32-bit indexing")
    if n * 19 * 4 * 2 > 0.80 * cp.cuda.runtime.memGetInfo()[0]:
        p.error("grid exceeds available GPU memory")
    shape = ["empty", "sphere", "flat", "recess"].index(args.shape)
    # Isothermal standard-air approximation. Sphere is a separate Re=100 benchmark.
    reynolds = args.sphere_re if shape == 1 else args.speed * (diameter / 1000) / 1.5e-5
    tau = 0.5 + 3 * speed * d / reynolds
    cs = 0 if shape == 1 and reynolds <= 200 else 0.16
    angle = math.radians(args.angle)
    along, across = math.cos(angle), math.sin(angle)
    code = Path(__file__).with_name("bottle_flow.cu").read_text(encoding="utf-8")
    module = cp.RawModule(code=code, options=("--std=c++11",))
    setup, advance, cut = (module.get_function(k) for k in ("setup", "advance", "cut"))
    mask = cp.empty(n, cp.uint32)
    src = cp.zeros((19, n), cp.float32)
    dst = cp.zeros_like(src)
    blocks, threads = ((n + 127) // 128,), (128,)
    sizes = tuple(np.int32(a) for a in (nx, ny, nz, d))
    inlet = tuple(np.float32(a) for a in (speed * along, speed * across))
    setup(blocks, threads, (mask, src, *sizes, np.int32(shape), gpu_geometry, *inlet))
    params = (
        *sizes,
        *inlet,
        np.float32(tau),
        np.float32(cs),
        np.float32(g[-1] / diameter + args.upstream),
    )
    sample_every = max(1, round(0.20 * d / speed))
    steps = math.ceil(args.times * d / speed / sample_every) * sample_every
    forces = cp.zeros((steps // sample_every, 6), cp.float32)
    args.output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    for step in range(steps):
        sample = (step + 1) % sample_every == 0
        advance(
            blocks,
            threads,
            (src, dst, mask, *params, np.int32(sample), forces[step // sample_every]),
        )
        src, dst = dst, src
        if step % 250 == 0:
            cp.cuda.Stream.null.synchronize()
    coeff = forces.get().astype(float) / (0.5 * speed**2 * math.pi * d * d / 4)
    cd = coeff[:, 0] * along + coeff[:, 1] * across
    cl = -coeff[:, 0] * across + coeff[:, 1] * along
    times = np.arange(1, len(cd) + 1) * sample_every * speed / d
    history = np.column_stack([times, cd, cl, coeff])
    names = ["tU_D", "Cd", "Cl", "Cx", "Cy", "Cz", "Croll", "Cpitch_y", "Cm_z"]
    np.savetxt(
        args.output / "history.csv", history, delimiter=",", header=",".join(names), comments=""
    )
    sample = history[times > times[-1] / 2, 1:]
    mean = sample.mean(axis=0)
    prev, last = np.array_split(sample, 2)
    plane = cp.empty((4, ny, nx), cp.float32)
    cut(((nx * ny + 127) // 128,), threads, (src, mask, plane, *sizes[:3]))
    u, v, dr, solid = plane.get()
    max_dr = float(cp.max(cp.abs(src.sum(axis=0))).get())
    if not (np.isfinite(history).all() and np.isfinite(max_dr) and max_dr < 0.2):
        raise RuntimeError(f"invalid density or force history: max |rho-1|={max_dr}")
    np.savez_compressed(
        args.output / "slice.npz",
        ux_U=u / speed,
        uy_U=v / speed,
        pressure_coeff=2 * dr / (3 * speed**2),
        solid=solid.astype(bool),
    )
    result = dict(
        shape=args.shape,
        assembly=model["key"],
        dimensions_mm=dims,
        cg_mm=model["loaded_cg_mm"],
        prior_cd=model["axial_cd"],
        d=d,
        grid=[nx, ny, nz],
        width_D=ny / d,
        upstream_D=args.upstream,
        Re=reynolds,
        lattice_Ma=speed * math.sqrt(3),
        Cs=cs,
        tau=tau,
        speed_mps=args.speed if shape != 1 else None,
        angle_deg=args.angle,
        cant_deg=args.cant,
        steps=steps,
        averaging_tU_D=[times[-1] / 2, times[-1]],
        mean=dict(zip(names[1:], mean, strict=True)),
        split_window_difference=dict(zip(names[1:], last.mean(0) - prev.mean(0), strict=True)),
        max_abs_density_departure=max_dr,
        seconds=time.monotonic() - start,
    )
    (args.output / "case.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        f"{args.output.name}: Cd={mean[0]:.5f}, Cl={mean[1]:.5f}, "
        f"roll={mean[5]:.5f}, Mz={mean[7]:.5f}, {result['seconds']:.1f} s",
        flush=True,
    )
    if dll_handle is not None:
        dll_handle.close()


if __name__ == "__main__":
    main()
