"use client";

/**
 * 3D view of the displayed design: plain three.js inside a ref (no react-three-fiber).
 * One renderer per mount; the model group is rebuilt whenever the design JSON changes and the
 * camera is refitted to it. OrbitControls with slow auto-rotate, soft shadow on a ground disc,
 * ResizeObserver on the container.
 */

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { fmt } from "../lib/format";
import { buildProceduralModel, disposeGroup } from "../lib/model3d";
import { canonicalJson } from "../lib/designState";
import { TIER_LABEL, type Design, type DimensionSummary, type DisplayOrigin, type ReferenceInfo, type Tier } from "../lib/types";
import TierBadge from "./TierBadge";
import { useWorkshop } from "../lib/WorkshopContext";

interface ModelViewerProps {
  design: Design | null;
  tier: Tier | null;
  origin: DisplayOrigin | null;
  reference: ReferenceInfo | null;
  dimensions: DimensionSummary | null;
  /** Build warnings to flag under the overlay (motor certification Level 1/2, coupler). */
  notes: string[];
}

const BACKGROUND = 0xffffff;

interface Scene3D {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  light: THREE.DirectionalLight;
  ground: THREE.Mesh;
  model: THREE.Group | null;
  frame: number;
}

const ORIGIN_LABEL: Record<DisplayOrigin, string> = {
  candidate: "合格案",
  attempt: "最新の試行",
  seed: "お手本からの初期案",
};

/** Place the camera so the model's bounding sphere fills the view, and aim the shadow light. */
function fitToView(s: Scene3D, model: THREE.Object3D): void {
  const box = new THREE.Box3().setFromObject(model);
  if (box.isEmpty()) return;
  const size = new THREE.Vector3();
  const center = new THREE.Vector3();
  box.getSize(size);
  box.getCenter(center);
  const radius = Math.max(size.length() / 2, 1e-3);
  const fov = (s.camera.fov * Math.PI) / 180;
  const dist = (radius / Math.sin(fov / 2)) * 1.05;
  const dir = new THREE.Vector3(1, 0.45, 1.3).normalize();
  s.camera.position.copy(center).addScaledVector(dir, dist);
  s.camera.near = Math.max(dist / 100, 1e-3);
  s.camera.far = dist * 20;
  s.camera.updateProjectionMatrix();
  s.controls.target.copy(center);
  s.controls.minDistance = radius * 0.6;
  s.controls.maxDistance = dist * 4;
  s.controls.update();
  // ground disc just under the tail, sized to the model
  s.ground.position.set(center.x, box.min.y - radius * 0.02, center.z);
  s.ground.scale.setScalar(radius * 3);
  // directional light with a shadow frustum that covers the model
  s.light.position.copy(center).add(new THREE.Vector3(radius * 1.5, radius * 3, radius * 1.2));
  s.light.target.position.copy(center);
  s.light.target.updateMatrixWorld();
  const cam = s.light.shadow.camera;
  cam.left = -radius * 1.6;
  cam.right = radius * 1.6;
  cam.top = radius * 1.6;
  cam.bottom = -radius * 1.6;
  cam.near = radius * 0.1;
  cam.far = radius * 8;
  cam.updateProjectionMatrix();
}

export default function ModelViewer({ design, tier, origin, reference, dimensions, notes }: ModelViewerProps) {
  const { motionEnabled } = useWorkshop();
  const hostRef = useRef<HTMLDivElement | null>(null);
  const sceneRef = useRef<Scene3D | null>(null);
  const designKey = design === null ? "" : canonicalJson(design);

  // Renderer lifecycle: one per mount (React strict mode mounts twice in dev; cleanup is full).
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.setSize(host.clientWidth || 300, host.clientHeight || 200, false);
    host.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(BACKGROUND);
    const camera = new THREE.PerspectiveCamera(38, 1, 0.01, 1000);
    camera.position.set(1, 0.5, 2);

    const hemi = new THREE.HemisphereLight(0xffffff, 0xc8d0da, 1.1);
    scene.add(hemi);
    const light = new THREE.DirectionalLight(0xffffff, 1.6);
    light.castShadow = true;
    light.shadow.mapSize.set(1024, 1024);
    light.shadow.radius = 4;
    scene.add(light);
    scene.add(light.target);

    const ground = new THREE.Mesh(
      new THREE.CircleGeometry(1, 48),
      new THREE.ShadowMaterial({ color: 0x000000, opacity: 0.14, transparent: true }),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.autoRotate = false;
    controls.autoRotateSpeed = 0.9;
    controls.enablePan = false;

    const s: Scene3D = { renderer, scene, camera, controls, light, ground, model: null, frame: 0 };
    sceneRef.current = s;

    const resize = (): void => {
      const w = host.clientWidth;
      const h = host.clientHeight;
      if (w === 0 || h === 0) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(host);

    const tick = (): void => {
      s.frame = window.requestAnimationFrame(tick);
      controls.update();
      renderer.render(scene, camera);
    };
    tick();

    return () => {
      window.cancelAnimationFrame(s.frame);
      observer.disconnect();
      controls.dispose();
      if (s.model) {
        scene.remove(s.model);
        disposeGroup(s.model);
      }
      ground.geometry.dispose();
      (ground.material as THREE.Material).dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === host) host.removeChild(renderer.domElement);
      sceneRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (sceneRef.current) sceneRef.current.controls.autoRotate = motionEnabled;
  }, [motionEnabled]);

  // Rebuild the model when the design changes.
  useEffect(() => {
    const s = sceneRef.current;
    if (!s) return;
    if (s.model) {
      s.scene.remove(s.model);
      disposeGroup(s.model);
      s.model = null;
    }
    if (designKey === "") return;
    const parsed = JSON.parse(designKey) as Design;
    const model = buildProceduralModel(parsed);
    s.scene.add(model);
    s.model = model;
    fitToView(s, model);
  }, [designKey]);

  const dimText =
    dimensions && dimensions.length_m !== null && dimensions.diameter_m !== null
      ? `全長 ${fmtLength(dimensions.length_m)} / 直径 ${fmtLength(dimensions.diameter_m)}`
      : null;

  return (
    <div className="panel model-panel">
      <div className="model-host" ref={hostRef} />
      {design === null && (
        <div className="model-empty">
          <div>設計案が届くと、ここに 3D モデルを表示します</div>
          <div className="muted">（お手本の実機から縮尺した初期案 → 試行 → 合格案の順に更新）</div>
        </div>
      )}
      <div className="model-overlay model-overlay-top">
        <TierBadge tier={tier} />
        {reference !== null && (
          <span className="chip chip-muted" title={reference.notes.join("\n")}>
            お手本：{reference.name}
          </span>
        )}
        {origin !== null && <span className="chip chip-accent">{ORIGIN_LABEL[origin]}</span>}
      </div>
      {design !== null && notes.length > 0 && (
        <div className="model-notes" role="note">
          {notes.map((n) => (
            <div key={n} className="model-note">
              {n}
            </div>
          ))}
        </div>
      )}
      <div className="model-overlay model-overlay-bottom">
        {dimText !== null && <span className="model-dims">{dimText}</span>}
        {design !== null && tier !== null && (
          <span className="muted model-caption">
            {TIER_LABEL[tier]}の概念モデル（ドラッグで回転、ホイールで拡大）
          </span>
        )}
      </div>
    </div>
  );
}

/** Metres for vehicles, millimetres for anything under a metre. */
function fmtLength(m: number): string {
  return m >= 1 ? `${fmt(m, 2)} m` : `${fmt(m * 1000, 0)} mm`;
}
