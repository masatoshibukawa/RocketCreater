# One concrete 1.5 L candidate

This is a continuation of the D02 1.5 L / 60 g payload study, separate from the
2 L printing trial. The catalog `bottle_concrete_fin.yaml` specifies Iten Resiten
G10FR4 cut plates, Prusament PETG external shoes, M2 hardware and skirt retention.
The 1.0 mm laminate is a requested procurement specification: stock, tolerance,
and properties at this thickness have not been confirmed. The manufacturer's
modulus/density refer to typical production material; test thickness is 3.175 mm.
No typical strength has been promoted to a design allowable. The PETG material
requires a compatible 1.75 mm printer, not the lab's 2.85 mm UltiMaker profile.

The four free fins have 120 mm span, 70/35 mm chords and 35 mm sweep. A captured
10.5 mm tab sits in a 12 mm high external shoe. The modeled shoe envelope is
70 x 12 x 7 mm, including two 3 mm jaws and the 1 mm plate. No pressure-bottle
drilling is specified. Slot clearance, skirt fit, strap slip, bolt preload,
print anisotropy and creep remain unresolved assembly properties.

Mass and CG include the laminate, printed solid envelope (less the tab slot),
and stated hardware/strap allowances. Exact polygon moments replace the old
fin local-inertia estimate; other local inertias remain documented surrogates.
The previous assembly's pass flags and holdout statistics are invalidated.

```text
python scenarios/concrete_fin/run.py prepare output/concrete-01 --input PRIOR/input.json
python scenarios/concrete_fin/run.py tunnel output/concrete-01 --cells 24
python scenarios/concrete_fin/run.py assess output/concrete-01 --solver PATH/ccx.exe
```

Before assessment, run `scenarios/cfd/run_flow.py` for `grid-d16-a005`,
`grid-d24-a005`, `grid-d28-a005` under the candidate directory: speed 18 m/s,
angle 5 degrees, flat body, interpolated wall, 1 mm fin, width 10D, upstream 3D,
40 D/U, rotated geometry and surface loads. The table uses 8 and 30 m/s with
0/5/10/15/45/90/135/180 degrees. The independent 18 m/s case checks interpolation.
These checks do not cover every angle or validate the turbulence model.

The workflow evaluates five 6DOF scenarios and recovers balanced section loads.
Each fin's CFD normal force and two root moments are transferred to the FEM mesh
using nonnegative face weights with matching first moments. In-plane traction is
not included. Force- and bending-governing ascent events are retained separately.
This is a frozen follower-load analysis, not moving-fin FSI. Mesh agreement does
not qualify material or attachment failure limits.

## Stability theorem checks

The initial analytic check is for the **defined frozen oscillator**
`I e'' + c e' + k e = 0`, with fixed air-aligned trim and no forcing. For
positive I, k and c, energy sublevels are compact/invariant, `V'=-c e'^2`,
and the largest invariant subset of `e'=0` is the origin. LaSalle therefore
establishes asymptotic stability of that linear model. Zero restoring stiffness
or zero damping must not pass the same conclusion.

The flight check builds a scheduled two-state reduction using CFD moment slope,
modeled inertia and aerodynamic rate damping. Grönwall bounds are for a precisely
defined piecewise-affine interpolation of those matrices over the finite ascent
interval. Endpoint logarithmic-norm maxima enclose each affine segment. This
cannot certify the original nonlinear 6DOF system, unsampled model uncertainty,
trim motion, mass-flux angular terms, flexure/slosh or event transitions.

Barbalat requires infinite-horizon conditions, including uniform continuity of
`W=-V'` and a finite integral. Even `W -> 0` needs an additional state-detection
argument to imply `e -> 0`. A finite flight trace supplies neither proof, so the
workflow reports those prerequisites as missing rather than claiming convergence.

References: [LaSalle lecture, H. Khalil](https://www.egr.msu.edu/~khalil/NonlinearSystems/Sample/Lect_10.pdf),
[Grönwall, R. Howard](https://people.math.sc.edu/howard/Notes/gronwall.pdf),
[Lyapunov and Barbalat, B. Yao](https://engineering.purdue.edu/~byao/Research/Supplements/Lyapunov.pdf).
