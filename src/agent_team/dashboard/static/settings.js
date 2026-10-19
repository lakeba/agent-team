"use strict";
// Settings: the options people change most, as plain switches, and team templates. Every change is
// previewed as a diff of .team.toml and saved only when you press Save, like the full editor.

const settings = { draft: null, sha: null, preview: null, templates: [], loading: false, error: "",
  comp: null, compInfo: null, servers: null, finding: false };

async function loadSettings() {
  settings.loading = true;
  try {
    const [cfg, tpl] = await Promise.all([getJSON("/api/config"), getJSON("/api/templates")]);
    settings.draft = JSON.parse(JSON.stringify(cfg.data));
    for (const k of ["project", "limits", "routing", "sandbox", "notify", "pricing"]) settings.draft[k] = settings.draft[k] || {};
    settings.sha = cfg.sha; settings.templates = tpl.templates; settings.preview = null; settings.error = "";
    const info = await postJSON("/api/composition", { data: settings.draft });
    settings.comp = info.composition; settings.compInfo = info;
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
  el.append(h("div", { class: "card" }, h("h2", {}, "Setup"),
    h("p", { class: "secondary small" }, "The guided setup: start another idea as a new project, or open one you started before."),
    h("div", { class: "actions" }, h("button", { type: "button", onclick: () => startSetup(true) }, "Run setup again"))));

  const ccard = compositionCard();

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

  el.append(ccard, tcard, ui);
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

// Team composition: where the models run, which members, how many builders, spend limits. The
// same choices `agent-team init` asks about; applied to the current team and reviewed as a diff.
function compositionCard() {
  const c = settings.comp, info = settings.compInfo;
  const card = h("div", { class: "card" }, h("h2", {}, "Team composition"),
    h("p", { class: "muted small" }, "Where the members' models run, who is on the team and how many builders. " +
      "Members that stay keep their names, skills and other settings."));
  if (!c || !info) return card;
  const choose = (key, value) => { c[key] = value; renderSettings(); };
  const models = h("div", { class: "segmented", role: "radiogroup" }, Object.entries(info.models).map(([v, about]) =>
    h("button", { type: "button", role: "radio", "aria-checked": String(c.models === v), title: about,
      onclick: () => choose("models", v) }, { mixed: "Claude + Ollama builders", ollama: "Only Ollama", claude: "Only Claude" }[v] || v)));
  card.append(setting("Models", info.models[c.models], models));

  if (c.models !== "claude") {
    const url = h("input", { type: "text", value: c.ollama_url, placeholder: "http://localhost:11434" });
    url.addEventListener("input", () => { c.ollama_url = url.value.trim(); });
    const find = h("button", { type: "button", disabled: settings.finding ? true : null, onclick: async () => {
      settings.finding = true; renderSettings();
      try { settings.servers = (await postJSON("/api/ollama/find", {})).servers; }
      catch (e) { toast(e.message); }
      settings.finding = false;
      if (settings.servers && settings.servers.length && !settings.servers.some(s => s.url === c.ollama_url)) c.ollama_url = settings.servers[0].url;
      renderSettings();
    } }, settings.finding ? "Looking…" : "Find Ollama");
    const found = settings.servers;
    const server = found ? found.find(s => s.url === c.ollama_url) : null;
    const pick = found && found.length ? h("div", { class: "inline" }, found.map(s =>
      h("label", { class: "choice" }, (() => { const r = h("input", { type: "radio", name: "ollama-server", checked: s.url === c.ollama_url ? true : null });
        r.addEventListener("change", () => choose("ollama_url", s.url)); return r; })(), ` ${s.url} (${s.models.length} models)`)))
      : found ? h("p", { class: "hint" }, "No Ollama answered on this machine, its host or the gateway. Type its address.") : null;
    const modelEl = server && server.models.length
      ? (() => { const m = h("select", {}, server.models.map(n => h("option", { value: n, selected: n === c.ollama_model ? true : null }, n)));
          m.addEventListener("change", () => { c.ollama_model = m.value; }); return m; })()
      : (() => { const m = h("input", { type: "text", value: c.ollama_model }); m.addEventListener("input", () => { c.ollama_model = m.value.trim(); }); return m; })();
    card.append(setting("Ollama", "The server the Ollama members use, and their model.",
      h("div", {}, h("div", { class: "inline" }, url, find), pick,
        h("label", { class: "field" }, h("span", { class: "field-label" }, "Model"), modelEl))));
  }

  const extras = h("div", { class: "inline" }, Object.entries(info.extras).map(([role, x]) =>
    h("label", { class: "choice", title: x.about }, (() => { const b = h("input", { type: "checkbox", checked: c.extras.includes(role) ? true : null });
      b.addEventListener("change", () => { c.extras = b.checked ? [...c.extras, role] : c.extras.filter(r => r !== role); }); return b; })(),
      ` ${x.name} (${role})`)));
  card.append(setting("Optional members", "Security reviews every build, QA writes tests first, Docs updates the docs.", extras));

  const builders = h("select", {}, Array.from({ length: info.max_builders }, (_, i) =>
    h("option", { value: String(i + 1), selected: c.builders === i + 1 ? true : null }, String(i + 1))));
  builders.addEventListener("change", () => { c.builders = Number(builders.value); });
  card.append(setting("Builders", "More than one lets build --parallel split a plan between them.", builders));

  card.append(h("div", { class: "actions" }, h("button", { type: "button", class: "primary", onclick: async () => {
    try {
      const { per_run, per_day, ...team } = c;   // limits are set in Settings below
      const r = await postJSON("/api/composition/apply", { composition: team, data: settings.draft });
      settings.draft = r.data; settings.preview = r.preview; renderSettings();
      document.getElementById("settings-preview")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) { toast(e.message); }
  } }, "Preview this team")));
  return card;
}
