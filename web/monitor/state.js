// Pure feed interpretation: safe to test without a browser or a backend.
export const milliseconds = (value) => {
  const n = Date.parse(value);
  return Number.isFinite(n) ? n : -Infinity;
};
const age = (value, now) => Math.max(0, now - milliseconds(value));
export const orderedEvents = (feed) => [...(feed?.events || [])]
  .sort((a, b) => milliseconds(b.created_at) - milliseconds(a.created_at));

export function connectionState({ feed, lastSuccess, failed = false, replay = false }, now = Date.now()) {
  if (replay) return 'replay';
  if (failed || (lastSuccess != null && now - lastSuccess >= 3000)) return 'offline';
  if (!feed) return 'waiting';
  if (feed.session?.finished_at) return 'idle';
  const activity = Math.max(
    milliseconds(feed.session?.started_at), milliseconds(feed.last_frame_at),
    milliseconds(feed.last_result?.at), ...orderedEvents(feed).map(e => milliseconds(e.created_at)),
  );
  return lastSuccess != null && now - lastSuccess < 3000 && now - activity < 30000 ? 'live' : 'idle';
}

export function deriveLens(feed, total = '?', now = Date.now()) {
  const step = feed?.current_step;
  if (!step) return { kind: 'notice', text: 'Waiting for the first step' };
  const watching = feed.last_result?.source === 'watch' && age(feed.last_result.at, now) < 6000 && !feed.session?.finished_at;
  const card = { idx: step.idx, total, title: step.title, keyLine: step.key_line,
    refImageUrl: step.ref_image_url, watching: watching ? 'active' : 'off' };
  const kinds = new Set(['check_fix', 'watch_warn', 'check_pass', 'check_unsure', 'step_change', 'warning_dismissed', 'session_end']);
  const latest = orderedEvents(feed).find(e => kinds.has(e.kind) &&
    (!e.step_id || e.step_id === step.id || ['step_change', 'warning_dismissed', 'session_end'].includes(e.kind)));
  const p = latest?.payload || {};
  if (latest?.kind === 'check_fix' || latest?.kind === 'watch_warn') {
    return { kind: 'fix', card, headline: p.headline || 'Check this step', fix: p.fix || 'Compare with the chef', proactive: latest.kind === 'watch_warn' };
  }
  if (latest?.kind === 'check_pass' && age(latest.created_at, now) < 3000) return { kind: 'pass', headline: p.headline || 'Looks right' };
  if (latest?.kind === 'check_unsure' && age(latest.created_at, now) < 4000) return { kind: 'unsure', headline: p.headline || "Can't tell", hint: p.fix || p.spoken || 'Show the board clearly' };
  return { kind: 'step', card };
}

export function frameUrl(url, timestamp, base) {
  if (!url) return null;
  const result = new URL(url, base);
  if (!['http:', 'https:'].includes(result.protocol)) return null;
  if (timestamp) result.searchParams.set('_frame_at', timestamp);
  return result.href;
}

export function describeEvent(event) {
  const p = event.payload || {};
  const confidence = Number.isFinite(p.confidence) ? ` · ${Math.round(p.confidence * 100)}% confidence` : '';
  const latency = Number.isFinite(p.latency_ms) ? ` · ${(p.latency_ms / 1000).toFixed(1)} s` : '';
  switch (event.kind) {
    case 'step_change': return { icon: '→', tone: 'step', text: `Step ${p.from_idx ?? '?'} → ${p.to_idx ?? '?'}${p.via ? ` · ${p.via}` : ''}` };
    case 'watch_warn': return { icon: '⚠', tone: 'fix', text: `Watcher: ${p.headline || 'Mistake spotted'}${confidence}${latency}` };
    case 'check_fix': return { icon: '⚠', tone: 'fix', text: `Check · fix: ${p.headline || 'Needs a change'}${confidence}${latency}` };
    case 'check_pass': return { icon: '✓', tone: 'pass', text: `Check · pass: ${p.headline || 'Looks right'}${confidence}${latency}` };
    case 'check_unsure': return { icon: '?', tone: 'unsure', text: `Check · unsure: ${p.headline || "Can't tell"}${confidence}${latency}` };
    case 'question': return { icon: '?', tone: 'question', text: `Question: ${p.caption || 'Asked the chef'}` };
    case 'warning_shown': return { icon: '!', tone: 'fix', text: `Warning shown${p.mistake_id ? ` · ${p.mistake_id}` : ''}` };
    case 'warning_dismissed': return { icon: '↩', tone: 'step', text: `Warning dismissed${p.mistake_id ? ` · ${p.mistake_id}` : ''}` };
    case 'show_me': return { icon: '◉', tone: 'step', text: 'Chef reference requested' };
    case 'client_error': return { icon: '!', tone: 'error', text: `Client error${p.where ? ` · ${p.where}` : ''}: ${p.detail || 'No detail'}` };
    case 'session_end': return { icon: '✓', tone: 'step', text: 'Session ended' };
    default: return { icon: '·', tone: 'step', text: String(event.kind || 'Event').replaceAll('_', ' ') };
  }
}
