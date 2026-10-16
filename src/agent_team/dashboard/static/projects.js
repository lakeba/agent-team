"use strict";
// Projects: every project agent-team has been used in on this Mac, with what each one spent, what
// it's doing and what waits for you. Opening one starts its own dashboard.

const projectsView = { data: null, error: "" };

async function loadProjects() {
  try { projectsView.data = await getJSON("/api/projects"); projectsView.error = ""; }
  catch (e) { projectsView.error = e.message; }
  renderProjects();
}

function renderProjects() {
  const el = document.getElementById("projects");
  if (!el) return;
  el.replaceChildren();
  if (projectsView.error) return el.append(errorCard("projects", projectsView.error));
  const d = projectsView.data;
  if (!d) { el.append(h("div", { class: "card empty" }, "Loading…")); loadProjects(); return; }
  const rows = d.projects;
  const today = rows.filter(r => r.ok).reduce((s, r) => s + r.cost_today, 0);
  const total = rows.filter(r => r.ok).reduce((s, r) => s + r.cost_total, 0);
  const waiting = rows.filter(r => r.ok).reduce((s, r) => s + r.waiting.length, 0);
  const running = rows.filter(r => r.ok).reduce((s, r) => s + r.running.length, 0);
  el.append(h("div", { class: "grid tiles" },
    h("div", { class: "card tile" }, h("div", { class: "label" }, "Projects"), h("div", { class: "value" }, fmtInt(rows.length))),
    h("div", { class: "card tile" }, h("div", { class: "label" }, "Spend today"), h("div", { class: "value" }, fmtUsd(today)), h("div", { class: "note" }, `${fmtUsd(total)} in total`)),
    h("div", { class: "card tile" }, h("div", { class: "label" }, "Running now"), h("div", { class: "value" }, fmtInt(running))),
    h("div", { class: "card tile" }, h("div", { class: "label" }, "Waiting for you"), h("div", { class: "value" }, waiting ? status("warn", String(waiting)) : "0"))));
  if (!rows.length) return el.append(h("div", { class: "card empty" }, "No projects yet. A project is remembered the first time you run agent-team in it."));
  el.append(h("div", { class: "grid cards" }, rows.map(r => {
    const here = r.root === d.current;
    const card = h("article", { class: "card member" },
      h("h3", {}, h("span", {}, r.name, h("span", { class: "muted" }, r.repo ? ` · ${r.repo}` : "")),
        here ? status("good", "this dashboard") : null),
      h("p", { class: "muted small mono" }, r.root));
    if (!r.ok) { card.append(h("p", { class: "health-line" }, status("bad", "can't read"), " ", r.problem)); return card; }
    card.append(h("dl", {},
      h("dt", {}, "Spend"), h("dd", {}, `${fmtUsd(r.cost_today)} today${r.limit_per_day ? ` of ${fmtUsd(r.limit_per_day)}` : ""} · ${fmtUsd(r.cost_total)} in total`),
      h("dt", {}, "Last run"), h("dd", {}, r.last_run ? `${r.last_run.workflow} · ${r.last_run.outcome || "—"} · ${fmtWhen(r.last_run.started)}` : "none yet"),
      h("dt", {}, "Running"), h("dd", {}, r.running.length ? r.running.join(", ") : "nothing"),
      h("dt", {}, "For you"), h("dd", {}, r.waiting.length ? r.waiting.map(w => status("warn", w)) : h("span", { class: "muted" }, "nothing waiting"))));
    if (!here) card.append(h("div", { class: "actions" }, h("button", { type: "button", onclick: async ev => {
      ev.target.disabled = true; ev.target.textContent = "Starting…";
      try { const res = await postJSON("/api/projects/open", { root: r.root }); window.open(res.url, "_blank", "noopener"); }
      catch (e) { toast(e.message); }
      ev.target.disabled = false; ev.target.textContent = "Open its dashboard";
    } }, "Open its dashboard")));
    return card;
  })));
}

document.querySelector('[role=tab][data-tab="projects"]')?.addEventListener("click", () => loadProjects());
