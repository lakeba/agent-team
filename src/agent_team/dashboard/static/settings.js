"use strict";
// Settings: the options people change most, as plain switches, and team templates. Every change is
// previewed as a diff of .team.toml and saved only when you press Save, like the full editor.

const settings = { draft: null, sha: null, preview: null, templates: [], loading: false, error: "" };

async function loadSettings() {
  settings.loading = true;
  try {
    const [cfg, tpl] = await Promise.all([getJSON("/api/config"), getJSON("/api/templates")]);
    settings.draft = JSON.parse(JSON.stringify(cfg.data));
    for (const k of ["project", "limits", "routing", "sandbox", "notify", "pricing"]) settings.draft[k] = settings.draft[k] || {};
    settings.sha = cfg.sha; settings.templates = tpl.templates; settings.preview = null; settings.error = "";
  } catch (e) { settings.error = e.message; }
  settings.loading = false;
  renderSettings();
}

function sChanged() { settings.preview = null; const b = document.getElementById("settings-review"); if (b) b.disabled = false; }

function segmented(obj, key, options, fallback) {
  const current = obj[key] ?? fallback;
  return h("div", { class: "segmented", role: "radiogroup" }, options.map(([v, label]) =>
    h("button", { type: "button", role: "radio", "aria-checked": String(current === v),
      onclick: () => { if (v === fallback) delete obj[key]; else obj[key] = v; sChanged(); renderSettings(); } }, label)));
}

function money(obj, key, placeholder) {
  const el = h("input", { type: "number", step: "0.5", min: "0", value: obj[key] ?? "", placeholder });
  el.addEventListener("input", () => { if (el.value === "" || Number(el.value) === 0) delete obj[key]; else obj[key] = Number(el.value); sChanged(); });
  return el;
}

function setting(title, about, control) {
  return h("div", { class: "setting" }, h("div", {}, h("div", { class: "setting-title" }, title), h("div", { class: "hint" }, about)), control);
}

function renderSettings() {
  const el = document.getElementById("settings");
  if (!el) return;
  el.replaceChildren();
  if (settings.error) return el.append(errorCard("the settings", settings.error));
  if (!settings.draft) {
    el.append(h("div", { class: "card empty" }, settings.loading ? "Loading…" : "Loading…"));
    if (!settings.loading) loadSettings();
    return;
  }
  const d = settings.draft, pr = d.project, sb = d.sandbox;

  // Templates
  const tcard = h("div", { class: "card" }, h("h2", {}, "Templates"),
    h("p", { class: "muted small" }, "Common setups in one step. You'll see exactly what changes in .team.toml before anything is saved."));
  tcard.append(h("div", { class: "grid cards" }, settings.templates.map(t => h("div", { class: "template" },
    h("h3", {}, t.name), h("p", { class: "secondary small" }, t.about),
    h("button", { type: "button", onclick: async () => {
      try {
        const r = await postJSON("/api/templates/apply", { id: t.id, data: settings.draft });
        settings.draft = r.data; settings.preview = r.preview; renderSettings();
        document.getElementById("settings-preview")?.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (e) { toast(e.message); }
    } }, "Preview this template")))));

  // Easy settings
  const ui = h("div", { class: "card" }, h("h2", {}, "Settings"),
    setting("Releases", "Who decides when a version ships.", segmented(pr, "release", [["auto", "Team releases"], ["ask", "I approve each release"]], "auto")),
    setting("Reviews", "How the lead checks the work.", segmented(pr, "review", [["tools", "Reads files and runs tests"], ["snapshot", "Sees all files up front"]], "tools")),
    setting("Context", "How much of the project goes into each prompt.", segmented(pr, "context", [["auto", "Auto"], ["focused", "Focused"], ["full", "Everything"]], "auto")),
    setting("Spend limits", "US dollars. A run stops before the next model call once it reaches one.",
      h("div", { class: "inline" }, h("label", { class: "field" }, h("span", { class: "field-label" }, "Per run"), money(d.limits, "per_run", "no limit")),
        h("label", { class: "field" }, h("span", { class: "field-label" }, "Per day"), money(d.limits, "per_day", "no limit")))),
    setting("Test sandbox", "Run the code the team writes in a throwaway container, with no network and none of your keys.",
      h("div", { class: "inline" }, segmented(sb, "mode", [["off", "Off"], ["container", "In a container"]], "off"),
        sb.mode === "container" ? h("label", { class: "choice" }, (() => { const c = h("input", { type: "checkbox", checked: sb.network ? true : null });
          c.addEventListener("change", () => { if (c.checked) sb.network = true; else delete sb.network; sChanged(); }); return c; })(), " Allow network (to download dependencies)") : null)),
    setting("Cheaper routine checks", "Model used for owners' sign-offs and fact-checks by Claude members.",
      segmented(d.routing, "light_model", [["", "Each member's own"], ["claude-haiku-5-5", "Claude Haiku"], ["claude-sonnet-5-5", "Claude Sonnet"]], "")),
    setting("Paths that need my approval", "One per line. PRs changing these merge only after you approve their exact commit.",
      (() => { const t = h("textarea", { rows: 3, placeholder: ".github/\npackage.json\n*.csproj" }); t.value = (pr.require_approval || []).join("\n");
        t.addEventListener("input", () => { const v = t.value.split("\n").map(s => s.trim()).filter(Boolean); if (v.length) pr.require_approval = v; else delete pr.require_approval; sChanged(); }); return t; })()),
    setting("Notifications", "The environment variable holding a Slack or webhook URL (save it with agent-team keys set NAME).",
      (() => { const t = h("input", { type: "text", value: d.notify.webhook_env || "", placeholder: "e.g. AGENT_TEAM_WEBHOOK" });
        t.addEventListener("input", () => { const v = t.value.trim(); if (v) d.notify.webhook_env = v; else delete d.notify.webhook_env; sChanged(); }); return t; })()),
    h("div", { class: "actions" },
      h("button", { type: "button", id: "settings-review", class: "primary", onclick: async () => {
        try { settings.preview = await postJSON("/api/config/preview", { data: settings.draft }); }
        catch (e) { settings.preview = { valid: false, error: e.message, diff: "" }; }
        renderSettings();
        document.getElementById("settings-preview")?.scrollIntoView({ behavior: "smooth", block: "start" });
      } }, "Review changes"),
      h("button", { type: "button", onclick: () => { settings.draft = null; loadSettings(); } }, "Discard")));

  el.append(tcard, ui);
  if (settings.preview) el.append(settingsPreview());
}

function settingsPreview() {
  const r = settings.preview;
  const box = h("div", { class: "card review", id: "settings-preview" }, h("h2", {}, "Review changes"));
  if (!r.valid) box.append(h("p", {}, status("bad", "Not valid"), " ", r.error));
  else if (!r.diff) box.append(h("p", { class: "muted" }, "No changes."));
  else box.append(status("good", "Valid"));
  if (r.diff) {
    const pre = h("pre", { class: "diff" });
    r.diff.split("\n").forEach(line => pre.append(h("span", { class: line.startsWith("+") && !line.startsWith("+++") ? "add" :
      line.startsWith("-") && !line.startsWith("---") ? "del" : null }, line + "\n")));
    box.append(pre);
  }
  if (r.valid && r.diff) box.append(h("p", { class: "muted small" }, "The current file is kept as .team.toml.bak."),
    h("div", { class: "actions" }, h("button", { type: "button", class: "primary", onclick: async () => {
      try {
        await postJSON("/api/config/save", { data: settings.draft, sha: settings.sha });
        toast("Saved .team.toml. The previous version is in .team.toml.bak.");
        settings.draft = null; await load(); loadSettings();
      } catch (e) { settings.preview = { ...settings.preview, valid: false, error: e.message }; renderSettings(); }
    } }, "Save .team.toml")));
  return box;
}
