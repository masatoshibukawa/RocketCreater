# Distance-aware stationary walls

`run_flow.py --wall interpolated` uses analytic link intersections for a sphere,
or a conical nose/cylindrical flat-base body with four trapezoidal fins. Add
`--fin-thickness-mm` to represent a finite plate instead of a zero-thickness sheet.
The default remains the previous halfway scheme, so existing cases are reproducible.
Recessed and rounded noses are explicitly rejected in the new mode.

The linear interpolated bounce-back rule follows Bouzidi, Firdaouss and Lallemand,
[Physics of Fluids 13, 3452 (2001)](https://doi.org/10.1063/1.1399290).
For a link fraction q <= 1/2 it interpolates post-collision outgoing populations
at the boundary node and the next fluid node; for q > 1/2 it combines opposite
post-collision populations at the boundary node. If the next fluid node lies
across a second wall, it falls back to halfway reflection. A stationary wall
contributes the sum of outgoing and reflected momentum. The surface and total
load exporters use the same populations. Reference rest pressure is subtracted.

Geometry and per-link distances are computed once. A sparse surface table keeps
distance storage small relative to the two volume population buffers. This is
not a resolved turbulent boundary layer or a moving-fluid/structure solver.
Finite plate thickness can be represented between lattice nodes, but its local
flow still requires a refinement study. Sphere accuracy does not establish
rocket accuracy.

`check_wall.py` runs ten checks on the actual GPU functions: sphere/cylinder/cone
intersections, a link passing through a body with both endpoints in fluid,
finite plate entry/occupancy, a miss, and the three interpolation branches.
Wind-tunnel control cases additionally compare surface and total loads. Case
metadata records the scheme, thickness, and all three source hashes. Never mix
old and new scheme results into a supposedly uniform convergence study.
