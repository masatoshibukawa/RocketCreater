# Bottle thermal and structural study

日本語概要 — 既存の試作機の荷重・温度を使い、フィン、搭載部、胴体を階層的に調べる再現用の解析です。材料物性・接合部・熱条件は未測定の仮定であり、製作・飛行の合格証明ではありません。

`assumptions.json` contains explicitly provisional SI inputs. `prepare.py` reads an existing build packet (`assembly.json`, `design.json`, `run.json`), reruns the repository's trajectory and records source hashes and the load envelope. The previous CFD failed absolute-drag validation, so these loads still depend on the original provisional constant drag model.

From the repository root, using Python with the project dependencies:

```powershell
python scenarios/thermostructural/prepare.py PATH_TO_PACKET output/study
```

In MATLAB R2025b, from this directory:

```matlab
input = jsondecode(fileread('../../output/study/input.json'));
cfg = jsondecode(fileread('assumptions.json'));
result = run_study('../../output/study/input.json','../../output/study');
```

The full run needs MATLAB, Control System Toolbox and Partial Differential Equation Toolbox. From the repository root after completion:

```powershell
python scenarios/thermostructural/verify.py output/study
python scenarios/thermostructural/report.py output/study
```

Open `output/study/index.html`. Its figures are embedded, so this one HTML file is portable. The raw `results.json`, source `input.json`, individual JSON/PNG files and `collar-fields.mat` retain numerical evidence. A `run-status.json` marker prevents report generation after an interrupted rerun, even if an older results file still exists. This scenario is not yet registered in the application agent's candidate pool.

## Hierarchy and applicability gates

| Layer | Target and category | Phase | Inputs | Method and outputs | Evaluation / next method |
| --- | --- | --- | --- | --- | --- |
| Low | Material and joint properties | Bench / temperature conditioning | Specimen, thickness, humidity, temperature, attachment | Measured E/G, strength, spring stiffness, damping, conductivity, CTE | Currently absent. All properties are provisional; no strength safety factor can be certified. |
| Middle | Fin bending and twist | Fixed-speed ascent snapshots | Geometry, CN slope, dynamic pressure, E/G, root springs, aerodynamic offset | Tapered Euler–Bernoulli integration and discrete torsion equilibrium; deflection, stress, twist and divergence pressure | Rotation <=5°, deflection/span <=0.1 and q<0.9 q_div are provisional model-usage gates. Otherwise require nonlinear plate/shell and aerodynamic coupling. |
| Middle | Payload load path | Launch / opening / landing | Masses, mount stiffness/damping, proper acceleration | Two-DOF base excitation; relative travel, transmitted forces | At the assumed 8 mm travel limit, stop interpreting the linear continuation as physical force. Require contact and a nonlinear pad law. |
| Middle | Body and nonpressurised sleeve | Pressure load / isolated inertia scenario | Pressure, thickness, diameter, axial force, eccentricity | Thin-wall membrane and section resultants | Stress demand only. Local geometry, creep, seam/peel, imperfections, allowables and manufacturer limits remain unresolved. |
| Middle | Gas, wall, fin and payload temperature | Water expulsion / separate unpressurised wait | Thermal properties, sunshine, convection and radiation | Finite-volume wall and lumped thermal circuit | Transfer temperatures to provisional stiffness and thermal strain. No coupled hot-gas flight simulation. |
| Middle | Printed payload collar | Isolated load envelope | Actual planned annulus dimensions, assumed solid isotropic E/CTE, uniform top load, rigid outer clamp | 3D quadratic solid FEM; mechanical, thermal and combined cases | Check free-node equilibrium, nodal reaction, superposition and mesh refinement away from clamp. Printed anisotropy/contact/strength are absent. |
| High | Local attitude | Dry coast at a fixed flow state | Only applicable fin cases, CN/CP, dry CG, rod inertia, assumed pitch damping | Linear pitch and Lyapunov decay | Conditional local result only. No flutter, variable-mass 6DOF or whole-flight proof. Missing inputs or invalid lower-layer results keep qualification blocked. |

The runner evaluates a fixed sensitivity set and applies these gates deterministically; it does not claim to have an LLM selecting the next analysis. Its output identifies the evidence and higher-fidelity methods the larger harness needs next.

## Mechanical models

`fin_response.m` assigns the set CN slope to the two active fins in a pitch plane, with a chord-weighted span load. The torsion model solves `(K_theta - q B) theta = q B alpha`; the signed aerodynamic offset is swept over -0.25, 0 and +0.25 chord. This range is a sensitivity assumption, not a measured uncertainty distribution. Above the first static divergence point, no finite displacement is reported. A two-slipping-ply case uses one-quarter bending/torsion stiffness at unchanged total thickness; its outer-ply bending stress is twice the bonded diagnostic at the same load. Root bending and twist springs are independent.

Finite-incidence bending changes the projection by `cos(beta)^2`; this produces a secant diagnostic. The zero-incidence local pitch derivative instead uses the linear torsion gain because the bending projection correction is second order. Every computed CN/CP still depends on the unvalidated strip-load approximation. The warm fin case uses the sun-wait temperature and an explicitly assumed E/G/root-stiffness multiplier; no claimed real material softening curve is used.

`payload_response.m` uses mass-normalised modal damping and proper base acceleration (including the gravity-related support load when relevant). The residual-air impulse from the trajectory is replaced by 10/30/100 ms half-sine pulses with the same impulse; these are sensitivity cases, not resolved gas discharge. Water-phase forcing is interpolated from the existing flight; subsequent drag is omitted in this short shock screen. A symmetric landing pulse of duration `2 stop_distance / landing_speed` gives the selected rigid-body stopping distance. The three opening pulses use a separately assumed 3 m/s velocity change. They are not a prediction of the existing idealised apogee opening. Dashed plot segments and reported maximum travel beyond the stop are **linear extrapolations**, not physical motion after contact.

`body_response.m` separates pressure-vessel membrane stresses from nonpressurised sleeve axial/bending stress and ideal-cylinder buckling. It does not combine maxima from different phases into one claimed simultaneous load. Von Mises stress is a scalar diagnostic, not a validated PET or printed-part failure criterion. No manufacturer pressure rating is inferred.

`collar_fem.m` models one 63/82/2.4 mm collar carrying the full chosen payload load `m_payload * peak_base_proper_acceleration`. This demand is not a bound on bottoming/contact force. It combines that load with the thermal circuit's warm-ring temperature as an illustrative envelope, without asserting that the extrema occur together. The outer cylindrical face is fully fixed; distributed top traction replaces real contact. Use an actual contact geometry and printed material law before interpreting strength. Point stress at the ideal clamp and stress-recovered boundary tractions are not converged; the script retains that diagnostic separately from the conservative FE nodal force balance. Interior stress excludes nodes within 2 mm of the outer clamp and 1 mm of the inner edge.

## Numerical verification

The MATLAB assertions check uniform thermal equilibrium, wall refinement, a uniform cantilever's closed-form displacement, fin refinement, mass-normalised modes, shock impulse, time refinement, membrane force equilibrium, unconstrained-node equilibrium and FEM superposition. `verify.py` independently checks solar energy balance, virtual-work fin displacement, mode frequencies, pressure-force balance and propagation of applicability flags. The collar uses 3/1.5/0.75 mm maximum mesh sizes. The final two meshes determine displacement and interior-stress convergence; a converged local maximum at the clamp is not claimed. Numerical verification is separate from physical validation.

## Thermal model

- Integrate liquid-expulsion volume with `p V^n = constant`, prescribed gas temperature `T V^(n-1) = constant`, and a 12-cell finite-volume wall. Repeat with 24 cells. Exponents 1.2 and 1.4 are sensitivity cases, not a validated uncertainty interval for this bottle.
- Gas-to-wall heat transfer is one way. The wall heat flux does not update the imposed gas pressure or temperature; humidity, condensation, liquid-side heat transfer and the subsequent gas-only blowdown are unresolved.
- Separately integrate a three-node payload-bay thermal circuit and an exposed-fin node during an **unpressurised** ten-minute wait. Absorptivities 0.2 and 0.8, side-on sunlight, ambient-temperature radiative surroundings and constant convection are assumptions. No hot pressurised launch is simulated.
- Thermal expansion mismatch is reported as free displacement. Stress depends on constraints. The temperature-dependent stiffness factor is an illustrative sensitivity law, not a material data sheet.
- Checks include preserved uniform thermal equilibrium and through-thickness refinement. This is numerical verification, not experimental validation.

## Sources

- [Romanelli, Bove and González, Air expansion in a water rocket](https://arxiv.org/abs/1211.1923), polytropic expansion, humidity and condensation. The exponent depends on initial conditions.
- [NASA, Isentropic compression](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/isentrophic-compression/), ideal gas temperature/pressure/volume relations.
- [MIT, Introduction to structural mechanics](https://ocw.mit.edu/courses/22-312-engineering-of-nuclear-reactors-fall-2015/eb49bc4f3e701be60ca651c5a109312f_MIT22_312F15_note_L4.pdf), thin-wall membrane stresses.
- [Georgia Tech, Divergence](https://aeresources.gatech.edu/aeroelasticity/Webpage/Divergence/Theory/Theory.php), static twist/load feedback and applicability limits.
- [MathWorks, Thermal stress analysis](https://www.mathworks.com/help/pde/ug/thermal-stress-analysis-of-jet-engine-turbine-blade.html), separate mechanical, thermal and combined loading workflows.

No measured strength allowables, egg fracture criterion, bond peel resistance or manufacturer pressure/temperature limits are supplied. Outputs must retain an unresolved physical-safety status.
