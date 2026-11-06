// Browser implementation of the repository's nominal water/recovery model.
// Scope: vertical launch, sea level, no wind, fins, parachute opening at apogee.
// Residual air uses the original provisional impulse approximation (not CFD).
export const MODEL = Object.freeze({
  id: "bottle-browser-v1", gravity: 9.80665, gamma: 1.4,
  gasConstant: 8.31432 / 0.0289644, dragCoefficient: 0.8,
  airImpulseEfficiency: 0.25, parachuteCd: 1.5, railLength: 1.5,
  source: "rocketwright/physics/water.py + recovery.py + atmosphere.py + cost.py",
  conditions: "海面・無風・鉛直発射・フィンあり・最高点で開傘",
});

export const DEFAULTS = Object.freeze({ target: 20, volume: 1.5, fill: 35, pressure: 330, dryMass: 180, payload: 60, nozzle: 9, parachute: 0.6, budget: 3000 });
export const LIMITS = Object.freeze({ target: [1, 200], volume: [0.5, 3], fill: [5, 80], pressure: [50, 400], dryMass: [50, 500], payload: [0, 200], nozzle: [5, 16], parachute: [0.3, 1.2], budget: [0, 100000] });

export function validate(input) {
  for (const [key, [min, max]] of Object.entries(LIMITS)) {
    if (typeof input[key] !== "number" || !Number.isFinite(input[key]) || input[key] < min || input[key] > max) throw new Error(`${key}: ${min}〜${max} の数値を入力してください。`);
  }
}

function atmosphere(altitude) {
  const z = Math.max(0, altitude);
  const h = 6356766 * z / (6356766 + z);
  const temperature = 288.15 - 0.0065 * h;
  const pressure = 101325 * (288.15 / temperature) ** (MODEL.gravity / (MODEL.gasConstant * -0.0065));
  return { temperature, pressure, density: pressure / (MODEL.gasConstant * temperature) };
}

function rk4(state, step, dynamics) {
  const plus = (a, b, factor) => a.map((value, index) => value + b[index] * factor);
  const a = dynamics(state), b = dynamics(plus(state, a, step / 2));
  const c = dynamics(plus(state, b, step / 2)), d = dynamics(plus(state, c, step));
  return state.map((value, i) => value + step * (a[i] + 2 * b[i] + 2 * c[i] + d[i]) / 6);
}

export function simulate(input) {
  validate(input);
  const volume = input.volume / 1000, fill = input.fill / 100;
  const dry = (input.dryMass + input.payload) / 1000;
  const water0 = volume * fill * 1000, air0 = volume * (1 - fill);
  const pAtm = 101325, p0 = pAtm + input.pressure * 1000;
  const nozzleArea = Math.PI * (input.nozzle / 2000) ** 2;
  const bodyDiameter = 0.09 * (volume / 0.0015) ** (1 / 3);
  const bodyArea = Math.PI * (bodyDiameter / 2) ** 2;
  const waterEnd = Math.max(0, 1000 * (volume - air0 * (p0 / pAtm) ** (1 / MODEL.gamma)));
  const pressure = (water) => p0 * (air0 / (volume - Math.max(water, 0) / 1000)) ** MODEL.gamma;
  let onRail = true, waterOn = true, state = [0, 0, water0], t = 0;
  let railExitTime = 0, railExitSpeed = 0, burnEnd = 0, airImpulse = 0;
  let maxSpeed = 0, maxAltitude = 0, leftRail = false;
  const peakThrust = 2 * input.pressure * 1000 * nozzleArea;
  const trace = [{ t_s: 0, altitude_m: 0, speed_mps: 0, mass_kg: dry + water0 }];
  const dynamics = ([z, v, water]) => {
    const dp = Math.max(0, pressure(water) - pAtm);
    const thrust = waterOn && water > 0 ? 2 * dp * nozzleArea : 0;
    const flow = waterOn && water > 0 ? 1000 * nozzleArea * Math.sqrt(2 * dp / 1000) : 0;
    const drag = 0.5 * atmosphere(z).density * v * Math.abs(v) * MODEL.dragCoefficient * bodyArea;
    let acceleration = (thrust - drag) / (dry + Math.max(water, 0)) - MODEL.gravity;
    if (onRail && v <= 0 && acceleration < 0) acceleration = 0;
    return [onRail ? Math.max(v, 0) : v, acceleration, -flow];
  };
  const record = () => {
    maxSpeed = Math.max(maxSpeed, state[1]);
    maxAltitude = Math.max(maxAltitude, state[0]);
    trace.push({ t_s: t, altitude_m: Math.max(0, state[0]), speed_mps: Math.abs(state[1]), mass_kg: dry + Math.max(state[2], 0) });
  };
  if (peakThrust > (dry + water0) * MODEL.gravity) {
    for (let iteration = 0; iteration < 150000 && t < 300; iteration++) {
      const step = waterOn ? 0.0002 : 0.01;
      const next = rk4(state, step, dynamics);
      const events = [];
      if (onRail && next[0] >= MODEL.railLength) events.push({ kind: "rail", axis: 0, value: MODEL.railLength, increasing: true });
      if (waterOn && next[2] <= waterEnd + 1e-12) events.push({ kind: "water", axis: 2, value: waterEnd, increasing: false });
      if (state[1] > 0 && next[1] <= 0) events.push({ kind: "apogee", axis: 1, value: 0, increasing: false });
      if (events.length) {
        for (const event of events) {
          let low = 0, high = step;
          for (let k = 0; k < 32; k++) {
            const mid = (low + high) / 2, candidate = rk4(state, mid, dynamics)[event.axis];
            const passed = event.increasing ? candidate >= event.value : candidate <= event.value;
            if (passed) high = mid; else low = mid;
          }
          event.time = (low + high) / 2;
        }
        events.sort((a, b) => a.time - b.time);
        const event = events[0];
        state = rk4(state, event.time, dynamics); t += event.time;
        state[event.axis] = event.value;
        if (event.kind === "rail") { onRail = false; leftRail = true; railExitTime = t; railExitSpeed = state[1]; }
        if (event.kind === "water") {
          waterOn = false; burnEnd = t;
          if (waterEnd === 0) {
            const pEnd = p0 * (air0 / volume) ** MODEL.gamma;
            if (pEnd > pAtm) {
              const airMass = p0 * air0 / (MODEL.gasConstant * 288.15);
              const work = pEnd * volume / (MODEL.gamma - 1) * (1 - (pAtm / pEnd) ** ((MODEL.gamma - 1) / MODEL.gamma));
              airImpulse = MODEL.airImpulseEfficiency * Math.sqrt(2 * airMass * work);
              state[1] += airImpulse / dry;
            }
          }
        }
        record();
        if (event.kind === "apogee") break;
      } else { state = next; t += step; if (iteration % (waterOn ? 25 : 2) === 0) record(); }
      if (!state.every(Number.isFinite)) throw new Error("数値計算を継続できません。条件を変更してください。");
    }
  }
  record();
  if (t >= 300) throw new Error("解析時間の上限を超えました。条件を見直してください。");
  const apogeeTime = t, apogee = maxAltitude;
  const mass = dry + Math.max(state[2], 0);
  const descentSpeed = leftRail ? Math.sqrt(2 * mass * MODEL.gravity / (atmosphere(apogee / 2).density * MODEL.parachuteCd * Math.PI * (input.parachute / 2) ** 2)) : 0;
  const descentTime = leftRail ? apogee / descentSpeed : 0;
  if (leftRail) for (let i = 1; i <= 40; i++) trace.push({ t_s: apogeeTime + descentTime * i / 40, altitude_m: apogee * (1 - i / 40), speed_mps: descentSpeed, mass_kg: mass });
  const cost = 2300; // Same provisional 1500 + 800 JPY placeholders as cost.py.
  const checks = [
    { label: "発射ガイドを離脱", passed: leftRail, detail: leftRail ? `${railExitSpeed.toFixed(2)} m/s` : "離脱しませんでした" },
    { label: "目標高度の±10%", passed: Math.abs(apogee - input.target) <= input.target * 0.1, detail: `${apogee.toFixed(2)} m / 目標 ${input.target} m` },
    { label: "計算上の降下速度", passed: leftRail && descentSpeed <= (input.payload > 0 ? 6 : 10), detail: leftRail ? `${descentSpeed.toFixed(2)} m/s` : "飛行なし" },
    { label: "暫定費用が予算内", passed: cost <= input.budget, detail: `${cost.toLocaleString("ja-JP")} 円 / 予算 ${input.budget.toLocaleString("ja-JP")} 円` },
  ];
  const stride = Math.max(1, Math.ceil(trace.length / 350));
  const compact = trace.filter((point, i) => i % stride === 0 || i === trace.length - 1 || Math.abs(point.t_s - apogeeTime) < 1e-9);
  return { model: MODEL.id, input: { ...input }, conditions: MODEL.conditions, passed: checks.every(c => c.passed), checks,
    metrics: { apogee_m: apogee, apogee_time_s: apogeeTime, max_speed_mps: maxSpeed, descent_speed_mps: descentSpeed, flight_time_s: apogeeTime + descentTime, liftoff_mass_kg: dry + water0, rail_exit_speed_mps: railExitSpeed, rail_exit_time_s: railExitTime, thrust_phase_duration_s: burnEnd, air_impulse_ns: airImpulse, cost_jpy: cost },
    body_diameter_m: bodyDiameter, trace: compact,
    limitations: ["一定Cd=0.8、残留空気は効率0.25の瞬間インパルスで近似。", "海面・無風・鉛直・フィンあり。最高点で開傘し、定常速度で降下。", "費用は既存モデルの暫定値。機体形状・姿勢・CFD・製造用CAD・実機検証は対象外。", "入力範囲は計算デモの範囲で、ボトルや発射装置の許容値を示しません。"] };
}

export function compareFill(input) {
  validate(input);
  return [15, 20, 25, 30, 35, 40, 45, 50, 55].map(fill => simulate({ ...input, fill }))
    .sort((a, b) => Math.abs(a.metrics.apogee_m - input.target) - Math.abs(b.metrics.apogee_m - input.target));
}
