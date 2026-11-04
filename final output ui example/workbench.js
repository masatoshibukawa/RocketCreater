/* Original implementation of the reference workspace; no third-party runtime dependencies. */
"use strict";
(() => {
  const data = window.ROCKET_DEMO;
  const $ = (id) => document.getElementById(id);
  const canvas = $("model-canvas");
  const context = canvas.getContext("2d");
  const money = (value) => `${Math.round(value).toLocaleString("ja-JP")} 円`;
  const format = (value, digits = 2) => Number(value).toLocaleString("ja-JP", { maximumFractionDigits: digits });
  let selected = 0, view = "model", part = null;
  let yaw = -0.58, tilt = -0.2, zoom = 1, drag = null, width = 1, height = 1;
  let drawingUrl = null;
  const candidate = () => data.candidates[selected];
  const escape = (value) => String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);

  function setView(next) {
    view = next;
    document.querySelectorAll("[data-pane]").forEach((pane) => { pane.hidden = pane.dataset.pane !== next; });
    document.querySelectorAll("[data-view]").forEach((button) => {
      const active = button.dataset.view === next;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    if (next === "model") drawModel();
  }

  function updateProperties() {
    const d = candidate().design;
    const groups = {
      nose: [["形状", d.nose_shape], ["ノーズ長", `${format(d.nose_length_m * 1000)} mm`]],
      body: [["胴体長", `${format(d.body_length_m * 1000)} mm`], ["外径", `${format(d.body_diameter_m * 1000)} mm`], ["乾燥質量", `${format(d.dry_mass_kg)} kg`]],
      fins: [["枚数", `${d.fins.count} 枚`], ["スパン", `${format(d.fins.span_m * 1000)} mm`], ["翼根長", `${format(d.fins.root_chord_m * 1000)} mm`]],
      motor: [["カタログ ID", d.motor_id], ["データ区分", "仮置き推力曲線"]],
      recovery: [["パラシュート径", `${format(d.parachute_diameter_m)} m`], ["頂点からの開傘遅延", `${format(d.deploy_delay_s)} s`]],
      payload: [["積載質量", `${format(d.payload_mass_kg)} kg`]],
    };
    const rows = part ? groups[part] : [...groups.body, ...groups.nose];
    $("design-properties").innerHTML = rows.map(([label, value]) => `<dt>${escape(label)}</dt><dd>${escape(value)}</dd>`).join("");
    document.querySelectorAll("[data-part]").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.part === part)));
  }

  function selectCandidate(index) {
    selected = index;
    const c = candidate(), r = c.result;
    $("project-candidate").textContent = c.label;
    $("model-name").textContent = `${c.label} / アマチュア`;
    $("selection-status").textContent = `${c.label} · ${r.success ? "公称飛行 合格" : "条件未達"}`;
    $("flight-candidate").textContent = c.label;
    document.querySelectorAll(".candidate-button").forEach((button, i) => button.setAttribute("aria-pressed", String(i === index)));
    updateProperties();
    if (drawingUrl) URL.revokeObjectURL(drawingUrl);
    drawingUrl = URL.createObjectURL(new Blob([c.drawing], { type: "image/svg+xml" }));
    $("drawing-image").src = drawingUrl;
    $("flight-metrics").innerHTML = [["到達高度", `${format(r.metrics.apogee_m)} m`], ["最大速度", `${format(r.metrics.max_speed_mps)} m/s`], ["降下速度", `${format(r.metrics.descent_speed_mps)} m/s`], ["概算費用", money(r.cost_jpy)]].map(([label, value]) => `<div><span>${escape(label)}</span><strong>${escape(value)}</strong></div>`).join("");
    $("result-summary").innerHTML = `<p>${escape(c.label)} / 公称飛行：${r.success ? "条件を達成" : "条件未達"}</p><p>到達高度 ${format(r.metrics.apogee_m)} m · 概算費用 ${money(r.cost_jpy)}</p><p class="warnings">${escape(r.warnings.join(" / "))}</p>`;
    $("report-preview").textContent = c.markdown;
    $("chat-candidate-summary").innerHTML = `<dl>${data.candidates.map((entry) => `<dt>${escape(entry.label)}</dt><dd>${format(entry.result.metrics.apogee_m)} m / ${money(entry.result.cost_jpy)}</dd>`).join("")}</dl>`;
    drawFlight(); drawModel();
  }

  function drawFlight() {
    const trace = candidate().result.trace;
    const w = 640, h = 360, left = 62, right = 18, top = 15, bottom = 45;
    const maxTime = Math.max(...trace.map((point) => point.t_s), 1);
    const maxAlt = Math.ceil(Math.max(...trace.map((point) => point.altitude_m), 1) / 500) * 500;
    const x = (value) => left + value / maxTime * (w - left - right);
    const y = (value) => h - bottom - value / maxAlt * (h - top - bottom);
    const grid = Array.from({ length: 5 }, (_, i) => {
      const value = maxAlt * i / 4;
      return `<line x1="${left}" y1="${y(value)}" x2="${w - right}" y2="${y(value)}" stroke="#363636"/><text x="${left - 10}" y="${y(value) + 4}" text-anchor="end">${format(value, 0)}</text>`;
    }).join("");
    const ticks = Array.from({ length: 5 }, (_, i) => `<text x="${x(maxTime * i / 4)}" y="${h - 22}" text-anchor="middle">${format(maxTime * i / 4, 0)}</text>`).join("");
    const path = trace.map((point, i) => `${i ? "L" : "M"}${x(point.t_s).toFixed(2)},${y(point.altitude_m).toFixed(2)}`).join(" ");
    $("flight-chart").setAttribute("viewBox", `0 0 ${w} ${h}`);
    $("flight-chart").innerHTML = `<title>${escape(candidate().label)} の飛行高度</title><desc>固定デモの計算結果。横軸は時間、縦軸は海面からの高度。</desc>${grid}${ticks}<path d="${path}" stroke="#aebedb" stroke-width="2" fill="none"/><text x="${left}" y="${top - 5}">高度 (m)</text><text x="${w - right}" y="${h - 3}" text-anchor="end">時間 (s)</text>`;
  }

  // A small software viewport, drawn from the demo's actual external dimensions.
  // Interior hardware, attachment geometry, and attitude physics are not represented.
  function rotate([x, y, z]) {
    const rx = x * Math.cos(yaw) + z * Math.sin(yaw);
    const rz = -x * Math.sin(yaw) + z * Math.cos(yaw);
    return [rx * Math.cos(tilt) - y * Math.sin(tilt), rx * Math.sin(tilt) + y * Math.cos(tilt), rz];
  }
  function drawModel() {
    if (!context || !data || view !== "model") return;
    context.clearRect(0, 0, width, height);
    const d = candidate().design, radius = d.body_diameter_m / 2;
    const length = d.body_length_m + d.nose_length_m;
    const scale = Math.min(height * 0.72 / length, width * 1.3 / length) * zoom;
    const faces = [];
    function addFace(points, name, brightness) {
      const transformed = points.map((p) => rotate(p));
      faces.push({ points: transformed, depth: transformed.reduce((sum, p) => sum + p[2], 0) / points.length, name, brightness });
    }
    const rings = [[-length / 2, 0], ...Array.from({ length: 15 }, (_, i) => {
      const u = (i + 1) / 15;
      return [-length / 2 + d.nose_length_m * u, radius * Math.sin(u * Math.PI / 2)];
    }), [length / 2, radius]];
    const segments = 56;
    for (let ring = 0; ring < rings.length - 1; ring++) {
      for (let i = 0; i < segments; i++) {
        const a = i / segments * Math.PI * 2, b = (i + 1) / segments * Math.PI * 2;
        const at = (r, angle) => [rings[r][1] * Math.cos(angle), rings[r][0], rings[r][1] * Math.sin(angle)];
        const normal = rotate([Math.cos((a + b) / 2), 0, Math.sin((a + b) / 2)]);
        const brightness = 63 + 138 * Math.max(0, normal[0] * -0.6 + normal[2] * -0.7);
        addFace([at(ring, a), at(ring, b), at(ring + 1, b), at(ring + 1, a)], ring < rings.length - 2 ? "nose" : "body", brightness);
      }
    }
    for (let i = 0; i < d.fins.count; i++) {
      const angle = i / d.fins.count * Math.PI * 2;
      const root = length / 2 - d.fins.root_chord_m;
      const point = (r, y) => [r * Math.cos(angle), y, r * Math.sin(angle)];
      addFace([point(radius, root), point(radius + d.fins.span_m, root + d.fins.sweep_m), point(radius + d.fins.span_m, root + d.fins.sweep_m + d.fins.tip_chord_m), point(radius, length / 2)], "fins", 133 + 38 * Math.cos(angle + yaw));
    }
    faces.sort((a, b) => b.depth - a.depth);
    for (const face of faces) {
      context.beginPath();
      face.points.forEach(([x, y], i) => {
        const px = width / 2 + x * scale, py = height / 2 + 5 + y * scale;
        if (i) context.lineTo(px, py); else context.moveTo(px, py);
      });
      context.closePath();
      const light = Math.round(face.brightness);
      context.fillStyle = face.name === part ? `rgb(${Math.round(light * .7)},${Math.round(light * .82)},${Math.min(255, light + 35)})` : `rgb(${light},${light},${light})`;
      context.fill();
      if (face.name === "fins") { context.strokeStyle = "#adadad"; context.lineWidth = .6; context.stroke(); }
    }
  }
  function resize() {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    width = rect.width; height = rect.height;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
    context?.setTransform(ratio, 0, 0, ratio, 0, 0);
    drawModel();
  }
  function setZoom(value) {
    zoom = Math.min(2.5, Math.max(.45, value));
    $("zoom-level").textContent = `${Math.round(zoom * 100)}%`;
    drawModel();
  }
  function resetCamera() { yaw = -.58; tilt = -.2; setZoom(1); }
  canvas.addEventListener("pointerdown", (event) => {
    drag = { x: event.clientX, y: event.clientY }; canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!drag) return;
    yaw += (event.clientX - drag.x) * .012;
    tilt += (event.clientY - drag.y) * .004;
    drag = { x: event.clientX, y: event.clientY }; drawModel();
  });
  for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) canvas.addEventListener(type, () => { drag = null; });
  canvas.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "+", "=", "-", "0"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "ArrowLeft") yaw -= .13;
    if (event.key === "ArrowRight") yaw += .13;
    if (event.key === "ArrowUp") tilt -= .08;
    if (event.key === "ArrowDown") tilt += .08;
    if (event.key === "+" || event.key === "=") setZoom(zoom * 1.1);
    if (event.key === "-") setZoom(zoom / 1.1);
    if (event.key === "0") resetCamera();
    drawModel();
  });
  $("zoom-in").addEventListener("click", () => setZoom(zoom * 1.15));
  $("zoom-out").addEventListener("click", () => setZoom(zoom / 1.15));
  $("reset-camera").addEventListener("click", resetCamera);
  $("fit-camera").addEventListener("click", resetCamera);
  document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => { setView(button.dataset.view); resize(); }));
  document.querySelectorAll("[data-part]").forEach((button) => button.addEventListener("click", () => {
    part = part === button.dataset.part ? null : button.dataset.part; updateProperties(); setView("model"); resize();
  }));
  document.querySelectorAll("[data-toggle]").forEach((button) => button.addEventListener("click", () => {
    const panel = $(button.dataset.toggle === "left" ? "left-panel" : "right-panel");
    let open;
    if (button.dataset.toggle === "right" && window.matchMedia("(min-width: 851px)").matches) {
      open = !document.querySelector(".workbench").classList.toggle("right-collapsed");
    } else {
      open = panel.classList.toggle("is-open");
    }
    document.querySelectorAll(`[data-toggle="${button.dataset.toggle}"]`).forEach((control) => control.setAttribute("aria-expanded", String(open)));
  }));
  $("reference-button").addEventListener("click", () => $("reference-dialog").showModal());
  $("close-reference").addEventListener("click", () => $("reference-dialog").close());
  document.querySelectorAll("[data-download]").forEach((button) => button.addEventListener("click", () => {
    const extension = button.dataset.download, c = candidate();
    const formats = { svg: [c.drawing, "image/svg+xml"], csv: ["\uFEFF" + c.csv, "text/csv;charset=utf-8"], md: [c.markdown, "text/markdown;charset=utf-8"], json: [JSON.stringify({ ...data, candidates: [c] }, null, 2), "application/json"] };
    const url = URL.createObjectURL(new Blob([formats[extension][0]], { type: formats[extension][1] }));
    const anchor = document.createElement("a");
    anchor.href = url; anchor.download = `rocketwright-design-${"ab"[selected]}.${extension}`;
    document.body.append(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  }));
  function addMessage(role, text) {
    const element = document.createElement("div");
    element.className = `message${role === "あなた" ? " user-message" : ""}`;
    const label = document.createElement("div"); label.className = "message-role"; label.textContent = role;
    const paragraph = document.createElement("p"); paragraph.textContent = text;
    element.append(label, paragraph); $("chat-messages").append(element);
    element.scrollIntoView({ block: "nearest", behavior: "auto" });
  }
  $("chat-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const text = $("chat-input").value.trim(); if (!text) return;
    addMessage("あなた", text); $("chat-input").value = "";
    let metric = "apogee_m", descending = true, caption = "到達高度";
    if (/費用|予算|安|コスト/.test(text)) { metric = "cost_jpy"; descending = false; caption = "概算費用"; }
    else if (/回収|着地|降下/.test(text)) { metric = "descent_speed_mps"; descending = false; caption = "降下速度"; }
    else if (!/高度|高さ|高く|飛行/.test(text)) {
      addMessage("RocketWright", "この固定デモでは、高度・費用・降下速度を比較できます。たとえば「費用が低いのは？」と入力してください。新しい設計計算は行いません。"); return;
    }
    const values = data.candidates.map((entry) => metric === "cost_jpy" ? entry.result.cost_jpy : entry.result.metrics[metric]);
    const index = values.indexOf(descending ? Math.max(...values) : Math.min(...values));
    selectCandidate(index); setView("flight");
    const pretty = (value) => metric === "cost_jpy" ? money(value) : `${format(value)} ${metric === "apogee_m" ? "m" : "m/s"}`;
    addMessage("RocketWright", `${caption}で比較すると、${data.candidates.map((entry, i) => `${entry.label}は${pretty(values[i])}`).join("、")}です。${data.candidates[index].label}を表示しました。同じ固定条件で計算した公称飛行の比較です。`);
  });

  $("candidate-list").innerHTML = data.candidates.map((entry, index) => `<button class="candidate-button" aria-pressed="${index === 0}" data-candidate="${index}"><svg aria-hidden="true"><use href="#i-cube"/></svg><span>${escape(entry.label)}</span><span class="candidate-result">${entry.result.success ? "公称飛行 合格" : "条件未達"}</span></button>`).join("");
  document.querySelectorAll("[data-candidate]").forEach((button) => button.addEventListener("click", () => selectCandidate(Number(button.dataset.candidate))));
  new ResizeObserver(resize).observe(canvas);
  selectCandidate(0); resize();
})();
