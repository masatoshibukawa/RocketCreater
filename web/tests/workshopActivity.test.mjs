import test from "node:test";
import assert from "node:assert/strict";
import { designCrewTask, chooseCrewTask, transitionCrew, INITIAL_CREW, CLEANUP_MS } from "../app/lib/workshopActivity.ts";

const state = (extra = {}) => ({ status: "idle", pendingQuestion: null, events: [], candidates: [], final: null, ...extra });
const event = (type, id, extra = {}) => ({ type, payload: { id, ...extra } });
const task = (status, id = "run-1") => ({ id, status, label: status });

test("inspection tracks unfinished calls and waits for the next actual operation", () => {
  const call = event("tool_call", "flight", { name: "simulate_design" });
  const result = event("tool_result", "flight");
  assert.equal(designCrewTask(state({ status: "streaming", events: [call] })).status, "working");
  assert.equal(designCrewTask(state({ status: "streaming", events: [call, result] })).status, "waiting");
  assert.equal(designCrewTask(state({ status: "streaming", pendingQuestion: "目標は？", events: [call] })).status, "waiting");
});

test("failed tools, interrupted runs and seed-only results never signal completion", () => {
  for (const payload of [{ is_error: true }, { result: { error: "unavailable" } }]) {
    assert.equal(designCrewTask(state({ status: "streaming", events: [event("tool_result", "bad", payload)] })).status, "attention");
  }
  assert.equal(designCrewTask(state({ status: "done" })).status, "stopped");
  assert.equal(designCrewTask(state({ status: "error" })).status, "attention");
  assert.equal(designCrewTask(state({ status: "done", final: {}, candidates: [{ passed: true, seededFrom: "reference" }] })).status, "attention");
  assert.equal(designCrewTask(state({ status: "done", final: {}, candidates: [{ passed: true }] })).status, "done");
});

test("only an observed successful end tidies, then returns to waiting once", () => {
  const inspecting = transitionCrew(INITIAL_CREW, task("working"), 100);
  assert.equal(inspecting.phase, "inspecting");
  const cleanup = transitionCrew(inspecting, task("done"), 200);
  assert.equal(cleanup.phase, "tidying");
  assert.equal(transitionCrew(cleanup, task("done"), 201).cleanupUntil, 200 + CLEANUP_MS);
  const waiting = transitionCrew(cleanup, task("done"), 200 + CLEANUP_MS);
  assert.equal(waiting.phase, "waiting");
  assert.equal(transitionCrew(waiting, task("done"), 99999).phase, "waiting");
  assert.equal(transitionCrew(INITIAL_CREW, task("done"), 200).phase, "waiting");
});

test("queue, failure, cancellation and a new design interrupt cleanup without celebrating", () => {
  const waiting = transitionCrew(INITIAL_CREW, task("waiting"), 1);
  assert.equal(waiting.phase, "waiting");
  for (const status of ["attention", "stopped"]) {
    const frozen = transitionCrew(waiting, task(status), 2);
    assert.equal(frozen.phase, "attention"); assert.equal(frozen.cleanupUntil, 0);
  }
  const cleanup = transitionCrew(waiting, task("done"), 3);
  assert.equal(transitionCrew(cleanup, task("waiting", "run-2"), 4).phase, "waiting");
});

test("a current operation outranks saved results; equal statuses use the latest operation", () => {
  const tasks = [
    { source: "design", task: task("done"), order: 20 },
    { source: "aero", task: task("working"), order: 10 },
  ];
  assert.equal(chooseCrewTask(tasks).id, "aero:run-1");
  assert.equal(chooseCrewTask([...tasks, { source: "print", task: task("working"), order: 30 }]).id, "print:run-1");
  assert.equal(chooseCrewTask([]).status, "idle");
});
