/**
 * Procedural three.js model of a Design ("something that looks right"), used by
 * components/ModelViewer.tsx until a real STL from the 3D teammate replaces it.
 *
 * The group's +Y axis is the vehicle axis (nose up); the tail (nozzle exit) sits at y = 0 and
 * the whole vehicle is built in metres, so the viewer's fit-to-view works for a 0.3 m bottle
 * and a 60 m heavy lifter alike.
 *
 * Proportions mirror rocketwright/drawing.py so the 3D view and the SVG side view agree:
 *   multistage  diameter = 0.05 * total_propellant^(1/3) m, stage length = prop / (1000 * area),
 *               fairing = 2.5 d (ogive), nozzle = 0.25 d, boosters 0.4 d wide and 0.6 * L1 long
 *               (SIMPLIFICATION: booster propellant is not in the UI, so it is left out of the
 *               diameter rule and the booster length falls back to the 0.6 * L1 rule)
 *   bottle      d = (4 V / (pi * 3.5))^(1/3), body 3.5 d, nose 0.8 d, neck 0.3 d, fins 0.8 d
 *   amateur     straight from the design (nose shape, fin set, body)
 *
 * STL swap point: `loadStl(url)` returns a BufferGeometry; replace the `buildProceduralModel`
 * call in ModelViewer with `loadStl(...)` wrapped in a Mesh to show the real model.
 */

import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import type { AmateurDesign, BottleDesign, Design, MultistageDesign } from "./types";

// drawing.py constants (keep in sync)
const DIAMETER_PER_CUBE_ROOT_KG = 0.05;
const PROPELLANT_BULK_DENSITY_KGPM3 = 1000;
const FAIRING_LENGTH_DIAMETERS = 2.5;
const NOZZLE_LENGTH_DIAMETERS = 0.25;
const BOOSTER_DIAMETER_FRAC = 0.4;
const BOOSTER_LENGTH_FRAC = 0.6;
const MAX_DRAWN_ENGINES = 9;
const MAX_DRAWN_BOOSTERS = 8;
const BOTTLE_ASPECT_RATIO = 3.5;
const BOTTLE_NOSE_DIAMETERS = 0.8;
const BOTTLE_NECK_DIAMETERS = 0.3;

const SEGMENTS = 48;

const COLOR = {
  body: 0xf4f6f8,
  bodyAlt: 0xdfe5ec,
  fin: 0xd64545,
  nose: 0xe8edf3,
  interstage: 0x5b6670,
  bell: 0x3b434c,
  bellInner: 0x1f252b,
  booster: 0xe9eef3,
  pet: 0xbfe0f5,
  water: 0x4aa3e0,
  cap: 0xd64545,
  chute: 0xf0a030,
  payload: 0x7c5cd6,
};

function matte(color: number): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.65, metalness: 0.05 });
}

function metal(color: number): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.4, metalness: 0.6 });
}

function addMesh(group: THREE.Group, geometry: THREE.BufferGeometry, material: THREE.Material): THREE.Mesh {
  const mesh = new THREE.Mesh(geometry, material);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  group.add(mesh);
  return mesh;
}

/** A cylinder along +Y from y0 to y0 + length. */
function cylinder(
  group: THREE.Group,
  radiusTop: number,
  radiusBottom: number,
  length: number,
  y0: number,
  material: THREE.Material,
): THREE.Mesh {
  const geom = new THREE.CylinderGeometry(radiusTop, radiusBottom, length, SEGMENTS);
  const mesh = addMesh(group, geom, material);
  mesh.position.y = y0 + length / 2;
  return mesh;
}

/**
 * Nose profile as lathe points (radius, y) from the base (y0, radius R) to the tip
 * (y0 + L, 0). `shape` follows AmateurDesign.nose_shape (Barrowman shapes).
 */
function noseProfile(shape: string, radius: number, length: number, y0: number, steps = 24): THREE.Vector2[] {
  const pts: THREE.Vector2[] = [];
  // tangent ogive radius
  const rho = (radius * radius + length * length) / (2 * radius);
  for (let i = 0; i <= steps; i += 1) {
    const x = (length * i) / steps; // distance from the base towards the tip
    let r: number;
    if (shape === "conical") {
      r = radius * (1 - x / length);
    } else if (shape === "elliptical") {
      const u = Math.min(1, x / length);
      r = radius * Math.sqrt(Math.max(0, 1 - u * u));
    } else {
      // ogive: y(x') = sqrt(rho^2 - (L - x')^2) + R - rho, with x' measured from the tip side
      const xp = length - x;
      r = Math.sqrt(Math.max(0, rho * rho - xp * xp)) + radius - rho;
    }
    pts.push(new THREE.Vector2(Math.max(0, r), y0 + x));
  }
  // close the tip exactly
  pts[pts.length - 1] = new THREE.Vector2(0, y0 + length);
  return pts;
}

function nose(group: THREE.Group, shape: string, radius: number, length: number, y0: number, material: THREE.Material): void {
  const geom = new THREE.LatheGeometry(noseProfile(shape, radius, length, y0), SEGMENTS);
  addMesh(group, geom, material);
}

interface FinSpec {
  count: number;
  rootChord: number;
  tipChord: number;
  span: number;
  sweep: number;
  thickness: number;
}

/**
 * Trapezoidal fins around the body at the tail. The root chord runs from y = yTail (trailing
 * edge) up to yTail + rootChord (leading edge); the tip leading edge is swept back by `sweep`.
 */
function fins(group: THREE.Group, bodyRadius: number, yTail: number, spec: FinSpec, material: THREE.Material): void {
  const shape = new THREE.Shape();
  const r = bodyRadius * 0.98; // sink the root slightly into the body so there is no seam
  shape.moveTo(r, yTail);
  shape.lineTo(r, yTail + spec.rootChord);
  shape.lineTo(r + spec.span, yTail + spec.rootChord - spec.sweep);
  shape.lineTo(r + spec.span, yTail + spec.rootChord - spec.sweep - spec.tipChord);
  shape.lineTo(r, yTail);
  const geom = new THREE.ExtrudeGeometry(shape, { depth: spec.thickness, bevelEnabled: false });
  geom.translate(0, 0, -spec.thickness / 2);
  for (let i = 0; i < spec.count; i += 1) {
    const mesh = new THREE.Mesh(geom, material);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.rotation.y = (2 * Math.PI * i) / spec.count;
    group.add(mesh);
  }
}

/** An engine bell (truncated cone, exit at the bottom) whose exit plane sits at y = yExit. */
function bell(group: THREE.Group, exitRadius: number, length: number, x: number, yExit: number, z: number): void {
  const outer = new THREE.CylinderGeometry(exitRadius * 0.45, exitRadius, length, 32, 1, true);
  const mesh = new THREE.Mesh(outer, new THREE.MeshStandardMaterial({ color: COLOR.bell, roughness: 0.45, metalness: 0.6, side: THREE.DoubleSide }));
  mesh.castShadow = true;
  mesh.position.set(x, yExit + length / 2, z);
  group.add(mesh);
  const throat = new THREE.CylinderGeometry(exitRadius * 0.45, exitRadius * 0.45, length * 0.3, 24);
  const tm = new THREE.Mesh(throat, metal(COLOR.bellInner));
  tm.position.set(x, yExit + length + length * 0.15, z);
  group.add(tm);
}

/** (x, z) positions for `n` engines inside a circle of radius `ringRadius`. */
function enginePositions(n: number, ringRadius: number): [number, number][] {
  if (n <= 1) return [[0, 0]];
  const out: [number, number][] = [];
  const ringCount = n >= 5 ? n - 1 : n;
  if (n >= 5) out.push([0, 0]);
  for (let i = 0; i < ringCount; i += 1) {
    const a = (2 * Math.PI * i) / ringCount;
    out.push([ringRadius * Math.cos(a), ringRadius * Math.sin(a)]);
  }
  return out;
}

// --------------------------------------------------------------------------- tiers

function buildAmateur(design: AmateurDesign): THREE.Group {
  const g = new THREE.Group();
  const r = design.body_diameter_m / 2;
  const L = design.body_length_m;
  const body = matte(COLOR.body);
  cylinder(g, r, r, L, 0, body);
  // a coloured payload band under the nose
  cylinder(g, r * 1.005, r * 1.005, Math.min(L * 0.12, r * 1.5), L - Math.min(L * 0.12, r * 1.5), matte(COLOR.payload));
  nose(g, design.nose_shape, r, design.nose_length_m, L, matte(COLOR.nose));
  fins(
    g,
    r,
    0,
    {
      count: design.fins.count,
      rootChord: design.fins.root_chord_m,
      tipChord: design.fins.tip_chord_m,
      span: design.fins.span_m,
      sweep: design.fins.sweep_m,
      thickness: Math.max(design.fins.thickness_m, r * 0.04),
    },
    matte(COLOR.fin),
  );
  // motor: a short casing flush with the tail and a small nozzle below it
  cylinder(g, r * 0.55, r * 0.55, r * 0.3, -r * 0.1, metal(COLOR.interstage));
  bell(g, r * 0.35, r * 0.5, 0, -r * 0.55, 0);
  return g;
}

function buildBottle(design: BottleDesign): THREE.Group {
  const g = new THREE.Group();
  const d = Math.cbrt((4 * design.bottle_volume_m3) / (Math.PI * BOTTLE_ASPECT_RATIO));
  const r = d / 2;
  const body = BOTTLE_ASPECT_RATIO * d;
  const noseLen = BOTTLE_NOSE_DIAMETERS * d;
  const neck = BOTTLE_NECK_DIAMETERS * d;
  const rNeck = Math.max(design.nozzle_diameter_m / 2, d * 0.1);
  const shoulder = d * 0.3;

  // PET shell as one lathe: neck (nozzle end, bottom) -> shoulder -> body -> dome (top)
  const pts: THREE.Vector2[] = [];
  pts.push(new THREE.Vector2(rNeck, 0));
  pts.push(new THREE.Vector2(rNeck, neck));
  const shoulderSteps = 8;
  for (let i = 1; i <= shoulderSteps; i += 1) {
    const u = i / shoulderSteps;
    const rr = rNeck + (r - rNeck) * Math.sin((u * Math.PI) / 2);
    pts.push(new THREE.Vector2(rr, neck + shoulder * u));
  }
  const yBody1 = neck + body;
  pts.push(new THREE.Vector2(r, yBody1));
  const domeSteps = 12;
  for (let i = 1; i <= domeSteps; i += 1) {
    const u = i / domeSteps;
    pts.push(new THREE.Vector2(r * Math.sqrt(Math.max(0, 1 - u * u)), yBody1 + noseLen * u));
  }
  pts[pts.length - 1] = new THREE.Vector2(0, yBody1 + noseLen);
  const shell = new THREE.Mesh(
    new THREE.LatheGeometry(pts, SEGMENTS),
    new THREE.MeshPhysicalMaterial({
      color: COLOR.pet,
      roughness: 0.15,
      metalness: 0,
      transparent: true,
      opacity: 0.38,
      side: THREE.DoubleSide,
      depthWrite: false,
    }),
  );
  shell.castShadow = true;
  shell.renderOrder = 2;
  g.add(shell);

  // water: fills the lower part of the body (the rocket stands neck-down on the pad)
  const waterH = Math.max(0, Math.min(1, design.water_fill_frac)) * (body + shoulder);
  const water = new THREE.Mesh(
    new THREE.CylinderGeometry(r * 0.96, Math.max(rNeck * 1.2, r * 0.5), waterH, SEGMENTS),
    new THREE.MeshStandardMaterial({ color: COLOR.water, roughness: 0.2, transparent: true, opacity: 0.85 }),
  );
  water.position.y = neck + waterH / 2;
  water.renderOrder = 1;
  g.add(water);

  // nozzle ring (bottle cap with a hole)
  cylinder(g, rNeck * 1.25, rNeck * 1.25, neck * 0.5, 0, matte(COLOR.cap));

  if (design.has_fins) {
    fins(
      g,
      r,
      neck + shoulder * 0.5,
      {
        count: 3,
        rootChord: 0.6 * d,
        tipChord: 0.3 * d,
        span: 0.8 * d, // drawing.py: representative fin size (SIMPLIFICATION)
        sweep: 0.2 * d,
        thickness: d * 0.03,
      },
      matte(COLOR.fin),
    );
  }
  if (design.has_parachute) {
    // the parachute pack rides on top of the dome as a small nose cone
    const top = yBody1 + noseLen;
    cylinder(g, r * 0.35, r * 0.5, d * 0.25, top - d * 0.05, matte(COLOR.chute));
    nose(g, "conical", r * 0.35, d * 0.2, top + d * 0.2, matte(COLOR.chute));
  }
  return g;
}

function buildMultistage(design: MultistageDesign): THREE.Group {
  const g = new THREE.Group();
  const totalProp = design.stages.reduce((acc, s) => acc + s.propellant_mass_kg, 0);
  const d = DIAMETER_PER_CUBE_ROOT_KG * Math.cbrt(Math.max(totalProp, 1));
  const r = d / 2;
  const area = (Math.PI * d * d) / 4;
  const stageLen = design.stages.map((s) => s.propellant_mass_kg / (PROPELLANT_BULK_DENSITY_KGPM3 * area));
  const nozzleLen = NOZZLE_LENGTH_DIAMETERS * d;
  const interstage = Math.max(d * 0.08, 0.01);

  // stage 1 engines below the tail (tail at y = nozzleLen so the exits sit at y = 0)
  const yTail = nozzleLen;
  const first = design.stages[0];
  const n = Math.min(Math.max(1, first.engine_count), MAX_DRAWN_ENGINES);
  const exitR = n === 1 ? r * 0.55 : Math.min(r * 0.3, (r * 0.95) / (n >= 5 ? 2.6 : 2.1));
  const ringR = n >= 5 ? r * 0.62 : r * 0.5;
  for (const [x, z] of enginePositions(n, ringR)) bell(g, exitR, nozzleLen, x, 0, z);
  // engine mount plate
  cylinder(g, r * 0.95, r * 0.95, d * 0.04, yTail - d * 0.04, metal(COLOR.interstage));

  let y = yTail;
  design.stages.forEach((_, i) => {
    const mat = matte(i % 2 === 0 ? COLOR.body : COLOR.bodyAlt);
    cylinder(g, r, r, stageLen[i], y, mat);
    y += stageLen[i];
    // interstage ring between stages (and the fairing adapter after the last stage)
    cylinder(g, r * 1.012, r * 1.012, interstage, y - interstage / 2, matte(COLOR.interstage));
  });
  // fairing: short cylindrical section + ogive, 2.5 d in total
  const fairing = FAIRING_LENGTH_DIAMETERS * d;
  const fairingCyl = fairing * 0.3;
  cylinder(g, r, r, fairingCyl, y, matte(COLOR.nose));
  nose(g, "ogive", r, fairing - fairingCyl, y + fairingCyl, matte(COLOR.nose));

  // heavy: strap-on boosters around stage 1
  if (design.tier === "heavy" && design.boosters.length > 0) {
    const count = Math.min(
      design.boosters.reduce((acc, b) => acc + b.count, 0),
      MAX_DRAWN_BOOSTERS,
    );
    const bd = BOOSTER_DIAMETER_FRAC * d;
    const br = bd / 2;
    const bl = Math.min(BOOSTER_LENGTH_FRAC * stageLen[0], stageLen[0]);
    const orbit = r + br * 1.02;
    for (let i = 0; i < count; i += 1) {
      const a = (2 * Math.PI * i) / count + Math.PI / count;
      const bx = orbit * Math.cos(a);
      const bz = orbit * Math.sin(a);
      const bg = new THREE.Group();
      cylinder(bg, br, br, bl, yTail, matte(COLOR.booster));
      nose(bg, "conical", br, bd * 1.2, yTail + bl, matte(COLOR.nose));
      bell(bg, br * 0.7, nozzleLen * 0.7, 0, yTail - nozzleLen * 0.7, 0);
      bg.position.set(bx, 0, bz);
      g.add(bg);
    }
  }
  return g;
}

/** Procedural placeholder model. The caller owns disposal (see `disposeGroup`). */
export function buildProceduralModel(design: Design): THREE.Group {
  if (design.tier === "amateur") return buildAmateur(design);
  if (design.tier === "bottle") return buildBottle(design);
  return buildMultistage(design);
}

/** Free every geometry / material under `group` (three.js does not garbage-collect GPU buffers). */
export function disposeGroup(group: THREE.Object3D): void {
  group.traverse((obj) => {
    const mesh = obj as THREE.Mesh;
    if (mesh.geometry) mesh.geometry.dispose();
    const m = mesh.material as THREE.Material | THREE.Material[] | undefined;
    if (Array.isArray(m)) m.forEach((mm) => mm.dispose());
    else if (m) m.dispose();
  });
}

/**
 * STL hook for the real model. Returns a geometry in the STL's own units; wrap it in a Mesh
 * (and scale to metres) in place of `buildProceduralModel` when the STL arrives:
 *
 *   const geom = await loadStl("/models/rocket.stl");
 *   const group = new THREE.Group();
 *   group.add(new THREE.Mesh(geom, new THREE.MeshStandardMaterial({ color: 0xf4f6f8 })));
 */
export function loadStl(url: string): Promise<THREE.BufferGeometry> {
  return new Promise((resolve, reject) => {
    new STLLoader().load(url, resolve, undefined, reject);
  });
}
