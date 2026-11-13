// Page chrome shared by every web tool: the settings dialog (gear) and the
// footer status strip that always shows what this page is talking to.

import { getConfig, setConfig, CONFIG_EVENT, DEFAULTS } from "./config.js";
import { health, listRecipes, ApiError } from "./api.js";
import { icon } from "./icons.js";

const POLL_MS = 10000;

function settingsDialog() {
  const dlg = document.createElement("dialog");
  dlg.className = "settings-dialog";
  dlg.setAttribute("aria-labelledby", "settings-title");
  dlg.innerHTML = `
    <form method="dialog" novalidate>
      <header>
        <h2 id="settings-title">Settings</h2>
        <button class="btn btn-icon btn-ghost" value="cancel" formnovalidate aria-label="Close settings">${icon("close")}</button>
      </header>
      <div class="field">
        <label for="set-base">API base URL</label>
        <input class="input" id="set-base" name="apiBase" type="url" inputmode="url" autocomplete="off" spellcheck="false" placeholder="http://localhost:8000">
        <span class="hint">Leave empty for the default: this page's origin under /app/, otherwise http://localhost:8000.</span>
      </div>
      <div class="field">
        <label for="set-key">Demo key</label>
        <input class="input" id="set-key" name="demoKey" type="password" autocomplete="off" spellcheck="false">
        <span class="hint">Sent as X-Demo-Key. Stored in this browser only.</span>
      </div>
      <div class="settings-row">
        <div class="field">
          <label for="set-threshold">Watch threshold</label>
          <input class="input" id="set-threshold" name="watchThreshold" type="number" min="0" max="1" step="0.05" placeholder="${DEFAULTS.watchThreshold}">
        </div>
        <div class="field">
          <label for="set-interval">Watch interval (ms)</label>
          <input class="input" id="set-interval" name="watchIntervalMs" type="number" min="500" max="30000" step="100" placeholder="${DEFAULTS.watchIntervalMs}">
        </div>
      </div>
      <div class="settings-actions">
        <button class="btn btn-ghost" value="cancel" formnovalidate>Cancel</button>
        <button class="btn btn-primary" value="save">Save settings</button>
      </div>
    </form>`;
  document.body.append(dlg);

  const f = dlg.querySelector("form");
  dlg.addEventListener("close", () => {
    if (dlg.returnValue !== "save") return;
    setConfig({
      apiBase: f.apiBase.value,
      demoKey: f.demoKey.value,
      watchThreshold: f.watchThreshold.value,
      watchIntervalMs: f.watchIntervalMs.value,
    });
  });

  return {
    open() {
      const c = getConfig();
      let storedBase = "";
      try {
        storedBase = localStorage.getItem("gc.apiBase") || "";
      } catch {}
      f.apiBase.value = storedBase;
      f.apiBase.placeholder = c.apiBase;
      f.demoKey.value = c.demoKey;
      f.watchThreshold.value = c.watchThreshold === DEFAULTS.watchThreshold ? "" : c.watchThreshold;
      f.watchIntervalMs.value = c.watchIntervalMs === DEFAULTS.watchIntervalMs ? "" : c.watchIntervalMs;
      dlg.returnValue = "";
      dlg.showModal();
      (c.demoKey ? f.apiBase : f.demoKey).focus();
    },
    get isOpen() {
      return dlg.open;
    },
  };
}

function statusStrip(openSettings) {
  const strip = document.createElement("footer");
  strip.className = "status-strip";
  strip.setAttribute("aria-live", "polite");
  document.body.append(strip);

  let last = { state: "checking" };

  function draw(s) {
    last = s;
    const { apiBase } = getConfig();
    strip.dataset.state = s.state;
    const base = `<span class="status-item">API <b>${apiBase}</b></span>`;
    let html;
    switch (s.state) {
      case "checking":
        html = `<span class="status-flag">Connecting</span>${base}`;
        break;
      case "down":
        html = `<span class="status-flag">${icon("warn", { size: 18 })}API unreachable</span>${base}<span class="status-item">${s.detail}</span>`;
        break;
      case "unauthorized":
        html = `<span class="status-flag">${icon("warn", { size: 18 })}Key rejected</span>${base}<span class="status-item">ai_mode <b>${s.h.ai_mode}</b></span><span class="status-item">storage <b>${s.h.storage}</b></span>`;
        break;
      default: {
        const fake = s.h.ai_mode === "fake";
        html = `${fake ? `<span class="status-flag">${icon("warn", { size: 18 })}Fake AI</span>` : `<span class="status-flag">Live</span>`}${base}<span class="status-item">ai_mode <b>${s.h.ai_mode}</b></span><span class="status-item">storage <b>${s.h.storage}</b></span><span class="status-item">contract <b>${s.h.contract_version}</b></span>`;
      }
    }
    const needsKey = s.state === "unauthorized" || s.state === "down";
    strip.innerHTML = `${html}<button type="button" class="status-action">${needsKey ? "Open settings" : "Settings"}</button>`;
    strip.querySelector(".status-action").addEventListener("click", openSettings);
    document.dispatchEvent(new CustomEvent("echo:status", { detail: s }));
  }

  async function poll() {
    let h;
    try {
      h = await health();
    } catch (e) {
      draw({ state: "down", detail: e instanceof ApiError ? e.message : "No answer" });
      return;
    }
    try {
      await listRecipes("published");
      draw({ state: h.ai_mode === "fake" ? "fake" : "ok", h });
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) draw({ state: "unauthorized", h });
      else draw({ state: h.ai_mode === "fake" ? "fake" : "ok", h });
    }
  }

  draw(last);
  poll();
  let timer = setInterval(poll, POLL_MS);
  addEventListener(CONFIG_EVENT, () => {
    draw({ state: "checking" });
    clearInterval(timer);
    poll();
    timer = setInterval(poll, POLL_MS);
  });
  return {
    get state() {
      return last;
    },
    refresh: poll,
  };
}

/** Wire the gear button (any element with [data-open-settings]) and the footer strip. */
export function mountChrome() {
  const settings = settingsDialog();
  document.querySelectorAll("[data-open-settings]").forEach((b) => b.addEventListener("click", () => settings.open()));
  const status = statusStrip(() => settings.open());
  return { settings, status };
}
