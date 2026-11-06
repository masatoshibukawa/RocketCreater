/** Small procedural guides, deliberately separate from engineering/human-clearance geometry. */
import * as THREE from "three";
import type { CrewPhase } from "./workshopActivity";

function material(color: number, roughness = .7) {
  return new THREE.MeshStandardMaterial({ color, roughness });
}
const PALETTE = { suit: 0x858681, trim: 0x555b58, boots: 0x303733, skin: 0xecc3a0,
  helmet: 0xe5ae35, metal: 0xaab8b9, dark: 0x293e40, paper: 0xeae7d8 };

function mesh(parent: THREE.Object3D, geometry: THREE.BufferGeometry, mat: THREE.Material, x = 0, y = 0, z = 0) {
  const result = new THREE.Mesh(geometry, mat);
  result.position.set(x, y, z); result.castShadow = true; result.receiveShadow = true;
  parent.add(result); return result;
}
function box(parent: THREE.Object3D, size: number[], mat: THREE.Material, x = 0, y = 0, z = 0) {
  return mesh(parent, new THREE.BoxGeometry(size[0], size[1], size[2]), mat, x, y, z);
}
function ball(parent: THREE.Object3D, radius: number, mat: THREE.Material, x = 0, y = 0, z = 0) {
  return mesh(parent, new THREE.SphereGeometry(radius, 16, 12), mat, x, y, z);
}

function person(index: number) {
  const root = new THREE.Group(); root.name = `Guide ${index + 1}`;
  const suit = material([PALETTE.suit, 0x92918b, 0x737e7c][index]);
  const trim = material(PALETTE.trim), skin = material(PALETTE.skin), boots = material(PALETTE.boots);
  const yellow = material(PALETTE.helmet, .42), dark = material(PALETTE.dark);
  const torso = new THREE.Group(); torso.position.y = .77; root.add(torso);
  mesh(torso, new THREE.CapsuleGeometry(.24, .28, 5, 12), suit, 0, .18);
  box(torso, [.43, .07, .35], trim, 0, -.05);
  box(torso, [.12, .13, .02], trim, -.11, .22, .225);
  box(torso, [.12, .13, .02], trim, .11, .22, .225);
  const head = new THREE.Group(); head.position.y = .77; torso.add(head);
  mesh(head, new THREE.CylinderGeometry(.07, .09, .12, 12), skin, 0, -.22);
  ball(head, .235, skin).scale.set(.96, 1.06, .95);
  for (const side of [-1, 1]) {
    ball(head, .025, dark, side * .082, .025, .212);
    ball(head, .035, skin, side * .23, 0, 0).scale.set(.5, 1, .7);
  }
  ball(head, .034, skin, 0, -.025, .235);
  const smile = mesh(head, new THREE.TorusGeometry(.052, .009, 5, 16, Math.PI), dark, 0, -.055, .217);
  smile.rotation.z = Math.PI;
  mesh(head, new THREE.SphereGeometry(.275, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2), yellow, 0, .12);
  mesh(head, new THREE.CylinderGeometry(.295, .295, .045, 24), yellow, 0, .125, .035);
  box(head, [.038, .055, .38], yellow, 0, .365, -.005);

  function arm(side: number) {
    const shoulder = new THREE.Group(); shoulder.position.set(side * .25, .4, 0); torso.add(shoulder);
    mesh(shoulder, new THREE.CapsuleGeometry(.085, .17, 4, 10), suit, 0, -.13);
    const elbow = new THREE.Group(); elbow.position.y = -.26; shoulder.add(elbow);
    mesh(elbow, new THREE.CapsuleGeometry(.075, .15, 4, 10), suit, 0, -.12);
    const hand = ball(elbow, .085, material(0xdddcd0), 0, -.26);
    return { shoulder, elbow, hand };
  }
  const left = arm(-1), right = arm(1);
  const tool = new THREE.Group(); right.hand.add(tool);
  box(tool, [.045, .3, .035], material(PALETTE.metal), 0, .08);
  const jaw = mesh(tool, new THREE.TorusGeometry(.065, .023, 6, 12, Math.PI * 1.4), material(PALETTE.metal), 0, .25);
  jaw.rotation.z = -.6;
  const clipboard = new THREE.Group(); left.hand.add(clipboard);
  box(clipboard, [.29, .38, .025], dark, 0, .04, .035);
  box(clipboard, [.24, .29, .008], material(PALETTE.paper), 0, .035, .052);
  box(clipboard, [.1, .04, .018], material(PALETTE.metal), 0, .2, .055);
  const legs = [-1, 1].map(side => {
    const hip = new THREE.Group(); hip.position.set(side * .135, .64, 0); root.add(hip);
    mesh(hip, new THREE.CapsuleGeometry(.1, .23, 4, 10), suit, 0, -.17);
    const knee = new THREE.Group(); knee.position.y = -.32; hip.add(knee);
    mesh(knee, new THREE.CapsuleGeometry(.09, .13, 4, 10), suit, 0, -.1);
    box(knee, [.22, .17, .34], boots, 0, -.23, .065);
    return { hip, knee };
  });
  return { root, torso, head, left, right, tool, clipboard, legs };
}

export function makeWorkshopCrew() {
  const root = new THREE.Group(); root.name = "Presentation-only workshop crew";
  const floor = material(0x303236), metal = material(0x48545c), wood = material(0x82745b);
  box(root, [11.8, .12, 3.7], floor, 0, -.09);
  box(root, [2.9, .1, .95], wood, -.15, .96, -.48);
  for (const x of [-1.35, 1.05]) for (const z of [-.8, -.15]) box(root, [.09, .9, .09], metal, x, .45, z);
  box(root, [2.6, .06, .7], material(0x54766e), -.15, 1.025, -.48);
  const part = new THREE.Group(); part.name = "Symbolic inspection prop, not a manufactured part";
  root.add(part); part.position.set(-.35, 1.1, -.45);
  mesh(part, new THREE.TorusGeometry(.24, .045, 8, 24), material(0xbac7c7), -.45, .2);
  const fin = new THREE.Shape(); fin.moveTo(0, 0); fin.lineTo(.55, 0); fin.lineTo(.18, .38); fin.closePath();
  mesh(part, new THREE.ExtrudeGeometry(fin, { depth: .035, bevelEnabled: false }), metal, .15);
  const cart = new THREE.Group(); cart.position.set(3.75, 0, -.4); root.add(cart);
  box(cart, [1.08, .92, .68], metal, 0, .65);
  for (const y of [.4, .68, .96]) {
    box(cart, [.96, .21, .025], material(0x82918e), 0, y, .35);
    box(cart, [.33, .025, .035], material(PALETTE.metal), 0, y + .04, .38);
  }
  for (const x of [-.4, .4]) for (const z of [-.23, .23]) ball(cart, .105, material(PALETTE.boots), x, .1, z);
  box(cart, [1.17, .07, .8], wood, 0, 1.15);
  const toolbox = new THREE.Group(); root.add(toolbox);
  box(toolbox, [.5, .24, .3], material(0xb28b3d), 0, .12);
  box(toolbox, [.17, .04, .04], metal, 0, .28);
  const people = [0, 1, 2].map(person);
  people.forEach(p => root.add(p.root));
  const homes = [[-2.45, -.02], [.45, .98], [2.45, .45]];

  function pose(phase: CrewPhase, seconds: number) {
    const time = seconds;
    const progress = THREE.MathUtils.smoothstep(time, 0, 5.8);
    people.forEach((p, i) => {
      p.root.position.set(homes[i][0], 0, homes[i][1]); p.root.rotation.set(0, [.62, -.3, -.6][i], 0);
      p.torso.position.y = .77; p.torso.rotation.set(0, 0, 0); p.head.rotation.set(0, 0, 0);
      p.left.shoulder.rotation.set(-.45, 0, -.13); p.right.shoulder.rotation.set(-.25, 0, .13);
      p.left.elbow.rotation.set(-.9, 0, 0); p.right.elbow.rotation.set(-.35, 0, 0);
      p.legs.forEach(l => { l.hip.rotation.set(0, 0, 0); l.knee.rotation.set(0, 0, 0); });
      p.clipboard.visible = i !== 0; p.tool.visible = i === 0;
      if (phase === "inspecting") {
        p.head.rotation.x = .13 + .035 * Math.sin(time * 1.6 + i);
        if (i === 0) {
          p.torso.rotation.z = -.12;
          p.right.shoulder.rotation.x = -1.25;
          p.right.elbow.rotation.x = -.35 + .15 * Math.sin(time * 3);
        } else if (i === 1) {
          p.torso.rotation.x = .15;
          p.right.shoulder.rotation.x = -1.1;
          p.right.elbow.rotation.x = -.7 + .1 * Math.sin(time * 2.7);
          p.clipboard.visible = false;
        } else {
          p.left.shoulder.rotation.x = -.75;
          p.right.shoulder.rotation.x = -.8;
          p.right.elbow.rotation.x = -1 + .12 * Math.sin(time * 2);
        }
      } else if (phase === "tidying") {
        if (i === 0) {
          p.root.position.x -= progress * .8; p.root.rotation.y = -.9;
          p.right.shoulder.rotation.x = -.9 * (1 - progress); p.tool.visible = progress < .8;
        } else if (i === 1) {
          p.root.position.x += progress * 1.65; p.root.rotation.y = 1;
          p.left.shoulder.rotation.x = p.right.shoulder.rotation.x = -.75;
          p.clipboard.visible = false;
        } else {
          p.root.position.x -= .8; p.torso.rotation.x = .14;
          p.right.shoulder.rotation.x = -1.2;
          p.right.shoulder.rotation.z = .2 * Math.sin(time * 3.2) * (1 - progress);
          p.clipboard.visible = false;
        }
        if (i < 2) p.legs.forEach((l, n) => {
          l.hip.rotation.x = Math.sin(time * 7 + n * Math.PI) * .3 * Math.sin(progress * Math.PI);
        });
      } else if (phase === "attention") {
        p.head.rotation.x = .1; p.tool.visible = false;
        p.left.shoulder.rotation.x = -.65; p.right.shoulder.rotation.x = -.1;
      } else {
        p.torso.position.y += Math.sin(time * 1.25 + i) * .009;
        p.head.rotation.y = Math.sin(time * .55 + i) * .1;
        p.right.shoulder.rotation.x = -.25 + Math.sin(time * .7 + i) * .025;
      }
    });
    toolbox.position.set(phase === "tidying" ? .55 + progress * 2.8 : 3.75,
      phase === "tidying" && progress < .92 ? .85 : 1.2, phase === "tidying" && progress < .92 ? 1.08 : -.4);
  }
  function dispose() {
    const materials = new Set<THREE.Material>();
    root.traverse(o => {
      if (o instanceof THREE.Mesh) {
        o.geometry.dispose(); (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => materials.add(m));
      }
    });
    materials.forEach(m => m.dispose());
  }
  pose("waiting", 0);
  return { root, pose, dispose };
}
