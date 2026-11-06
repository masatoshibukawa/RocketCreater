import { DEFAULTS, LIMITS, simulate, compareFill } from './bottle-model.mjs';
import { report, trajectoryCsv, shapeSvg } from './outputs.mjs';

const $ = id => document.getElementById(id);
const form = $('conditions');
let selected = null, candidates = [], tab = 'result';
const labels = { target: '目標高度', volume: 'ボトル容量', fill: '水の充填率', pressure: '初期ゲージ圧', dryMass: '乾燥質量', payload: '搭載質量', nozzle: 'ノズル径', parachute: 'パラシュート径', budget: '材料予算' };
const units = { target:'m', volume:'L', fill:'%', pressure:'kPa', dryMass:'g', payload:'g', nozzle:'mm', parachute:'m', budget:'円' };
const fmt = (value, digits = 2) => value.toLocaleString('ja-JP', { maximumFractionDigits: digits });
function setValues(input) { for (const key of Object.keys(LIMITS)) form.elements.namedItem(key).value = input[key]; }
function readValues() { return Object.fromEntries(Object.keys(LIMITS).map(key => [key, Number(form.elements.namedItem(key).value)])); }
function showTab(next) {
  tab = next;
  document.querySelectorAll('[data-tab]').forEach(button => { const active = button.dataset.tab === next; button.setAttribute('aria-selected', String(active)); button.tabIndex = active ? 0 : -1; });
  document.querySelectorAll('[data-pane]').forEach(pane => { pane.hidden = pane.dataset.pane !== next; });
}
function drawChart(result) {
  const width = 640, height = 340, left = 54, right = 18, top = 25, bottom = 40;
  const maxTime = Math.max(result.metrics.flight_time_s, 1);
  const maxHeight = Math.max(result.metrics.apogee_m * 1.15, result.input.target * 1.2, 1);
  const x = value => left + value / maxTime * (width - left - right);
  const y = value => height - bottom - value / maxHeight * (height - top - bottom);
  const grid = Array.from({ length:5 }, (_, i) => { const h = maxHeight * i / 4; return `<line x1="${left}" x2="${width-right}" y1="${y(h)}" y2="${y(h)}" stroke="#393939"/><text x="${left-10}" y="${y(h)+4}" text-anchor="end">${fmt(h,1)}</text><text x="${x(maxTime*i/4)}" y="${height-18}" text-anchor="middle">${fmt(maxTime*i/4,1)}</text>`; }).join('');
  const path = result.trace.map((point, index) => `${index ? 'L' : 'M'}${x(point.t_s).toFixed(3)},${y(point.altitude_m).toFixed(3)}`).join(' ');
  $('trajectory').setAttribute('viewBox', `0 0 ${width} ${height}`);
  $('trajectory').innerHTML = `<title>目標 ${result.input.target} m / 計算高度 ${fmt(result.metrics.apogee_m)} m</title><desc>海面・無風・鉛直の簡易飛行計算。横軸は秒、縦軸はメートル。</desc><rect x="${left}" y="${y(result.input.target*1.1)}" width="${width-left-right}" height="${y(result.input.target*.9)-y(result.input.target*1.1)}" fill="#687da42b"/>${grid}<path d="${path}" fill="none" stroke="#9db6ff" stroke-width="2.5"/><text x="${left}" y="14">高度 (m)</text><text x="${width-right}" y="${height-2}" text-anchor="end">時間 (s)</text>`;
}
function renderCandidateList() {
  const fragment = document.createDocumentFragment();
  candidates.forEach((result, index) => {
    const button = document.createElement('button'); button.className = 'candidate'; button.type = 'button';
    button.setAttribute('aria-pressed', String(result === selected));
    const title = document.createElement('b'); title.textContent = `水 ${result.input.fill}% · ${fmt(result.metrics.apogee_m)} m`;
    const note = document.createElement('span'); note.textContent = `${result.passed ? '条件通過' : '未達あり'} / 目標との差 ${fmt(Math.abs(result.metrics.apogee_m-result.input.target))} m`;
    button.append(title, note); button.addEventListener('click', () => { setValues(result.input); render(result); $('progress').textContent = `比較候補 ${index+1} / ${candidates.length} を表示中`; }); fragment.append(button);
  });
  $('candidates').replaceChildren(fragment);
}
function render(result) {
  selected = result;
  $('welcome').hidden = true; $('results').hidden = false; $('dirty-note').hidden = true;
  const m = result.metrics;
  $('verdict').textContent = result.passed ? '計算条件を通過' : '未達の条件あり';
  $('verdict').classList.toggle('is-fail', !result.passed);
  $('metrics').innerHTML = [['最高高度',`${fmt(m.apogee_m)} m`],['定常降下速度',`${fmt(m.descent_speed_mps)} m/s`],['全飛行時間',`${fmt(m.flight_time_s)} s`],['暫定費用',`${fmt(m.cost_jpy,0)} 円`]].map(([name,value])=>`<div><small>${name}</small><strong>${value}</strong></div>`).join('');
  $('run-conditions').textContent = `${result.input.volume} L / 水 ${result.input.fill}% / ${result.input.pressure} kPa / 乾燥 ${result.input.dryMass} g / 搭載 ${result.input.payload} g / ${result.conditions}${result.checks[0].passed ? '' : '。ガイドを離れていないため、自由飛行と降下は未計算です。'}`;
  const fragment = document.createDocumentFragment();
  result.checks.forEach(check => {
    const row = document.createElement('div'); row.className = `check${check.passed ? '' : ' is-fail'}`;
    const title = document.createElement('b'); title.textContent = `${check.passed ? '✓' : '△'} ${check.label}`;
    const detail = document.createElement('span'); detail.textContent = check.detail; row.append(title,detail); fragment.append(row);
  });
  $('checks').replaceChildren(fragment);
  $('shape').innerHTML = shapeSvg(result);
  $('input-summary').innerHTML = Object.entries(result.input).map(([key,value])=>`<dt>${labels[key]}</dt><dd>${fmt(value)} ${units[key]}</dd>`).join('');
  $('report').textContent = report(result);
  drawChart(result); renderCandidateList(); showTab(tab);
}
async function run(comparing = false) {
  if (!form.reportValidity()) return;
  const input = readValues();
  $('error').hidden = true;
  $('progress').textContent = comparing ? '9通りの水量で飛行を計算しています…' : '入力条件から飛行を計算しています…';
  const buttons = [...document.querySelectorAll('button')]; buttons.forEach(button => { button.disabled = true; });
  try {
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const start = performance.now();
    candidates = comparing ? compareFill(input) : [simulate(input)];
    const elapsed = performance.now() - start;
    if (comparing) setValues(candidates[0].input);
    render(candidates[0]);
    $('progress').textContent = `${comparing ? '9案の比較' : '解析'}が完了しました · 計算 ${fmt(elapsed,0)} ms`;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    $('error').textContent = message.replace(/^[A-Za-z]+:/, key => (labels[key.slice(0,-1)] ?? key) + ':'); $('error').hidden = false;
    $('progress').textContent = '解析できませんでした。入力条件を確認してください。';
  } finally { buttons.forEach(button => { button.disabled = false; }); }
}
form.addEventListener('submit', event => { event.preventDefault(); void run(); });
form.addEventListener('input', () => { if (selected) { $('dirty-note').hidden = false; $('progress').textContent = '入力変更あり / 再解析すると結果を更新します'; } });
$('compare').addEventListener('click', () => void run(true));
$('sample').addEventListener('click', () => { setValues(DEFAULTS); void run(); });
$('budget-example').addEventListener('click', () => { setValues({...DEFAULTS,budget:1500}); void run(); });
$('reset').addEventListener('click', () => {
  setValues(DEFAULTS); selected = null; candidates = [];
  $('results').hidden = true; $('welcome').hidden = false; $('dirty-note').hidden = true; $('error').hidden = true;
  $('checks').replaceChildren(); $('candidates').replaceChildren(); $('progress').textContent = '条件の入力を待っています'; showTab('result');
});
const tabs = [...document.querySelectorAll('[data-tab]')];
tabs.forEach((button,index) => {
  button.addEventListener('click', () => showTab(button.dataset.tab));
  button.addEventListener('keydown', event => {
    const next = event.key === 'ArrowRight' ? (index+1)%tabs.length : event.key === 'ArrowLeft' ? (index+tabs.length-1)%tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length-1 : null;
    if (next !== null) { event.preventDefault(); showTab(tabs[next].dataset.tab); tabs[next].focus(); }
  });
});
document.querySelectorAll('[data-export]').forEach(button => button.addEventListener('click', () => {
  if (!selected) return;
  const format = button.dataset.export;
  const content = { json:[JSON.stringify({schema_version:1,...selected},null,2),'application/json'], csv:[trajectoryCsv(selected),'text/csv;charset=utf-8'], md:[report(selected),'text/markdown;charset=utf-8'], svg:[shapeSvg(selected),'image/svg+xml'] }[format];
  const url = URL.createObjectURL(new Blob([content[0]],{type:content[1]}));
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = `rocketwright-bottle-result.${format}`; document.body.append(anchor); anchor.click(); anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url),5000);
}));
setValues(DEFAULTS); showTab('result');
