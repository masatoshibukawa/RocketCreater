import test from "node:test";
import assert from "node:assert/strict";
import { fmtAltitude, fmtMass } from "../app/lib/units.ts";

test("heights read in metres below 1 km and in kilometres above", () => {
  assert.equal(fmtAltitude(20), "20 m");
  assert.equal(fmtAltitude(19.36), "19.4 m");
  assert.equal(fmtAltitude(2000), "2 km");
  assert.equal(fmtAltitude(400000), "400 km");
});

test("masses read in grams below 1 kg and in kilograms above", () => {
  assert.equal(fmtMass(0.06), "60 g");
  assert.equal(fmtMass(1), "1 kg");
  assert.equal(fmtMass(3.985), "3.985 kg");
  assert.equal(fmtMass(150), "150 kg");
});
