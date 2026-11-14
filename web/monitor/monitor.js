import { mountChrome } from '../shared/chrome.js';
import { CONFIG_EVENT, getConfig } from '../shared/config.js';
import { getMonitor, listSessions, getRecipe } from '../shared/api.js';
import { renderLens } from '../shared/lens.js';
import { icon } from '../shared/icons.js';
import { MonitorPoller } from './polling.js';
import { connectionState, deriveLens, describeEvent, frameUrl, milliseconds, orderedEvents } from './state.js';

const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const state = { feed: null, lastSuccess: null, failed: false, replay: false, health: null, total: '?', error: '' };
let sessions = [], lensSignature = '', timelineSignature = '', recipeVersion = 0, wakeLock = null, videoUrl = null;
const recipes = new Map();
const clock = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Helsinki', hour: '2-digit', minute: '2-digit', second: '2-digit' });
const seconds = value => Number.isFinite(value) ? `${(value / 1000).toFixed(1)} s` : '—';
const timeText = value => Number.isFinite(milliseconds(value)) ? clock.format(new Date(value)) : '—';
const ageText = value => Number.isFinite(milliseconds(value)) ? `${Math.max(0, (Date.now() - milliseconds(value)) / 1000).toFixed(1)} s` : 'unknown';

function updatePicker() {
  const picker = $('session-picker'), previous = picker.value;
  const options = [new Option('Auto · newest active session', '')];
  for (const session of sessions) options.push(new Option(`${session.recipe_title || 'Untitled recipe'} · ${session.device_label || session.client} · ${timeText(session.started_at)}`, session.id));
  if (poller.pinned && poller.sessionId && !sessions.some(s => s.id === poller.sessionId)) options.push(new Option(`Pinned session · ${poller.sessionId.slice(0, 8)}`, poller.sessionId));
  picker.replaceChildren(...options);
  picker.value = poller.pinned ? poller.sessionId : '';
  if (document.activeElement === picker && previous !== picker.value) picker.focus();
}

function paintImage(id, emptyId, url, key) {
  const image = $(id), empty = $(emptyId);
  if (image.dataset.key === key) return;
  image.dataset.key = key;
  if (!url) { image.hidden = true; empty.hidden = false; image.removeAttribute('src'); return; }
  image.onerror = () => {
    if (image.dataset.key !== key) return;
    image.hidden = true; empty.hidden = false;
    empty.textContent = id === 'wearer-image' ? 'Latest frame is unavailable.' : 'Reference image is unavailable.';
  };
  image.onload = () => { if (image.dataset.key === key) { image.hidden = false; empty.hidden = true; } };
  image.src = url;
  image.hidden = false; empty.hidden = true;
}

function paintTimeline() {
  const events = orderedEvents(state.feed);
  const signature = JSON.stringify(events);
  if (signature === timelineSignature) return;
  timelineSignature = signature;
  const list = $('timeline'), oldScroll = list.scrollTop;
  if (!events.length) {
    const li = document.createElement('li'); li.className = 'timeline-empty'; li.textContent = 'No events yet. Waiting for the first step or check.';
    list.replaceChildren(li); return;
  }
  list.replaceChildren(...events.map(event => {
    const description = describeEvent(event), li = document.createElement('li');
    li.dataset.tone = description.tone;
    const time = document.createElement('time'); time.textContent = timeText(event.created_at);
    if (Number.isFinite(milliseconds(event.created_at))) time.dateTime = event.created_at;
    const mark = document.createElement('span'); mark.className = 'event-icon'; mark.textContent = description.icon; mark.setAttribute('aria-hidden', 'true');
    const text = document.createElement('span'); text.textContent = description.text;
    li.append(time, mark, text); return li;
  }));
  if (oldScroll > 0) list.scrollTop = oldScroll;
}

function paint() {
  const status = connectionState(state);
  $('connection').dataset.state = status;
  $('connection').textContent = status.toUpperCase();
  const feed = state.feed, step = feed?.current_step;
  $('recipe-title').textContent = feed?.recipe_title || (poller.sessionId ? 'Connecting to session' : 'Waiting for a session');
  $('step-title').textContent = step ? `Step ${step.idx} of ${state.total}: ${step.title}${feed.session.finished_at ? ' · Session ended' : ''}` : 'Start a cook-along in the simulator or iOS app.';
  let note = poller.pinned ? 'Pinned session · automatic switching paused' : 'Auto · following the newest active session';
  if (status === 'offline') note = `${state.error || 'Reconnecting'}${state.lastSuccess ? ` · last update ${((Date.now() - state.lastSuccess) / 1000).toFixed(0)} s ago` : ''}`;
  else if (status === 'waiting') note = state.error || 'Looking for an active session…';
  else if (status === 'idle') note += feed?.session.finished_at ? ' · ended' : ' · no recent activity';
  $('connection-note').textContent = note;
  $('frame-age').textContent = feed?.last_frame_at ? `Frame age ${ageText(feed.last_frame_at)}` : 'No frame yet';
  $('ref-step').textContent = step ? `Step ${step.idx}` : 'Current step';
  $('reference-line').textContent = step?.key_line || 'Follow the chef’s method.';
  const last = feed?.last_result;
  const watchRecent = last?.source === 'watch' && Date.now() - milliseconds(last.at) < 6000;
  $('watch-ticker').textContent = watchRecent ? `Watching… ${last.body?.status === 'ok' ? 'ok' : 'warning'} (${seconds(last.body?.latency_ms)})` : last ? `Last ${last.source} result ${ageText(last.at)} ago` : 'Waiting for watcher results.';
  const screen = feed ? deriveLens(feed, state.total) : { kind: 'notice', text: poller.sessionId ? 'Connecting to session' : 'Waiting for a cook-along' };
  const signature = JSON.stringify(screen);
  if (signature !== lensSignature) { renderLens($('monitor-lens'), screen); lensSignature = signature; }
  const latency = feed?.latency || {};
  $('check-latency').textContent = `${seconds(latency.check_p50_ms)} / ${seconds(latency.check_max_ms)}`;
  $('watch-latency').textContent = `${seconds(latency.watch_p50_ms)} / ${seconds(latency.watch_max_ms)}`;
  $('check-count').textContent = `${latency.n_check || 0} checks`;
  $('watch-count').textContent = `${latency.n_watch || 0} watches`;
  $('device-label').textContent = feed?.session.device_label || '—';
  $('client-label').textContent = feed?.session.client || '—';
  $('ai-storage').textContent = state.health ? `${state.health.ai_mode} / ${state.health.storage}` : 'Not verified';
  $('ai-storage').dataset.fake = String(state.health?.ai_mode === 'fake');
  $('fake-banner').hidden = state.health?.ai_mode !== 'fake';
}

function loadRecipe(id) {
  if (!id) return;
  if (recipes.has(id)) { const item = recipes.get(id); if (item?.steps) state.total = item.steps.length; return; }
  const version = recipeVersion;
  recipes.set(id, null);
  getRecipe(id).then(recipe => {
    if (version !== recipeVersion) return;
    recipes.set(id, recipe);
    if (state.feed?.current_step?.recipe_id === id) { state.total = recipe.steps?.length || '?'; paint(); }
  }).catch(() => { if (version === recipeVersion) recipes.delete(id); });
}

const poller = new MonitorPoller({
  listSessions, getMonitor, enabled: () => !document.hidden && !state.replay,
  onSessions(items) { sessions = items; updatePicker(); if (!poller.sessionId) { state.failed = false; state.error = ''; paint(); } },
  onAttach() {
    Object.assign(state, { feed: null, lastSuccess: null, failed: false, total: '?', error: '' });
    paintImage('reference-image', 'reference-empty', null, 'empty');
    paintImage('wearer-image', 'wearer-empty', null, 'empty');
    timelineSignature = ''; paintTimeline(); updatePicker(); paint();
  },
  onFeed(feed, receivedAt) {
    Object.assign(state, { feed, lastSuccess: receivedAt, failed: false, error: '' });
    loadRecipe(feed.current_step?.recipe_id);
    const step = feed.current_step;
    paintImage('reference-image', 'reference-empty', step?.ref_image_url, `${step?.id}|${step?.ref_image_url}`);
    paintImage('wearer-image', 'wearer-empty', frameUrl(feed.last_frame_url, feed.last_frame_at, getConfig().apiBase), `${feed.session.id}|${feed.last_frame_at}`);
    paintTimeline(); paint();
  },
  onError(error, kind) {
    if (kind === 'discovery' && state.feed) return;
    state.failed = true;
    state.error = error.status === 401 ? 'Key rejected. Open Settings.' : `${error.message || 'Connection lost'} · reconnecting`;
    paint();
  },
});

// Shared settings and status strip, with no background polling while hidden or replaying.
document.querySelector('[data-open-settings]').innerHTML = icon('gear', { size: 21 });
const chrome = mountChrome({ shouldPoll: () => !document.hidden && !state.replay });
document.addEventListener('echo:status', event => {
  if (event.detail.h) state.health = event.detail.h;
  paint();
});
addEventListener(CONFIG_EVENT, () => {
  recipeVersion++; recipes.clear(); state.health = null;
  poller.reset(); void poller.tick(); paint();
});
$('session-picker').addEventListener('change', event => {
  const id = event.target.value, next = new URL(location.href);
  if (id) next.searchParams.set('session', id); else next.searchParams.delete('session');
  history.replaceState(null, '', next);
  void poller.select(id || poller.sessionId, Boolean(id));
  updatePicker(); void poller.tick();
});

let detailsHidden = params.get('clean') === '1';
function toggleDetails() {
  $('details').hidden = detailsHidden;
  $('lower').dataset.hide = String(detailsHidden);
  $('details-toggle').setAttribute('aria-pressed', String(detailsHidden));
  $('details-toggle').innerHTML = `${detailsHidden ? 'Show' : 'Hide'} details <kbd>H</kbd>`;
}
toggleDetails();
$('details-toggle').addEventListener('click', () => { detailsHidden = !detailsHidden; toggleDetails(); });

async function fullscreen() {
  try { if (document.fullscreenElement) await document.exitFullscreen(); else await document.documentElement.requestFullscreen(); }
  catch { $('connection-note').textContent = 'Full screen is unavailable in this browser.'; }
}
$('fullscreen').addEventListener('click', fullscreen);
async function keepAwake() {
  if (!navigator.wakeLock || document.hidden || wakeLock) return;
  try { wakeLock = await navigator.wakeLock.request('screen'); wakeLock.addEventListener('release', () => { wakeLock = null; }); }
  catch { /* Optional: unsupported or battery policy may deny the lock. */ }
}

const backupDialog = $('backup-dialog'), video = $('backup-video');
function openBackup() { $('backup-error').textContent = ''; backupDialog.showModal(); }
$('backup-open').addEventListener('click', openBackup);
$('backup-file').addEventListener('change', () => {
  const file = $('backup-file').files[0];
  if (file) $('backup-label').value = file.name.replace(/\.[^.]+$/, '');
});
$('backup-form').addEventListener('submit', event => {
  if (event.submitter?.value !== 'play') return;
  event.preventDefault();
  const file = $('backup-file').files[0], label = $('backup-label').value.trim();
  if (!file || !label || (file.type && !file.type.startsWith('video/'))) { $('backup-error').textContent = 'Choose a video and give the recording a label.'; return; }
  if (videoUrl) URL.revokeObjectURL(videoUrl);
  videoUrl = URL.createObjectURL(file); video.src = videoUrl;
  $('replay-label').textContent = `REPLAY — recorded ${label}`;
  $('replay-message').textContent = '';
  state.replay = true; $('replay').hidden = false; backupDialog.close(); paint();
  video.play().catch(() => { $('replay-message').textContent = 'Press Play to start the recording.'; });
});
video.addEventListener('error', () => { $('replay-message').textContent = 'This video could not be played. Choose a supported recording.'; });
// Keep fullscreen on the document so the permanent REPLAY label cannot disappear
// into the browser's native video-only fullscreen player.
video.addEventListener('contextmenu', event => event.preventDefault());
const videoClock = n => Number.isFinite(n) ? `${Math.floor(n / 60)}:${String(Math.floor(n % 60)).padStart(2, '0')}` : '0:00';
function paintVideo() {
  $('backup-toggle').textContent = video.paused ? 'Play' : 'Pause';
  $('backup-time').textContent = `${videoClock(video.currentTime)} / ${videoClock(video.duration)}`;
  if (document.activeElement !== $('backup-seek')) $('backup-seek').value = video.duration ? video.currentTime / video.duration * 100 : 0;
}
for (const type of ['timeupdate', 'loadedmetadata', 'play', 'pause', 'ended']) video.addEventListener(type, paintVideo);
$('backup-toggle').addEventListener('click', () => {
  if (video.paused) video.play().catch(() => { $('replay-message').textContent = 'Press Play to retry playback.'; });
  else video.pause();
});
$('backup-seek').addEventListener('input', event => { if (Number.isFinite(video.duration)) video.currentTime = video.duration * Number(event.target.value) / 100; });
$('backup-fullscreen').addEventListener('click', fullscreen);

function closeBackup() {
  video.pause(); video.removeAttribute('src'); video.load();
  if (videoUrl) URL.revokeObjectURL(videoUrl); videoUrl = null;
  state.replay = false; $('replay').hidden = true;
  state.lastSuccess = null; state.failed = false;
  void poller.tick(); void chrome.status.refresh(); paint();
}
$('backup-close').addEventListener('click', closeBackup);
addEventListener('keydown', event => {
  if (event.altKey || event.ctrlKey || event.metaKey || event.target.closest('input, textarea, select, [contenteditable="true"]') || backupDialog.open || document.querySelector('.settings-dialog[open]')) return;
  const key = event.key.toLowerCase();
  if (key === 'escape' && state.replay) { event.preventDefault(); closeBackup(); }
  if (key === 'f') { event.preventDefault(); void fullscreen(); }
  if (key === 'b') { event.preventDefault(); openBackup(); }
  if (key === 's' && !state.replay) { event.preventDefault(); $('session-picker').focus(); }
  if (key === 'h' && !state.replay) { event.preventDefault(); detailsHidden = !detailsHidden; toggleDetails(); }
});
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) { void poller.tick(); void chrome.status.refresh(); void keepAwake(); paint(); }
});
addEventListener('pagehide', () => { if (videoUrl) URL.revokeObjectURL(videoUrl); wakeLock?.release(); });
if (params.get('session')) void poller.select(params.get('session'), true);
void poller.tick();
setInterval(() => { void poller.tick(); }, 1000);
setInterval(() => { if (!document.hidden) paint(); }, 500);
void keepAwake(); paint();
