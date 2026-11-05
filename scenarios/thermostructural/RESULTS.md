# Reference run — 2026-11-05

日本語概要 — 階層をつないだ実計算は完了。仮定した条件ではフィンの大変形と搭載部の底付きが問題となり、実機の安全性・全飛行の安定性は未確定です。

MATLAB R2025b with Control System and PDE toolboxes, plus independent Python/SciPy checks. The input is the existing generated D02/9/carton_wide prototype, not a manufactured specimen. Input JSON hashes are preserved in each run's `input.json` and `results.json`.

| Item | Computed result | Interpretation |
| --- | --- | --- |
| Flight envelope | Maximum speed 26.99 m/s, dynamic pressure 445.13 Pa; water-phase peak proper acceleration 135.13 m/s² | Provisional existing Cd model; previous CFD absolute drag validation failed. |
| Fin applicability | 3 of 24 cases eligible for local pitch; none at the maximum dynamic pressure | Total thickness 1 mm, E=2 GPa, 3° incidence and assumed root springs. The rest exceed small-deformation or divergence limits. |
| Local pitch | Conditional decay rates 2.089–2.457 /s in the three eligible 135 Pa cases | Dry fixed-flow linearisation with assumed damping; no whole-flight or flutter certificate. |
| Payload mount | 7 of 9 shock cases reach the assumed 8 mm stop | All launch and landing cases fail this model-usage gate. Free-vibration settling alone was insufficient. |
| Launch travel | Linear continuation requires 19.34–48.48 mm over assumed air-pulse durations | Not actual motion after contact. Nonlinear pad/contact analysis is required. |
| Landing travel | Linear continuation requires 23.66–27.83 mm for body stop distances 30–5 mm | Uses provisional 2.863 m/s descent speed; does not establish egg survival. |
| Pressure wall | Hoop 45–90 MPa, axial 22.5–45 MPa over assumed thickness 0.4–0.2 mm | 90 mm straight cylinder at the existing 400 kPa design input; no allowable operating pressure inferred. |
| Sun wait | After 600 s: skin 46.82°C, mount 27.93°C, payload 25.40°C, exposed fin 54.33°C | Separate unpressurised case, ambient 35°C, initial 25°C, solar 800 W/m², absorptivity 0.8. |
| 3D collar | 77.73 N load scenario and 27.93°C; finest-mesh displacement 0.01387 mm; interior equivalent stress 0.992 MPa | Solid isotropic 63/82/2.4 mm annulus with a fully fixed outer face; not a print/contact strength qualification. |

## Numerical checks actually performed

- Solar energy-balance relative error below 0.0048%.
- Fin virtual-work comparison relative error below 0.0068%.
- Payload time-refinement relative difference below 0.0051%.
- Collar meshes 3/1.5/0.75 mm, with 5,232 / 22,826 / 162,237 nodes. Last-step displacement difference 1.17%, interior stress difference 3.99%.
- Conservative FE nodal reaction balances the assembled load to about 3.4e-14 relative. Surface-load integration differs from the analytic circular-annulus demand by 0.29%.
- Clamp point stresses **do not converge** (1.306 / 1.379 / 1.979 MPa maxima). Stress-recovered boundary traction errors are also nonmonotonic (2.64 / 1.28 / 4.20%). These observables are explicitly unresolved and are excluded from allowable-strength decisions.
- Thermal wall refinement, uniform equilibrium, analytical beam limit, mode normalisation, pulse impulse, membrane equilibrium and FEM superposition checks passed.
- Report opened in Edge at 1280 and 390 px widths; all five result images loaded, no page errors or horizontal page overflow, and section navigation worked.

The standalone scenario includes the applicability gates; the production web application's search agent has not been connected to these methods. Material strength, temperature-dependent properties, root/tab/adhesive properties, nonlinear contact, detailed pressure-vessel geometry, physical measurements and full flight stability remain unresolved.
