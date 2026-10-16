"use strict";
// Activity: live charts of what the team does, how well, and what goes wrong. Refreshed every five
// seconds while this tab is open. One hue per chart (the accent); problems are split into small
// multiples rather than colours, and every bar has a tooltip with its exact value.

const activity = { data: null, timer: null, error: "" };

async function loadActivity() {
  try { activity.data = await getJSON("/api/metrics"); activity.error = ""; }
  catch (e) { activity.error = e.message; }
  renderActivity();
}

function activityVisible() {
  const panel = document.getElementById("activity");
  return panel && !panel.hidden && document.visibilityState === "visible";
}

function pollActivity() {
  clearTimeout(activity.timer);
  activity.timer = setTimeout(async () => { if (activityVisible()) await loadActivity(); pollActivity(); }, 5000);
}

function columns(rows, value, label, { height = 120 } = {}) {
  const max = Math.max(...rows.map(value), 0);
  const wrap = h("div", { class: "columns" });
  wrap.style.height = `${height}px`;
  rows.forEach(r => {
    const col = h("div", { class: "column" });
    col.style.height = max ? `${(value(r) / max) * 100}%` : "0%";
    attachTip(col, label(r));
    wrap.append(col);
  });
  return wrap;
}

function axisLabels(first, last) {
  return h("div", { class: "column-labels" }, h("span", {}, first), h("span", {}, last));
}

function tile(label, value, note, kind) {
  return h("div", { class: "card tile" }, h("div", { class: "label" }, label),
    h("div", { class: "value" }, kind ? status(kind, value) : value), note ? h("div", { class: "note" }, note) : null);
}

function renderActivity() {
  const el = document.getElementById("activity");
  if (!el) return;
  el.replaceChildren();
  if (activity.error) return el.append(errorCard("activity", activity.error));
  const m = activity.data;
  if (!m) { el.append(h("div", { class: "card empty" }, "Loading…")); loadActivity(); return; }
  const t = m.tiles;
  const pct = v => v == null ? "—" : `${Math.round(v * 100)}%`;
  el.append(h("div", { class: "filters" }, status("good", "Live"), h("span", { class: "muted small" },
    `Updates every 5 seconds while this tab is open · ${new Date(m.now).toLocaleTimeString()}`)));
  el.append(h("div", { class: "grid tiles" },
    tile("Spend today", fmtUsd(t.cost_today), `${fmtUsd(t.cost_7d)} in 7 days`),
    tile("Runs today", fmtInt(t.runs_today), `${fmtInt(t.calls_last_hour)} model calls in the last hour`),
    tile("Running now", fmtInt(t.running), t.running ? m.running.map(r => r.workflow).join(", ") : "nothing"),
    tile("Approved, 7 days", pct(t.approval_rate_7d), "builds and fixes the lead accepted"),
    tile("Merged, 7 days", fmtInt(t.merged_7d), "pull requests"),
    tile("Problems, 7 days", fmtInt(t.problems_7d), "rejected builds, refused merges, failed runs", t.problems_7d ? "warn" : null)));

  const hourly = m.hourly, daily = m.daily;
  el.append(h("div", { class: "grid two" },
    h("div", { class: "card" }, h("h2", {}, "Spend per hour"), h("p", { class: "muted small" }, "Last 48 hours, US dollars"),
      columns(hourly, r => r.cost, r => `${r.hour.replace("T", " ")}:00 · ${fmtUsd(r.cost)} · ${fmtInt(r.calls)} calls`),
      axisLabels(hourly[0].hour.slice(5).replace("T", " ") + ":00", "now")),
    h("div", { class: "card" }, h("h2", {}, "Model calls per hour"), h("p", { class: "muted small" }, "Last 48 hours"),
      columns(hourly, r => r.calls, r => `${r.hour.replace("T", " ")}:00 · ${fmtInt(r.calls)} calls · ${fmtTokens(r.tokens)} tokens`),
      axisLabels(hourly[0].hour.slice(5).replace("T", " ") + ":00", "now"))));

  el.append(h("div", { class: "grid two" },
    h("div", { class: "card" }, h("h2", {}, "Runs per day"), h("p", { class: "muted small" }, "Last 30 days, every workflow"),
      columns(daily, r => r.runs, r => `${r.day} · ${r.runs} runs · ${r.approved} approved, ${r.rejected} not approved · ${r.merged} merged`),
      axisLabels(daily[0].day.slice(5), daily[daily.length - 1].day.slice(5))),
    h("div", { class: "card" }, h("h2", {}, "Merged pull requests per day"), h("p", { class: "muted small" }, "Last 30 days"),
      columns(daily, r => r.merged, r => `${r.day} · ${r.merged} merged`),
      axisLabels(daily[0].day.slice(5), daily[daily.length - 1].day.slice(5)))));

  // Problems as small multiples: one hue, one chart per kind.
  const kinds = [["rejected", "Builds not approved"], ["changes_requested", "Changes requested"], ["refused", "Merges refused"], ["failed_jobs", "Runs failed"]];
  el.append(h("div", { class: "card" }, h("h2", {}, "Problems per day"),
    h("p", { class: "muted small" }, "Last 30 days. Reviews asking for changes are normal; refusals and failures need a look."),
    h("div", { class: "grid multiples" }, kinds.map(([k, label]) => h("div", {},
      h("div", { class: "multiple-title" }, label, h("span", { class: "muted" }, ` · ${daily.reduce((s, r) => s + r[k], 0)}`)),
      columns(daily, r => r[k], r => `${r.day} · ${r[k]} ${label.toLowerCase()}`, { height: 60 }))))));

  const members = Object.entries(m.by_member);
  el.append(h("div", { class: "grid two" },
    h("div", { class: "card" }, h("h2", {}, "Spend by member, 30 days"),
      members.length ? barList(members.map(([name, v]) => ({ name, ...v })), r => r.cost, r => `${r.name}: ${fmtUsd(r.cost)} · ${fmtInt(r.calls)} calls`)
                     : h("p", { class: "muted" }, "No model calls recorded in the last 30 days.")),
    h("div", { class: "card" }, h("h2", {}, "Evals"),
      m.evals.length ? table(["When", "Passed", "Cost"], m.evals.slice().reverse().slice(0, 8).map(r =>
        [fmtWhen(r.at), r.passed === r.total ? status("good", `${r.passed}/${r.total}`) : status("bad", `${r.passed}/${r.total}`), fmtUsd(r.cost)]), [2])
                     : h("p", { class: "muted" }, "No evals yet. Run agent-team eval to test the team's real models on fixed scenarios."))));

  const feed = h("div", { class: "card" }, h("h2", {}, "Latest events"));
  if (!m.feed.length) feed.append(h("p", { class: "muted" }, "Nothing logged yet."));
  else feed.append(h("ul", { class: "feed" }, m.feed.map(f => h("li", {},
    h("span", { class: "muted small" }, fmtWhen(f.at)), " ", h("strong", {}, f.who), " ",
    h("span", { class: "secondary" }, f.what || f.workflow), " ", markerBadge(f.marker),
    f.actions.length ? h("span", { class: "muted small" }, ` · ${f.actions.join("; ")}`) : null))));
  el.append(feed);
}

document.querySelector('[role=tab][data-tab="activity"]')?.addEventListener("click", () => loadActivity());
pollActivity();
