"use strict";
// The first-run wizard: from an idea to a team at work, without a terminal. Every step calls the
// same code the command line uses (/api/setup/* on this computer); nothing leaves this machine
// except what the person chooses (their Anthropic key goes to Anthropic to be checked, GitHub
// sign-in happens on GitHub's own page).

const wizard = { step: 0, status: null, busy: "", error: "", project: "", ready: null, tasks: null, chosen: [],
  own: "", login: null, pull: {}, repo: "", keyResult: null,
  form: { name: "", vision: "", owner: "", models: "", ollama_url: "", ollama_model: "", extras: ["qa"], builders: 1, per_day: 5,
          folder: "", existing: false, inspire: { url: "", journeys: "", ok: false } },
  explore: null };   // the inspire run started from the last step: {id, status, story}
const STEPS = ["Welcome", "Your idea", "Inspiration", "Where the AI runs", "Your team", "GitHub", "Ready check", "First version"];

function wizardRoot() { return document.getElementById("setup"); }

async function startSetup(fromDashboard) {
  document.querySelector("nav.tabs").hidden = true;
  document.getElementById("project-name").textContent = "Lakeba OS";
  document.getElementById("version").textContent = "Let’s set up your project";
  const repo = document.getElementById("repo-link"); repo.textContent = ""; repo.removeAttribute("href");
  document.title = "Set up · Lakeba OS";
  document.querySelectorAll("[role=tabpanel]").forEach(p => { p.hidden = true; });
  wizardRoot().hidden = false;
  wizard.step = 0; wizard.error = ""; wizard.fromDashboard = !!fromDashboard;
  wizard.busy = "Looking at this computer…"; renderSetup();
  try { wizard.status = await getJSON("/api/setup/status"); } catch (e) { wizard.error = e.message; }
  const s = wizard.status || {};
  const f = wizard.form;
  if (s.ollama && s.ollama.length) { f.ollama_url = s.ollama[0].url; f.ollama_model = pickModel(s.ollama[0].models, s.recommended_model); }
  f.models = s.claude_key && s.ollama && s.ollama.length ? "mixed" : s.claude_key ? "claude" : "ollama";
  if (s.git_name) f.owner = s.git_name;
  wizard.busy = ""; renderSetup();
  scanNetwork();
}

// The other computers on the network take a few seconds more: look in the background, add what's found.
async function scanNetwork() {
  wizard.scanning = true;
  try {
    const more = (await getJSON("/api/setup/scan")).servers || [];
    const s = wizard.status, known = new Set((s.ollama || []).map(x => x.url));
    s.ollama = [...(s.ollama || []), ...more.filter(x => !known.has(x.url))];
    if (!wizard.form.ollama_url && s.ollama.length) { wizard.form.ollama_url = s.ollama[0].url; wizard.form.local_kind = s.ollama[0].kind; }
  } catch (_) {}
  wizard.scanning = false;
  if (wizard.step === 3) renderSetup();
}

function pickModel(models, recommended) {
  if (!models || !models.length) return recommended;
  if (models.includes(recommended) || models.includes(`${recommended}:latest`)) return recommended;
  const size = n => { const m = n.match(/(\d+(?:\.\d+)?)b\b/); return m ? Number(m[1]) : 0; };
  const score = n => (/instruct|chat/i.test(n) ? 3 : 0) + (n.includes("coder") ? 4 : 0) + (n.includes("qwen") ? 2 : 0) + (size(n) >= 7 && size(n) <= 40 ? 2 : 0)
    - (size(n) > 70 ? 6 : 0) - (/embed|ocr|vision/.test(n) ? 9 : 0);
  return [...models].sort((a, b) => score(b) - score(a))[0];
}

function stepDots() {
  return h("ol", { class: "wiz-steps", "aria-label": "Setup steps" }, STEPS.map((name, i) =>
    h("li", { class: i === wizard.step ? "on" : i < wizard.step ? "done" : "" , "aria-current": i === wizard.step ? "step" : null },
      h("span", { class: "n" }, i < wizard.step ? "✓" : String(i + 1)), h("span", { class: "t" }, name))));
}

function nav(nextLabel, onNext, opts = {}) {
  return h("div", { class: "wiz-nav" },
    wizard.step > 0 && !opts.noBack ? h("button", { type: "button", onclick: () => { wizard.step--; wizard.error = ""; renderSetup(); } }, "Back") : h("span"),
    h("span", { class: "spacer" }),
    opts.skip ? h("button", { type: "button", onclick: opts.skip }, opts.skipLabel || "Skip for now") : null,
    onNext ? h("button", { type: "button", class: "primary big", disabled: wizard.busy ? true : null, onclick: onNext }, nextLabel) : null);
}

function renderSetup() {
  const root = wizardRoot();
  if (!root) return;
  root.replaceChildren();
  const card = h("div", { class: "card wiz" }, stepDots());
  if (wizard.error) card.append(h("div", { class: "card notice bad wiz-msg", role: "alert" }, wizard.error));
  if (wizard.busy) card.append(h("p", { class: "wiz-busy", role: "status" }, h("span", { class: "spinner", "aria-hidden": "true" }), wizard.busy));
  const body = [welcome, idea, inspiration, models, team, github, readyCheck, firstVersion][wizard.step]();
  card.append(...[body].flat());
  root.append(card);
}

const go = n => { wizard.step = n; wizard.error = ""; renderSetup(); window.scrollTo(0, 0); };
const area = (obj, key, attrs) => { const el = h("textarea", attrs); el.value = obj[key] || ""; el.addEventListener("input", () => { obj[key] = el.value; }); return el; };
const input = (obj, key, attrs) => { const el = h("input", { type: "text", ...attrs }); el.value = obj[key] ?? ""; el.addEventListener("input", () => { obj[key] = attrs && attrs.type === "number" ? Number(el.value) : el.value; }); return el; };

// ---------- 0. Welcome ----------
function welcome() {
  const s = wizard.status || {};
  const out = [h("h2", { class: "wiz-title" }, "Have an idea? Let’s build it."),
    h("p", { class: "lede" }, "In a few minutes you’ll have an AI team ready to build your idea: a lead who plans and reviews, " +
      "builders who write the code, and tests on every change. You describe what you want and approve each step; the team writes the code."),
    h("div", { class: "wiz-four" }, [["1", "Describe", "Tell us your idea in plain words."], ["2", "Build", "The AI team builds a first working version."],
      ["3", "Apply", "Lakeba OS prepares your pitch for Lakeba."], ["4", "Found", "If approved, Lakeba co-founds your company with you."]]
      .map(([n, t, d]) => h("div", { class: "card" }, h("div", { class: "kind" }, `Step ${n}`), h("h3", {}, t), h("p", { class: "secondary small" }, d))))];
  const here = s.here || {};
  if (here.usable) {
    out.push(h("div", { class: "card wiz-box wiz-here" },
      h("h3", {}, here.has_files ? "Set up this folder" : "Start your idea in this folder"),
      h("p", { class: "mono small" }, here.path),
      h("p", { class: "secondary small" }, here.has_files
        ? `It already has files${here.language && here.language !== "general" ? ` (a ${here.language_label} project)` : ""}. The team works on them as they are: nothing is changed or removed, agent-team only adds its own files.`
        : "An empty folder: your project starts here."),
      h("div", { class: "actions" }, h("button", { type: "button", class: "primary", onclick: useHere }, "Use this folder"))));
  }
  if (s.projects && s.projects.length) {
    out.push(h("h3", { class: "wiz-sub" }, here.usable ? "Or open a project you’ve started" : "Or continue one you’ve started"),
      h("div", { class: "wiz-projects" }, s.projects.map(p => h("button", { type: "button", onclick: () => openProject(p.root) },
        h("strong", {}, p.name), h("span", { class: "muted small" }, p.root)))));
  }
  out.push(nav(here.usable ? "Start a new idea elsewhere" : "Start a new idea", () => {
    Object.assign(wizard.form, { folder: "", existing: false }); go(1); }, { noBack: true,
    skip: wizard.fromDashboard ? () => { location.reload(); } : null, skipLabel: "Back to the dashboard" }));
  return out;
}

function useHere() {
  const here = (wizard.status || {}).here || {}, f = wizard.form;
  f.folder = here.path; f.existing = true;
  if (!f.name) f.name = here.name;
  if (!f.vision && here.vision) f.vision = here.vision.replace(/^#\s*Vision\s*\n+/i, "").trim();
  go(1);
}

async function openProject(root) {
  wizard.busy = "Opening…"; renderSetup();
  try { await postJSON("/api/setup/open", { root }); location.hash = "#mvp"; location.reload(); }
  catch (e) { wizard.busy = ""; wizard.error = e.message; renderSetup(); }
}

// ---------- 1. Your idea ----------
function idea() {
  const f = wizard.form;
  return [h("h2", { class: "wiz-title" }, f.existing ? "About this project" : "Your idea"),
    h("p", { class: "secondary" }, f.existing
      ? `The team works in ${f.folder}. Describe what the product is and should become: who it’s for and what it should do next.`
      : "Give it a name and describe it the way you’d explain it to a friend. The team plans everything from this, so say who it’s for and what it should do first."),
    field("Name", input(f, "name", { placeholder: "e.g. Study Buddy", maxlength: 80 })),
    field("Your idea", area(f, "vision", { rows: 9, placeholder:
      "e.g. A web app for university students to plan their study week. They add their exams and how many hours they have, " +
      "and it suggests a weekly plan with breaks. First version: add exams, see the plan, tick sessions off. Later: reminders and sharing with friends." }),
      "A few sentences is enough. You can change it any time (it’s saved as VISION.md)."),
    field("Your name (optional)", input(f, "owner", { placeholder: "Shown on the changes you keep", maxlength: 80 })),
    nav("Next", () => {
      if (!f.name.trim()) return fail("Give your idea a name.");
      if (f.vision.trim().length < 30) return fail("Describe your idea in a few sentences (at least 30 characters) so the team knows what to build.");
      go(2);
    })];
}
function fail(msg) { wizard.error = msg; renderSetup(); }

// ---------- 2. An app you like (optional) ----------
function journeyLines() {
  return wizard.form.inspire.journeys.split("\n").map(l => l.split(";").map(x => x.trim()).filter(Boolean)).filter(j => j.length).slice(0, 3);
}
function inspiration() {
  const i = wizard.form.inspire;
  const ok = h("input", { type: "checkbox", checked: i.ok ? true : null, onchange: e => { i.ok = e.target.checked; } });
  return [h("h2", { class: "wiz-title" }, "Is there an app you like?"),
    h("p", { class: "secondary" }, "Optional. Most products start as “like X, but for Y”. Name X and the team looks at it the way a visitor does: " +
      "its public pages and a few steps you choose, with a screenshot of each. Atlas then writes a brief (what it does, its prices, " +
      "what’s missing, and how yours can be different) and plans your product with it in mind. Nothing is copied, and the members " +
      "who write the code never see it."),
    field("The app’s web address", input(i, "url", { type: "url", placeholder: "https://an-app-you-like.com", maxlength: 2000 })),
    field("What to try there (optional)", area(i, "journeys", { rows: 3, placeholder: 'click link "Pricing"\nclick link "Features"; click button "Watch the demo"' }),
      "One journey per line, up to three, steps separated by ; (click, fill, press, goto, wait)."),
    h("label", { class: "choice wiz-confirm" }, ok, " ", "I use this app, and I may look at its public pages this way: from the outside, " +
      "without signing in, keeping to its robots.txt. The team won’t copy its code, wording, names, logos or designs."),
    nav("Next", () => {
      if (!i.url.trim()) return go(3);
      if (!/^https?:\/\/[^\s/]+\S*$/.test(i.url.trim())) return fail("The app’s address starts with https:// (or leave it empty to skip).");
      if (!i.ok) return fail("Tick the confirmation to explore that app, or skip this step.");
      go(3);
    }, { skip: () => { Object.assign(i, { url: "", journeys: "", ok: false }); go(3); } })];
}

// ---------- 2. Where the AI runs ----------
function models() {
  const f = wizard.form, s = wizard.status || {};
  const found = (s.ollama || []);
  const choice = (value, title, cost, needs) => h("label", { class: `card wiz-choice ${f.models === value ? "on" : ""}` },
    h("input", { type: "radio", name: "models", value, checked: f.models === value ? true : null, onchange: () => { f.models = value; renderSetup(); } }),
    h("div", {}, h("h3", {}, title), h("p", { class: "secondary small" }, cost), h("p", { class: "muted small" }, needs)));
  const out = [h("h2", { class: "wiz-title" }, "Where should the AI run?"),
    h("div", { class: "wiz-choices" },
      choice("ollama", "Free, on this computer", "No per-use cost: models run on your own machine with Ollama (or mlx_lm on a Mac).", "Needs Ollama (or mlx_lm) and a model download (a few GB). Slower on small laptops."),
      choice("claude", "Claude, best quality", "Pay per use with your own Anthropic account; a small first version usually costs a few dollars.", "Needs an Anthropic API key."),
      choice("mixed", "Both (recommended)", "Claude plans and reviews; the builders run free on this computer.", "Needs both: an Anthropic key and Ollama."))];
  if (f.models !== "ollama") out.push(keyBox());
  if (f.models !== "claude") out.push(ollamaBox(found));
  out.push(nav("Next", () => {
    if (f.models !== "ollama" && !s.claude_key) return fail("Add your Anthropic key first, or choose “Free, on this computer”.");
    if (f.models !== "claude" && !f.ollama_url) return fail("No local model server was found. Install Ollama and press “Check again”, or choose Claude.");
    if (f.models !== "claude" && !f.ollama_model) return fail("Say which model the local server runs.");
    go(4);
  }));
  return out;
}

function keyBox() {
  const s = wizard.status || {};
  const box = h("div", { class: "card wiz-box" }, h("h3", {}, "Your Anthropic key"));
  if (s.claude_key && !(wizard.keyResult && !wizard.keyResult.ok)) {
    box.append(status("good", "A key is saved on this computer"), wizard.keyResult ? h("p", { class: "muted small" }, wizard.keyResult.status) : null);
    return box;
  }
  const key = h("input", { type: "password", autocomplete: "off", spellcheck: "false", placeholder: "sk-ant-…" });
  box.append(h("p", { class: "secondary small" }, "Create one at ", h("a", { href: "https://console.anthropic.com/settings/keys", target: "_blank", rel: "noopener noreferrer" }, "console.anthropic.com"),
      ", then paste it here. It’s saved only on this computer, readable only by you, and never shown again."),
    h("div", { class: "row" }, key, h("button", { type: "button", class: "primary", onclick: async () => {
      wizard.busy = "Checking the key with Anthropic…"; renderSetup();
      try { wizard.keyResult = await postJSON("/api/setup/key", { value: key.value }); key.value = "";
        wizard.status.claude_key = true;
        wizard.error = wizard.keyResult.ok ? "" : `The key was saved, but Anthropic said: ${wizard.keyResult.status}`;
      } catch (e) { wizard.error = e.message; }
      wizard.busy = ""; renderSetup();
    } }, "Save and check")));
  return box;
}

function ollamaBox(found) {
  const f = wizard.form, s = wizard.status || {};
  const box = h("div", { class: "card wiz-box" }, h("h3", {}, "Free local models"),
    wizard.scanning ? h("p", { class: "muted small" }, h("span", { class: "spinner", "aria-hidden": "true" }), " Also looking on the other computers on your network…") : null);
  if (!found.length) {
    box.append(status("bad", "No local model server is running on this computer"),
      h("p", { class: "secondary small" }, "Download Ollama from ", h("a", { href: "https://ollama.com/download", target: "_blank", rel: "noopener noreferrer" }, "ollama.com/download"),
        ", install it, open it once, then come back here. (Already running mlx_lm or LM Studio? Start its server, then check again.)"),
      h("div", { class: "actions" }, h("button", { type: "button", onclick: recheck }, "Check again")));
    return box;
  }
  const server = found.find(x => x.url === f.ollama_url) || found[0];
  if (f.ollama_url !== server.url) f.ollama_model = "";
  f.ollama_url = server.url; f.local_kind = server.kind;
  if (found.length > 1) box.append(h("div", { class: "choices" }, found.map(x => {
    const r = h("input", { type: "radio", name: "local-server", checked: x.url === server.url ? true : null });
    r.addEventListener("change", () => { f.ollama_url = x.url; f.local_kind = x.kind; f.ollama_model = ""; renderSetup(); });
    return h("label", { class: "choice" }, r, ` ${x.label} at ${x.url} (${x.models.length} models)`);
  })));
  else box.append(status("good", `Found ${server.label} at ${server.url}`));
  const have = server.models || [];
  const isOllama = server.kind === "ollama";
  const model = f.ollama_model || (isOllama ? pickModel(have, s.recommended_model) : (have.length ? pickModel(have, have[0]) : ""));
  f.ollama_model = model;
  const pulled = have.includes(model) || have.includes(`${model}:latest`);
  const options = isOllama ? [...new Set([...have, s.recommended_model])] : have;
  const sel = h("select", {}, options.filter(m => !/embed|ocr/.test(m)).map(m => h("option", { value: m, selected: m === model ? true : null },
    m + (have.includes(m) ? "" : " (download)") + (isOllama && m === s.recommended_model ? " · recommended" : ""))));
  sel.addEventListener("change", () => { f.ollama_model = sel.value; renderSetup(); });
  if (!isOllama && !have.length) {   // mlx_lm lists only the models it has downloaded
    if (f.ollama_model === undefined || f.ollama_model === "undefined") f.ollama_model = "";
    box.append(field("Model the builders use", input(f, "ollama_model", { placeholder: "e.g. mlx-community/Qwen2.5-Coder-7B-Instruct-4bit" }),
      "The model the server runs (the name you gave mlx_lm.server --model)."));
    return box;
  }
  box.append(field("Model the builders use", sel, pulled ? "Already on this computer." :
    isOllama ? "Not downloaded yet." : "Start the server with a model first (mlx_lm.server --model …)."));
  if (!pulled && isOllama) box.append(pullControl(server.url, model));
  return box;
}

function pullControl(url, model) {
  const key = `${url}|${model}`, p = wizard.pull[key];
  const wrap = h("div", { class: "actions" });
  if (p && p.state === "pulling") {
    const pct = p.total ? Math.round((p.completed / p.total) * 100) : 0;
    const bar = h("div", { class: "bar" }); bar.style.width = `${pct}%`;
    wrap.append(h("div", { class: "wiz-progress" }, h("div", { class: "bar-track" }, bar), h("span", { class: "muted small" }, `${p.status} ${p.total ? pct + "%" : ""}`)));
  } else if (p && p.state === "done") {
    wrap.append(status("good", "Downloaded"));
  } else {
    if (p && p.state === "failed") wrap.append(status("bad", p.error || "download failed"));
    wrap.append(h("button", { type: "button", class: "primary", onclick: () => startPull(url, model) }, `Download ${model}`));
  }
  return wrap;
}

async function startPull(url, model) {
  const key = `${url}|${model}`;
  try { wizard.pull[key] = await postJSON("/api/setup/pull", { url, model }); } catch (e) { return fail(e.message); }
  const poll = async () => {
    try { wizard.pull[key] = await getJSON(`/api/setup/pull?url=${encodeURIComponent(url)}&model=${encodeURIComponent(model)}`); } catch (_) {}
    if (wizard.pull[key].state === "pulling") setTimeout(poll, 1500);
    else if (wizard.pull[key].state === "done") await recheck();
    renderSetup();
  };
  poll();
}

async function recheck() {
  wizard.busy = "Looking for Ollama…"; renderSetup();
  try { wizard.status = await getJSON("/api/setup/status"); } catch (e) { wizard.error = e.message; }
  const found = wizard.status.ollama || [];
  if (found.length && !wizard.form.ollama_url) { wizard.form.ollama_url = found[0].url; wizard.form.local_kind = found[0].kind; }
  wizard.busy = ""; renderSetup();
}

// ---------- 3. Your team ----------
function team() {
  const f = wizard.form, s = wizard.status || {};
  const onClaude = role => f.models === "claude" || (f.models === "mixed" && role !== "builder");
  const where = role => onClaude(role) ? "Claude" : `${f.ollama_model || "a local model"}, on this computer`;
  const people = [["Atlas", "lead", "Plans the work and reviews every change."],
    ...Array.from({ length: f.builders }, (_, i) => [["Forge", "Anvil", "Kiln", "Smith"][i], "builder", "Writes the code."]),
    ["Spark", "marketing", "Writes your positioning brief, website and pitch deck."],
    ["Harbor", "devops", "Merges and releases on GitHub, with your approval."]];
  const extras = s.extras || {};
  const sw = role => { const el = h("input", { type: "checkbox", checked: f.extras.includes(role) ? true : null });
    el.addEventListener("change", () => { f.extras = el.checked ? [...f.extras, role] : f.extras.filter(r => r !== role); renderSetup(); }); return el; };
  const limit = h("input", { type: "range", min: 0, max: 50, step: 1, value: f.per_day });
  const limitLabel = h("strong", {}, f.per_day ? `$${f.per_day} a day` : "no daily limit");
  limit.addEventListener("input", () => { f.per_day = Number(limit.value); limitLabel.textContent = f.per_day ? `$${f.per_day} a day` : "no daily limit"; });
  const builders = h("select", {}, [1, 2, 3, 4].slice(0, s.max_builders || 4).map(n => h("option", { value: n, selected: n === f.builders ? true : null }, n === 1 ? "1 builder" : `${n} builders`)));
  builders.addEventListener("change", () => { f.builders = Number(builders.value); renderSetup(); });
  return [h("h2", { class: "wiz-title" }, "Meet your team"),
    h("p", { class: "secondary" }, "Each member has one job. You can change the team later under Team."),
    h("div", { class: "grid cards" }, people.map(([n, role, job]) => h("div", { class: "card member" },
      h("h3", {}, n, h("span", { class: "muted" }, ` · ${role}`)), h("p", { class: "secondary small" }, job), h("p", { class: "muted small" }, where(role))))),
    h("h3", { class: "wiz-sub" }, "Extra help (optional)"),
    h("div", { class: "choices" }, Object.entries(extras).map(([role, x]) => h("label", { class: "choice" }, sw(role), ` ${x.name} (${role}): ${x.about}`))),
    h("div", { class: "form-grid" }, field("Builders", builders, "More builders work on parts of a task at the same time."),
      f.models === "ollama" ? null : field("Spend limit", h("div", {}, limit, " ", limitLabel), "The team stops before it spends more than this in a day. Local models are free.")),
    nav(wizard.form.existing ? "Set up my project" : "Create my project", createProject)];
}

async function createProject() {
  const f = wizard.form;
  wizard.busy = "Setting up your project: folder, team, rules and a first save…"; wizard.error = ""; renderSetup();
  try {
    const inspire = f.inspire.url.trim() ? { url: f.inspire.url.trim(), confirmed: f.inspire.ok } : null;
    const made = await postJSON("/api/setup/project", { ...f, inspire, per_day: f.models === "ollama" ? 0 : f.per_day });
    wizard.project = made.root;
    wizard.busy = ""; go(5);
  } catch (e) { wizard.busy = ""; fail(e.message); }
}

// ---------- 4. GitHub ----------
function github() {
  const out = [h("h2", { class: "wiz-title" }, "Keep your code safe online (optional)"),
    h("p", { class: "secondary" }, `Your project is ready in ${wizard.project}. GitHub keeps a copy of it online and lets the team work with pull requests. You can skip this and connect later.`)];
  const g = (wizard.status || {}).github || {};
  const box = h("div", { class: "card wiz-box" });
  if (wizard.repo) box.append(status("good", `Your code is on GitHub: ${wizard.repo}`));
  else if (!g.installed) box.append(status("warn", "The GitHub app for this computer isn’t installed"),
    h("p", { class: "secondary small" }, "Install it from ", h("a", { href: "https://cli.github.com", target: "_blank", rel: "noopener noreferrer" }, "cli.github.com"), ", then press Check again."),
    h("div", { class: "actions" }, h("button", { type: "button", onclick: refreshGithub }, "Check again")));
  else if (!g.signed_in) {
    const l = wizard.login;
    if (l && l.code) box.append(h("p", {}, "Your one-time code:"), h("p", { class: "wiz-code mono" }, l.code),
      h("div", { class: "actions" }, h("a", { class: "button primary", href: l.url, target: "_blank", rel: "noopener noreferrer" }, "Open GitHub and enter the code")),
      h("p", { class: "muted small" }, "This page notices when you’ve signed in."));
    else box.append(h("p", { class: "secondary small" }, "You’ll sign in on GitHub’s own page; this computer never sees your password."),
      h("div", { class: "actions" }, h("button", { type: "button", class: "primary", onclick: githubLogin }, "Sign in to GitHub")));
  } else box.append(status("good", `Signed in to GitHub as ${g.user}`),
    h("p", { class: "secondary small" }, "Create a private repository for this project and upload the code."),
    h("div", { class: "actions" }, h("button", { type: "button", class: "primary", onclick: makeRepo }, "Create my private repository")));
  out.push(box, nav("Next", () => go(6), { skip: () => go(6) }));
  return out;
}
async function refreshGithub() { try { wizard.status.github = await getJSON("/api/setup/github"); } catch (e) { wizard.error = e.message; } renderSetup(); }
async function githubLogin() {
  try { wizard.login = await postJSON("/api/setup/github/login", {}); } catch (e) { return fail(e.message); }
  const poll = async () => {
    try { const g = await getJSON("/api/setup/github"); wizard.login = g.login; wizard.status.github = g;
      if (g.signed_in) { renderSetup(); return; }
      if (g.login.state === "failed") { fail("GitHub sign-in didn’t finish. " + (g.login.output || "").slice(-200)); return; }
    } catch (_) {}
    renderSetup(); setTimeout(poll, 2500);
  };
  poll();
}
async function makeRepo() {
  wizard.busy = "Creating the repository and uploading your code…"; renderSetup();
  try { wizard.repo = (await postJSON("/api/setup/github/repo", { private: true })).repo; } catch (e) { wizard.error = e.message; }
  wizard.busy = ""; renderSetup();
}

// ---------- 5. Ready check ----------
function readyCheck() {
  if (!wizard.ready && !wizard.busy) { loadReady(); return [h("h2", { class: "wiz-title" }, "Checking everything is ready")]; }
  const checks = (wizard.ready || []);
  const missing = checks.filter(c => !c.ok && !c.optional);
  const out = [h("h2", { class: "wiz-title" }, missing.length ? "Almost there" : "Everything’s ready"),
    h("ul", { class: "wiz-checks" }, checks.map(c => h("li", {},
      c.ok ? status("good", c.name) : c.optional ? status("warn", c.name) : status("bad", c.name),
      h("span", { class: "muted small" }, ` ${c.detail}`),
      !c.ok ? fixFor(c) : null)))];
  out.push(nav(missing.length ? "Continue anyway" : "Next", () => go(7),
    { skip: () => { wizard.ready = null; renderSetup(); }, skipLabel: "Check again" }));
  return out;
}
async function installRea() {
  wizard.busy = "Installing REA (a minute or two)…"; wizard.error = ""; renderSetup();
  try { await postJSON("/api/setup/rea", {}); } catch (e) { wizard.error = e.message; }
  wizard.busy = ""; wizard.ready = null; renderSetup();
}
async function loadReady() {
  wizard.busy = "Checking git, GitHub, keys and models…"; renderSetup();
  try { wizard.ready = (await getJSON("/api/setup/ready")).checks; } catch (e) { wizard.error = e.message; wizard.ready = []; }
  wizard.busy = ""; renderSetup();
}
function fixFor(c) {
  const a = c.action || "";
  if (a === "key") return h("div", { class: "wiz-fix" }, keyBox());
  if (a.startsWith("pull:")) return h("div", { class: "wiz-fix" }, pullControl(wizard.form.ollama_url || "http://localhost:11434", a.slice(5)));
  if (a === "github") return h("button", { type: "button", onclick: () => go(5) }, "Connect GitHub");
  if (a === "rea") return h("button", { type: "button", onclick: installRea }, "Install REA");
  if (a === "identity") {
    const who = { name: wizard.form.owner || "", email: "" };
    return h("div", { class: "wiz-fix row" }, input(who, "name", { placeholder: "Your name" }), input(who, "email", { placeholder: "Email (optional)" }),
      h("button", { type: "button", onclick: async () => { try { await postJSON("/api/setup/identity", who); wizard.ready = null; renderSetup(); } catch (e) { fail(e.message); } } }, "Save"));
  }
  return c.fix ? h("p", { class: "muted small" }, `To fix: ${c.fix}`) : null;
}

// ---------- 6. First version ----------
function exploreBox() {
  const i = wizard.form.inspire, x = wizard.explore;
  if (!i.url.trim()) return null;
  const box = h("div", { class: "card wiz-box" }, h("h3", {}, "The app you like"), h("p", { class: "mono small" }, i.url.trim()));
  const reaMissing = (wizard.ready || []).some(c => c.action === "rea");
  if (!x) {
    if (reaMissing) box.append(h("p", { class: "secondary small" }, "Exploring it needs REA, which looks at web pages like a visitor."),
      h("div", { class: "actions" }, h("button", { type: "button", onclick: installRea }, "Install REA")));
    else box.append(h("p", { class: "secondary small" }, "First the team explores it, then Atlas suggests your first tasks with the brief in mind. A few minutes."),
      h("div", { class: "actions" }, h("button", { type: "button", class: "primary", onclick: startExplore }, "Explore it now"),
        h("button", { type: "button", onclick: () => { wizard.explore = { status: "skipped" }; renderSetup(); } }, "Skip")));
  } else if (x.status === "running") {
    box.append(h("p", { class: "wiz-busy", role: "status" }, h("span", { class: "spinner", "aria-hidden": "true" }), x.story || "Exploring…"));
  } else if (x.status === "succeeded") {
    box.append(h("p", {}, status("good", "brief written"), " ", h("span", { class: "muted small" }, "Read it any time in the Inspiration tab.")));
    box.append(inspiredBox());
  } else if (x.status !== "skipped") {
    box.append(h("p", {}, status("bad", `didn’t finish (${x.status})`), " ", h("span", { class: "muted small" }, x.tail || "")),
      h("div", { class: "actions" }, h("button", { type: "button", onclick: startExplore }, "Try again")));
  }
  return box;
}
async function startExplore() {
  const i = wizard.form.inspire;
  wizard.error = "";
  try {
    const job = await postJSON("/api/jobs/start", { workflow: "inspire", params: { url: i.url.trim(), journeys: journeyLines(), max_pages: 12 } });
    wizard.explore = { id: job.id, status: "running", story: "Exploring…" };
    renderSetup();
    followExplore();
  } catch (e) { fail(e.message); }
}
async function followExplore() {
  const x = wizard.explore;
  while (x && x.status === "running") {
    await new Promise(r => setTimeout(r, 3000));
    try {
      const out = await getJSON(`/api/jobs/${encodeURIComponent(x.id)}?offset=0`);
      x.status = out.status;
      const last = out.text.trim().split("\n").filter(l => l.includes("inspire:")).pop();
      x.story = last ? last.replace(/^.*inspire:\s*/, "").replace(/^looking at /, "Looking at ") : x.story;
      if (out.status !== "running") x.tail = out.text.trim().split("\n").slice(-2).join(" ").slice(-300);
    } catch (e) { x.status = "lost"; x.tail = e.message; }
    if (wizard.step === 7) renderSetup();
  }
}
function inspiredBox() {
  const v = wizard.vision || (wizard.vision = { text: null, done: false });
  if (v.done) return h("p", { class: "muted small" }, "Added to your vision (VISION.md).");
  if (v.text === null) return h("div", { class: "actions" },
    h("button", { type: "button", disabled: wizard.busy ? true : null, onclick: async () => {
      wizard.busy = "Atlas is writing how yours will be different…"; renderSetup();
      try { v.text = (await postJSON("/api/setup/inspired", {})).text; } catch (e) { wizard.error = e.message; }
      wizard.busy = ""; renderSetup();
    } }, "Draft “Inspired by, and different from” for my vision"));
  return h("div", {}, field("Inspired by, and different from (edit as you like)", area(v, "text", { rows: 7 })),
    h("div", { class: "actions" }, h("button", { type: "button", class: "primary", onclick: async () => {
      try { await postJSON("/api/setup/vision", { text: v.text }); v.done = true; } catch (e) { wizard.error = e.message; }
      renderSetup();
    } }, "Add to my vision"), h("button", { type: "button", onclick: () => { v.done = true; v.text = ""; renderSetup(); } }, "Not now")));
}

function firstVersion() {
  const out = [h("h2", { class: "wiz-title" }, "What should the first version do?")];
  const ex = exploreBox();
  if (ex) out.push(ex);
  if (ex && wizard.explore?.status === "running") return out;   // the tasks wait for the brief
  if (wizard.tasks === null && !wizard.busy) {
    out.push(h("p", { class: "secondary" }, "Atlas, your lead, can read your idea and suggest the first tasks. It takes a minute (longer on a local model)."),
      h("div", { class: "actions" }, h("button", { type: "button", class: "primary", onclick: suggest }, "Suggest the first tasks"),
        h("button", { type: "button", onclick: () => { wizard.tasks = []; renderSetup(); } }, "I’ll write my own")));
    return out;
  }
  const tasks = wizard.tasks || [];
  if (tasks.length) out.push(h("p", { class: "secondary" }, "Tick what to build, in order. The team builds one at a time; the rest wait in My MVP."),
    h("div", { class: "choices wiz-tasks" }, tasks.map(t => { const el = h("input", { type: "checkbox", checked: wizard.chosen.includes(t) ? true : null });
      el.addEventListener("change", () => { wizard.chosen = el.checked ? [...wizard.chosen, t] : wizard.chosen.filter(x => x !== t); });
      return h("label", { class: "choice" }, el, " ", t); })));
  out.push(field(tasks.length ? "Or your own" : "What should the team build first?", area(wizard, "own", { rows: 3, placeholder: "e.g. A page where students add their exams and see them in a list" })),
    nav("Build it", buildFirst));
  return out;
}
async function suggest() {
  wizard.busy = "Atlas is reading your idea…"; renderSetup();
  try { wizard.tasks = (await postJSON("/api/setup/tasks", {})).tasks; wizard.chosen = wizard.tasks.slice(0, 1); }
  catch (e) { wizard.tasks = []; wizard.error = e.message; }
  wizard.busy = ""; renderSetup();
}
async function buildFirst() {
  const queue = [...wizard.chosen, ...(wizard.own.trim() ? [wizard.own.trim()] : [])];
  if (!queue.length) return fail("Tick a task or write one.");
  wizard.busy = "Starting the team…"; renderSetup();
  try {
    await postJSON("/api/jobs/start", { workflow: "build", params: { task: queue[0], rounds: 3 } });
    saveNextTasks(wizard.project, queue.slice(1));
    location.hash = "#mvp"; location.reload();
  } catch (e) { wizard.busy = ""; fail(e.message); }
}

function nextTasksKey(root) { return `lakeba-next-tasks:${root}`; }
function saveNextTasks(root, tasks) { try { localStorage.setItem(nextTasksKey(root), JSON.stringify(tasks)); } catch (_) {} }
function loadNextTasks(root) { try { return JSON.parse(localStorage.getItem(nextTasksKey(root)) || "[]"); } catch (_) { return []; } }
