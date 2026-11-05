# Adaptive analysis results — 2026-11-06

The two executed campaigns completed **15 selected actions**: 21 additional GPU
CFD cases, 246 beam-screen candidates (54 material/thickness/root combinations and
192 geometry combinations), 8 nonlinear FEM meshes and 24 flight integrations.
The 24 integrations include baselines and matching damping references; they are
not 24 independent physical conditions. All figures use actual computed outputs.

Public guide: https://rocketwright-bottle-design-guide.taichi-uchida-offici.chatgpt.site/adaptive-analysis.html

## What changed the decisions

1. **A material/mass mismatch was exposed.** The earlier solid-fin structural
   assumption implies 38.64 g for four 1 mm fins including tabs, versus 24 g in the
   BOM. These are inconsistent assumptions, not a measurement error. Reflight now
   updates the fin mass, loaded/wet CG and inertia together.
2. **Stiffness-only changes fail the mission tradeoff.** Under the governing
   crosswind load at 0.24798 s, q=228.671 Pa and incidence=15.0989 degrees, warm
   nonlinear displacement is 100.29 mm for the reference 1 mm assumption,
   2.733 mm for the assumed 20 GPa/1.5 mm/stiffer-root choice, and 4.420 mm for the
   assumed 2 GPa/3 mm/stiffer-root choice. Temperature is 44.8369 C. Mesh changes
   are below 2% for max displacement and p95 stress. The load is slightly outside
   the declared 15-degree low-angle model range; this remains an extrapolated
   demand comparison. Frozen follower pressure does not recalculate the fluid.
3. **Extra mass reduces conditional altitude.** With the original rigid CFD table
   held fixed to isolate mass effects, the two choices have dry masses 206.07 g and
   244.71 g, and apogees 18.734 m and 16.671 m, versus 21.673 m previously. This is
   not qualification of changed finite-thickness geometry.
4. **The selector returns to shape.** Among 192 shape/material/thickness/root
   combinations, 27 pass the temporary deflection/static-restoring screen and 11
   remain on the mass/deflection/wet-margin Pareto frontier. The lightest has
   120 mm span, 70/35 mm root/tip, 1 mm thickness, assumed E=20 GPa,
   density=1600 kg/m3 and root stiffness=5 MN/m. Four fins weigh 44.8 g; dry mass is
   173.59 g. Its wet CP-minus-CG margin after an adverse 15 mm water-centroid shift
   is 10.16 mm. This is a weak positive static screen, not a dynamic certificate.
5. **The new candidate is checked separately.** Warm nonlinear FEM gives 4.369 mm
   displacement; 2->3 mesh changes are 1.02% for displacement and 0.46% for p95
   stress. New geometry CFD has 16->24-cell changes at 5 degrees of 28.20% axial,
   6.41% lateral and 5.63% pitch moment. Its new aerodynamic table and flight-load
   chain are not yet qualified; no new apogee is asserted.

## Aerodynamic accuracy remains the bottleneck

At 24 m/s, eleven new 16-cell cases cover 5..15 degrees in 1-degree increments.
Even angles 6/8/10/12/14 are the fixed interpolation training stations; odd angles
7/9/11/13 are independent checks. At 11 degrees the six-component norm error is
25.99%, with a 44.09% pitch-moment error. Increasing interpolation density alone
does not resolve this failure. Changes from 16 to 24 cells at 10/12/14 degrees
remain 10.87–13.07% in the aggregate norm.

At 12 degrees, extending the duration from 40 to 160 D/U changes the aggregate
mean by 2.12%; changing lattice speed from 0.075 to 0.05 with an 80 D/U run changes
it by 3.33%. The latter also changes time step and averaging duration, so it does
not isolate Mach effects. Symmetry-zero components retain absolute normalization
floors and are reported separately. Four time blocks are descriptive diagnostics,
not independent-sample confidence intervals.

The substantial angle/grid dependence motivates an interpolated wall treatment
or boundary-fitted solver and finite-thickness geometry. That adapter is explicitly
planned, not implemented. The 40-cell action was rejected by the 8 GiB host memory
reservation (estimated requirement 21.5 GiB); other processes were not terminated.
No Richardson extrapolation or GCI confidence interval is fabricated from these
non-asymptotic results. Existing absolute-aero validation failures remain open.

## Precision and stability

Central +/-5% and +/-10% component perturbations give a conservative local sum of
altitude sensitivity magnitudes of 8.1045 m per relative coefficient error, mostly
axial force (about -8.002 m). A 1.5 m altitude numerical budget allocates 0.75 m to
aero and retains the stricter existing 5% cap. A 0.2 m budget would request about
1.23%. These local sensitivities do not bound model-form uncertainty or supersede
separate attitude/load accuracy gates.

Nonlinear finite perturbations in initial tilt (-0.5, +0.5, +2 degrees) are compared
over common free-ascent intervals at two assumed damping values. A +2-degree tilt
gives 5.77 degrees attitude difference near apogee with damping 10 and 9.69 degrees
with damping 2. The reference trajectory also changes, so this is a finite-time
trajectory comparison, not proof of an unstable equilibrium or a Lyapunov/global
exponential-stability certificate.

## Validation performed and remaining scope

33 focused selector, beam, geometry, integrity, flight-load, generation and
workbench tests pass. Ruff check/format and Git diff checks pass. The responsive
report was checked at 390 and 1280 px: search, shelf switching, decision details,
precision slider, four loaded figures and contained table scrolling. CI is not
claimed. Live LLM decision quality was not tested; the actual runs use the host's
deterministic eligible-choice ranking.

Physical qualification remains false. Required next work includes convergent
geometry-specific aerodynamics, finite-thickness/deformation coupling, actual
material/joint allowables, fluid slosh/damping identification, new flight/load
evaluation and applicable hardware correlation. The demonstrated output is an
improved analysis/selection system and a conditional next candidate, not a design
approved for fabrication, pressurization or flight.
