import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { simulate, compareFill, DEFAULTS } from '../dist/functional/bottle-model.mjs';
import { report, shapeSvg, trajectoryCsv } from '../dist/functional/outputs.mjs';

const reference = JSON.parse(readFileSync(new URL('./python-reference.json', import.meta.url), 'utf8'));
test('fixtures retain the matching Python model source', () => {
  for (const [path, expected] of Object.entries(reference.sources)) {
    const location = new URL('../../../' + path, import.meta.url);
    if (existsSync(location)) {
      const text = readFileSync(location, 'utf8').replaceAll('\r\n', '\n');
      assert.equal(createHash('sha256').update(text).digest('hex'), expected, path);
    }
  }
});
for (const fixture of reference.cases) test(`matches Python: ${fixture.name}`, () => {
  const result = simulate(fixture.input);
  // The Python solver omits the instant immediately after the residual-air impulse
  // from its sampled maximum-speed metric. Compare the shared event/integral metrics.
  for (const key of ['apogee_m','apogee_time_s','descent_speed_mps','flight_time_s','liftoff_mass_kg','rail_exit_speed_mps','air_impulse_ns']) {
    const expected = fixture.metrics[key];
    const tolerance = Math.max(0.015, Math.abs(expected) * 0.003);
    assert.ok(Math.abs(result.metrics[key] - expected) <= tolerance, `${key}: ${result.metrics[key]} vs ${expected}`);
  }
  if (result.checks[0].passed) assert.equal(result.trace.at(-1).altitude_m, 0);
  for (let i = 1; i < result.trace.length; i++) assert.ok(result.trace[i].t_s >= result.trace[i-1].t_s);
});
test('changes to conditions are recalculated and unmet checks are visible', () => {
  const baseline = simulate(DEFAULTS), lowPressure = simulate({...DEFAULTS, pressure:150});
  assert.ok(baseline.passed);
  assert.ok(lowPressure.metrics.apogee_m < baseline.metrics.apogee_m * 0.5);
  assert.ok(!lowPressure.passed);
  assert.ok(!simulate({...DEFAULTS,budget:1500}).checks.find(check => check.label.includes('予算')).passed);
  const cases = compareFill(DEFAULTS);
  assert.equal(cases.length, 9);
  assert.equal(new Set(cases.map(result => result.input.fill)).size, 9);
  assert.ok(cases.every((result,index) => index === 0 || Math.abs(result.metrics.apogee_m - DEFAULTS.target) >= Math.abs(cases[index-1].metrics.apogee_m - DEFAULTS.target)));
});
test('exports contain the selected calculation and invalid inputs are rejected', () => {
  const result = simulate({...DEFAULTS,fill:25});
  assert.ok(report(result).includes('充填率 25%'));
  assert.ok(shapeSvg(result).includes('充填率 25%'));
  assert.equal(trajectoryCsv(result).trim().split('\r\n').length, result.trace.length+1);
  for (const invalid of [NaN, Infinity, 0, -1, 401]) assert.throws(() => simulate({...DEFAULTS,pressure:invalid}));
});
