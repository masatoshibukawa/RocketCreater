# D02-G10-120-C1 — executed comparison, 2026-11-06

The specified G10FR4 fins, PETG shoes, fasteners and straps raise dry mass from
152.7873 g to 220.0783 g, excluding the 60 g payload. This is a numerical prototype,
not an approved build or launch configuration. The 1 mm plate stock and matching
material properties, attachment allowables and pressure hardware remain unverified.

## Aerodynamics

Executed 16 three-dimensional CFD conditions (8/30 m/s and 0/5/10/15/45/90/135/180
degrees) using finite 1 mm fins and the external mounting-shoe envelope. Stationary
distance-aware wall interpolation replaces the optional halfway wall in this study.
An independent 18 m/s, 5-degree case checks table interpolation; separate 16/24/28
cells-per-diameter cases check grid sensitivity at that condition.

The 24-to-28 differences are 6.39% axial force, 8.28% normal force and 27.42% pitch
moment: **the 5% accuracy gate fails**. Independent-speed interpolation differences
are 0.24%, 0.42% and 2.34%, respectively, but this does not remove spatial error.
Other angles, domains, averaging duration and physical validation remain open.
Sphere Re=100 controls give Cd=1.15012/1.12475/1.10532 at 12/16/24 cells, compared
with the reference correlation 1.0917. This is a solver control, not rocket validation.

## Flight and structure

| Flight condition | Apogee m | Peak ascent incidence deg | Impact speed m/s |
| --- | ---: | ---: | ---: |
| Nominal wind | 19.536 | 18.59 | 4.973 |
| Calm | 19.697 | 1.05 | 4.590 |
| Increased crosswind | 19.267 | 42.57 | 5.954 |
| Lower rate damping | 19.432 | 16.78 | 4.990 |
| Initial tilt +2 deg | 19.493 | 16.09 | 4.983 |

Peak incidence is evaluated after rail exit and only while ascent dynamic pressure
exceeds 10 Pa; the plotted time histories include low-dynamic-pressure endpoints.
The common 30 m objective is unmet. These are conditional predictions using the
unqualified CFD table. Section-load equilibrium residuals are below 2.2e-13.
Axial symmetry means the near-zero modeled roll cannot qualify actual roll behavior.

Both the force- and bending-governing fin event occur in the same crosswind sample:
normal force 0.70653 N, root bending 0.035372 N m, time 0.28614 s. The undeformed
FEM pressure mapping preserves force and both first moments; follower pressure
rotates with the deformed surface. Tangential traction and coupled aeroelastic
feedback are excluded.

At the assumed 45 C condition, CalculiX 2.23 yields maximum displacement 2.3476 mm
and 95th-percentile integration-point von Mises stress 1.8813 MPa (maximum 2.5124
MPa). Two meshes (2,373 and 5,141 nodes) differ by 3.31% displacement and 0.92%
stress, passing this numerical comparison. Von Mises stress is a demand indicator,
not a laminate failure criterion; there is no matching design allowable.
The warm modulus reduction and jaw-derived root stiffness are assumptions, not
measured properties. Bolts, contact, local bearing, skirt transfer and strap slip
are not resolved in this spring-supported fin model.

The bending-beam first mode is 30.02 Hz, ranging from 21.24 to 34.53 Hz when root
stiffness is multiplied by 0.25 to 4. This excludes full-vehicle bending/torsion,
slosh and flutter. The inherited thermal network is a scenario input, not new
thermal qualification of the changed materials.

## Stability and adaptive selection

All 76 sampled frozen, unforced pitch oscillators have positive inertia, restoring
stiffness and damping, satisfying the implemented LaSalle proof for that linear
model. The largest invariant subset of zero energy dissipation is its origin.

The declared piecewise-affine two-state model has a Gronwall weighted-norm
homogeneous endpoint gain bound of about 0.0619. Not every interval contracts.
This omits trim forcing, trajectory-direction dynamics, angular momentum flux,
flexure, events and CFD uncertainty: it is not a nonlinear flight certificate.
Indeed, the initial 2-degree attitude difference grows to 4.640 degrees at the
end of the shared nonlinear ascent interval (ratio 2.320).

Two actual host campaigns select LaSalle for the frozen model and Gronwall for the
scheduled model. Barbalat remains in the pool but is rejected when infinite-horizon
and uniform-continuity/state-detection prerequisites are absent. The three methods
are not interchangeable stability tests.

## Reproduction and verification

See [README.md](README.md) for run commands and primary sources. The compact
[reference-summary.json](reference-summary.json) retains numerical outcomes and
input/case hashes. Full flow, trajectory and solver outputs remain local generated
artifacts under `output/concrete-01`; the report generator produces the site figures.

31 affected Python tests and 13 direct GPU geometry/wall checks passed. Lint passed
for changed Python files. A separate pre-existing OpenFOAM test cannot run on this
Windows host because its Docker command uses `os.getuid`; it is not counted as a
passing check. Initial temporary-directory and native-launch permission failures
were resolved with a workspace test directory and normal native solver execution.

Next numerical priority is reliable pitch-moment grid/domain/time convergence,
then a mass/geometry trade study under the same material and mounting assumptions.
Passing the FEM mesh comparison does not remove either priority or qualify hardware.
