"use strict";
// Inspiration: apps the founder likes, explored from the outside, and the scout's brief for each.
// Exploring starts a background run (agent-team inspire), after the owner confirms, here, that they
// use the app and may look at it this way. Captures stay on this machine; builders never see them.

const inspireView = { data: null, error: "", selected: null, app: null, busy: false, form: { url: "", journeys: "", pages: 12, ok: false } };

async function loadInspire() {
  try {
    inspireView.data = await getJSON("/api/inspiration");
    inspireView.error = "";
    const apps = inspireView.data.apps;
    if (!inspireView.selected && apps.length) inspireView.selected = apps[0].app;
    if (inspireView.selected) inspireView.app = await getJSON(`/api/inspiration/${encodeURIComponent(inspireView.selected)}`);
  } catch (e) { inspireView.error = e.message; }
  renderInspire();
}

// The brief is the model's Markdown: drawn as text nodes only (headings, lists, tables, bold), never as HTML.
function inline(text) {
  const out = [];
  text.split(/(\*\*[^*]+\*\*)/).forEach(part => {
    if (/^\*\*[^*]+\*\*$/.test(part)) out.push(h("strong", {}, part.slice(2, -2)));
    else if (part) out.push(part);
  });
  return out;
}

function markdownNodes(md) {
  const nodes = [];
  const lines = md.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;
    const head = /^(#{1,4})\s+(.*)$/.exec(line);
    if (head) { nodes.push(h(head[1].length <= 2 ? "h3" : "h4", {}, ...inline(head[2]))); continue; }
    if (/^\s*\|/.test(line)) {   // a table: header, separator, rows
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(lines[i++]);
      i--;
      const cells = r => r.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
      const body = rows.filter((_, n) => n !== 1 || !/^[\s|:-]+$/.test(rows[1]));
      nodes.push(table(cells(body[0]), body.slice(1).map(r => cells(r).map(c => h("span", {}, ...inline(c))))));
      continue;
    }
    const item = /^\s*(?:[-*]|\d+[.)])\s+(.*)$/.exec(line);
    if (item) {
      const ordered = /^\s*\d/.test(line);
      const list = h(ordered ? "ol" : "ul", {});
      while (i < lines.length && /^\s*(?:[-*]|\d+[.)])\s+/.test(lines[i])) {
        list.append(h("li", {}, ...inline(lines[i].replace(/^\s*(?:[-*]|\d+[.)])\s+/, ""))));
        i++;
      }
      i--;
      nodes.push(list);
      continue;
    }
    nodes.push(h("p", {}, ...inline(line)));
  }
  return nodes;
}

function shotLink(app, item, label) {
  if (!item.shot) return null;
  const src = `/api/inspiration/${encodeURIComponent(app)}/shot/${item.shot}`;
  return h("a", { href: src, target: "_blank", rel: "noopener", title: "Open the full screenshot" },
    h("img", { class: "shot", alt: `${label}: screenshot`, src, loading: "lazy" }));
}

async function explore(url, journeys, pages, needsConfirm) {
  inspireView.busy = true; renderInspire();
  try {
    if (needsConfirm) await postJSON("/api/inspiration/confirm", { url });
    await postJSON("/api/jobs/start", { workflow: "inspire", params: { url, journeys, max_pages: pages } });
    toast("Exploring the app. Follow it in Runs; the brief appears here when it's written.");
    inspireView.form = { url: "", journeys: "", pages: 12, ok: false };
  } catch (e) { toast(e.message); }
  inspireView.busy = false;
  loadInspire();
}

function addForm() {
  const f = inspireView.form;
  const d = inspireView.data;
  const known = d.apps.find(a => a.url && a.url === f.url.trim());
  const needsConfirm = !(known && known.confirmed);
  const parse = () => f.journeys.split("\n").map(l => l.split(";").map(s => s.trim()).filter(Boolean)).filter(j => j.length);
  const url = h("input", { type: "url", placeholder: "https://an-app-you-like.com", value: f.url, "aria-label": "The app's address",
    oninput: e => { f.url = e.target.value; } });
  const journeys = h("textarea", { rows: 3, placeholder: 'click link "Pricing"\nclick link "Features"; click button "Watch the demo"',
    "aria-label": "Journeys, one per line", oninput: e => { f.journeys = e.target.value; } }, f.journeys);
  const pages = h("input", { type: "number", min: 1, max: 50, value: f.pages, style: "width:5em", "aria-label": "Pages to read",
    oninput: e => { f.pages = Number(e.target.value); } });
  const ok = h("input", { type: "checkbox", id: "inspire-ok", checked: f.ok, onchange: e => { f.ok = e.target.checked; renderInspire(); } });
  return h("div", { class: "card" }, h("h2", {}, "Add an app that inspires you"),
    h("p", { class: "muted small" }, "The scout reads its public pages the way a visitor does, takes a screenshot of each, follows your journeys, " +
      "then writes a brief: features, business model, gaps, ways to be different, and what not to copy. Nothing is signed into; " +
      "robots.txt is respected; members who write code never see any of it."),
    h("label", {}, "Address", url),
    h("label", {}, "Journeys (optional): one per line, steps separated by ;", journeys),
    h("label", {}, "Pages to read ", pages),
    needsConfirm ? h("label", { class: "check" }, ok, " ", d.statement) : h("p", { class: "muted small" }, "You've confirmed this app before."),
    h("p", {}, h("button", { type: "button", class: "primary", disabled: inspireView.busy || (needsConfirm && !f.ok),
      onclick: () => explore(f.url.trim(), parse(), f.pages, needsConfirm) }, inspireView.busy ? "Starting…" : "Explore")));
}

function renderInspire() {
  const el = document.getElementById("inspire");
  if (!el) return;
  el.replaceChildren();
  if (inspireView.error) return el.append(errorCard("inspiration", inspireView.error));
  const d = inspireView.data;
  if (!d) { el.append(h("div", { class: "card empty" }, "Loading…")); loadInspire(); return; }
  if (d.apps.length) {
    el.append(h("div", { class: "card" }, h("h2", {}, "Apps you like"),
      table(["App", "Brief", "Seen", "When"], d.apps.map(a => [
        h("button", { type: "button", class: a.app === inspireView.selected ? "link selected" : "link",
          onclick: () => { inspireView.selected = a.app; loadInspire(); } }, a.url || a.app),
        a.brief ? status("good", "written") : status("pending", a.pages ? "not written" : "not explored yet"),
        `${a.pages} pages · ${a.journeys} journeys`,
        a.updated ? fmtWhen(a.updated) : "",
      ]))));
  }
  el.append(addForm());
  const app = inspireView.app;
  if (!app || app.app !== inspireView.selected) return;
  const head = h("div", { class: "card" }, h("h2", {}, app.url || app.app),
    h("p", {},
      h("button", { type: "button", disabled: inspireView.busy || !app.url || !app.confirmed,
        onclick: () => explore(app.url, app.asked || [], Math.max(1, app.pages.length || 12), false) }, "Run again"), " ",
      h("button", { type: "button", class: "danger", onclick: async () => {
        if (!confirm(`Delete everything kept about ${app.url || app.app}: the brief and the screenshots?`)) return;
        try { await postJSON("/api/inspiration/forget", { app: app.app }); inspireView.selected = null; inspireView.app = null; }
        catch (e) { toast(e.message); }
        loadInspire();
      } }, "Forget")));
  el.append(head);
  el.append(app.brief ? h("div", { class: "card brief" }, ...markdownNodes(app.brief))
    : h("div", { class: "card empty" }, "No brief yet. It's written after the app is explored."));
  if (app.pages.length || app.journeys.length) {
    const gallery = h("div", { class: "card" }, h("h2", {}, "What the scout saw"),
      h("p", { class: "muted small" }, "Kept on this machine for you and the lead; never shown to members who write code."));
    const grid = h("div", { class: "grid three" });
    app.pages.forEach((p, i) => grid.append(h("div", {}, h("p", { class: "muted small" }, `page ${i + 1}: ${p.url}`, p.problem ? ` (${p.problem})` : ""),
      shotLink(app.app, p, `page ${i + 1}`))));
    app.journeys.forEach((js, j) => js.forEach((s, k) => grid.append(h("div", {},
      h("p", { class: "muted small" }, `journey ${j + 1}, step ${k + 1}`, s.problem ? ` (stopped: ${s.problem})` : ""),
      shotLink(app.app, s, `journey ${j + 1}, step ${k + 1}`)))));
    gallery.append(grid);
    for (const n of app.notes || []) gallery.append(h("p", { class: "muted small" }, n));
    if (app.skipped?.length) gallery.append(h("p", { class: "muted small" }, `Not visited (robots.txt): ${app.skipped.join(", ")}`));
    el.append(gallery);
  }
}

document.querySelector('[role=tab][data-tab="inspire"]')?.addEventListener("click", () => loadInspire());
if (document.querySelector('[role=tab][data-tab="inspire"]')?.getAttribute("aria-selected") === "true") loadInspire();
