"use strict";
// Behaviour: the latest behaviour checks. Each journey ran on the version a build started from
// (before) and with the team's changes (now); this shows what a user would notice side by side.

const behaviourView = { data: null, error: "", selected: null };

async function loadBehaviour() {
  try {
    behaviourView.data = await getJSON("/api/behaviour");
    behaviourView.error = "";
    if (!behaviourView.selected && behaviourView.data.checks.length) behaviourView.selected = behaviourView.data.checks[0].id;
  } catch (e) { behaviourView.error = e.message; }
  renderBehaviour();
}

const BEHAVIOUR_WORDS = { same: ["good", "behaves as before"], changed: ["warn", "behaves differently"], failed: ["bad", "couldn't run"] };
const API_WORDS = { same: ["good", "public API unchanged"], changed: ["warn", "public API changed"], failed: ["bad", "couldn't be inspected"] };

function outcomeBadge(o) {
  const [kind, label] = (o.kind === "api" ? API_WORDS : BEHAVIOUR_WORDS)[o.status] || ["pending", o.status];
  return status(kind, label);
}

function side(checkId, label, obs, kind) {
  const box = h("div", { class: "card" }, h("h3", {}, label));
  if (obs.problem) { box.append(h("p", {}, status("bad", "didn't run"), " ", obs.problem)); return box; }
  const facts = [obs.exit, obs.url && kind === "browser" ? `at ${obs.url}` : "", obs.files?.length ? `files: ${obs.files.join(", ")}` : ""]
    .filter(Boolean).join(" · ");
  if (facts) box.append(h("p", { class: "muted small" }, facts));
  if (obs.errors?.length) box.append(h("p", {}, status("bad", `${obs.errors.length} error(s)`), " ", obs.errors.slice(0, 3).join("; ")));
  if (obs.screenshot) box.append(h("img", { class: "shot", alt: `${label}: screenshot`, src: `/api/evidence/${encodeURIComponent(checkId)}/${encodeURIComponent(obs.screenshot)}` }));
  if (obs.view && kind !== "api") box.append(h("pre", { class: "screen" }, obs.view));
  if (kind === "api" && obs.view) box.append(h("details", {}, h("summary", {}, `${obs.view.split("\n").length} public members`), h("pre", { class: "screen" }, obs.view)));
  return box;
}

function renderBehaviour() {
  const el = document.getElementById("behaviour");
  if (!el) return;
  el.replaceChildren();
  if (behaviourView.error) return el.append(errorCard("behaviour checks", behaviourView.error));
  const d = behaviourView.data;
  if (!d) { el.append(h("div", { class: "card empty" }, "Loading…")); loadBehaviour(); return; }
  if (!d.checks.length) {
    el.append(h("div", { class: "card empty" },
      d.configured ? "No behaviour checks yet. They run in every build round; or run agent-team behaviour run."
        : "Behaviour checks use the program like a user, before and after each change. Set them up with: agent-team rea setup"));
    return;
  }
  const list = h("div", { class: "card" }, h("h2", {}, "Behaviour checks"),
    h("p", { class: "muted small" }, "Each journey ran on the version a change started from (before) and with the change (now)."),
    table(["When", "From", "Journeys"], d.checks.map(c => [
      h("button", { type: "button", class: c.id === behaviourView.selected ? "link selected" : "link",
        onclick: () => { behaviourView.selected = c.id; renderBehaviour(); } }, fmtWhen(c.created)),
      c.label,
      h("span", {}, c.outcomes.map(o => outcomeBadge(o))),
    ])));
  el.append(list);
  const c = d.checks.find(x => x.id === behaviourView.selected);
  if (!c) return;
  for (const o of c.outcomes) {
    const card = h("div", { class: "card" }, h("h2", {}, o.name, " ", outcomeBadge(o)),
      h("p", { class: "muted small" }, `${o.kind} · base ${String(c.base).slice(0, 10)} → ${c.target}`));
    if (o.first_difference) card.append(h("p", {}, h("strong", {}, "First difference: "), o.first_difference));
    if (o.breaking?.length) card.append(h("p", {}, status("bad", "breaks callers"), " ", o.breaking.join(", ")));
    if (o.added?.length) card.append(h("p", {}, status("good", "added"), " ", o.added.join(", ")));
    for (const n of o.notes || []) card.append(h("p", { class: "muted small" }, n));
    card.append(h("div", { class: "grid two" }, side(c.id, "Before", o.base, o.kind), side(c.id, "Now", o.work, o.kind)));
    el.append(card);
  }
}

document.querySelector('[role=tab][data-tab="behaviour"]')?.addEventListener("click", () => loadBehaviour());
// Opened by its address (#behaviour) before this script loaded: load now.
if (document.querySelector('[role=tab][data-tab="behaviour"]')?.getAttribute("aria-selected") === "true") loadBehaviour();
