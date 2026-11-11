import { test } from "node:test";
import assert from "node:assert/strict";
import { jobsDue } from "../src/schedule.js";

// Fecha UTC: 2026-11-11 es miercoles; 2026-11-13 es viernes; 2026-11-15 es domingo.
const at = (iso) => new Date(iso);

test("news runs at 13:05 UTC every day", () => {
  assert.deepEqual(jobsDue(at("2026-11-11T13:05:00Z")), ["news"]);
  assert.deepEqual(jobsDue(at("2026-11-14T13:05:00Z")), ["news"]);
});

test("session runs every 15 minutes in market hours on weekdays", () => {
  assert.deepEqual(jobsDue(at("2026-11-11T15:15:00Z")), ["session"]);
  assert.deepEqual(jobsDue(at("2026-11-11T15:20:00Z")), []);
  assert.deepEqual(jobsDue(at("2026-11-14T15:15:00Z")), []);
});

test("paper and candidates run after the close on weekdays", () => {
  assert.deepEqual(jobsDue(at("2026-11-11T21:35:00Z")), ["paper"]);
  assert.deepEqual(jobsDue(at("2026-11-11T21:50:00Z")), ["candidates"]);
});

test("scan runs on Friday at 22:00 UTC only", () => {
  assert.deepEqual(jobsDue(at("2026-11-13T22:00:00Z")), ["scan"]);
  assert.deepEqual(jobsDue(at("2026-11-11T22:00:00Z")), []);
});

test("quiet minutes run nothing", () => {
  assert.deepEqual(jobsDue(at("2026-11-11T10:37:00Z")), []);
});
