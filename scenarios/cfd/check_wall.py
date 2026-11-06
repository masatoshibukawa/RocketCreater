"""GPU checks of analytic intersections and the actual compiled wall interpolator."""

import json
import os
from pathlib import Path

import numpy as np


def main():
    handle = os.add_dll_directory(os.environ["CFD_CUDA_DLL_DIR"]) if os.name == "nt" else None
    import cupy as cp

    folder = Path(__file__).parent
    code = (
        (folder / "bottle_flow.cu")
        .read_text()
        .replace("// WALL_HELPERS", (folder / "interpolated_wall.cuh").read_text())
    )
    code += r"""
extern "C" __global__ void check(const float *g,float *v,const float *src,
        const unsigned *mask,const int *lookup,const float *fractions) {
    v[0]=exact_distance(1,-.2,0,0,1,0,0,g);
    v[1]=exact_distance(2,2,.7,0,0,-.4,0,g);
    v[2]=exact_distance(2,.5,.4,0,0,-.4,0,g);
    v[3]=exact_distance(2,3.2,1,.1,0,0,-.2,g);
    v[4]=exact_distance(2,2,.6,-.6,0,0,1.2,g);
    v[5]=exact_distance(2,2,.4,-.6,0,0,1.2,g);
    v[6]=fin_distance(3.2,1,0,0,0,0,g);
    for(int j=0;j<3;++j) v[7+j]=reflected(src,mask,lookup,fractions,13+j,1,27,3,3,1);
}
"""
    module = cp.RawModule(code=code, options=("--std=c++11",))
    g = cp.asarray([4, 1, 1, 0.5, 1, 0.3, 0.1, 0, 2, 0, 3, 1, 0, 0.02], dtype="f")
    src = cp.zeros((19, 27), dtype="f")
    src[2, 13:16] = 0.04
    src[2, 14] = 0.08
    src[1, 13:16] = 0.02
    mask = cp.zeros(27, dtype=cp.uint32)
    lookup = cp.zeros(27, dtype=cp.int32)
    lookup[13:16] = cp.arange(3, dtype=cp.int32)
    fractions = cp.full((3, 19), 0.5, dtype="f")
    fractions[:, 1] = cp.asarray([0.25, 0.5, 0.75], dtype="f")
    out = cp.zeros(10, dtype="f")
    module.get_function("check")((1,), (1,), (g, out, src, mask, lookup, fractions))
    expected = np.array([0.2, 0.5, 0.375, 0.45, 2, 0.25, 0, 0.06, 0.08, 1 / 30])
    np.testing.assert_allclose(out.get(), expected, atol=2e-6, rtol=2e-6)
    print(
        json.dumps({"gpu_checks": 10, "max_absolute_error": float(abs(out.get() - expected).max())})
    )
    if handle:
        handle.close()


if __name__ == "__main__":
    main()
