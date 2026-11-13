// renderLens(el, screen): the lens card, shared by the simulator and the monitor.
// `screen` mirrors the iOS LensScreen: { kind, ... } — see web/tasks/01 WEB-01.2.

import { icon } from "./icons.js";

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const WATCH_LABEL = { active: "watching", paused: "paused", offline: "offline" };

function refImage(card, extra = "") {
  if (!card || !card.refImageUrl) {
    return `<div class="lens-ref"><div class="lens-ref-missing">No reference image</div>${extra}</div>`;
  }
  const alt = `Chef's reference for step ${card.idx}: ${card.title}`;
  return `<div class="lens-ref"><img src="${esc(card.refImageUrl)}" alt="${esc(alt)}" decoding="async">${extra}</div>`;
}

function titleRow(card) {
  return `<div class="lens-title"><span class="lens-counter">${card.idx}/${card.total}</span><span>${esc(card.title)}</span></div>`;
}

function watchRow(state) {
  if (!state || state === "off") return "";
  return `<div class="lens-watch" data-state="${state}"><span class="lens-dot"></span>${WATCH_LABEL[state] || state}</div>`;
}

function center(iconName, big, line = "") {
  return `<div class="lens-center">${icon(iconName)}<div class="lens-big">${esc(big)}</div>${
    line ? `<div class="lens-line">${esc(line)}</div>` : ""
  }</div>`;
}

const RENDER = {
  step: ({ card }) =>
    `${titleRow(card)}<div class="lens-rule"></div>${refImage(card)}<div class="lens-line">${esc(card.keyLine)}</div>${watchRow(card.watching)}`,

  checking: ({ card }) =>
    `${titleRow(card)}<div class="lens-rule"></div>${refImage(
      card,
      `<div class="lens-checking" role="status"><span class="lens-spinner"></span>Checking…</div>`,
    )}<div class="lens-line">${esc(card.keyLine)}</div>`,

  pass: ({ headline }) => center("check", headline || "Looks right"),

  fix: ({ card, headline, fix, proactive }) =>
    `<div class="lens-title">${icon("warn")}<span>${esc(headline)}</span>${
      proactive ? `<span class="lens-flag">Spotted</span>` : ""
    }</div><div class="lens-rule"></div>${refImage(card)}<div class="lens-line">${esc(fix)}</div>`,

  unsure: ({ headline, hint }) => center("question", headline || "Can't tell", hint),

  notice: ({ text }) => `<div class="lens-center">${icon("info")}<div class="lens-line">${esc(text)}</div></div>`,

  done: ({ summary }) => center("check", "Done", summary),

  recipePick: ({ titles = [], selected = 0 }) =>
    `<div class="lens-title">Pick a recipe</div><div class="lens-rule"></div><ul class="lens-list" role="listbox" aria-label="Recipes">${titles
      .map((t, i) => `<li role="option" aria-selected="${i === selected}">${esc(t)}</li>`)
      .join("")}</ul>`,
};

const TONE = { fix: "fix", pass: "pass", unsure: "unsure", notice: "notice", done: "pass" };

/** A short text version of the screen for screen readers. */
export function describeLens(screen) {
  switch (screen.kind) {
    case "step":
      return `Step ${screen.card.idx} of ${screen.card.total}: ${screen.card.title}. ${screen.card.keyLine}.`;
    case "checking":
      return "Checking.";
    case "pass":
      return `Pass: ${screen.headline || "Looks right"}.`;
    case "fix":
      return `${screen.proactive ? "Warning" : "Fix"}: ${screen.headline}. ${screen.fix}.`;
    case "unsure":
      return `Not sure: ${screen.headline}. ${screen.hint || ""}`;
    case "notice":
      return screen.text;
    case "done":
      return `Done. ${screen.summary || ""}`;
    case "recipePick":
      return "Pick a recipe.";
    default:
      return "";
  }
}

export function renderLens(el, screen) {
  const render = RENDER[screen && screen.kind];
  if (!render) throw new Error(`renderLens: unknown kind ${screen && screen.kind}`);
  el.classList.add("lens");
  el.dataset.kind = screen.kind;
  el.dataset.tone = TONE[screen.kind] || "";
  // Skip the entry blur when only the watching dot changed on the same step.
  const sig = `${screen.kind}|${screen.card ? screen.card.idx : ""}|${screen.headline || ""}`;
  const fresh = el.dataset.sig !== sig;
  el.dataset.sig = sig;
  el.innerHTML = `<div class="lens-inner${fresh ? " lens-enter" : ""}">${render(screen)}</div>`;
}
