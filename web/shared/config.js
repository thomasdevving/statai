// Runtime configuration, kept in this browser's localStorage only.
// The demo key is typed into Settings and never written into a file.

const KEYS = {
  apiBase: "gc.apiBase",
  demoKey: "gc.demoKey",
  watchThreshold: "gc.watchThreshold",
  watchIntervalMs: "gc.watchIntervalMs",
};

export const DEFAULTS = Object.freeze({
  watchThreshold: 0.7,
  watchIntervalMs: 2500,
});

export const CONFIG_EVENT = "echo:config";

function read(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key, value) {
  try {
    if (value === null || value === undefined || value === "") localStorage.removeItem(key);
    else localStorage.setItem(key, String(value));
  } catch {
    /* private mode or blocked storage: settings last for this page only */
  }
}

/** Same origin when served by the backend under /app/, otherwise a local backend. */
export function defaultApiBase(loc = globalThis.location) {
  if (loc && loc.pathname && loc.pathname.startsWith("/app/")) return loc.origin;
  return "http://localhost:8000";
}

function num(raw, fallback, { min, max }) {
  const n = Number(raw);
  if (raw === null || raw === "" || !Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}

export function getConfig() {
  const base = (read(KEYS.apiBase) || defaultApiBase()).trim().replace(/\/+$/, "");
  return {
    apiBase: base,
    demoKey: read(KEYS.demoKey) || "",
    watchThreshold: num(read(KEYS.watchThreshold), DEFAULTS.watchThreshold, { min: 0, max: 1 }),
    watchIntervalMs: num(read(KEYS.watchIntervalMs), DEFAULTS.watchIntervalMs, { min: 500, max: 30000 }),
  };
}

/** Pass only the fields to change. An empty string resets a field to its default. */
export function setConfig(patch) {
  for (const [field, key] of Object.entries(KEYS)) {
    if (field in patch) write(key, typeof patch[field] === "string" ? patch[field].trim() : patch[field]);
  }
  const cfg = getConfig();
  globalThis.dispatchEvent?.(new CustomEvent(CONFIG_EVENT, { detail: cfg }));
  return cfg;
}
