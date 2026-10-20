"use strict";
// Editing the team. Changes stay in a local draft until "Review changes" shows the exact diff of
// .team.toml and "Save" writes it (validated server-side, with a .team.toml.bak backup).
// Uses h(), status() and getJSON() from app.js.

const edit = { on: false, draft: null, sha: null, hasComments: false, token: null, review: null, wizard: null };
const ROLES = ["lead", "builder", "devops", "marketing", "factcheck", "reviewer", "security", "qa", "docs"];
const KINDS = { anthropic: "Claude (Anthropic API)", ollama: "Ollama", openai: "OpenAI-compatible server", "agent-http": "agent-team node" };
const EFFORTS = ["low", "medium", "high", "xhigh", "max"];

async function postJSON(path, body, retried = false) {
  if (!edit.token) edit.token = (await getJSON("/api/session")).token;
  const r = await fetch(path, { method: "POST", cache: "no-store",
    headers: { "Content-Type": "application/json", "X-Agent-Team-Token": edit.token }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));
  if (r.status === 403 && !retried && /session token/.test(data.error || "")) {
    edit.token = null;                       // the dashboard restarted: fetch its new token once and retry
    return postJSON(path, body, true);
  }
  if (!r.ok || data.error) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

async function startEditing() {
  const cfg = await getJSON("/api/config");
  edit.draft = JSON.parse(JSON.stringify(cfg.data));
  edit.draft.pricing = edit.draft.pricing || {};
  edit.draft.limits = edit.draft.limits || {};
  edit.draft.routing = edit.draft.routing || {};
  edit.sha = cfg.sha; edit.hasComments = cfg.has_comments; edit.on = true; edit.review = null; edit.wizard = null;
  renderTeam();
}
function stopEditing() { edit.on = false; edit.draft = null; edit.review = null; edit.wizard = null; renderTeam(); }

// ---------- small form helpers (each updates the draft in place) ----------
function field(label, input, hint) {
  return h("label", { class: "field" }, h("span", { class: "field-label" }, label), input, hint ? h("span", { class: "hint" }, hint) : null);
}
function text(obj, key, attrs = {}) {
  const el = h("input", { type: "text", value: obj[key] ?? "", ...attrs });
  el.addEventListener("input", () => { if (el.value === "") delete obj[key]; else obj[key] = el.value; markDirty(); });
  return el;
}
function list(obj, key, attrs = {}) {      // one item per line
  const el = h("textarea", { rows: attrs.rows || 3, ...attrs });
  el.value = (obj[key] || []).join("\n");
  el.addEventListener("input", () => { obj[key] = el.value.split("\n").map(s => s.trim()).filter(Boolean); markDirty(); });
  return el;
}
function select(obj, key, options, { allowBlank = false, onchange } = {}) {
  const el = h("select", {}, allowBlank ? h("option", { value: "" }, "—") : null,
    options.map(([v, label]) => h("option", { value: v, selected: obj[key] === v ? true : null }, label)));
  if (obj[key] && !options.some(([v]) => v === obj[key])) el.append(h("option", { value: obj[key], selected: true }, obj[key]));
  el.addEventListener("change", () => { if (el.value === "") delete obj[key]; else obj[key] = el.value; markDirty(); onchange && onchange(); });
  return el;
}
// Mirrors config.looks_like_secret: a key pasted where a variable's name goes. The value is never shown.
function looksLikeSecret(value) {
  const v = (value || "").trim();
  if (v.startsWith("sk-")) return true;
  if (v.length < 20 || v.includes(" ") || /^[A-Z0-9_]+$/.test(v)) return false;
  if (!/^[A-Za-z_][A-Za-z0-9_]{0,99}$/.test(v)) return true;
  const mixed = /[a-z]/.test(v) && /[A-Z]/.test(v) && (v.match(/[0-9]/g) || []).length >= 3;
  return mixed || (v.length >= 40 && !v.includes("_"));
}
function keyVariable(p) {
  const input = text(p, "api_key_env", { placeholder: p.kind === "anthropic" ? "default: ANTHROPIC_API_KEY" : "e.g. STUDIO_NODE_TOKEN" });
  const warn = h("span", { class: "hint warn-text", role: "alert" },
    "This looks like a key, not a variable's name. Save the key with agent-team keys set ANTHROPIC_API_KEY " +
    "(or the key step of the guided setup) and put the variable's name here.");
  const check = () => { warn.hidden = !looksLikeSecret(input.value); };
  input.addEventListener("input", check);
  check();
  return h("span", { class: "key-variable" }, input, warn);
}
function markDirty() { edit.review = null; const b = document.getElementById("review-btn"); if (b) b.disabled = false; }

// ---------- the editor ----------
function renderEditor(el) {
  const d = edit.draft;
  const providerNames = Object.keys(d.providers);
  el.append(h("div", { class: "card editbar" },
    h("div", {}, h("strong", {}, "Editing the team"), h("span", { class: "muted small" }, " Changes stay here until you review and save them.")),
    h("div", { class: "actions" },
      h("button", { type: "button", onclick: () => { edit.wizard = { step: 1, kind: "ollama" }; renderTeam(); } }, "Add a machine"),
      h("button", { type: "button", onclick: stopEditing }, "Discard"),
      h("button", { type: "button", id: "review-btn", class: "primary", onclick: review }, "Review changes"))));

  if (edit.wizard) el.append(renderWizard());
  if (edit.review) el.append(renderReview());

  // Members
  const members = h("div", { class: "card" }, h("div", { class: "section-head" }, h("h2", {}, "Members"),
    h("button", { type: "button", onclick: () => {
      d.agents.push({ name: `Member${d.agents.length + 1}`, role: "reviewer", provider: providerNames[0] || "" });
      markDirty(); renderTeam();
    } }, "Add member")));
  d.agents.forEach((a, i) => {
    a.owns = a.owns || [];
    members.append(h("fieldset", { class: "member-edit" },
      h("legend", {}, a.name || "(unnamed)"),
      h("div", { class: "form-grid" },
        field("Name", text(a, "name")),
        field("Role", select(a, "role", ROLES.map(r => [r, r]))),
        field("Connection", select(a, "provider", providerNames.map(p => [p, `${p} (${KINDS[d.providers[p].kind] || d.providers[p].kind})`]))),
        modelField(a, d.providers[a.provider], i),
        field("Effort", select(a, "effort", EFFORTS.map(x => [x, x]), { allowBlank: true }), "default: high"),
        field("Owns (one path per line)", list(a, "owns", { rows: 2 }), "This member must sign off PRs that change these paths"),
        field("Description", text(a, "description", { placeholder: "Shown to the team; also this member's view in discussions" })),
        field("Prompt file", text(a, "prompt", { placeholder: "optional, e.g. team/sentinel.md" }), "Replaces the whole role prompt"),
        field("Escalate to", select(a, "escalate_to", d.agents.filter(o => o !== a && o.name).map(o => [o.name, `${o.name} (${o.role})`]), { allowBlank: true }),
          "A stronger member who takes over after rejected rounds"),
        field("Skills (one per line)", list(a, "skills", { rows: 2, placeholder: "team/skills/owasp.md\n~/.claude/skills/security-review" }),
          "Markdown files or skill folders (with SKILL.md), added to this member's prompt")),
      h("div", { class: "actions" }, h("button", { type: "button", class: "danger",
        onclick: () => { d.agents.splice(i, 1); markDirty(); renderTeam(); } }, `Remove ${a.name || "member"}`))));
  });

  // Providers
  const provs = h("div", { class: "card" }, h("div", { class: "section-head" }, h("h2", {}, "Connections"),
    h("span", { class: "muted small" }, "How members reach their models: this Mac, another machine, or an API")));
  Object.entries(d.providers).forEach(([name, p]) => {
    const used = d.agents.filter(a => a.provider === name).map(a => a.name);
    const result = h("span", { class: "test-result" });
    provs.append(h("fieldset", { class: "member-edit" },
      h("legend", {}, name, used.length ? h("span", { class: "muted small" }, ` · used by ${used.join(", ")}`) : h("span", { class: "muted small" }, " · unused")),
      h("div", { class: "form-grid" },
        field("Kind", select(p, "kind", Object.entries(KINDS), { onchange: () => renderTeam() })),
        p.kind !== "anthropic" ? field("URL", text(p, "url", { placeholder: p.kind === "ollama" ? "http://localhost:11434" : "http://host:port" })) : null,
        field("Key variable", keyVariable(p),
          "The name of an environment variable. Never the key itself.")),
      h("div", { class: "actions" },
        h("button", { type: "button", onclick: async () => {
          result.replaceChildren(status("pending", "testing…"));
          const model = (d.agents.find(a => a.provider === name) || {}).model || "";
          try { const r = await postJSON("/api/test-provider", { provider: p, model });
                result.replaceChildren(status(r.ok ? "good" : "bad", r.status), r.note ? h("span", { class: "muted small" }, " " + r.note) : "");
          } catch (e) { result.replaceChildren(status("bad", e.message)); }
        } }, "Test connection"), result,
        h("button", { type: "button", class: "danger", disabled: used.length ? true : null, title: used.length ? "Members use this connection" : null,
          onclick: () => { delete d.providers[name]; markDirty(); renderTeam(); } }, "Remove"))));
  });

  // Project
  const pr = d.project;
  const project = h("div", { class: "card" }, h("h2", {}, "Project"),
    h("div", { class: "form-grid" },
      field("Name", text(pr, "name")),
      field("GitHub repo", text(pr, "repo", { placeholder: "owner/name" })),
      field("Test command", text(pr, "test_command", { placeholder: "e.g. npm test" })),
      field("Test count pattern", text(pr, "test_count_pattern", { placeholder: "Ran (\\d+) tests?" }), "A regex with one group, matched in CI logs"),
      field("Guarantees (one per line)", list(pr, "guarantees", { rows: 5 }), "The lead holds every change to these"),
      field("Need my approval (one path per line)", list(pr, "require_approval", { rows: 3, placeholder: "auth/\npackage.json\n*.csproj" }),
        "PRs changing these merge only after you approve their exact commit"),
      field("Never send these paths (one per line)", list(pr, "context_skip", { rows: 3 }), "Build output, vendored code, large assets"),
      field("Releases", select(pr, "release", [["auto", "The devops shift releases on its own"], ["ask", "It proposes; I approve each release"]], { allowBlank: true }),
        "Who decides when a version ships"),
      field("Context", select(pr, "context", [["auto", "Auto: focused when the project is large"], ["focused", "Focused: the lead picks files"], ["full", "Full: every file, every time"]], { allowBlank: true }),
        "What each prompt includes")));

  // Spend limits
  const money = key => { const el = h("input", { type: "number", step: "0.5", min: "0", value: d.limits[key] ?? "", placeholder: "no limit" });
    el.addEventListener("input", () => { if (el.value === "" || Number(el.value) === 0) delete d.limits[key]; else d.limits[key] = Number(el.value); markDirty(); }); return el; };
  const limits = h("div", { class: "card" }, h("h2", {}, "Spend limits"),
    h("p", { class: "muted small" }, "A run stops before the next model call once an estimate reaches a limit. US dollars; leave blank for no limit."),
    h("div", { class: "form-grid" }, field("Per run", money("per_run")), field("Per day (UTC)", money("per_day"))));

  // Pricing
  const pricing = h("div", { class: "card" }, h("div", { class: "section-head" }, h("h2", {}, "Prices"),
    h("button", { type: "button", onclick: () => { d.pricing["model-id"] = { input: 0, output: 0 }; markDirty(); renderTeam(); } }, "Add a price")),
    h("p", { class: "muted small" }, "Optional overrides for cost estimates, in US dollars per million tokens. Claude models have built-in prices; local models count as free."));
  Object.entries(d.pricing).forEach(([model, price]) => {
    const name = h("input", { type: "text", value: model });
    name.addEventListener("change", () => { if (name.value && name.value !== model) { d.pricing[name.value] = price; delete d.pricing[model]; markDirty(); renderTeam(); } });
    const num = key => { const el = h("input", { type: "number", step: "0.01", min: "0", value: price[key] ?? "" });
      el.addEventListener("input", () => { if (el.value === "") delete price[key]; else price[key] = Number(el.value); markDirty(); }); return el; };
    pricing.append(h("div", { class: "price-row" }, field("Model", name), field("Input", num("input")), field("Output", num("output")),
      field("Cache read", num("cache_read")),
      h("button", { type: "button", class: "danger", onclick: () => { delete d.pricing[model]; markDirty(); renderTeam(); } }, "Remove")));
  });

  const routingCard = h("div", { class: "card" }, h("h2", {}, "Model routing"),
    h("p", { class: "muted small" }, "Members with \"Escalate to\" hand their work to a stronger member after this many rejected rounds. A light model runs owners' sign-offs and fact-checks for Claude members."),
    h("div", { class: "form-grid" },
      field("Escalate after (rejected rounds)", (() => { const el = h("input", { type: "number", min: "1", value: d.routing.escalate_after ?? "", placeholder: "1" });
        el.addEventListener("input", () => { if (el.value === "") delete d.routing.escalate_after; else d.routing.escalate_after = Number(el.value); markDirty(); }); return el; })()),
      field("Light model", text(d.routing, "light_model", { placeholder: "e.g. claude-haiku-5-5 (blank: off)" }))));
  el.append(members, provs, project, limits, routingCard, pricing);
}

async function review() {
  try {
    edit.review = await postJSON("/api/config/preview", { data: edit.draft });
  } catch (e) { edit.review = { valid: false, error: e.message, diff: "" }; }
  renderTeam();
  document.getElementById("review")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderReview() {
  const r = edit.review;
  const box = h("div", { class: "card review", id: "review" }, h("h2", {}, "Review changes"));
  if (!r.valid) box.append(h("p", {}, status("bad", "Not valid"), " ", r.error));
  else if (!r.diff) box.append(h("p", { class: "muted" }, "No changes."));
  else box.append(status("good", "Valid"));
  if (r.diff) {
    const pre = h("pre", { class: "diff" });
    r.diff.split("\n").forEach(line => pre.append(h("span", { class: line.startsWith("+") && !line.startsWith("+++") ? "add" :
      line.startsWith("-") && !line.startsWith("---") ? "del" : null }, line + "\n")));
    box.append(pre);
  }
  if (r.valid && r.diff) {
    if (edit.hasComments) box.append(h("p", { class: "muted small" }, "Saving rewrites .team.toml, so comments in it are not kept. The current file is saved as .team.toml.bak."));
    else box.append(h("p", { class: "muted small" }, "The current file is saved as .team.toml.bak."));
    box.append(h("div", { class: "actions" }, h("button", { type: "button", class: "primary", onclick: save }, "Save .team.toml")));
  }
  return box;
}

async function save() {
  try {
    await postJSON("/api/config/save", { data: edit.draft, sha: edit.sha });
    edit.on = false; edit.draft = null; edit.review = null;
    await load();   // reload everything from disk
    toast("Saved .team.toml. The previous version is in .team.toml.bak.");
  } catch (e) {
    edit.review = { ...edit.review, valid: false, error: e.message };
    renderTeam();
  }
}

function toast(msg) {
  const t = h("div", { class: "toast", role: "status" }, msg);
  document.body.append(t);
  setTimeout(() => t.remove(), 5000);
}

// The model box: for a member on a local model server, the models that server serves, and a warning
// (with the likely right name) when the one typed isn't among them.
const servedModels = {};   // url -> {models, reachable} | "loading"
function modelField(a, p, i) {
  const kind = p && p.kind;
  const local = kind === "ollama" || kind === "openai";
  const input = text(a, "model", { list: local ? `models-${i}` : null,
    placeholder: kind === "agent-http" ? "chosen by the node" : kind === "openai" ? "e.g. mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"
      : kind === "ollama" ? "e.g. qwen3.8:27b-mlx" : "e.g. claude-sonnet-5-5" });
  if (!local) return field("Model", input);
  const url = (p.url || (kind === "ollama" ? "http://localhost:11434" : "")).replace(/\/$/, "");
  const served = servedModels[url];
  if (served === undefined && url) {
    servedModels[url] = "loading";
    postJSON("/api/models", { url }).then(r => { servedModels[url] = r; renderTeam(); })
      .catch(() => { servedModels[url] = { models: [], reachable: false }; });
  }
  const models = served && served !== "loading" ? served.models : [];
  const note = h("span", { class: "hint" });
  input.addEventListener("input", () => refresh());
  function refresh() {
    note.replaceChildren();
    if (!served || served === "loading") return note.append("Looking at what the server serves…");
    if (!served.reachable) return note.append(`The server at ${url} doesn't answer right now.`);
    if (!a.model || models.includes(a.model)) return note.append(models.length ? `Served there: ${models.length} models` : "");
    const want = a.model.toLowerCase();
    const near = models.find(m => m.toLowerCase().split("/").pop() === want.split("/").pop() || m.toLowerCase() === `${want}:latest`);
    note.append(h("span", { class: "warn-text" }, `${a.model} isn't served there. `));
    if (near) note.append(h("button", { type: "button", onclick: () => { a.model = near; markDirty(); renderTeam(); } }, `Use ${near}`));
    else note.append(`It serves: ${models.join(", ")}`);
  }
  refresh();
  return h("label", { class: "field" }, h("span", { class: "field-label" }, "Model"), input,
    h("datalist", { id: `models-${i}` }, models.map(m => h("option", { value: m }))), note);
}

// ---------- Add a machine ----------
function renderWizard() {
  const w = edit.wizard, d = edit.draft;
  const box = h("div", { class: "card wizard" }, h("div", { class: "section-head" }, h("h2", {}, "Add a machine"),
    h("button", { type: "button", onclick: () => { edit.wizard = null; renderTeam(); } }, "Close")));
  const kinds = [["ollama", "Another computer running Ollama"], ["openai", "A server with an OpenAI-compatible API (mlx_lm, vLLM, LM Studio, llama.cpp)"],
                 ["agent-http", "An agent-team node (the machine runs `agent-team serve` and keeps its own model and keys)"]];
  box.append(h("div", { class: "choices" }, kinds.map(([k, label]) => h("label", { class: "choice" },
    h("input", { type: "radio", name: "wk", value: k, checked: w.kind === k ? true : null, onchange: () => { w.kind = k; w.token = null; renderTeam(); } }), " ", label))));
  w.name = w.name ?? "";
  w.url = w.url ?? "";
  w.model = w.model ?? "";
  w.env = w.env ?? "";
  const nameIn = h("input", { type: "text", value: w.name, placeholder: "e.g. studio" });
  nameIn.addEventListener("input", () => { w.name = nameIn.value.trim(); envIn.placeholder = suggestedEnv(); });
  const urlIn = h("input", { type: "text", value: w.url, placeholder: w.kind === "ollama" ? "http://studio.local:11434" : w.kind === "openai" ? "http://gpu-01:8000" : "http://studio.tailnet:8765" });
  urlIn.addEventListener("input", () => { w.url = urlIn.value.trim(); w.tested = null; });
  const modelIn = h("input", { type: "text", value: w.model, list: "wizard-models",
    placeholder: w.kind === "agent-http" ? "the node chooses" : w.kind === "openai" ? "e.g. mlx-community/Qwen2.5-Coder-7B-Instruct-4bit" : "e.g. qwen3.8:27b-mlx" });
  modelIn.addEventListener("input", () => { w.model = modelIn.value.trim(); });
  const modelList = h("datalist", { id: "wizard-models" });
  const envIn = h("input", { type: "text", value: w.env });
  function suggestedEnv() { return ((w.name || "machine").toUpperCase().replace(/[^A-Z0-9]+/g, "_") + (w.kind === "agent-http" ? "_NODE_TOKEN" : "_API_KEY")); }
  envIn.placeholder = suggestedEnv();
  envIn.addEventListener("input", () => { w.env = envIn.value.trim(); });
  box.append(h("div", { class: "form-grid" },
    field("Connection name", nameIn), field("URL", urlIn),
    w.kind !== "agent-http" ? field("Model", modelIn) : null,
    w.kind !== "ollama" ? field("Key variable on this Mac", envIn, w.kind === "agent-http" ? "Holds the node's token here" : "Only if the server needs a key") : null));

  if (w.kind !== "agent-http") {   // model servers already running somewhere on the network
    const picked = (w.servers || []).find(s => s.url === w.url);
    modelList.replaceChildren(...(picked ? picked.models : (w.tested || [])).map(m => h("option", { value: m })));
    box.append(modelList);
    const found = h("div", { class: "found" });
    if (w.servers === null) found.append(status("pending", "looking here, on this machine's host and on the network… (up to half a minute)"));
    else if (w.servers && !w.servers.length) found.append(h("p", { class: "muted small" }, "No model server answered. On another computer it must listen on the network: Ollama with OLLAMA_HOST=0.0.0.0, mlx_lm with --host 0.0.0.0."));
    else if (w.servers) found.append(h("ul", { class: "found-list" }, w.servers.map(s => h("li", {},
      h("strong", {}, s.label), ` ${s.url} · ${s.models.length} models `,
      h("button", { type: "button", onclick: () => {
        w.kind = s.kind; w.url = s.url; w.model = w.model && s.models.includes(w.model) ? w.model : (s.models.find(m => /instruct|chat/i.test(m)) || s.models[0] || "");
        w.name = w.name || (s.label === "Ollama" ? "ollama" : s.label.toLowerCase().replace(/[^a-z0-9]+/g, "-")) + "-" + s.url.split("//")[1].split(":")[0].split(".").pop();
        renderTeam(); } }, "Use")))));
    box.append(h("div", { class: "actions" }, h("button", { type: "button", disabled: w.servers === null ? true : null, onclick: async () => {
      w.servers = null; renderTeam();
      try { w.servers = (await postJSON("/api/ollama/find", {})).servers; } catch (e) { w.servers = []; toast(e.message); }
      renderTeam();
    } }, "Find servers on this network"), found));
  }

  if (w.kind === "agent-http") {
    const found = h("div", { class: "found" });
    const showFound = () => {
      found.replaceChildren();
      if (w.found === undefined) return;
      if (w.found === null) return found.append(status("pending", "looking…"));
      if (!w.found.length) return found.append(h("p", { class: "muted small" }, "No nodes answered. A node answers when started with --host 0.0.0.0 on this network (and its firewall allows UDP 8766)."));
      found.append(h("ul", { class: "found-list" }, w.found.map(n => h("li", {},
        h("strong", {}, n.node), ` ${n.url} · ${n.provider}/${n.model} `,
        h("button", { type: "button", onclick: () => { w.url = n.url; w.name = w.name || n.node.toLowerCase().replace(/[^a-z0-9-]+/g, "-"); renderTeam(); } }, "Use")))));
    };
    box.append(h("div", { class: "actions" }, h("button", { type: "button", onclick: async () => {
      w.found = null; showFound();
      try { w.found = (await postJSON("/api/discover", {})).nodes; } catch (e) { w.found = []; toast(e.message); }
      showFound();
    } }, "Find nodes on this network"), found));
    showFound();
    const steps = h("div", { class: "steps" });
    if (!w.token) {
      steps.append(h("button", { type: "button", onclick: async () => {
        try { w.token = (await postJSON("/api/node-token", {})).token; renderTeam(); } catch (e) { toast(e.message); } } }, "Generate a token for this node"));
    } else {
      const env = w.env || suggestedEnv();
      const node = w.name || "node";
      steps.append(
        h("p", {}, h("strong", {}, "1. On the other machine"), " (install agent-team there first: see docs/remote-agents.md):"),
        codeBlock(`export AGENT_TEAM_TOKEN='${w.token}'\nagent-team serve --provider ollama --model <model> --host 0.0.0.0 --port 8765 --node ${node}`),
        h("p", { class: "muted small" }, "Put it behind a VPN or SSH tunnel: the token travels in request headers."),
        h("p", {}, h("strong", {}, "2. On this Mac"), ", add to your shell profile, then restart the dashboard so it sees it:"),
        codeBlock(`export ${env}='${w.token}'`),
        h("p", { class: "muted small" }, "This token is shown once and never saved by the dashboard. Copy it now."));
    }
    box.append(steps);
  }

  const result = h("span", { class: "test-result" });
  box.append(h("div", { class: "actions" },
    h("button", { type: "button", onclick: async () => {
      const bad = addressProblem(w.url);
      if (bad) return result.replaceChildren(status("bad", bad));
      result.replaceChildren(status("pending", "testing…"));
      try { const r = await postJSON("/api/test-provider", { provider: wizardProvider(), model: w.model });
            if (r.models && r.models.length) {   // what the server offers becomes the Model list; with none chosen, a likely one
              w.tested = r.models;
              modelList.replaceChildren(...r.models.map(m => h("option", { value: m })));
              if (!w.model) { w.model = r.models.find(m => /instruct|chat/i.test(m)) || r.models[0]; modelIn.value = w.model; }
            }
            result.replaceChildren(status(r.ok ? "good" : "bad", r.status), r.note ? h("span", { class: "muted small" }, " " + r.note) : "");
      } catch (e) { result.replaceChildren(status("bad", e.message)); }
    } }, "Test connection"), result,
    h("button", { type: "button", class: "primary", onclick: () => {
      if (!w.name || !w.url) return toast("Give the connection a name and a URL.");
      if (addressProblem(w.url)) return toast(addressProblem(w.url));
      if (d.providers[w.name]) return toast(`A connection named ${w.name} already exists.`);
      d.providers[w.name] = wizardProvider();
      edit.wizard = null; markDirty(); renderTeam();
      toast(`Added the connection ${w.name}. Point a member at it, then review and save.`);
    } }, "Add this connection")));
  return box;

  function wizardProvider() {
    const p = { kind: w.kind, url: w.url };
    const env = w.kind === "ollama" ? "" : (w.env || (w.kind === "agent-http" ? suggestedEnv() : ""));
    if (env) p.api_key_env = env;
    return p;
  }
}

// The same check as config.address_problem, before anything is sent.
function addressProblem(url) {
  if (!url) return "";
  if (!/^https?:\/\//.test(url)) return `${url} needs http:// or https:// in front`;
  let host = ""; try { host = new URL(url).hostname; } catch (_) { return `${url} isn't a valid address`; }
  const raw = url.split("//")[1].split(/[:/]/)[0];   // the URL parser would quietly "fix" 192.168.141
  if (/^[\d.]+$/.test(raw)) {
    const parts = raw.split(".");
    if (parts.length !== 4 || parts.some(p => p === "" || Number(p) > 255)) {
      const example = parts.length === 3 ? [parts[0], parts[1], "1", parts[2]].join(".") : "192.168.1.20";
      return `${raw} isn't a valid address: an IPv4 address has four numbers from 0 to 255 (for example ${example})`;
    }
  }
  return "";
}

function codeBlock(textValue) {
  const pre = h("pre", { class: "code" }, textValue);
  const btn = h("button", { type: "button", class: "copy", onclick: async () => {
    try { await navigator.clipboard.writeText(textValue); btn.textContent = "Copied"; } catch (_) { btn.textContent = "Select and copy"; }
  } }, "Copy");
  return h("div", { class: "codewrap" }, pre, btn);
}
