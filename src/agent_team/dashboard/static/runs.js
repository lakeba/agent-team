"use strict";
// Starting runs from the dashboard. A run is the same CLI workflow as in a terminal, started in the
// background on this Mac; it keeps going if the page or the dashboard closes. Output is text only.

const launch = { workflow: "build", params: { rounds: 3, skip: [] }, jobs: [], open: null, output: {}, offsets: {}, timer: null, busy: false };

const WORKFLOWS = [
  ["build", "Build a task", "The lead plans, builders implement, tests run, the lead reviews."],
  ["autopilot", "Autopilot", "Work through the roadmap a PR at a time: build, review, fix and merge, until the milestone is done."],
  ["fix", "Fix a pull request", "A builder applies the lead's review to an open PR's branch and pushes; the next shift reviews it again."],
  ["ship", "Devops shift", "Triage, sign-offs, lead review, merges and releases on GitHub."],
  ["discuss", "Roadmap discussion", "Members discuss a topic until they agree; the lead updates ROADMAP.md."],
  ["market", "Marketing", "Brief, website and pitch deck, reviewed with screenshots."],
  ["doctor", "Health check", "Check every member can be reached."],
];
const JOB_STATUS = { running: "pending", succeeded: "good", "not approved": "warn", "spend limit": "warn", skipped: "warn", stopped: "warn", failed: "bad", lost: "bad" };

async function loadJobs() {
  try { launch.jobs = (await getJSON("/api/jobs")).jobs; } catch (e) { launch.jobs = []; launch.error = e.message; }
  if (!launch.open) { const running = launch.jobs.find(j => j.status === "running"); if (running) launch.open = running.id; }
  if (launch.open) await pollOutput(launch.open);
  refreshJobList();
  schedulePoll();
}
function schedulePoll() {
  clearTimeout(launch.timer);
  if (launch.jobs.some(j => j.status === "running")) launch.timer = setTimeout(loadJobs, 2000);
}
async function pollOutput(id) {
  try {
    const r = await getJSON(`/api/jobs/${encodeURIComponent(id)}?offset=${launch.offsets[id] || 0}`);
    launch.output[id] = (launch.output[id] || "") + r.text;
    launch.offsets[id] = r.offset;
  } catch (e) { launch.output[id] = (launch.output[id] || "") + `\n[couldn't read the output: ${e.message}]`; }
}

function renderLauncher() {
  const t = state.team;
  const wrap = h("div", { class: "grid two launch" });
  if (!t || t.error) return wrap;
  const p = launch.params;
  const has = role => t.members.some(m => m.role === role);
  const builders = t.members.filter(m => m.role === "builder").length;

  const choose = h("select", {}, WORKFLOWS.map(([v, label]) => h("option", { value: v, selected: launch.workflow === v ? true : null }, label)));
  choose.addEventListener("change", () => { launch.workflow = choose.value; renderRuns(); });
  const about = WORKFLOWS.find(w => w[0] === launch.workflow)[2];

  const textIn = (key, attrs = {}) => { const el = h(attrs.rows ? "textarea" : "input", { type: "text", ...attrs }); el.value = p[key] || "";
    el.addEventListener("input", () => { p[key] = el.value; }); return el; };
  const numIn = (key, def, min, max) => { const el = h("input", { type: "number", min, max, value: p[key] ?? def });
    el.addEventListener("input", () => { p[key] = el.value === "" ? undefined : Number(el.value); }); return el; };
  const check = (key, label, disabled) => { const el = h("input", { type: "checkbox", checked: p[key] ? true : null, disabled: disabled ? true : null });
    el.addEventListener("change", () => { p[key] = el.checked; }); return h("label", { class: "choice" }, el, " ", label); };
  const skipBox = role => { const el = h("input", { type: "checkbox", checked: p.skip.includes(role) ? null : true });
    el.addEventListener("change", () => { p.skip = el.checked ? p.skip.filter(r => r !== role) : [...p.skip, role]; }); return h("label", { class: "choice" }, el, " ", { qa: "QA writes tests first", security: "Security review", docs: "Docs update" }[role]); };

  const fields = [];
  if (launch.workflow === "build") {
    fields.push(field("Task", textIn("task", { rows: 3, placeholder: "What should the team build?" })),
      h("div", { class: "form-grid" }, field("Rounds", numIn("rounds", 3, 1, 10)), field("Branch", textIn("branch", { placeholder: "e.g. feature/export (optional)" }))),
      h("div", { class: "choices" },
        check("pr", "Commit, push and open a pull request when approved (needs a branch)"),
        check("parallel", builders > 1 ? `Split the work across all ${builders} builders` : "Split across builders (the team has one)", builders < 2),
        ["qa", "security", "docs"].filter(has).map(skipBox)));
  } else if (launch.workflow === "autopilot") {
    fields.push(field("Milestone", textIn("milestone", { placeholder: "e.g. M2 (optional: the whole roadmap)" })),
      field("Most cycles", numIn("max_cycles", 6, 1, 30), "Each cycle is one build or one devops shift"));
  } else if (launch.workflow === "fix") {
    fields.push(field("Pull request number", numIn("number", "", 1, 99999), "Its latest review comes from the last devops shift"));
  } else if (launch.workflow === "discuss") {
    fields.push(field("Topic", textIn("topic", { placeholder: "e.g. the next three features" })), field("Messages", numIn("turns", 12, 2, 40)));
  } else if (launch.workflow === "ship") {
    fields.push(field("Most steps", numIn("max_steps", 30, 1, 100), "Model calls the devops member may make in this shift"));
  } else if (launch.workflow === "market") {
    fields.push(field("Rounds", numIn("rounds", 3, 1, 10)));
  }
  const lim = (state.usage && state.usage.limits) || {};
  const limits = lim.per_run || lim.per_day
    ? `Spend limits apply: ${[lim.per_run ? fmtUsd(lim.per_run) + " per run" : "", lim.per_day ? fmtUsd(lim.per_day) + " per day" : ""].filter(Boolean).join(", ")}.`
    : "No spend limits are set; add them under Team → Edit team.";

  const est = h("p", { class: "secondary small" });
  if (launch.workflow !== "doctor") {
    getJSON(`/api/estimate?workflow=${launch.workflow}&cycles=${launch.workflow === "autopilot" ? (p.max_cycles || 6) : 1}`)
      .then(e => { est.textContent = e.note + (e.warning ? " " + e.warning : ""); if (e.warning) est.classList.add("warn-text"); })
      .catch(() => {});
  }
  const start = h("button", { type: "button", class: "primary", disabled: launch.busy ? true : null, onclick: startRun }, launch.busy ? "Starting…" : "Start");
  wrap.append(h("div", { class: "card" }, h("h2", {}, "Start a run"),
    field("Workflow", choose, about), ...fields,
    est,
    h("p", { class: "muted small" }, limits, " Runs go on in the background on this Mac, as if started in a terminal."),
    h("div", { class: "actions" }, start)));

  wrap.append(jobList());
  return wrap;
}

// Polling redraws only this card, so typing in the form above is never interrupted.
function refreshJobList() {
  const old = document.getElementById("job-list");
  if (old) old.replaceWith(jobList()); else renderRuns();
}
function jobList() {
  const list = h("div", { class: "card", id: "job-list" }, h("h2", {}, "Background runs"));
  if (!launch.jobs.length) list.append(h("p", { class: "muted" }, "None yet. Runs started here or from the Claude panel appear here with their output."));
  launch.jobs.slice(0, 8).forEach(j => {
    const isOpen = launch.open === j.id;
    list.append(h("div", { class: "job" },
      h("div", { class: "job-head" },
        h("strong", {}, j.workflow), h("span", { class: "title muted", title: j.argv.join(" ") }, " " + (j.params.task || j.params.topic || j.params.milestone || (j.params.number ? `PR #${j.params.number}` : ""))),
        h("span", { class: "spacer" }), status(JOB_STATUS[j.status] || "pending", j.status), h("span", { class: "muted small" }, fmtWhen(j.started)),
        h("button", { type: "button", onclick: async () => { launch.open = isOpen ? null : j.id; if (!isOpen && launch.output[j.id] === undefined) await pollOutput(j.id); refreshJobList(); } }, isOpen ? "Hide output" : "Output"),
        j.status === "running" ? h("button", { type: "button", class: "danger", onclick: () => stopRun(j.id) }, "Stop") : null),
      isOpen ? h("pre", { class: "job-output" }, launch.output[j.id] || "(no output yet)") : null));
  });
  requestAnimationFrame(() => { const out = list.querySelector(".job-output"); if (out) out.scrollTop = out.scrollHeight; });
  return list;
}

async function startRun() {
  const p = { ...launch.params };
  if (launch.workflow === "build" && !(p.task || "").trim()) return toast("Describe the task first.");
  if (launch.workflow === "discuss" && !(p.topic || "").trim()) return toast("Give the discussion a topic.");
  if (launch.workflow === "fix" && !(p.number > 0)) return toast("Which pull request? Give its number.");
  if (launch.workflow === "fix" && !confirm(`This pushes the fix to pull request #${p.number}'s branch on GitHub. Start?`)) return;
  if (launch.workflow === "build" && p.pr && !confirm("When the lead approves, this commits, pushes the branch and opens a pull request on GitHub. Start?")) return;
  if (launch.workflow === "autopilot" && !confirm("Autopilot builds, reviews and merges PRs on GitHub by itself, within the team's rules and your spend limits. Start?")) return;
  if (launch.workflow === "ship" && !confirm("A devops shift acts on GitHub: comments, labels, merges and releases, within the team's rules. Start?")) return;
  for (const k of Object.keys(p)) if (p[k] === undefined || p[k] === "") delete p[k];
  launch.busy = true; renderRuns();
  try {
    const job = await postJSON("/api/jobs/start", { workflow: launch.workflow, params: p });
    launch.open = job.id; launch.output[job.id] = ""; launch.offsets[job.id] = 0;
    toast(`Started ${job.workflow}.`);
  } catch (e) { toast(e.message); }
  launch.busy = false;
  renderRuns();
  await loadJobs();
}
async function stopRun(id) {
  if (!confirm("Stop this run? It stops after the current step.")) return;
  try { await postJSON("/api/jobs/stop", { id }); } catch (e) { toast(e.message); }
  await loadJobs();
}

loadJobs();
