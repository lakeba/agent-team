# Inspire in the app, and a website for people who don't code

Status: approved on 20 October 2026, with the decisions in section 6. Phases A1 and A2 are done (not yet released).

Checked against agent-team 0.13.12 (`main` at f839d12) and lakebaos-client `main` at a2850c0, on 20 October 2026.

Two tracks, which can run in parallel:

- **A. Inspire without a terminal.** It becomes part of the guided setup and of the desktop app.
- **B. A website for founders who don't code.** It leads with the app, uses real screenshots and short looping
  videos, and moves the command line to a "For developers" section.

## 1. Where things stand

| Area | Today (checked in the code) |
|---|---|
| Inspire | CLI only: `agent-team inspire <url>` (`inspire.py`). |
| Background runs | `jobs.argv_for` accepts `doctor`, `ship`, `market`, `discuss`, `autopilot`, `fix` and `build`, not `inspire`. |
| API | `/api/*` has no inspiration endpoints. `FEATURES` in `dashboard/server.py` lists what a client can rely on. |
| Guided setup | `dashboard/static/setup.js` has 7 steps: Welcome, Your idea, Where the AI runs, Your team, GitHub, Ready check, First version (`setup_wizard.py` does the work). It never sets up REA, which Inspire needs. |
| Desktop app | It shows that same guided setup for a folder without a team. The project window has five tabs (Team, Runs, Spend, Approvals, Edit team) and a side rail. Nothing about Inspire. |
| MCP | `mcp_server.WORKFLOWS` is an explicit list; `inspire` isn't in it. |
| Website | The hero is an animated terminal running `agent-team build ... --pr`. The only images are six dashboard screenshots (`docs/assets/img`). There's no video, and ffmpeg isn't installed here. |

## 2. Track A: Inspire without a terminal

### What stays fixed

The boundary from `plans/inspire-plan.md` is unchanged, whoever starts the run:

- outside only;
- `robots.txt` first;
- the fixed capture set;
- untrusted wrapping;
- members who write code never get the brief or the captures.

On top of that:

- **Only a person confirms.** The "I use this app and may look at it this way" confirmation is the owner's action, like
  approving a pull request. Its endpoint is documented as such:
  - in the desktop app, the main process shows a native dialog before sending it;
  - in the dashboard, it's a checkbox the owner ticks.

  Neither MCP nor the chat can confirm, and MCP never offers `inspire`. A test pins that.
- **Spend limits and guardrails apply.** Inspire becomes a background run, started through `POST /api/jobs/start`
  like every other one.

### A1. agent-team: Inspire as a background run, with an API

- **`jobs.argv_for("inspire")`** checks every field:
  - `url`: http(s), at most 2,000 characters;
  - `journeys`: up to 5, each of up to 8 steps, every step parsed with `steps.parse_step` so a typo is refused
    before anything starts;
  - `max_pages`: 1–50.

  It isn't one of the `WRITERS`: it only writes under `.team/inspiration/`.
- **`jobs.start` refuses an unconfirmed app**, with a message that says how to confirm.
- **Endpoints.** Writes need the owner's token (the page's session token, or the client token). Reads follow
  the dashboard's existing rule: this machine only, Host-checked, no CORS.

| Endpoint | What |
|---|---|
| `GET /api/inspiration` | The apps explored: address, pages, journeys, whether a brief exists, when |
| `GET /api/inspiration/<app>` | The brief (Markdown), the pages and journey steps with their addresses and problems, and the notes |
| `GET /api/inspiration/<app>/shot/<name>` | One screenshot (PNG). The name is checked against `index.json`, so no other file can be read |
| `POST /api/inspiration/confirm` | `{"url"}`: the owner's confirmation. Returns the statement that was confirmed |
| `POST /api/inspiration/forget` | `{"app"}`: deletes the captures and the brief |

  The feature is called `inspiration` in `/api/meta`, so the desktop app shows its card only when agent-team has it.
  `docs/api.md` documents all of this.
- **A dashboard Inspiration tab**:
  - each app's brief;
  - the screenshots gallery;
  - Run again and Forget;
  - an "Add an app" form (address, journeys, the confirmation checkbox).

### A2. agent-team: a step in the guided setup

- **A new optional step, "An app you like", after "Your idea"** (8 steps in all):
  - the address;
  - up to 3 journeys in plain words, with examples (`click link "Pricing"`);
  - the confirmation statement, with a checkbox that starts unticked;
  - "Skip": most founders will.
- **The Ready check offers REA** when an app was named.
  - "Install REA (needed for Inspire and behaviour checks)" is a fix the page can do itself (`rea.install` and
    `rea.configure`).
  - Without a supported Node.js, the step says which version to install and how, and Inspire is skipped with a note.
    The rest of the setup carries on.
- **First version** runs Inspire before the lead proposes the first tasks, showing its progress.
  - The lead reads the brief (`inspire.for_member`) when it suggests tasks.
  - The lead drafts an "Inspired by, and different from" section for `VISION.md`, which the founder accepts or edits
    in the page.
- **`agent-team init`** asks the same optional question in a terminal, so both ways of setting up give the same project.

### A3. Desktop app (lakebaos-client)

- **An Inspiration card on the project's side rail**, shown when `/api/meta` lists `inspiration`:
  - the apps explored, each with whether its brief is ready;
  - "Add an app".
- **Add an app**: a form for the address and journeys. Then, in the main process:
  1. the first time for that app, a native dialog shows the confirmation statement, with "I confirm" and "Cancel";
  2. on "I confirm", `POST /api/inspiration/confirm`;
  3. then `POST /api/jobs/start` with `inspire`.

  The run appears in the Runs tab like any other, and spend limits answer in agent-team's words.
  The renderer can only ask for "add an app"; it has no direct path to the confirm endpoint (the preload exposes
  no such call).
- **The brief view**: the Markdown is rendered with DOMPurify, as in the chat. The screenshots are fetched by the
  main process and shown as images, and stay in the window (no saving, no sharing). Forget asks first.
- **Remote projects** work the same way through the SSH tunnel.
- **Not in the chat.** The chat's MCP server (`--no-merge`) doesn't offer `inspire`, and Claude can't read
  the captures.
- **The smoke test** gets a fake agent-team with the new endpoints. It checks:
  - the confirmation dialog is required, and Cancel sends nothing;
  - the run starts with checked parameters;
  - the card is hidden without the feature.

## 3. Track B: a website for founders who don't code

### B1. Screens and loops made from the real app, by a script

- **`scripts/capture.js` in lakebaos-client** starts the real app with a throwaway profile and the real agent-team.
  It uses a demo project made by `agent-team try --with replay --keep`, which needs no key, no model and no
  network, and gives real runs and real numbers.
  - It walks the app the way a person would: the Projects window, the guided setup, Team, Runs during a build,
    Spend, Approvals, and the Inspiration card.
  - It saves PNG screenshots (`webContents.capturePage`) in light and dark, at 2× for sharp screens.
- **Short loops, 5–10 seconds each.** The plan is to record them with Electron's own recorder (MediaRecorder on the
  window's stream), so no ffmpeg is needed. B1 starts by checking that Electron 44 records MP4 (H.264, which every
  browser plays) as well as WebM. If it only records WebM, the fallback is ffmpeg on the machine that makes the
  captures. Planned scenes:
  1. describing the idea;
  2. a build running;
  3. approving a change;
  4. the inspiration brief.
- **Nothing private on screen.**
  - The demo lives under a neutral folder (`~/LakebaOS/Tally`, in a temporary home).
  - No keys, account names or real addresses.
  - The Inspire scene explores a **made-up app** served locally by the script, never a real company's site, so the
    website never shows someone else's brand.
- **One command remakes everything after each release**: `npm run capture`, with output to
  `docs/assets/app/` in agent-team.

### B2. The page

- **Hero:**
  - a real app screen (a loop of a build running) instead of the terminal;
  - "Download for Mac" and "Download for Linux" next to "Start your MVP";
  - plain words, with no "PR", "CLI" or "MCP" above the fold.
- **How it works, in four steps, each with its loop:**
  1. describe your idea (or name an app you like);
  2. the team builds;
  3. you approve;
  4. you ship.
- **Inspire** keeps its section, with a screenshot of a brief from the made-up app.
- **For developers.** The terminal animation, the Claude Code plugin, MCP, behaviour checks and the library move
  into one section lower down. The README keeps covering the command line in full.
- **Loops:** `<video muted autoplay loop playsinline>`, each with a still poster and a text description.
  - With "reduce motion" set, only the poster shows.
  - Loops below the fold load when they scroll into view.
- **Budget:** at most about 1.5 MB per loop and 6 MB for the whole page, checked by a small script before each push (the site has no build step today).
- **Checked** in light and dark mode, at phone width (no sideways scroll), and on a slow connection (posters first).

### B3. Later

A 60–90 second narrated walkthrough, from idea to a running MVP, once the app's screens have settled.

## 4. Phases (each ships on its own)

| Phase | Repository | What ships | Size |
|---|---|---|---|
| A0 | agent-team, installers | REA installed with agent-team and kept at the pinned version | S |
| A1 | agent-team | Inspire as a background run, its endpoints and confirmation, the dashboard Inspiration tab, docs | M |
| A2 | agent-team | The guided setup step, REA in the Ready check, the lead's first tasks and `VISION.md` section from the brief, `init` | M |
| A3 | lakebaos-client | The Inspiration card, the native confirmation, the brief view and gallery, smoke tests | M |
| B1 | lakebaos-client | `npm run capture`: screenshots and loops from the real app and a demo project | M |
| B2 | agent-team | The new page: hero, the four steps with loops, Inspire, For developers | M |
| A4 | agent-team | Inspire for desktop apps and APKs: run them and watch | M |
| A5 | agent-team | Opening up apps the founder owns or may inspect | M |
| B3 | either | The narrated walkthrough on YouTube (later) | S |

- A1, then A2 and A3. B1, then B2.
- B can start now with the screens the app already has; the Inspire scene is added once A3 ships.
- Each agent-team phase is a patch release (0.13.13 and up), as before.

## 5. Testing

- **agent-team:**
  - `argv_for("inspire")` refuses bad addresses, too many journeys and mistyped steps;
  - a job for an unconfirmed app is refused;
  - the confirm endpoint needs the client token;
  - a screenshot name outside `index.json` (`../`, absolute paths) is refused;
  - MCP never lists or starts `inspire`;
  - the setup step writes the same files as the CLI;
  - "Skip" leaves nothing behind;
  - without Node.js, setup still finishes.
- **lakebaos-client:**
  - Cancel in the dialog sends nothing;
  - the renderer has no path to the confirm endpoint;
  - the card is hidden without the feature;
  - remote projects work;
  - all existing checks still pass.
- **Website:** media sizes within budget; reduced motion shows posters; no sideways scroll at 375 px; dark mode.

## 6. Decisions (20 October 2026)

1. **REA is a prerequisite, installed with agent-team and kept up to date.** This is a new phase, A0:
   - the Lakeba OS installer, the desktop app's first run and `pipx install agent-team` followed by `agent-team init` all
     install REA (and a supported Node.js, where the installer can);
   - agent-team pins the REA version its tests passed with, and moves the pin forward in its own releases;
   - on start, the dashboard and `doctor` update agent-team's REA copy to the pinned version when it's older, in the
     background, and say so.

   A REA you installed yourself is still used as it is.
2. **Apps, binaries and APKs, not only websites.** This changes the boundary approved in `plans/inspire-plan.md`
   ("never decompiling, disassembling, unpacking app bundles"). So it's split in two, and only the first part is
   planned:
   - **Running the app and watching it (phase A4).** Inspire opens a desktop app or an APK the way a user does and
     records its screens and the text a screen reader gets: macOS apps (Electron ones included) and Android apps in
     an emulator. As with websites: no sign-in, nothing beyond what a user sees, and the founder confirms.
     - Checked against REA 6.5.0: its macOS window tools (`observe_native_ui`, `capture_native_ui_scenario`) only
       work after `open_binary`, which loads the app into a disassembler. That is opening it up, so A4 doesn't use
       them. It uses the operating system's own tools instead: `screencapture` for a window, System Events for the
       accessibility tree and for pressing a named button, and `adb` (screencap, `uiautomator dump`, `input tap`)
       for Android. macOS asks the person once for Screen Recording and Accessibility permission; without them,
       the run stops and says which one is missing.
     - Linux desktop apps aren't covered yet (no common accessibility tool to rely on).
   - **Opening the app up (decided: allowed only for apps the founder owns or has written permission to
     inspect; phase A5).** The Terms & Conditions set out the user's responsibility for this. This covers decompiling,
     disassembling, unpacking bundles, and reading the code, its strings or its network API. Most apps' licences
     forbid it for anyone else, so the limits are in code, not just in the confirmation:
     - the founder states which applies (their own app, or written permission) and attaches or names the
       permission; it's kept with the captures, dated;
     - REA's inspection tools are offered for that run only, to the scout, never to the lead's tools or members
       who write code (`config.REVERSE_TOOL` and `WRITES_CODE` stay as they are);
     - the brief describes what the app does in the team's words, never its code, and the "Don't copy" rules apply.

   No separate legal review is part of the flow (decided 20 October 2026): the user's statements, kept dated with
   the captures, and the Terms & Conditions carry the responsibility.

3. **The walkthrough video lives on YouTube**, embedded with `youtube-nocookie.com`.
4. **The hero's main button is "Start your Business Now".**
5. **The made-up app needs a better idea.** Proposed (change it freely): **ChairTime**, bookings for one-chair
   barbers and hairdressers who today take appointments over WhatsApp. Clients pick a free slot from a link, get a
   reminder the day before, and the barber sees the day at a glance on their phone. It has a clear founder story
   ("like the big booking tools, but for one chair and no front desk"), a real audience, and screens that read well
   in screenshots (a week grid, a booking page, a reminder). The Inspire scene explores **Slotbook**, a made-up
   booking site for salon chains served locally by the capture script (`slotbook.example`), never a real company.
6. **Use cases as a sub-site of lakeba.github.io** (later): a few worked examples, from idea to MVP, each with its
   own pages. It needs its own plan.
7. **macOS screenshots only**, for now.

## 7. Still open

1. **The Terms & Conditions** text, with the user's responsibilities for Inspire (looking at other apps, and opening
   up only apps they own or may inspect), and where the app and the site link to it.
