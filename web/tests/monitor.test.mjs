import { test } from 'node:test';
import assert from 'node:assert/strict';
import { connectionState, deriveLens, frameUrl, describeEvent } from '../monitor/state.js';
import { MonitorPoller } from '../monitor/polling.js';

const now = Date.parse('2026-11-14T12:00:00Z');
const at = age => new Date(now - age).toISOString();
const event = (kind, age = 0, payload = {}, step_id = 'step-4') => ({ id: `${kind}-${age}`, kind, created_at: at(age), payload, step_id });
const feed = events => ({ session: { id: 'a', started_at: at(60000), finished_at: null },
  current_step: { id: 'step-4', recipe_id: 'recipe', idx: 4, title: 'Add fillings', key_line: 'One even layer, edge to edge', ref_image_url: '/ref.jpg' },
  events, last_frame_at: at(500), last_result: null });

test('LIVE requires a recent poll and actual recent activity; replay always wins', () => {
  const state = { feed: feed([]), lastSuccess: now - 2999 };
  assert.equal(connectionState(state, now), 'live');
  assert.equal(connectionState({ ...state, lastSuccess: now - 3000 }, now), 'offline');
  assert.equal(connectionState({ ...state, failed: true }, now), 'offline');
  assert.equal(connectionState({ ...state, replay: true, failed: true }, now), 'replay');
  assert.equal(connectionState({ feed: { ...feed([]), last_frame_at: at(30000) }, lastSuccess: now }, now), 'idle');
  assert.equal(connectionState({ feed: { ...feed([]), session: { ...feed([]).session, finished_at: at(100) } }, lastSuccess: now }, now), 'idle');
});

test('fresh question activity keeps a session live without a new frame', () => {
  const f = feed([event('question', 100, { caption: 'Why to the edges?' })]);
  f.last_frame_at = at(40000);
  assert.equal(connectionState({ feed: f, lastSuccess: now }, now), 'live');
});

test('warning persists across unrelated events and disappears after dismissal or step change', () => {
  const warning = event('watch_warn', 5000, { headline: 'Filling piled up', fix: 'Spread it to the edges' });
  let screen = deriveLens(feed([event('question', 100), warning]), 6, now);
  assert.equal(screen.kind, 'fix'); assert.equal(screen.proactive, true);
  assert.equal(screen.fix, 'Spread it to the edges');
  screen = deriveLens(feed([event('warning_dismissed', 100), warning]), 6, now);
  assert.equal(screen.kind, 'step');
  assert.equal(deriveLens(feed([event('step_change', 100), warning]), 6, now).kind, 'step');
});

test('pass and unsure expire at the specified boundaries', () => {
  assert.equal(deriveLens(feed([event('check_pass', 2999)]), 6, now).kind, 'pass');
  assert.equal(deriveLens(feed([event('check_pass', 3000)]), 6, now).kind, 'step');
  assert.equal(deriveLens(feed([event('check_unsure', 3999)]), 6, now).kind, 'unsure');
  assert.equal(deriveLens(feed([event('check_unsure', 4000)]), 6, now).kind, 'step');
});

test('late check results from another step cannot replace the current lens card', () => {
  const screen = deriveLens(feed([event('check_fix', 0, { headline: 'Old mistake' }, 'step-3')]), 6, now);
  assert.equal(screen.kind, 'step'); assert.equal(screen.card.idx, 4);
});

test('newer pass beats an older warning; equal timestamps retain newest-first feed order', () => {
  assert.equal(deriveLens(feed([event('watch_warn', 4000), event('check_pass', 100)]), 6, now).kind, 'pass');
  assert.equal(deriveLens(feed([event('warning_dismissed', 0), event('watch_warn', 0)]), 6, now).kind, 'step');
});

test('watcher indicator expires after six seconds and is not active after session end', () => {
  const f = feed([]); f.last_result = { source: 'watch', at: at(5999), body: { status: 'ok' } };
  assert.equal(deriveLens(f, 6, now).card.watching, 'active');
  f.last_result.at = at(6000);
  assert.equal(deriveLens(f, 6, now).card.watching, 'off');
  f.last_result.at = at(1); f.session.finished_at = at(0);
  assert.equal(deriveLens(f, 6, now).card.watching, 'off');
});

test('frame cache busting preserves signed queries and rejects executable URLs', () => {
  const url = new URL(frameUrl('https://example.com/frame?token=abc#photo', at(0), 'http://localhost:8100'));
  assert.equal(url.searchParams.get('token'), 'abc');
  assert.equal(url.searchParams.get('_frame_at'), at(0));
  assert.equal(url.hash, '#photo');
  assert.equal(frameUrl('javascript:alert(1)', at(0), 'http://localhost:8100'), null);
});

test('timeline labels include the verdict, measured latency, and confidence', () => {
  const item = describeEvent(event('check_fix', 0, { headline: 'Filling piled up', confidence: .91, latency_ms: 1400 }));
  assert.match(item.text, /fix/); assert.match(item.text, /91%/); assert.match(item.text, /1\.4 s/);
  assert.match(describeEvent(event('question', 0, { caption: 'Why to the edges?' })).text, /Why to the edges/);
});

const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
const active = (id, age = 0) => ({ id, started_at: at(age) });

test('discovery attaches immediately, follows a restart, and does not override a pin', async () => {
  let clock = now, rows = [active('older', 1000), active('new')], received = [];
  const p = new MonitorPoller({ now: () => clock, listSessions: async () => ({ sessions: rows }), getMonitor: async id => ({ id }), onFeed: f => received.push(f.id) });
  await p.tick(); assert.equal(p.sessionId, 'new'); assert.deepEqual(received, ['new']);
  clock += 5000; rows = [active('restart', -5000), ...rows];
  await p.tick(); assert.equal(p.sessionId, 'restart');
  await p.select('older', true); clock += 5000;
  await p.tick(); assert.equal(p.sessionId, 'older');
});

test('slow polls never overlap; a response from an old session is discarded on pin', async () => {
  const gate = deferred(); let inFlight = 0, max = 0; const seen = [];
  const p = new MonitorPoller({ listSessions: async () => ({ sessions: [] }), getMonitor: async id => {
    max = Math.max(max, ++inFlight); if (id === 'a') await gate.promise; inFlight--; return { id };
  }, onFeed: f => seen.push(f.id) });
  const first = p.select('a', true);
  await p.tick(); await p.tick();
  await p.select('b', true);
  gate.resolve(); await first; await Promise.resolve(); await Promise.resolve();
  assert.equal(max, 1); assert.ok(!seen.includes('a')); assert.ok(seen.includes('b'));
});

test('hidden and backup states make no new requests; discovery remains at five seconds', async () => {
  let visible = false, clock = now, calls = 0;
  const p = new MonitorPoller({ enabled: () => visible, now: () => clock, listSessions: async () => { calls++; return { sessions: [] }; }, getMonitor: async () => { calls++; return {}; } });
  await p.tick(); assert.equal(calls, 0);
  visible = true; await p.tick(); assert.equal(calls, 1);
  clock += 4999; await p.tick(); assert.equal(calls, 1);
  clock++; await p.tick(); assert.equal(calls, 2);
  visible = false; clock += 10000; await p.tick(); assert.equal(calls, 2);
});
