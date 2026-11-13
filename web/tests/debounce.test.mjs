import { test } from "node:test";
import assert from "node:assert/strict";
import { createDebouncer } from "../shared/debounce.js";

const warn = (id, confidence = 0.9) => ({ status: "warn", mistake_id: id, confidence });
const ok = () => ({ status: "ok", mistake_id: null, confidence: 0.9 });

test("two warns with the same id alert on the second", () => {
  const d = createDebouncer({ threshold: 0.7 });
  assert.equal(d.ingest(warn("rice_too_thick"), 0), null);
  const second = warn("rice_too_thick");
  assert.equal(d.ingest(second, 2500), second);
});

test("an alert starts a new streak", () => {
  const d = createDebouncer();
  d.ingest(warn("a"), 0);
  assert.ok(d.ingest(warn("a"), 1));
  assert.equal(d.ingest(warn("a"), 2), null);
  assert.ok(d.ingest(warn("a"), 3));
});

test("different ids do not alert", () => {
  const d = createDebouncer();
  assert.equal(d.ingest(warn("a"), 0), null);
  assert.equal(d.ingest(warn("b"), 1), null);
  assert.equal(d.ingest(warn("a"), 2), null);
});

test("warn, ok, warn does not alert", () => {
  const d = createDebouncer();
  d.ingest(warn("a"), 0);
  d.ingest(ok(), 1);
  assert.equal(d.ingest(warn("a"), 2), null);
});

test("below the threshold does not count and breaks the streak", () => {
  const d = createDebouncer({ threshold: 0.7 });
  assert.equal(d.ingest(warn("a", 0.69), 0), null);
  assert.equal(d.ingest(warn("a", 0.69), 1), null);
  d.ingest(warn("a", 0.9), 2);
  d.ingest(warn("a", 0.5), 3);
  assert.equal(d.ingest(warn("a", 0.9), 4), null);
});

test("exactly the threshold counts", () => {
  const d = createDebouncer({ threshold: 0.7 });
  d.ingest(warn("a", 0.7), 0);
  assert.ok(d.ingest(warn("a", 0.7), 1));
});

test("a dismissed id is muted for 20 s, then alerts again", () => {
  const d = createDebouncer({ muteMs: 20000 });
  d.dismissed("a", 1000);
  assert.equal(d.ingest(warn("a"), 2000), null);
  assert.equal(d.ingest(warn("a"), 4500), null);
  assert.equal(d.ingest(warn("a"), 20999), null);
  assert.equal(d.ingest(warn("a"), 21000), null); // mute over: first of a new streak
  assert.ok(d.ingest(warn("a"), 23500));
});

test("muting one id leaves another alone", () => {
  const d = createDebouncer();
  d.dismissed("a", 0);
  d.ingest(warn("b"), 1);
  assert.ok(d.ingest(warn("b"), 2));
});

test("third consecutive error returns true, a success resets the count", () => {
  const d = createDebouncer();
  assert.equal(d.recordError(), false);
  assert.equal(d.recordError(), false);
  assert.equal(d.recordError(), true);
  assert.equal(d.recordError(), false);
  d.ingest(ok(), 0);
  assert.equal(d.recordError(), false);
  assert.equal(d.recordError(), false);
  assert.equal(d.recordError(), true);
});

test("an error breaks a streak", () => {
  const d = createDebouncer();
  d.ingest(warn("a"), 0);
  d.recordError();
  assert.equal(d.ingest(warn("a"), 1), null);
});

test("reset clears the streak", () => {
  const d = createDebouncer();
  d.ingest(warn("a"), 0);
  d.reset();
  assert.equal(d.ingest(warn("a"), 1), null);
});
