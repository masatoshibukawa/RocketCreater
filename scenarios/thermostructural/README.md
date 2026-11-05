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
thermal = thermal_response(input,cfg,'../../output/study');
```

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
