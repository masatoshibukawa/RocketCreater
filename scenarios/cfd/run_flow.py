"""Run one independent GPU wind-tunnel case from a generated assembly.json."""

import argparse
import atexit
import hashlib
import json
import math
import os
import time
from pathlib import Path

import numpy as np


def sample_volume(cp, module, src, mask, sizes, stride):
    nx, ny, nz = map(int, sizes[:3])
    shape = tuple(math.ceil(s / stride) for s in (nz, ny, nx))
    vol = cp.empty((2, *shape), cp.float32)
    module.get_function("volume")(
        ((math.prod(shape) + 127) // 128,), (128,), (src, mask, vol, *sizes[:3], np.int32(stride))
    )
    velocity, inside = vol.get()
    return velocity, inside.astype(bool)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("assembly", type=Path)
    p.add_argument("output", type=Path, help="new directory for this case")
    shapes = ["empty", "sphere", "flat", "recess", "rounded_flat"]
    p.add_argument("--shape", choices=shapes, default="recess")
    p.add_argument("--cells", type=int, default=16, help="cells per body diameter")
    p.add_argument("--width", type=float, default=8, help="periodic transverse width in diameters")
    p.add_argument("--upstream", type=float, default=3, help="inlet-to-nose distance in diameters")
    p.add_argument("--sphere-re", type=float, default=100, help="Reynolds number of sphere control")
    p.add_argument("--angle", type=float, default=0, help="in-plane incidence in degrees")
    p.add_argument(
        "--rotate-geometry",
        action="store_true",
        help="rotate the body, keeping flow along open x boundaries; allows 180 degrees",
    )
    p.add_argument(
        "--surface-loads",
        action="store_true",
        help="save time-averaged wall-adjacent pressure and distributed total loads",
    )
    p.add_argument("--cant", type=float, default=0, help="equal-handed fin cant in degrees")
    p.add_argument("--wall", choices=("halfway", "interpolated"), default="halfway")
    p.add_argument("--fin-thickness-mm", type=float, default=0)
    p.add_argument("--times", type=float, default=36, help="duration in D/U; average last half")
    p.add_argument("--speed", type=float, default=15, help="rocket free-stream speed, m/s")
    p.add_argument("--nu", type=float, default=1.5e-5, help="physical kinematic viscosity, m²/s")
    p.add_argument("--lattice-speed", type=float, default=0.075)
    p.add_argument("--volume", action="store_true", help="save a 3-D sampled wake for plotting")
    p.add_argument("--study-position", nargs=2, type=int, help=argparse.SUPPRESS)
    p.add_argument(
        "--preview",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="publish a live progress.html and four PNGs (requires preview packages)",
    )
    p.add_argument(
        "--paired-samples",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="average adjacent lattice steps to check odd/even force sampling bias",
    )
    args = p.parse_args()
    if args.wall == "interpolated" and args.shape not in ("empty", "sphere", "flat"):
        p.error("interpolated walls support empty, sphere and flat geometry")
    if not 0 <= args.fin_thickness_mm <= 10:
        p.error("fin thickness must be in [0,10] mm")
    if args.fin_thickness_mm and args.wall != "interpolated":
        p.error("finite thickness requires interpolated geometry")
    if (
        not 6 <= args.cells <= 64
        or not 5 <= args.width <= 16
        or args.times < 2
        or not 0 < args.lattice_speed < 0.1
        or not 0 < args.speed <= 35
        or not 2 <= args.upstream <= 10
        or not 1 <= args.sphere_re <= 2e5
        or abs(args.cant) > 15
        or abs(args.angle) > (180 if args.rotate_geometry else 15)
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
    rotation_angle = math.radians(args.angle) if args.rotate_geometry else 0.0
    gpu_geometry = cp.asarray(
        np.r_[
            g / diameter,
            math.tan(math.radians(args.cant)),
            args.upstream,
            math.cos(rotation_angle),
            math.sin(rotation_angle),
            args.fin_thickness_mm / diameter,
        ],
        dtype="f",
    )
    d, speed = args.cells, args.lattice_speed
    nx, ny = round((15 + args.upstream) * d), 2 * round(args.width * d / 2)
    nz, n = ny, nx * ny * ny
    if n * 19 >= 2**31:
        p.error("grid exceeds 32-bit indexing")
    if n * 19 * 4 * 2 > 0.80 * cp.cuda.runtime.memGetInfo()[0]:
        p.error("grid exceeds available GPU memory")
    shape = shapes.index(args.shape)
    if not 0 < args.nu < 0.001:
        p.error("--nu must be a positive physical kinematic viscosity below 0.001")
    # Isothermal standard-air approximation. Sphere is a separate Re=100 benchmark.
    reynolds = args.sphere_re if shape == 1 else args.speed * (diameter / 1000) / args.nu
    tau = 0.5 + 3 * speed * d / reynolds
    cs = 0 if shape == 1 and reynolds <= 200 else 0.16
    angle = math.radians(args.angle)
    along, across = math.cos(angle), math.sin(angle)
    transverse_extent = max(g[-1], g[0] - g[-1]) / diameter * abs(math.sin(rotation_angle)) + (
        0.5 + dims["fin_span"] / diameter
    ) * abs(math.cos(rotation_angle))
    if args.rotate_geometry and transverse_extent > args.width / 2 - 0.75:
        p.error("rotated body is too close to the periodic transverse boundaries")
    code = Path(__file__).with_name("bottle_flow.cu").read_text(encoding="utf-8")
    wall_source = Path(__file__).with_name("interpolated_wall.cuh")
    code = code.replace("// WALL_HELPERS", wall_source.read_text(encoding="utf-8"))
    module = cp.RawModule(code=code, options=("--std=c++11",))
    setup, advance, cut = (module.get_function(k) for k in ("setup", "advance", "cut"))
    mask = cp.empty(n, cp.uint32)
    src = cp.zeros((19, n), cp.float32)
    dst = cp.zeros_like(src)
    blocks, threads = ((n + 127) // 128,), (128,)
    sizes = tuple(np.int32(a) for a in (nx, ny, nz, d))
    inlet = tuple(
        np.float32(a)
        for a in ((speed, 0) if args.rotate_geometry else (speed * along, speed * across))
    )
    wall_mode = np.int32(args.wall == "interpolated")
    setup(blocks, threads, (mask, src, *sizes, np.int32(shape), gpu_geometry, *inlet, wall_mode))
    surface_ids = cp.where((mask > 0) & (mask < (1 << 31)))[0].astype(cp.int32)
    lookup = cp.full(n if wall_mode else 1, -1, cp.int32)
    fractions = cp.full((len(surface_ids) if wall_mode else 1, 19), 0.5, cp.float32)
    if wall_mode and len(surface_ids):
        module.get_function("wall_setup")(
            ((len(surface_ids) + 127) // 128,),
            threads,
            (
                mask,
                surface_ids,
                np.int32(len(surface_ids)),
                lookup,
                fractions,
                *sizes,
                np.int32(shape),
                gpu_geometry,
            ),
        )
    wall_args = (lookup, fractions, wall_mode)
    surface_stats = cp.zeros((4, len(surface_ids)), cp.float32)
    surface_count = 0
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
    preview = None
    if args.preview:
        try:
            if __package__:
                from .flow_preview import FlowPreview
            else:
                from flow_preview import FlowPreview
        except ImportError as error:
            print(
                f"CFD preview unavailable ({error}). Install requirements-preview.txt.", flush=True
            )
        else:
            preview = FlowPreview(
                args.output,
                dims,
                args.shape,
                args.angle,
                args.cant,
                args.speed,
                reynolds,
                d,
                args.upstream,
                args.study_position,
            )
            atexit.register(preview.page, "中断")
            print(f"CFD progress: {(args.output / 'progress.html').resolve().as_uri()}", flush=True)
            if args.study_position:
                print(
                    f"Study progress: {(args.output.parent / 'progress.html').resolve().as_uri()}",
                    flush=True,
                )
    nsamples = steps // sample_every
    milestones = {math.ceil(nsamples * f / 4) * sample_every for f in (1, 2, 3)}
    scale = 0.5 * speed**2 * math.pi * d * d / 4 * (2 if args.paired_samples else 1)

    def draw_progress(completed):
        stride = max(1, round(d / 6))
        velocity, inside = sample_volume(cp, module, src, mask, sizes, stride)
        # Use the actual center slice, independent of the stride/parity of the volume.
        plane = cp.empty((4, ny, nx), cp.float32)
        cut(((nx * ny + 127) // 128,), threads, (src, mask, plane, *sizes[:3]))
        data = plane.get()
        count = completed // sample_every
        f = forces[:count, :2].get().astype(float)
        t = np.arange(1, count + 1) * sample_every * speed / d
        preview.snapshot(
            round(100 * completed / steps),
            velocity / speed,
            inside,
            stride,
            data[0] / speed,
            data[3].astype(bool),
            t,
            (f[:, 0] if args.rotate_geometry else along * f[:, 0] + across * f[:, 1]) / scale,
        )

    def publish_progress(completed):
        nonlocal preview
        if preview is None:
            return
        try:
            draw_progress(completed)
        except (MemoryError, OSError, ValueError, RuntimeError) as error:
            print(f"CFD preview stopped ({error}); simulation continues.", flush=True)
            atexit.unregister(preview.page)
            try:
                preview.page("画像更新を停止")
            except OSError:
                pass
            preview = None

    start = time.monotonic()
    for step in range(steps):
        phase = (step + 1) % sample_every
        sample = phase == 0 or (args.paired_samples and phase == sample_every - 1)
        if args.surface_loads and sample and (step // sample_every + 1) * sample_every > steps / 2:
            if len(surface_ids):
                module.get_function("surface_probe")(
                    ((len(surface_ids) + 127) // 128,),
                    threads,
                    (
                        src,
                        mask,
                        surface_ids,
                        np.int32(len(surface_ids)),
                        *sizes[:3],
                        surface_stats,
                        *wall_args,
                    ),
                )
            surface_count += 1
        advance(
            blocks,
            threads,
            (src, dst, mask, *params, np.int32(sample), forces[step // sample_every], *wall_args),
        )
        src, dst = dst, src
        if step % 250 == 0:
            cp.cuda.Stream.null.synchronize()
        if (step + 1) in milestones:
            print(f"{args.output.name}: {100 * (step + 1) / steps:.0f}%", flush=True)
            publish_progress(step + 1)
    del dst
    cp.get_default_memory_pool().free_all_blocks()
    coeff = forces.get().astype(float) / (0.5 * speed**2 * math.pi * d * d / 4)
    if args.paired_samples:
        coeff /= 2
    if args.rotate_geometry:
        for j in (0, 3):
            x, y = coeff[:, j].copy(), coeff[:, j + 1].copy()
            coeff[:, j] = along * x - across * y
            coeff[:, j + 1] = across * x + along * y
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
    surface_summary = None
    if args.surface_loads:
        if __package__:
            from .surface_loads import body_samples, reduce_line
        else:
            from surface_loads import body_samples, reduce_line
        stats = surface_stats.get().astype(float) / surface_count
        stats[1:] /= 0.5 * speed**2 * math.pi * d**2 / 4
        xyz, cf = body_samples(
            surface_ids.get(),
            stats,
            (nx, ny, nz),
            d,
            args.upstream,
            diameter / 1000,
            g[-1] / 1000,
            args.angle,
            args.rotate_geometry,
        )
        cp_wall = 2 * stats[0] / (3 * speed**2)
        np.savez_compressed(
            args.output / "surface-loads.npz",
            position_m=xyz,
            pressure_coeff=cp_wall,
            force_coeff=cf,
        )
        line = reduce_line(xyz, cf, dims["overall"] / 1000, diameter / 1000)
        moment = np.cross(xyz - [g[-1] / 1000, 0, 0], cf).sum(0) / (diameter / 1000)
        residual = np.r_[cf.sum(0), moment] - mean[2:]
        relative = float(np.linalg.norm(residual) / max(np.linalg.norm(mean[2:]), 1e-8))
        line.update(
            integration_relative_residual=relative,
            samples=surface_count,
            pressure_scope="mean pressure at wall-adjacent fluid cell centres",
            load_scope="momentum exchange: total pressure plus viscous contribution",
            case_geometry_sha256=hashlib.sha256(args.assembly.read_bytes()).hexdigest(),
        )
        (args.output / "line-loads.json").write_text(
            json.dumps(line, indent=2) + "\n", encoding="utf-8"
        )
        if not np.isfinite(cp_wall).all() or relative > 2e-4:
            raise RuntimeError(f"surface/total load mismatch: {relative}")
        surface_summary = {
            "samples": surface_count,
            "points": len(xyz),
            "integration_relative_residual": relative,
        }
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
    if args.volume:
        stride = max(1, d // 8)
        velocity, inside = sample_volume(cp, module, src, mask, sizes, stride)
        np.savez_compressed(
            args.output / "volume.npz",
            ux_U=velocity / speed,
            solid=inside.astype(bool),
            stride=stride,
        )
    result = dict(
        shape=args.shape,
        wall_scheme=args.wall,
        fin_thickness_mm=args.fin_thickness_mm,
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
        rotated_geometry=args.rotate_geometry,
        surface_loads=surface_summary,
        geometry_sha256=hashlib.sha256(args.assembly.read_bytes()).hexdigest(),
        source_sha256={
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), Path(__file__).with_name("bottle_flow.cu"), wall_source)
        },
        cant_deg=args.cant,
        steps=steps,
        paired_samples=args.paired_samples,
        averaging_tU_D=[times[-1] / 2, times[-1]],
        mean=dict(zip(names[1:], mean, strict=True)),
        split_window_difference=dict(zip(names[1:], last.mean(0) - prev.mean(0), strict=True)),
        max_abs_density_departure=max_dr,
        seconds=time.monotonic() - start,
    )
    (args.output / "case.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    publish_progress(steps)
    if preview is not None:
        atexit.unregister(preview.page)
    print(
        f"{args.output.name}: Cd={mean[0]:.5f}, Cl={mean[1]:.5f}, "
        f"roll={mean[5]:.5f}, Mz={mean[7]:.5f}, {result['seconds']:.1f} s",
        flush=True,
    )
    if dll_handle is not None:
        dll_handle.close()


if __name__ == "__main__":
    main()
