"use client";

import { useEffect, useRef, useState } from "react";
import { useWorkshop } from "../lib/WorkshopContext";
import { INITIAL_CREW, transitionCrew, type CrewPhase } from "../lib/workshopActivity";

const PHASE_LABEL: Record<CrewPhase, string> = {
  waiting: "待機", inspecting: "点検", tidying: "片付け", attention: "確認待ち",
};

/** A separate presentation stage; its controls never change design or job state. */
export default function WorkshopCrew() {
  const { task, visible, paused, reduced, motionEnabled, setVisible, setPaused } = useWorkshop();
  const [crew, setCrew] = useState(INITIAL_CREW);
  useEffect(() => {
    setCrew(previous => transitionCrew(previous, task, Date.now()));
  }, [task]);
  useEffect(() => {
    if (crew.phase !== "tidying") return;
    const timer = window.setTimeout(() => {
      setCrew(previous => transitionCrew(previous, task, Date.now()));
    }, Math.max(0, crew.cleanupUntil - Date.now()));
    return () => window.clearTimeout(timer);
  }, [crew.phase, crew.cleanupUntil, task]);

  return <section className="crew-panel" aria-label="整備チーム" data-phase={crew.phase}>
    <div className="crew-toolbar">
      <div className="crew-heading"><strong>整備チーム</strong><span className={`crew-phase crew-phase-${crew.phase}`}>{PHASE_LABEL[crew.phase]}</span></div>
      <div className="crew-controls">
        <label><input type="checkbox" checked={visible} onChange={e => setVisible(e.target.checked)}/>表示</label>
        <button type="button" className="btn" aria-pressed={paused} onClick={() => setPaused(!paused)} disabled={reduced}>
          {paused ? "動きを再開" : "動きを止める"}
        </button>
      </div>
    </div>
    {visible ? <CrewCanvas phase={crew.phase} animate={motionEnabled && crew.phase !== "attention"}/> : null}
    <div className="crew-description">
      <p role="status" aria-live="polite">{crew.label}</p>
      <small>{reduced ? "端末の設定に合わせて静止表示 · " : paused ? "演出は静止中 · " : ""}工程の案内役です。実機の点検完了を示すものではありません。</small>
    </div>
  </section>;
}

function CrewCanvas({ phase, animate }: { phase: CrewPhase; animate: boolean }) {
  const host = useRef<HTMLDivElement>(null);
  const latest = useRef({ phase, animate });
  const runtime = useRef<{ update: () => void } | null>(null);
  const [fallback, setFallback] = useState(false);
  useEffect(() => { latest.current = { phase, animate }; runtime.current?.update(); }, [phase, animate]);

  useEffect(() => {
    const container = host.current;
    if (!container) return;
    let cancelled = false;
    let dispose: (() => void) | undefined;
    // No renderer or character geometry is loaded while the crew is hidden.
    void Promise.all([import("three"), import("../lib/workshopCrew3d")]).then(([THREE, { makeWorkshopCrew }]) => {
      if (cancelled) return;
      let renderer: InstanceType<typeof THREE.WebGLRenderer>;
      try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true }); }
      catch { setFallback(true); return; }
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      renderer.domElement.setAttribute("aria-hidden", "true");
      container.appendChild(renderer.domElement);
      const scene = new THREE.Scene();
      const camera = new THREE.OrthographicCamera(-6, 6, 2, -2, .1, 60);
      camera.position.set(3, 4.2, 10); camera.lookAt(0, .65, 0);
      scene.add(new THREE.HemisphereLight(0xffffff, 0x81958c, 2.2));
      const light = new THREE.DirectionalLight(0xfff4dd, 3);
      light.position.set(-3, 7, 4); light.castShadow = true;
      light.shadow.mapSize.set(512, 512);
      Object.assign(light.shadow.camera, { left: -7, right: 7, top: 5, bottom: -5 });
      light.shadow.bias = -.001;
      scene.add(light);
      const crew = makeWorkshopCrew(); scene.add(crew.root);
      let frame = 0, elapsed = 0, last = 0, drawn = 0, contextAvailable = true, currentPhase = latest.current.phase;
      const draw = () => { if (contextAvailable) { crew.pose(currentPhase, elapsed); renderer.render(scene, camera); } };
      const canAnimate = () => contextAvailable && latest.current.animate && !document.hidden;
      const tick = (time: number) => {
        frame = 0;
        if (!canAnimate()) { last = 0; return; }
        elapsed += last ? Math.min((time - last) / 1000, .1) : 0;
        last = time;
        if (time - drawn >= 1000 / 30) { draw(); drawn = time; }
        frame = requestAnimationFrame(tick);
      };
      const update = () => {
        if (currentPhase !== latest.current.phase) { currentPhase = latest.current.phase; elapsed = 0; }
        cancelAnimationFrame(frame); frame = 0; last = 0;
        draw();
        if (canAnimate()) frame = requestAnimationFrame(tick);
      };
      const resize = () => {
        const width = container.clientWidth, height = container.clientHeight;
        if (!width || !height) return;
        const aspect = width / height;
        const halfHeight = Math.max(1.8, 5.9 / aspect);
        camera.left = -halfHeight * aspect; camera.right = halfHeight * aspect;
        camera.top = halfHeight; camera.bottom = -halfHeight;
        camera.updateProjectionMatrix(); renderer.setSize(width, height, false); draw();
      };
      const contextLost = (event: Event) => { event.preventDefault(); contextAvailable = false; cancelAnimationFrame(frame); setFallback(true); };
      const observer = new ResizeObserver(resize); observer.observe(container);
      renderer.domElement.addEventListener("webglcontextlost", contextLost);
      document.addEventListener("visibilitychange", update);
      runtime.current = { update }; resize(); update();
      dispose = () => {
        runtime.current = null; cancelAnimationFrame(frame); observer.disconnect();
        document.removeEventListener("visibilitychange", update);
        renderer.domElement.removeEventListener("webglcontextlost", contextLost);
        crew.dispose(); light.shadow.dispose(); renderer.dispose(); renderer.forceContextLoss();
        renderer.domElement.remove();
      };
    }).catch(() => { if (!cancelled) setFallback(true); });
    return () => { cancelled = true; dispose?.(); };
  }, []);

  return <div className={`crew-stage${fallback ? " crew-fallback" : ""}`} ref={host} role="img"
    aria-label={`3人の整備員が${PHASE_LABEL[phase]}している工程案内`} data-motion={animate ? "playing" : "still"}>
    {fallback ? <svg viewBox="0 0 600 120" aria-hidden="true">
      <rect x="170" y="70" width="230" height="8" rx="3" fill="#c1b89d"/>
      <path d="M185 78v34m200-34v34" stroke="#576c68" strokeWidth="7"/>
      {[125, 295, 460].map((x, i) => <g key={x} transform={`translate(${x} 18)`}>
        <rect x="-17" y="38" width="34" height="39" rx="10" fill="#858681"/>
        <path d="M-9 74v19m18-19v19" stroke="#4d5753" strokeWidth="11"/>
        <circle cy="23" r="17" fill="#ecc3a0"/>
        <path d="M-20 19a20 20 0 0 1 40 0z" fill="#e5ae35"/><path d="M-23 19h46" stroke="#e5ae35" strokeWidth="6"/>
        <path d={phase === "inspecting" ? "M-16 47l-16 17m48-17l22-8" : "M-16 47l-9 24m41-24l9 24"} stroke="#858681" strokeWidth="9"/>
        <circle cx="-6" cy="24" r="2" fill="#293e40"/><circle cx="6" cy="24" r="2" fill="#293e40"/>
        {i === 2 ? <rect x="-38" y="59" width="20" height="24" fill="#eae7d8" stroke="#576c68"/> : null}
      </g>)}
    </svg> : null}
    {fallback ? <span className="crew-fallback-label">簡易表示</span> : null}
  </div>;
}
