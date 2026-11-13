// Echo simulator: the cook-along loop in a browser (web/tasks/01 WEB-01.4, WEB-01.5).
// Client rules follow docs/API-CONTRACT.md §3.3 (watcher) and §3.4 (stale results) exactly.

import { mountChrome } from "../shared/chrome.js";
import { getConfig, CONFIG_EVENT } from "../shared/config.js";
import * as API from "../shared/api.js";
import { ApiError, newRequestId } from "../shared/api.js";
import { renderLens, describeLens } from "../shared/lens.js";
import { createDebouncer } from "../shared/debounce.js";
import { icon } from "../shared/icons.js";

// ---------- timings (contract + task file) ----------
const PASS_ADVANCE_MS = 2000;
const UNSURE_MS = 4000;
const NOTICE_MS = 3000;
const RETRY_DELAY_MS = 1000;
const WARNING_TIMEOUT_MS = 12000;
const ERROR_PAUSE_MS = 15000;
const BACKOFF_429_MS = 10000;
const TICK_MS = 200;

const $ = (sel) => document.querySelector(sel);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

document.querySelectorAll("[data-icon]").forEach((el) => (el.outerHTML = icon(el.dataset.icon, { size: 20 })));
$("[data-open-settings]").innerHTML = icon("gear", { size: 22 });
const chrome = mountChrome();

// ====================================================================
// Gallery: ?gallery=1 renders every lens kind for visual review
// ====================================================================
if (new URLSearchParams(location.search).has("gallery")) {
  renderGallery();
} else {
  startSimulator();
}

async function renderGallery() {
  let refUrl = null;
  try {
    const list = await API.listRecipes("published");
    if (list.recipes.length) {
      const r = await API.getRecipe(list.recipes[0].id);
      const st = r.steps.find((s) => s.idx === 3 && s.ref_image_url) || r.steps.find((s) => s.ref_image_url);
      refUrl = st ? st.ref_image_url : null;
    }
  } catch {
    /* gallery works without a backend; the cards show "No reference image" */
  }
  const card = { idx: 3, total: 6, title: "Spread rice", keyLine: "Thin layer, leave 2cm top", refImageUrl: refUrl, watching: "active" };
  const screens = [
    ["step · watching active", { kind: "step", card }],
    ["step · paused", { kind: "step", card: { ...card, watching: "paused" } }],
    ["step · offline", { kind: "step", card: { ...card, watching: "offline" } }],
    ["step · no watch_fors, no image", { kind: "step", card: { ...card, idx: 2, title: "Wet hands", keyLine: "Dip fingers, shake off the excess", watching: "off", refImageUrl: null } }],
    ["checking", { kind: "checking", card }],
    ["pass", { kind: "pass", headline: "Looks right" }],
    ["fix", { kind: "fix", card, headline: "Too much rice", fix: "Spread thinner, 2cm nori free", proactive: false }],
    ["fix · proactive warning", { kind: "fix", card, headline: "Too much rice", fix: "Spread thinner, 2cm nori free", proactive: true }],
    ["unsure", { kind: "unsure", headline: "Can't tell", hint: "Look straight down at mat" }],
    ["notice", { kind: "notice", text: "Can't check right now" }],
    ["done", { kind: "done", summary: "4 of 6 first try · 2 fixes caught" }],
    ["recipePick", { kind: "recipePick", titles: ["Maki roll", "Nigiri", "Temaki hand roll"], selected: 0 }],
  ];
  const main = $("#sim");
  main.className = "gallery";
  main.innerHTML = screens
    .map(([label], i) => `<figure><div id="g${i}"></div><figcaption>${label}</figcaption></figure>`)
    .join("");
  screens.forEach(([, s], i) => renderLens(document.getElementById(`g${i}`), s));
}

// ====================================================================
// Simulator
// ====================================================================
function startSimulator() {
  // ---------- state ----------
  const S = {
    recipes: [],
    pickIndex: 0,
    recipe: null,
    steps: [],
    refUrls: new Map(), // step id -> preloaded image URL
    sessionId: null,
    idx: 0, // 0-based index into steps
    mode: "pick", // pick | step | checking | pass | fix | warning | unsure | notice | done
    result: null, // body for result screens
    checkInFlight: false,
    latestCheckReq: null,
    latestWatchReq: null,
    modeTimer: null,
    warningMistake: null,
    // watcher
    watchEnabled: true,
    watchInFlight: false,
    watchLastEnd: 0,
    watchPausedUntil: 0,
    watchOffline: false,
    watchSeq: 0,
    watchLog: [],
    loopToken: 0,
    // speech
    speak: readBool("gc.speak", true),
  };
  let debouncer = createDebouncer({ threshold: getConfig().watchThreshold });
  addEventListener(CONFIG_EVENT, (e) => (debouncer.threshold = e.detail.watchThreshold));

  const lensEl = $("#lens");
  const liveEl = $("#lens-live");

  // ---------- frame source ----------
  const vf = $("#viewfinder");
  const video = $("#video");
  // Created here, not in the HTML, so the page never ships an <img> without a src.
  const photo = document.createElement("img");
  photo.id = "photo";
  photo.alt = "";
  vf.insertBefore(photo, $("#vf-empty"));
  const fileInput = $("#file");
  const camNote = $("#camera-note");
  let source = "photo";
  let stream = null;
  let photoUrl = null;

  function frameAvailable() {
    if (source === "webcam") return Boolean(stream && video.readyState >= 2 && video.videoWidth);
    return Boolean(photoUrl && photo.complete && photo.naturalWidth);
  }

  function setEmpty() {
    vf.dataset.source = source;
    vf.dataset.empty = String(!frameAvailable());
    $("#replace-photo").hidden = !(source === "photo" && photoUrl);
    $("#vf-empty-text").textContent =
      source === "webcam"
        ? "Waiting for the camera…"
        : "Drop a photo here or choose one. It stands in for what the glasses see until you replace it.";
    $("#choose-photo").hidden = source !== "photo";
  }

  async function useWebcam() {
    source = "webcam";
    setEmpty();
    camNote.textContent = "";
    if (!navigator.mediaDevices?.getUserMedia) {
      camNote.textContent = "This page can't use the camera here. Browsers allow it only on https:// or localhost. Use a photo instead.";
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 960 } },
        audio: false,
      });
      video.srcObject = stream;
      await video.play().catch(() => {});
      camNote.textContent = stream.getVideoTracks()[0]?.label || "Webcam on";
    } catch (e) {
      camNote.textContent =
        e && e.name === "NotAllowedError"
          ? "Camera permission was refused. Allow it in the browser's site settings, or use a photo."
          : "No camera could be opened. Use a photo instead.";
    }
    setEmpty();
  }

  function stopWebcam() {
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
    video.srcObject = null;
  }

  function usePhoto() {
    source = "photo";
    stopWebcam();
    camNote.textContent = photoUrl ? "This photo is what the camera sees." : "";
    setEmpty();
  }

  function loadPhoto(file) {
    if (!file || !file.type.startsWith("image/")) {
      camNote.textContent = "That file isn't an image. Choose a JPEG or PNG.";
      return;
    }
    if (photoUrl) URL.revokeObjectURL(photoUrl);
    photoUrl = URL.createObjectURL(file);
    photo.onload = () => {
      setEmpty();
      camNote.textContent = `${file.name} is what the camera sees.`;
    };
    photo.alt = `Uploaded photo standing in for the camera: ${file.name}`;
    photo.src = photoUrl;
  }

  document.querySelectorAll("[data-source]").forEach((b) =>
    b.addEventListener("click", () => {
      document.querySelectorAll("[data-source]").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
      if (b.dataset.source === "webcam") useWebcam();
      else usePhoto();
    }),
  );
  video.addEventListener("loadeddata", setEmpty);
  $("#choose-photo").addEventListener("click", () => fileInput.click());
  $("#replace-photo").addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => loadPhoto(fileInput.files[0]));
  vf.addEventListener("dragover", (e) => {
    e.preventDefault();
    vf.dataset.drag = "true";
  });
  vf.addEventListener("dragleave", () => (vf.dataset.drag = "false"));
  vf.addEventListener("drop", (e) => {
    e.preventDefault();
    vf.dataset.drag = "false";
    const f = e.dataTransfer.files[0];
    if (f) {
      document.querySelector('[data-source="photo"]').click();
      loadPhoto(f);
    }
  });
  setEmpty();

  /** Current frame as JPEG, long edge capped (never upscaled). */
  function grabFrame(maxLongEdge, quality) {
    if (!frameAvailable()) return Promise.resolve(null);
    const srcEl = source === "webcam" ? video : photo;
    const w0 = source === "webcam" ? video.videoWidth : photo.naturalWidth;
    const h0 = source === "webcam" ? video.videoHeight : photo.naturalHeight;
    const scale = Math.min(1, maxLongEdge / Math.max(w0, h0));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(w0 * scale));
    canvas.height = Math.max(1, Math.round(h0 * scale));
    canvas.getContext("2d").drawImage(srcEl, 0, 0, canvas.width, canvas.height);
    return new Promise((resolve) => canvas.toBlob((b) => resolve(b), "image/jpeg", quality));
  }

  // ---------- speech ----------
  function say(text) {
    if (!("speechSynthesis" in window)) return;
    speechSynthesis.cancel(); // a new result cancels an older utterance
    if (!S.speak || !text) return;
    speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  }

  // ---------- rendering ----------
  const step = () => S.steps[S.idx];

  function watchState() {
    const st = step();
    if (!st || !st.watch_fors || !st.watch_fors.length || !S.watchEnabled) return "off";
    if (S.watchOffline || Date.now() < S.watchPausedUntil) return "offline";
    return canWatch() || S.watchInFlight ? "active" : "paused";
  }

  function card() {
    const st = step();
    return {
      idx: st.idx,
      total: S.steps.length,
      title: st.title,
      keyLine: st.key_line,
      refImageUrl: S.refUrls.get(st.id) || null,
      watching: watchState(),
    };
  }

  function screen() {
    const r = S.result || {};
    switch (S.mode) {
      case "pick":
        return { kind: "recipePick", titles: S.recipes.map((x) => x.title), selected: S.pickIndex };
      case "step":
        return { kind: "step", card: card() };
      case "checking":
        return { kind: "checking", card: card() };
      case "pass":
        return { kind: "pass", headline: r.headline };
      case "fix":
        return { kind: "fix", card: card(), headline: r.headline, fix: r.fix, proactive: false };
      case "warning":
        return { kind: "fix", card: card(), headline: r.headline, fix: r.fix, proactive: true };
      case "unsure":
        return { kind: "unsure", headline: r.headline, hint: r.fix };
      case "notice":
        return { kind: "notice", text: r.text };
      case "done":
        return { kind: "done", summary: r.summary };
      default:
        return { kind: "notice", text: "" };
    }
  }

  let lastAnnounced = "";
  function draw() {
    const s = screen();
    renderLens(lensEl, s);
    const said = describeLens(s);
    if (said !== lastAnnounced) {
      liveEl.textContent = said;
      lastAnnounced = said;
    }
    const cooking = S.mode !== "pick";
    $("#picker").hidden = cooking;
    $("#cook").hidden = !cooking;
    if (!cooking) return;

    $("#cook-title").textContent = S.recipe ? S.recipe.title : "";
    const label = {
      step: "Check my work",
      checking: "Checking…",
      pass: S.idx === S.steps.length - 1 ? "Finish" : "Next step",
      fix: "Check again",
      warning: "Check my work",
      unsure: "Check again",
      notice: "Check my work",
      done: "Pick another recipe",
    }[S.mode];
    $("#primary-label").textContent = label;
    $("#primary").disabled = S.mode === "checking";
    $("#prev").disabled = S.mode === "done" || S.idx === 0;
    $("#next").disabled = S.mode === "done";
    $("#dismiss").disabled = !["fix", "warning", "unsure", "notice", "checking"].includes(S.mode);
    $("#watch-line").textContent = watchLine();
  }

  function watchLine() {
    const st = step();
    if (!st || S.mode === "done") return "";
    if (!S.watchEnabled) return "Watcher off.";
    if (!st.watch_fors || !st.watch_fors.length) return "Nothing to watch for on this step.";
    if (Date.now() < S.watchPausedUntil) return "Watcher paused for 15 s after three errors.";
    if (S.watchOffline) return "Watcher offline: the last call failed.";
    if (!frameAvailable()) return "Watcher paused: no camera frame. Choose a photo or turn on the webcam.";
    if (document.hidden) return "Watcher paused while this tab is hidden.";
    if (S.mode !== "step") return "Watcher paused while a result is showing.";
    return `Watching every ${(getConfig().watchIntervalMs / 1000).toFixed(1)} s.`;
  }

  // ---------- debug panel ----------
  function debugResponse(body, kind) {
    $("#dbg-json").textContent = JSON.stringify({ endpoint: kind, ...body }, null, 2);
    if (body.request_id) $("#dbg-req").textContent = body.request_id;
    if (body.latency_ms != null) $("#dbg-latency").textContent = `${body.latency_ms} ms (${kind})`;
    if (body.model) $("#dbg-model").textContent = body.model;
  }

  function debugWatch(entry) {
    S.watchLog.unshift(entry);
    S.watchLog.length = Math.min(S.watchLog.length, 10);
    $("#dbg-watch").innerHTML = S.watchLog
      .map(
        (w) =>
          `<tr data-warn="${w.status === "warn"}"><td>${w.n}</td><td>${w.sent}</td><td>${w.took} ms</td><td>${w.status}</td><td>${w.mistake || "—"}</td><td>${w.conf ?? "—"}</td><td>${w.server ?? "—"}</td></tr>`,
      )
      .join("");
  }

  const clock = (t) => new Date(t).toLocaleTimeString([], { hour12: false }) + "." + String(t % 1000).padStart(3, "0");

  // ---------- events (best effort, never block the loop) ----------
  function post(kind, opts) {
    if (!S.sessionId) return;
    API.postEvent(S.sessionId, kind, opts).catch((e) => console.warn("event failed", kind, e));
  }

  // ---------- mode changes ----------
  function clearModeTimer() {
    clearTimeout(S.modeTimer);
    S.modeTimer = null;
  }

  function setMode(mode, result = null, { afterMs, then } = {}) {
    clearModeTimer();
    S.mode = mode;
    S.result = result;
    if (afterMs) S.modeTimer = setTimeout(then, afterMs);
    draw();
  }

  function backToStep() {
    S.checkInFlight = false;
    setMode("step");
  }

  function goTo(newIdx, via) {
    if (newIdx < 0 || newIdx >= S.steps.length) return;
    const from = step();
    S.idx = newIdx;
    S.latestCheckReq = null; // in-flight answers are about the old step now
    S.latestWatchReq = null;
    S.checkInFlight = false;
    S.warningMistake = null;
    S.watchOffline = false;
    debouncer.reset();
    say("");
    post("step_change", { stepId: step().id, payload: { from_idx: from ? from.idx : null, to_idx: step().idx, via } });
    setMode("step");
  }

  function next(via = "tap") {
    if (S.idx === S.steps.length - 1) finish();
    else goTo(S.idx + 1, via);
  }

  function prev() {
    goTo(S.idx - 1, "tap");
  }

  // ---------- recipe pick and session ----------
  const pickerList = $("#picker-list");
  const pickerMsg = $("#picker-msg");

  async function loadRecipes() {
    pickerMsg.textContent = "Loading recipes…";
    pickerList.innerHTML = "";
    try {
      const { recipes } = await API.listRecipes("published");
      S.recipes = recipes;
      S.pickIndex = 0;
      pickerMsg.textContent = recipes.length ? "" : "No published recipes yet. Publish one on the review page.";
      pickerList.innerHTML = recipes
        .map(
          (r, i) =>
            `<li><button class="btn" type="button" data-pick="${i}"><span>${escapeHtml(r.title)}</span><small>${r.step_count} steps</small></button></li>`,
        )
        .join("");
      pickerList.querySelectorAll("[data-pick]").forEach((b) => b.addEventListener("click", () => startRecipe(Number(b.dataset.pick))));
    } catch (e) {
      S.recipes = [];
      pickerMsg.textContent =
        e instanceof ApiError && e.status === 401
          ? "The API rejected the demo key. Open Settings and enter the key from the backend owner."
          : `Can't load recipes: ${e.message}. Check the API base URL in Settings.`;
    }
    if (S.mode === "pick") draw();
  }

  async function startRecipe(i) {
    const summary = S.recipes[i];
    if (!summary) return;
    pickerMsg.textContent = `Opening ${summary.title}…`;
    try {
      const recipe = await API.getRecipe(summary.id);
      const { session_id } = await API.createSession(recipe.id, source === "webcam" ? "laptop webcam" : "photo upload");
      // Preload every reference image before cooking starts (contract §2).
      S.refUrls = new Map();
      await Promise.all(
        recipe.steps.map(
          (st) =>
            new Promise((resolve) => {
              if (!st.ref_image_url) return resolve();
              const img = new Image();
              img.onload = () => {
                S.refUrls.set(st.id, st.ref_image_url);
                resolve();
              };
              img.onerror = () => resolve();
              img.src = st.ref_image_url;
            }),
        ),
      );
      S.recipe = recipe;
      S.steps = recipe.steps;
      S.sessionId = session_id;
      S.idx = 0;
      S.watchLog = [];
      $("#dbg-session").textContent = session_id;
      $("#dbg-watch").innerHTML = `<tr><td colspan="7">No watch calls yet</td></tr>`;
      debouncer = createDebouncer({ threshold: getConfig().watchThreshold });
      pickerMsg.textContent = "";
      setMode("step");
      startWatchLoop();
      $("#primary").focus();
    } catch (e) {
      pickerMsg.textContent = `Can't start: ${e.message}.`;
    }
  }

  async function finish() {
    const sid = S.sessionId;
    stopWatchLoop();
    S.latestCheckReq = null;
    setMode("done", { summary: "Saving the session…" });
    say("Done.");
    try {
      await API.postEvent(sid, "session_end", {});
      const sess = await API.getSession(sid);
      const m = sess.summary || {};
      const parts = [`${m.steps_passed_first_try ?? 0} of ${m.steps_total ?? S.steps.length} first try`];
      parts.push(`${m.fixes_caught ?? 0} ${m.fixes_caught === 1 ? "fix" : "fixes"} caught`);
      if (S.mode === "done") setMode("done", { summary: parts.join(" · ") });
    } catch {
      if (S.mode === "done") setMode("done", { summary: "Session not saved: no connection" });
    }
  }

  function restart() {
    stopWatchLoop();
    if (S.sessionId && S.mode !== "done") post("session_end", {});
    S.sessionId = null;
    S.recipe = null;
    S.steps = [];
    S.latestCheckReq = null;
    S.latestWatchReq = null;
    S.checkInFlight = false;
    say("");
    $("#dbg-session").textContent = "—";
    setMode("pick");
    loadRecipes();
  }

  // ---------- on-demand check ----------
  async function runCheck(isRetry = false) {
    const st = step();
    const blob = await grabFrame(1280, 0.8);
    if (!blob) {
      setMode("notice", { text: "No camera frame. Choose a photo or turn on the webcam." }, { afterMs: NOTICE_MS, then: backToStep });
      return;
    }
    const requestId = newRequestId();
    S.latestCheckReq = requestId;
    S.checkInFlight = true;
    setMode("checking");
    $("#dbg-req").textContent = requestId;

    let body;
    try {
      body = await API.check({ frame: blob, stepId: st.id, requestId, sessionId: S.sessionId, capturedAt: new Date().toISOString() });
    } catch (e) {
      if (S.latestCheckReq !== requestId || step().id !== st.id) return; // stale: no UI effect
      S.checkInFlight = false;
      const serverSide = e instanceof ApiError && [500, 503, 504].includes(e.status);
      if (serverSide && !isRetry) {
        await sleep(RETRY_DELAY_MS);
        if (S.latestCheckReq !== requestId || step().id !== st.id || S.mode !== "checking") return;
        return runCheck(true);
      }
      $("#dbg-json").textContent = JSON.stringify({ endpoint: "check", error: { status: e.status, code: e.code, message: e.message } }, null, 2);
      const text =
        e.code === "network" || e.code === "timeout"
          ? "No connection"
          : e.status === 401
            ? "Key rejected: open Settings"
            : "Can't check right now";
      setMode("notice", { text }, { afterMs: NOTICE_MS, then: backToStep });
      return;
    }

    // Stale-result rule (§3.4): only the latest request, only for the step on screen.
    if (body.request_id !== S.latestCheckReq || body.step_id !== step().id) {
      console.info("discarded stale /check", body.request_id);
      return;
    }
    S.checkInFlight = false;
    debugResponse(body, "check");
    say(body.spoken);
    if (body.verdict === "pass") {
      setMode("pass", body, { afterMs: PASS_ADVANCE_MS, then: () => next("auto") });
    } else if (body.verdict === "fix") {
      setMode("fix", body);
    } else {
      setMode("unsure", body, { afterMs: UNSURE_MS, then: backToStep });
    }
  }

  // ---------- proactive watcher ----------
  function canWatch() {
    const st = step();
    return (
      S.watchEnabled &&
      S.sessionId &&
      S.mode === "step" &&
      !S.checkInFlight &&
      !document.hidden &&
      st &&
      st.watch_fors &&
      st.watch_fors.length > 0 &&
      frameAvailable() &&
      Date.now() >= S.watchPausedUntil
    );
  }

  function startWatchLoop() {
    const token = ++S.loopToken;
    S.watchLastEnd = Date.now();
    S.watchPausedUntil = 0;
    S.watchOffline = false;
    (async () => {
      let lastState = "";
      while (token === S.loopToken) {
        const state = `${watchState()}|${watchLine()}`;
        if (state !== lastState && S.mode === "step") draw();
        lastState = state;
        const due = Date.now() - S.watchLastEnd >= getConfig().watchIntervalMs;
        if (due && canWatch()) await watchOnce();
        else await sleep(TICK_MS);
      }
    })();
  }

  function stopWatchLoop() {
    S.loopToken++;
    S.latestWatchReq = null;
  }

  async function watchOnce() {
    const st = step();
    const blob = await grabFrame(512, 0.6);
    if (!blob) return;
    const requestId = newRequestId();
    S.latestWatchReq = requestId;
    S.watchInFlight = true;
    const sent = Date.now();
    const n = ++S.watchSeq;
    let body = null;
    let err = null;
    try {
      body = await API.watch({ frame: blob, stepId: st.id, requestId, sessionId: S.sessionId, capturedAt: new Date(sent).toISOString() });
    } catch (e) {
      err = e;
    }
    S.watchInFlight = false;
    S.watchLastEnd = Date.now(); // the interval runs from the end of the call
    const took = S.watchLastEnd - sent;

    if (err) {
      debugWatch({ n, sent: clock(sent), took, status: err.status === 429 ? "429 skip" : `error ${err.status || err.code}`, mistake: null, conf: null, server: null });
      if (err.status === 429) {
        // One in flight per session or quota: skip this tick and back off.
        S.watchLastEnd = Date.now() + BACKOFF_429_MS - getConfig().watchIntervalMs;
        return;
      }
      S.watchOffline = true; // silent: only the dot turns grey
      if (debouncer.recordError()) S.watchPausedUntil = Date.now() + ERROR_PAUSE_MS;
      if (S.mode === "step") draw();
      return;
    }

    debugWatch({ n, sent: clock(sent), took, status: body.status, mistake: body.mistake_id, conf: body.confidence?.toFixed(2), server: body.latency_ms });
    S.watchOffline = false;

    // Stale-result rule, and the watcher is paused unless the step card is showing.
    if (body.request_id !== S.latestWatchReq || body.step_id !== step().id || S.mode !== "step" || S.checkInFlight) {
      console.info("discarded stale /watch", body.request_id);
      return;
    }
    debugResponse(body, "watch");
    const alert = debouncer.ingest(body, Date.now());
    if (alert) showWarning(alert);
    else draw();
  }

  function showWarning(body) {
    S.warningMistake = body.mistake_id;
    say(body.spoken);
    post("warning_shown", { stepId: step().id, requestId: body.request_id, payload: { mistake_id: body.mistake_id } });
    // No input for 12 s: dismiss itself, counts as dismissed.
    setMode("warning", body, { afterMs: WARNING_TIMEOUT_MS, then: () => dismissWarning() });
  }

  function dismissWarning() {
    const id = S.warningMistake;
    S.warningMistake = null;
    debouncer.dismissed(id, Date.now());
    post("warning_dismissed", { stepId: step().id, payload: { mistake_id: id } });
    S.watchLastEnd = Date.now();
    setMode("step");
  }

  // ---------- inputs ----------
  function primary() {
    switch (S.mode) {
      case "pick":
        return startRecipe(S.pickIndex);
      case "step":
      case "fix":
      case "unsure":
      case "notice":
        return runCheck();
      case "warning":
        S.warningMistake = null;
        return runCheck();
      case "pass":
        clearModeTimer();
        return next("tap");
      case "done":
        return restart();
      default:
        return undefined;
    }
  }

  function dismiss() {
    switch (S.mode) {
      case "warning":
        return dismissWarning();
      case "checking":
        S.latestCheckReq = null; // its answer will be discarded
        return backToStep();
      case "fix":
      case "unsure":
      case "notice":
        say("");
        return backToStep();
      default:
        return undefined;
    }
  }

  $("#primary").addEventListener("click", primary);
  $("#next").addEventListener("click", () => {
    clearModeTimer();
    next("tap");
  });
  $("#prev").addEventListener("click", prev);
  $("#dismiss").addEventListener("click", dismiss);
  $("#restart").addEventListener("click", restart);

  const speakBtn = $("#speak-toggle");
  const watchBtn = $("#watch-toggle");
  function drawToggles() {
    speakBtn.setAttribute("aria-pressed", String(S.speak));
    speakBtn.innerHTML = `${icon(S.speak ? "sound" : "mute", { size: 20 })}${S.speak ? "Speak results" : "Speech muted"}`;
    watchBtn.setAttribute("aria-pressed", String(S.watchEnabled));
    watchBtn.innerHTML = `${icon(S.watchEnabled ? "eye" : "eyeOff", { size: 20 })}${S.watchEnabled ? "Watcher on" : "Watcher off"}`;
  }
  speakBtn.addEventListener("click", () => {
    S.speak = !S.speak;
    writeBool("gc.speak", S.speak);
    if (!S.speak) say("");
    drawToggles();
  });
  watchBtn.addEventListener("click", () => {
    S.watchEnabled = !S.watchEnabled;
    debouncer.reset();
    drawToggles();
    draw();
  });
  drawToggles();

  document.addEventListener("keydown", (e) => {
    if (chrome.settings.isOpen || e.metaKey || e.ctrlKey || e.altKey) return;
    const t = e.target;
    if (t instanceof Element && (t.matches("input, textarea, select") || t.isContentEditable)) return;
    if (S.mode === "pick" && S.recipes.length) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        S.pickIndex = (S.pickIndex + (e.key === "ArrowDown" ? 1 : -1) + S.recipes.length) % S.recipes.length;
        draw();
        return;
      }
    }
    switch (e.key) {
      case " ":
        e.preventDefault();
        if (S.mode !== "checking") primary();
        break;
      case "ArrowRight":
        if (S.mode === "pick" || S.mode === "done") return;
        e.preventDefault();
        clearModeTimer();
        next("tap");
        break;
      case "ArrowLeft":
        if (S.mode === "pick" || S.mode === "done") return;
        e.preventDefault();
        prev();
        break;
      case "Escape":
        dismiss();
        break;
      case "r":
      case "R":
        restart();
        break;
      default:
    }
  });

  document.addEventListener("visibilitychange", () => S.mode === "step" && draw());
  addEventListener(CONFIG_EVENT, () => S.mode === "pick" && loadRecipes());
  document.addEventListener("echo:status", (e) => {
    // Retry the recipe list once the key or the API comes good.
    if (S.mode === "pick" && !S.recipes.length && ["ok", "fake"].includes(e.detail.state)) loadRecipes();
  });

  draw();
  loadRecipes();
}

// ---------- helpers ----------
function readBool(key, fallback) {
  try {
    const v = localStorage.getItem(key);
    return v === null ? fallback : v === "1";
  } catch {
    return fallback;
  }
}

function writeBool(key, v) {
  try {
    localStorage.setItem(key, v ? "1" : "0");
  } catch {}
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
