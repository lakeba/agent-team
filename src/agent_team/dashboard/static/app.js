"use strict";
// agent-team dashboard. Everything from the API is inserted as text (never HTML): run logs hold
// agent output and text from outside the team.

const state = { team: null, health: null, runs: null, usage: null, github: null, filter: "all" };

// ---------- small DOM helpers ----------
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}
const fmtInt = n => Number(n || 0).toLocaleString();
const fmtUsd = n => (n || 0) < 0.01 && n > 0 ? "< $0.01" : "$" + Number(n || 0).toFixed(2);
function fmtTokens(n) {
  n = Number(n || 0);
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "k";
  return String(n);
}
function fmtWhen(iso) {
  if (!iso) return "time not recorded";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
function status(kind, label) {     // a colour never carries meaning alone: icon + label
  const icon = { good: "✓", bad: "✕", warn: "!", pending: "…" }[kind] || "";
  return h("span", { class: `badge status-${kind}` }, h("span", { class: "dot", "aria-hidden": "true" }), `${icon} ${label}`);
}
function markerBadge(m) {
  if (!m) return null;
  const kind = { APPROVED: "good", YES: "good", AGREE: "good", OK: "good", CHANGES: "warn", CONTINUE: "warn", NO: "bad", ISSUES: "bad" }[m] || "pending";
  return status(kind, m.toLowerCase());
}

// ---------- tooltip (hover layer for the charts) ----------
const tip = document.getElementById("tooltip");
function attachTip(el, text) {
  el.addEventListener("mousemove", e => {
    tip.textContent = text; tip.hidden = false;
    tip.style.left = Math.min(e.clientX + 14, window.innerWidth - 280) + "px";
    tip.style.top = (e.clientY + 14) + "px";
  });
  el.addEventListener("mouseleave", () => { tip.hidden = true; });
  el.setAttribute("aria-label", text);
}

// ---------- data ----------
async function getJSON(path) {
  const r = await fetch(path, { cache: "no-store" });
  const data = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));
  if (!r.ok || data.error) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}
async function load() {
  document.getElementById("refreshed").textContent = "Loading…";
  const results = await Promise.allSettled([getJSON("/api/team"), getJSON("/api/runs"), getJSON("/api/usage")]);
  [state.team, state.runs, state.usage] = results.map(r => r.status === "fulfilled" ? r.value : { error: r.reason.message });
  render();
  // Slow sources fill in when they arrive.
  getJSON("/api/health").then(v => { state.health = v; render(); }).catch(e => { state.health = { error: e.message }; render(); });
  getJSON("/api/github").then(v => { state.github = v; render(); }).catch(e => { state.github = { available: false, reason: e.message }; render(); });
  document.getElementById("refreshed").textContent = "Updated " + new Date().toLocaleTimeString();
}

// ---------- views ----------
function errorCard(what, err) { return h("div", { class: "card notice bad" }, `Couldn't load ${what}: ${err}`); }

function renderHeader() {
  const t = state.team;
  if (!t || t.error) return;
  document.getElementById("project-name").textContent = t.project.name;
  document.title = `${t.project.name} · agent-team`;
  const link = document.getElementById("repo-link");
  if (t.project.repo) { link.textContent = t.project.repo; link.href = `https://github.com/${t.project.repo}`; }
  else { link.textContent = "no GitHub repo configured"; link.removeAttribute("href"); }
  document.getElementById("version").textContent = `agent-team ${t.version}`;
}

function healthSummary() {
  if (!state.health) return status("pending", "checking…");
  if (state.health.error) return status("bad", "check failed");
  const all = Object.values(state.health.members);
  const bad = all.filter(m => !m.ok).length;
  return bad ? status("bad", `${bad} of ${all.length} unreachable`) : status("good", `all ${all.length} reachable`);
}

function renderOverview() {
  const el = document.getElementById("overview");
  el.replaceChildren();
  const t = state.team;
  if (!t || t.error) return el.append(errorCard("the team", t && t.error));
  const runs = (state.runs && state.runs.runs) || [];
  const total = (state.usage && state.usage.total) || {};
  const remote = t.members.filter(m => m.remote).length;
  const gh = state.github;

  el.append(h("div", { class: "grid tiles" },
    h("div", { class: "card tile" }, h("div", { class: "label" }, "Team members"),
      h("div", { class: "value" }, t.members.length), h("div", { class: "note" }, remote ? `${remote} on other machines` : "all on this machine")),
    h("div", { class: "card tile" }, h("div", { class: "label" }, "Reachability"), h("div", { class: "value small-value" }, healthSummary())),
    h("div", { class: "card tile" }, h("div", { class: "label" }, "Runs logged"),
      h("div", { class: "value" }, runs.length), h("div", { class: "note" }, runs[0] ? `latest: ${runs[0].workflow}` : "none yet")),
    h("div", { class: "card tile" }, h("div", { class: "label" }, "Estimated spend"),
      h("div", { class: "value" }, fmtUsd(total.cost)), h("div", { class: "note" }, `${fmtInt(total.calls)} model calls recorded`)),
    h("div", { class: "card tile" }, h("div", { class: "label" }, "GitHub"),
      gh && gh.available
        ? [h("div", { class: "value" }, `${gh.open_prs.length} PRs`),
           h("div", { class: "note" }, `${gh.open_issues.length} open issues · ${gh.releases[0] ? "latest " + gh.releases[0].tagName : "no releases"}`)]
        : h("div", { class: "note" }, gh ? gh.reason : "loading…")),
  ));

  if (Object.keys(t.missing_roles).length) {
    el.append(h("div", { class: "card notice" }, h("h3", {}, "Roles missing from the team"),
      h("p", { class: "secondary" }, "Some workflows need a member with these roles:"),
      h("ul", {}, Object.entries(t.missing_roles).map(([r, why]) => h("li", {}, h("strong", {}, r), ` (needed by ${why})`)))));
  }

  const recent = h("div", { class: "card" }, h("h2", {}, "Recent runs"));
  if (!runs.length) recent.append(h("p", { class: "empty" }, "No runs logged yet. Logs appear in .team/logs/ after the first workflow."));
  else recent.append(table(["Workflow", "Run", "Started", "Outcome"],
    runs.slice(0, 6).map(r => [r.workflow, r.title, fmtWhen(r.started), r.outcome || "—"])));

  const ghCard = h("div", { class: "card" }, h("h2", {}, "GitHub"));
  if (!gh) ghCard.append(h("p", { class: "muted" }, "Loading…"));
  else if (!gh.available) ghCard.append(h("p", { class: "muted" }, gh.reason));
  else {
    ghCard.append(h("p", { class: "secondary" }, `main ${gh.main.sha} · CI ${gh.main.ci}`));
    ghCard.append(h("h3", {}, "Open pull requests"),
      gh.open_prs.length ? h("ul", {}, gh.open_prs.map(p => h("li", {}, h("a", { href: p.url, target: "_blank", rel: "noopener noreferrer" }, `#${p.number}`), ` ${p.title}`)))
                         : h("p", { class: "muted" }, "None"));
    ghCard.append(h("h3", {}, "Recently merged"),
      gh.recently_merged.length ? h("ul", {}, gh.recently_merged.slice(0, 5).map(p => h("li", {}, h("a", { href: p.url, target: "_blank", rel: "noopener noreferrer" }, `#${p.number}`), ` ${p.title}`)))
                                : h("p", { class: "muted" }, "None"));
  }
  el.append(h("div", { class: "grid two" }, recent, ghCard));
}

function renderTeam() {
  const el = document.getElementById("team");
  el.replaceChildren();
  const t = state.team;
  if (!t || t.error) return el.append(errorCard("the team", t && t.error));
  if (typeof edit !== "undefined" && edit.on) return renderEditor(el);
  const health = state.health && state.health.members;
  el.append(h("div", { class: "filters" }, h("span", { class: "secondary" }, `${t.members.length} members`), healthSummary(),
    state.health && state.health.checked_at ? h("span", { class: "muted small" }, `checked ${fmtWhen(state.health.checked_at)}`) : null,
    h("span", { class: "spacer" }),
    h("button", { type: "button", class: "primary", onclick: () => startEditing().catch(e => alert(e.message)) }, "Edit team")));
  el.append(h("div", { class: "grid cards" }, t.members.map(m => {
    const hm = health && health[m.name];
    const where = m.kind === "agent-http" ? `remote node ${m.url}` : m.url ? `${m.kind} at ${m.url}` : m.kind;
    return h("article", { class: "card member" },
      h("h3", {}, h("span", {}, m.name, h("span", { class: "muted" }, ` · ${m.role}`)),
        hm ? status(hm.ok ? "good" : "bad", hm.ok ? "reachable" : "unreachable") : status("pending", "checking")),
      m.description ? h("p", { class: "secondary small" }, m.description) : null,
      h("dl", {},
        h("dt", {}, "Model"), h("dd", { class: "mono" }, m.model || "chosen by the node"),
        h("dt", {}, "Runs on"), h("dd", {}, where),
        h("dt", {}, "Effort"), h("dd", {}, m.effort),
        h("dt", {}, "Owns"), h("dd", {}, m.owns.length ? h("span", { class: "chips" }, m.owns.map(o => h("span", { class: "chip" }, o))) : h("span", { class: "muted" }, "nothing")),
        m.key_env ? [h("dt", {}, "Key"), h("dd", {}, h("span", { class: "mono" }, m.key_env), " ", m.key_set ? status("good", "set") : status("bad", "not set"))] : null,
        m.custom_prompt ? [h("dt", {}, "Prompt"), h("dd", {}, "custom")] : null),
      hm && !hm.ok ? h("p", { class: "health-line" }, hm.status) : null);
  })));
  const g = t.project.guarantees;
  el.append(h("div", { class: "card" }, h("h2", {}, "Project guarantees"),
    g.length ? h("ul", {}, g.map(x => h("li", {}, x))) : h("p", { class: "muted" }, "None set. The lead enforces these in every review; add them under [project] in .team.toml."),
    h("p", { class: "muted small" }, `Tests: ${t.project.test_command || "no test command set"}`)));
}

function renderRuns() {
  const el = document.getElementById("runs");
  el.replaceChildren();
  if (!state.runs || state.runs.error) return el.append(errorCard("runs", state.runs && state.runs.error));
  const runs = state.runs.runs;
  const workflows = ["all", ...new Set(runs.map(r => r.workflow))];
  el.append(h("div", { class: "filters", role: "group", "aria-label": "Filter by workflow" },
    workflows.map(w => h("button", { type: "button", "aria-pressed": String(state.filter === w),
      onclick: () => { state.filter = w; renderRuns(); } }, w === "all" ? `All (${runs.length})` : `${w} (${runs.filter(r => r.workflow === w).length})`))));
  const shown = runs.filter(r => state.filter === "all" || r.workflow === state.filter);
  if (!shown.length) return el.append(h("div", { class: "card empty" }, "No runs logged yet."));
  el.append(h("div", { class: "runs" }, shown.map(r => h("details", { class: "card run" },
    h("summary", {},
      h("span", { class: "wf" }, r.workflow),
      h("span", { class: "title", title: r.title }, r.title),
      h("span", { class: "meta" }, `${fmtWhen(r.started)} · ${r.outcome || "—"} · ${r.entries.length} steps`)),
    h("div", { class: "entries" }, r.entries.map(e => {
      const pre = h("pre", {}, e.text || "(empty)");
      const more = (e.text || "").split("\n").length > 6 || (e.text || "").length > 600
        ? h("button", { type: "button", class: "more", onclick: ev => { pre.classList.toggle("open"); ev.target.textContent = pre.classList.contains("open") ? "Show less" : "Show more"; } }, "Show more")
        : null;
      return h("div", { class: "entry" },
        h("header", {}, h("span", { class: "who" }, e.who), e.what ? h("span", { class: "secondary" }, e.what) : null,
          markerBadge(e.marker), e.at ? h("span", { class: "muted small" }, fmtWhen(e.at)) : null),
        e.files.length ? h("div", { class: "chips" }, e.files.map(f => h("span", { class: "chip" }, f))) : null,
        e.actions.length ? h("div", {}, e.actions.map(a => status("good", a))) : null,
        pre, more);
    }))))));
}

function barList(rows, valueOf, labelOf) {   // single series: one hue, value labelled, no legend
  const max = Math.max(...rows.map(valueOf), 0) || 1;
  return h("div", { class: "bars" }, rows.map(r => {
    const bar = h("div", { class: "bar" });
    bar.style.width = `${(valueOf(r) / max) * 100}%`;   // CSSOM, allowed by the CSP
    attachTip(bar, labelOf(r));
    return h("div", { class: "bar-row" }, h("span", {}, r.name), h("div", { class: "bar-track" }, bar), h("span", { class: "v" }, fmtUsd(valueOf(r))));
  }));
}

function renderCosts() {
  const el = document.getElementById("costs");
  el.replaceChildren();
  const u = state.usage;
  if (!u || u.error) return el.append(errorCard("usage", u && u.error));
  const t = u.total;
  el.append(h("div", { class: "grid tiles" },
    h("div", { class: "card tile" }, h("div", { class: "label" }, "Estimated spend"), h("div", { class: "value" }, fmtUsd(t.cost))),
    h("div", { class: "card tile" }, h("div", { class: "label" }, "Input tokens"), h("div", { class: "value" }, fmtTokens(t.input + t.cache_read + t.cache_write)),
      h("div", { class: "note" }, `${fmtTokens(t.cache_read)} read from cache`)),
    h("div", { class: "card tile" }, h("div", { class: "label" }, "Output tokens"), h("div", { class: "value" }, fmtTokens(t.output))),
    h("div", { class: "card tile" }, h("div", { class: "label" }, "Model calls"), h("div", { class: "value" }, fmtInt(t.calls)))));
  if (!u.recorded_calls) {
    el.append(h("div", { class: "card empty" }, "No usage recorded yet. Usage is recorded for runs made with this version onwards; earlier runs have none."));
    return;
  }
  const members = Object.entries(u.by_agent).map(([name, v]) => ({ name, ...v })).sort((a, b) => b.cost - a.cost);
  const days = Object.entries(u.by_day).map(([day, v]) => ({ day, ...v }));
  const maxDay = Math.max(...days.map(d => d.cost), 0) || 1;
  const columns = h("div", { class: "columns" }, days.map(d => {
    const col = h("div", { class: "column" });
    col.style.height = `${(d.cost / maxDay) * 100}%`;
    attachTip(col, `${d.day}: ${fmtUsd(d.cost)} · ${fmtTokens(d.input)} in / ${fmtTokens(d.output)} out`);
    return col;
  }));
  el.append(h("div", { class: "grid two" },
    h("div", { class: "card" }, h("h2", {}, "Spend by member"),
      barList(members, r => r.cost, r => `${r.name}: ${fmtUsd(r.cost)} · ${fmtInt(r.calls)} calls · ${fmtTokens(r.input + r.cache_read)} in / ${fmtTokens(r.output)} out`)),
    h("div", { class: "card" }, h("h2", {}, "Spend by day"), columns,
      h("div", { class: "column-labels" }, h("span", {}, days[0] ? days[0].day : ""), h("span", {}, days.length > 1 ? days[days.length - 1].day : "")))));
  el.append(h("div", { class: "card" }, h("h2", {}, "By model"),
    table(["Model", "Calls", "Input", "Cache read", "Output", "Est. cost"],
      Object.entries(u.by_model).sort((a, b) => b[1].cost - a[1].cost)
        .map(([m, v]) => [m, fmtInt(v.calls), fmtTokens(v.input), fmtTokens(v.cache_read), fmtTokens(v.output), fmtUsd(v.cost)]), [1, 2, 3, 4, 5])));
  el.append(h("div", { class: "card" }, h("h2", {}, "By run"),
    table(["Run", "Calls", "Output", "Est. cost"],
      Object.entries(u.by_run).sort((a, b) => b[1].cost - a[1].cost).slice(0, 25)
        .map(([r, v]) => [r.replace("@", " · "), fmtInt(v.calls), fmtTokens(v.output), fmtUsd(v.cost)]), [1, 2, 3])));
  el.append(h("p", { class: "muted small" },
    "Costs are estimates from list prices (US dollars per million tokens); local and self-hosted models count as free. Override prices with [pricing.\"model\"] in .team.toml.",
    u.unpriced_models.length ? ` No price known for: ${u.unpriced_models.join(", ")}.` : ""));
}

function table(headers, rows, numericCols = []) {
  return h("table", {},
    h("thead", {}, h("tr", {}, headers.map((x, i) => h("th", { class: numericCols.includes(i) ? "num" : null }, x)))),
    h("tbody", {}, rows.map(r => h("tr", {}, r.map((c, i) => h("td", { class: numericCols.includes(i) ? "num" : null }, c))))));
}

function render() { renderHeader(); renderOverview(); renderTeam(); renderRuns(); renderCosts(); }

// ---------- tabs ----------
document.querySelectorAll("[role=tab]").forEach(tab => tab.addEventListener("click", () => {
  document.querySelectorAll("[role=tab]").forEach(t => t.setAttribute("aria-selected", String(t === tab)));
  document.querySelectorAll("[role=tabpanel]").forEach(p => { p.hidden = p.id !== tab.dataset.tab; });
  try { localStorage.setItem("agent-team-tab", tab.dataset.tab); } catch (_) {}
}));
try {
  const saved = localStorage.getItem("agent-team-tab");
  if (saved) document.querySelector(`[role=tab][data-tab="${saved}"]`)?.click();
} catch (_) {}
document.getElementById("refresh").addEventListener("click", () => {
  if (typeof edit !== "undefined" && edit.on && !confirm("Refreshing discards your unsaved edits. Continue?")) return;
  if (typeof edit !== "undefined") { edit.on = false; edit.draft = null; }
  load();
});
load();
