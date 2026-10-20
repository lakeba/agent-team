"use strict";
// My MVP: the owner's view in plain words. What's being built right now (the run's story), the app
// to try, what changed and keeping it, the next feature, and the application to Lakeba.

const mvpView = { data: null, app: null, story: null, job: null, timer: null, cliArgs: "", cliOut: null, keepMsg: "", next: "", busy: "" };

async function loadMvp() {
  try {
    [mvpView.data, mvpView.app] = await Promise.all([getJSON("/api/mvp"), getJSON("/api/app")]);
    const jobs = (await getJSON("/api/jobs")).jobs;
    mvpView.job = jobs.find(j => j.status === "running") || jobs[0] || null;
    mvpView.story = mvpView.job ? await getJSON(`/api/story/${encodeURIComponent(mvpView.job.id)}`) : null;
  } catch (e) { mvpView.error = e.message; }
  renderMvp();
  clearTimeout(mvpView.timer);
  if (mvpView.job && mvpView.job.status === "running") mvpView.timer = setTimeout(loadMvp, 3000);
}

function renderMvp() {
  const el = document.getElementById("mvp");
  if (!el) return;
  el.replaceChildren();
  const d = mvpView.data;
  if (mvpView.error && !d) return el.append(errorCard("your MVP", mvpView.error));
  if (!d) return el.append(h("p", { class: "muted" }, "Loading…"));
  const root = (state.team && state.team.root) || "";

  el.append(h("div", { class: "card mvp-head" }, h("h2", {}, d.name),
    d.vision ? h("p", { class: "secondary" }, d.vision.length > 600 ? d.vision.slice(0, 600) + "…" : d.vision) : h("p", { class: "muted" }, "No VISION.md yet."),
    h("p", { class: "muted small" }, `Spent so far: ${fmtUsd(d.cost)}${d.repo ? " · on GitHub: " + d.repo : " · not on GitHub yet"}`)));

  if (d.needs_key) el.append(h("div", { class: "card notice" }, h("h2", {}, "The team can’t start yet"),
    h("p", { class: "secondary" }, "It has no AI to use. Paste your Claude key in Settings under “Claude key”, " +
      "or choose a local AI app (Ollama, LM Studio…) there under “Team composition”. Your tasks wait here until then."),
    h("div", { class: "actions" }, h("button", { type: "button", class: "primary",
      onclick: () => document.querySelector('[role=tab][data-tab="settings"]')?.click() }, "Open Settings"))));

  // Right now
  const now = h("div", { class: "card" }, h("h2", {}, mvpView.job && mvpView.job.status === "running" ? "The team is working" : "Latest run"));
  if (!mvpView.job) now.append(h("p", { class: "muted" }, "Nothing has run yet. Build your first feature below."));
  else {
    const j = mvpView.job;
    now.append(h("p", { class: "secondary" }, h("strong", {}, j.workflow === "build" ? "Building: " : `${j.workflow}: `), j.params.task || j.params.topic || ""),
      status(JOB_STATUS[j.status] || "pending", j.status));
    const story = (mvpView.story && mvpView.story.story) || [];
    now.append(h("ol", { class: "story" }, story.map(s => h("li", { class: `story-${s.kind}` }, s.text))));
    if (j.status === "running") now.append(h("p", { class: "muted small" }, h("span", { class: "spinner", "aria-hidden": "true" }), " This page updates by itself. The full log is under Runs."));
  }
  el.append(now);

  // Your app
  const a = mvpView.app || {}, how = a.how || {};
  const appCard = h("div", { class: "card" }, h("h2", {}, "Try your app"));
  if (how.kind === "web" || how.kind === "static") {
    if (a.running) appCard.append(status("good", "Running"), a.url ? h("p", {}, h("a", { href: a.url, target: "_blank", rel: "noopener noreferrer", class: "button primary" }, "Open it")) : h("p", { class: "muted small" }, "Starting… its address appears here."),
      h("div", { class: "actions" }, h("button", { type: "button", onclick: () => appAction("/api/app/stop") }, "Stop it")));
    else appCard.append(h("p", { class: "secondary small" }, `Starts with: ${how.command || how.why}`),
      h("div", { class: "actions" }, h("button", { type: "button", class: "primary", onclick: () => appAction("/api/app/start") }, "Run my app")));
    if (a.output) appCard.append(h("details", {}, h("summary", { class: "muted small" }, "What it printed"), h("pre", { class: "job-output" }, a.output)));
  } else if (how.kind === "cli") {
    const args = h("input", { type: "text", placeholder: "e.g. --help" }); args.value = mvpView.cliArgs;
    args.addEventListener("input", () => { mvpView.cliArgs = args.value; });
    appCard.append(h("p", { class: "secondary small" }, "This is a command-line tool. Type what you’d give it and run it here."),
      h("div", { class: "row" }, args, h("button", { type: "button", class: "primary", onclick: runCli }, "Run")),
      mvpView.cliOut ? h("pre", { class: "job-output", title: mvpView.cliOut.command }, `› ${mvpView.cliOut.args}\n${mvpView.cliOut.output}`) : null);
  } else appCard.append(h("p", { class: "muted" }, how.why || "There’s nothing to run yet."));
  el.append(appCard);

  // Changes and keeping them
  const keep = h("div", { class: "card" }, h("h2", {}, "Changes not kept yet"));
  if (!d.changed.length) keep.append(h("p", { class: "muted" }, "Everything is kept."));
  else {
    const msg = h("input", { type: "text", placeholder: "What changed, in a few words" }); msg.value = mvpView.keepMsg;
    msg.addEventListener("input", () => { mvpView.keepMsg = msg.value; });
    keep.append(h("div", { class: "chips" }, d.changed.slice(0, 30).map(f => h("span", { class: "chip" }, f))),
      h("p", { class: "secondary small" }, "Happy with how it works? Keep this version" + (d.repo ? " (it’s also uploaded to GitHub)." : ".")),
      h("div", { class: "row" }, msg, h("button", { type: "button", class: "primary", onclick: keepVersion }, "Keep this version")));
  }
  el.append(keep);

  // Next feature
  const queue = typeof loadNextTasks === "function" ? loadNextTasks(root) : [];
  const running = mvpView.job && mvpView.job.status === "running";
  const next = h("div", { class: "card" }, h("h2", {}, "Build the next feature"));
  if (queue.length) next.append(h("p", { class: "secondary small" }, "Waiting from your first plan:"),
    h("ul", { class: "next-tasks" }, queue.map((t, i) => h("li", {}, t, " ", h("button", { type: "button", disabled: running ? true : null, onclick: () => buildTask(t, i) }, "Build this")))));
  const box = h("textarea", { rows: 3, placeholder: "Describe the next thing the app should do" }); box.value = mvpView.next;
  box.addEventListener("input", () => { mvpView.next = box.value; });
  next.append(box, h("div", { class: "actions" }, h("button", { type: "button", class: "primary", disabled: running ? true : null, onclick: () => buildTask(mvpView.next) }, running ? "Wait for the current run" : "Build it")));
  if (d.roadmap.length) next.append(h("p", { class: "muted small" }, "On the roadmap: " + d.roadmap.slice(0, 5).join(" · ")));
  el.append(next);

  // What's been built
  if (d.built.length || d.versions.length) el.append(h("div", { class: "grid two" },
    h("div", { class: "card" }, h("h2", {}, "What the team has built"), d.built.length ? h("ul", {}, d.built.map(b => h("li", { class: "small" }, b))) : h("p", { class: "muted" }, "Nothing yet.")),
    h("div", { class: "card" }, h("h2", {}, "Kept versions"), h("ul", {}, d.versions.map(v => h("li", { class: "small" }, h("span", { class: "mono" }, v.sha), ` ${v.date} · ${v.message}`))))));

  // Apply
  const ap = d.application;
  el.append(h("div", { class: "card mvp-apply" }, h("h2", {}, "Apply to Lakeba"),
    h("p", { class: "secondary" }, "When your first version works, apply to Lakeba to co-found your company. Spark, your marketing member, writes the positioning brief and pitch deck for your application."),
    ap.brief ? h("p", {}, status("good", "Brief written"), ap.deck ? [" ", status("good", "Pitch deck made")] : null,
      h("span", { class: "muted small" }, ` In your project folder: BRIEF.md${ap.deck ? " and " + ap.deck : ""}.`)) : null,
    h("div", { class: "actions" },
      h("button", { type: "button", disabled: running ? true : null, onclick: prepareApplication }, ap.brief ? "Update my brief and deck" : "Prepare my application"),
      h("a", { class: "button primary", href: ap.apply_url, target: "_blank", rel: "noopener noreferrer" }, "Apply with your MVP")),
    h("p", { class: "muted small" }, "Lakeba reviews every application and funds a limited number of ventures. You keep your MVP whatever the outcome.")));
}

async function appAction(path) {
  try { mvpView.app = { ...mvpView.app, ...(await postJSON(path, {})) }; } catch (e) { toast(e.message); }
  renderMvp(); setTimeout(async () => { try { mvpView.app = await getJSON("/api/app"); } catch (_) {} renderMvp(); }, 2500);
}
async function runCli() {
  try { mvpView.cliOut = { ...(await postJSON("/api/app/cli", { args: mvpView.cliArgs })), args: mvpView.cliArgs }; } catch (e) { toast(e.message); }
  renderMvp();
}
async function keepVersion() {
  try { const r = await postJSON("/api/mvp/keep", { message: mvpView.keepMsg }); toast(r.kept ? `Kept: ${r.note}.` : r.note); mvpView.keepMsg = ""; }
  catch (e) { toast(e.message); }
  loadMvp();
}
async function buildTask(task, queueIndex) {
  task = (task || "").trim();
  if (!task) return toast("Describe what to build first.");
  try {
    await postJSON("/api/jobs/start", { workflow: "build", params: { task, rounds: 3 } });
    const root = state.team.root;
    if (queueIndex !== undefined && typeof saveNextTasks === "function") { const q = loadNextTasks(root); q.splice(queueIndex, 1); saveNextTasks(root, q); }
    else mvpView.next = "";
    toast("The team has started.");
  } catch (e) { toast(e.message); }
  loadMvp();
}
async function prepareApplication() {
  if (!confirm("Spark writes a positioning brief, a website and a pitch deck for your product, checked against the code. Start?")) return;
  try { await postJSON("/api/jobs/start", { workflow: "market", params: { rounds: 3 } }); toast("Spark has started on your application."); }
  catch (e) { toast(e.message); }
  loadMvp();
}
