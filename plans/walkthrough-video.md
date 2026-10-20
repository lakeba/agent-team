# The walkthrough video: from installing Lakeba OS to ChairTime running on your server

Status: approved on 20 October 2026. The script is ready for recording (section 5); nothing has been filmed yet.

## 1. What it is

One video of about 6½ minutes, for YouTube (`youtube-nocookie.com` on the site), with chapters. It follows
ChairTime, the made-up founder's idea from the website, from installing Lakeba OS to the app running on a server.

Everything on screen is real and recorded, never mocked up:
- the installs, the builds and the release are real runs;
- waits are sped up, and say so on screen ("sped up 8×");
- keys, tokens and personal folders never appear: the key is pasted off camera, and paths show as `~`.

## 2. Decisions (20 October 2026)

| Topic | Decision |
|---|---|
| Repository | [lakeba/chairtime](https://github.com/lakeba/chairtime), created **private**; make it public before the video is published if viewers should see the code |
| Narration | Your voice, recorded from the script in section 5 |
| Budget | Approved: the ChairTime builds on Claude, about $10–20 in all, within the project's daily limit |
| Assembly | ffmpeg, installed with Homebrew on this Mac |
| Upload | You upload to YouTube; I hand over the MP4, the chapter list, the description and a thumbnail |

### What "deploy" means here, honestly

agent-team doesn't deploy to hosting. Its devops shift merges approved pull requests and publishes a GitHub
release, and My MVP can run the app on the machine the project is on. So the deploy chapter shows:
1. the v0.1.0 release of ChairTime on GitHub;
2. your own server running it: the Ubuntu VM, added in the desktop app as another machine over SSH, with ChairTime
   opened and started there, and the booking page opened from the Mac.

To check in the dry run: the app must listen on the VM's network address, not only `127.0.0.1`, for the Mac's
browser to reach it. If it doesn't, the team adds a `HOST` setting as a task, which the video can show.

## 3. How it's made

| Scene | Source |
|---|---|
| Terminal (install) | Real runs on a clean machine (the Ubuntu VM, and a fresh macOS user for the Mac app), replayed in a clean terminal frame at the original pace or sped up |
| Guided setup, project window, approvals, remote machine | `npm run capture` in lakebaos-client, extended with these scenes; 1920×1200 at 2× |
| GitHub release, the running app | The browser pane, recorded the same way |
| Titles, captions, chapter cards, the "sped up" labels | Drawn by the assembly script |
| Assembly | ffmpeg: each chapter's picture cut to the length of its narration, joined with short fades, plus a subtitle file (`.srt`) made from the script |

Order of work:
1. **Dry run** on the VM and a fresh macOS user: install, set up, one build, release, run on the server. This fixes
   anything in the flow before filming, and anything found becomes a task first.
2. **You record the narration** (section 4 and 5), one file per chapter.
3. **Filming**: the real run again, captured scene by scene.
4. **Assembly**, then you review a draft and I adjust timing.
5. **Hand-over**: the MP4 (1080p), the chapters, the description, the thumbnail and the `.srt`.

## 4. Recording the narration

- A quiet room, a headset or a USB mic if you have one. QuickTime Player > File > New Audio Recording is enough.
- **One file per chapter**, named `01-install.m4a`, `02-idea.m4a` and so on, as in section 5.
- Read at a relaxed pace (about 140 words a minute). Leave a second of silence at the start and the end.
- If you stumble, pause and say the sentence again: I cut the retakes. Don't restart the whole chapter.
- The timings in section 5 are targets. The picture is cut to your recording, not the other way round.
- Words in *[brackets]* are what's on screen, for you to picture; don't read them.

## 5. The script

Total: about 900 words, 6½ minutes.

### 00 · Opening (about 15 s)

*[The ChairTime booking page on a phone-sized browser: free slots for the week; a client picks one.]*

> This is ChairTime: online booking for barbers who work alone. A client opens a link, picks a free slot, and
> that's it. Nobody wrote this code by hand. An AI team built it, with Lakeba OS. Let me show you how, from the
> very beginning.

### 01 · Install (about 45 s) · `01-install.m4a`

*[lakeba.github.io; the download buttons; the Lakeba OS app on a Mac, double-clicked. Then a terminal on Linux:
the install command, sped up.]*

> Start at lakeba.github.io and download Lakeba OS. On a Mac, you open the app and it installs everything it needs:
> the engine, called agent-team, and REA, the tool the team uses to try your app like a real user would.
>
> On Linux, or if you like a terminal, it's one command. You paste it, and a minute later it's done. Nothing else to
> install by hand, and you can uninstall it just as easily.

### 02 · Your idea (about 60 s) · `02-idea.m4a`

*[The guided setup: typing the idea; naming Slotbook; ticking the confirmation; choosing where the AI runs; the team;
connecting GitHub; the ready check turning green.]*

> The guided setup asks for your idea in plain words. Here's mine: booking for one-chair barbers, who today take
> appointments over WhatsApp.
>
> Then, if you like, an app that inspires you. I'm naming Slotbook, a booking tool for salon chains. The team will
> look at it the way a visitor does, from the outside, and nothing is copied.
>
> Next, where the AI runs: Claude for the best results, a free model on your own computer, or both. Then your team: a
> lead who plans and reviews, builders, QA, marketing and devops. I set a daily spend limit of five dollars.
>
> I connect the project to GitHub, so the code lives online, and a last check makes sure everything is ready.

### 03 · The brief (about 30 s) · `03-brief.m4a`

*[The team exploring Slotbook; the brief appearing: features, prices, gaps, ways to be different.]*

> While I wait, the team reads Slotbook's pages and writes a brief: what it does, what it costs, what's missing, and
> how ChairTime can be different. Slotbook charges per location and has no free plan. That's exactly the gap for a
> barber with one chair.

### 04 · The team builds (about 75 s) · `04-build.m4a`

*[The lead suggesting the first tasks; ticking the booking page; Build it. The run in plain words, sped up: the plan,
the tests written first, the code, the tests passing, the lead's review.]*

> Atlas, the lead, reads my idea and the brief, and suggests the first tasks. I pick the booking page and press Build.
>
> Now the team works. You can follow it in plain words: the lead writes a plan, QA writes the tests first, the builder
> writes the code. Then the tests run, for real, and the lead reviews everything against the plan.
>
> If something isn't right, the lead sends it back with exactly what to fix, and the team goes another round. Nothing
> is approved until the tests have actually run and pass. This part is sped up: it takes a few minutes.

### 05 · You approve (about 35 s) · `05-approve.m4a`

*[The pull request on GitHub; the Approvals tab in the desktop app; the confirmation dialog; approved.]*

> When the lead is happy, the change arrives as a pull request, and it waits for me. I can read what changed, comment
> on a line, or approve it. Approving is always mine: the app asks me to confirm, and no AI can do it for me.

### 06 · Ship it (about 40 s) · `06-ship.m4a`

*[The devops shift merging; the release proposal; approving v0.1.0; the release on GitHub.]*

> Harbor, the devops member, works in shifts. It merges what I approved, once the checks are green, and proposes a
> release with notes written for humans. I approve version 0.1.0, and it's published on GitHub.

### 07 · On your server (about 60 s) · `07-server.m4a`

*[The Projects window: adding a machine, the Ubuntu server, by its SSH address; opening ChairTime there; Run my app; the
booking page opening in the browser; a booking made.]*

> Now let's put it on a server. In the desktop app I add another machine: my Ubuntu server, by its SSH address. The
> app uses my own SSH keys, and never asks for a password.
>
> Lakeba OS is installed there too, so I open ChairTime on the server, and in My MVP I press Run my app. And here
> it is, running, from my browser. A client picks Thursday at ten, leaves a name and a number, and the booking is saved.

### 08 · Costs and schedule (about 25 s) · `08-spend.m4a`

*[The Spend tab: today against the limit, by member; the schedule card.]*

> Everything the team spends is on one screen, against the limit I set. And I can schedule the devops shift, say every
> six hours, so approved work ships on its own.

### 09 · Close (about 20 s) · `09-close.m4a`

*[The website hero; "Start your Business Now".]*

> That's the whole journey: an idea in plain words, a team that builds it, and you deciding what ships. When it's
> working, Lakeba can help you build a company around it. Start at lakeba.github.io.

## 6. YouTube chapters (from the script; the times are set from the final cut)

```
0:00 ChairTime, built by an AI team
0:15 Install Lakeba OS
1:00 Your idea, in plain words
2:00 The inspiration brief
2:30 The team builds it
3:45 You approve
4:20 Ship it
5:00 On your own server
6:00 Costs and schedule
6:25 Start your business
```

## 7. Still to settle

1. The repository's visibility when the video goes out (private now).
2. Whether the opening shows ChairTime on a phone-sized browser (it's a web page, not a native app).
3. The thumbnail: a frame from chapter 7 (the booking page) with the title, unless you have a brand template.

## 8. Dry run on the Ubuntu VM (20 October 2026)

A clean install in a fresh home folder on the VM, with the published installer and agent-team 0.13.13; then
ChairTime through the guided setup's code, a build, a release, and the app running on the VM. It cost $3.03
on Claude (one build, one fix run, four devops shifts, the Slotbook brief).

**It worked, end to end:**
- install in about 9 s (with npm and pip caches);
- the Slotbook brief in 47 s;
- a build approved in round 1, in 13½ min (98 tests);
- PR #1 merged by the devops shift, then v0.1.0 released on [lakeba/chairtime](https://github.com/lakeba/chairtime/releases/tag/v0.1.0);
- ChairTime running on the VM: the barber set hours, a client booked 10:00 from the Mac, and a second client
  was refused the same slot (409, "taken").

**What broke, and what I did about it:**

| # | What broke | Status |
|---|---|---|
| 1 | Members are told "No test command is configured" in a project that started empty, and the detected Python command ran without the project's dependencies | **Fixed** (b7be9f8): one `test_command_for()` for the build and the lead's tool; Python tests run in the project's `.venv` with `requirements.txt` |
| 2 | "Install REA" left `.team.toml` uncommitted, so the first build on a branch refused to start | **Fixed** (b7be9f8): the setup commits it |
| 3 | Inspire read `/` and `/index.html` as two pages | **Fixed** (b7be9f8) |
| 4 | The release refused `## Unreleased` (without brackets), which the team itself wrote | **Fixed** (f97b984) |
| 5 | **A new project has no CI**, so the devops shift can never merge or release (it rightly wants a green CI run with test counts) | **Fixed**: the setup's GitHub step (and `agent-team ci setup`) adds a CI workflow; the Ready check names a missing one |
| 6 | `test_count_pattern` stays at the unittest default when the tests turn out to be pytest, so CI counts are never read | **Fixed**: counts are read in the usual formats when the configured pattern finds nothing |
| 7 | QA wrote a test asserting the CHANGELOG says "Unreleased", which fails as soon as a release dates it | **Fixed**: QA's prompt says never to test document wording |
| 8 | The guided setup's GitHub step can only create a new repository, not connect an existing one | **Fixed**: "Use this repository" (an empty `owner/name`) |
| 9 | Run my app doesn't recognise a Flask (or FastAPI) app that is a package with an app factory (`flask --app chairtime run`) | **Fixed**: packages with a Flask app or factory, or `app = FastAPI()`; a `.venv` is made first when missing |
| 10 | Run my app starts Flask's development server ("do not use in production"), on `127.0.0.1` unless told otherwise | For the video, chapter 7 says "running on my server", which is true. A real deployment (gunicorn and a service) is a task for the team, and it touches deployment files, which need your approval |
| 11 | The installer's "not on your PATH" warning on a brand-new account | **Fixed**: "open a new terminal" where `~/.profile` adds `~/.local/bin` |

**Notes for filming:**
- This VM already has REA 6.7.0 installed globally, so the installer used it (by design). On a truly new machine it
  installs its own copy; film the install on a fresh macOS user or a new VM if that should show.
- Chapter 7 needs the barber's hours set first (`/barber`, with the barber token from the server's environment) so
  slots show. The script can add one sentence for it.
- The app keeps running on the VM at `http://10.211.55.4:5055` until stopped (Run my app's Stop, or `apprun.stop`).

## 9. Filming plan (from agent-team 0.13.14)

Everything the dry run broke is fixed in 0.13.14, so filming is one clean run, captured as it happens.

### What you prepare

1. **A clean Mac account**, for chapter 1's Mac install: System Settings > Users & Groups > Add User (it needs your
   admin password, so it's yours to do). Log in to it once, then I take it from there over SSH or you sign in
   for the recording.
2. **A clean Ubuntu machine**, for the terminal install and the server chapter: a clone of the VM taken *before*
   anything was installed, or a new VM. The current VM has REA installed globally, so the installer would skip
   installing its own (that's correct, but it wouldn't show).
3. **The narration**: the ten files from section 5, in one folder (say `~/LakebaOS-video/narration/`).
4. **The repository's visibility on the day**: [lakeba/chairtime](https://github.com/lakeba/chairtime) is private.
   If it stays private, the GitHub scenes are shown from inside the desktop app (Approvals, Review a pull request),
   never github.com. If you make it public before filming, github.com pages can appear too.

### What I do

| Step | What | Cost / time |
|---|---|---|
| 1 | **Reset the demo repository**: delete the dry run's history in `lakeba/chairtime` (a force push to an empty `main`, its two PRs closed and the v0.1.0 release removed), with your OK on the day, so filming starts from nothing | — |
| 2 | **Terminal recording**: record the installs as real terminal sessions (asciinema in a virtualenv on the machines) and render them to video. This needs two downloads, asciinema and its renderer `agg`, which I'll name, with sizes, before installing | ~1 h |
| 3 | **Extend `npm run capture`** with the scenes the dry run didn't film: the Projects window, adding the server, the remote project, Approvals with the v0.1.0 release, My MVP's Run my app, Spend and the schedule | ~half a day |
| 4 | **The filming run**: the whole flow once more on the clean machines, captured scene by scene; long waits are recorded in full and sped up later | ~$3–5 on Claude, ~1½ h |
| 5 | **Assembly with ffmpeg**: each chapter cut to your narration's length, title cards, "sped up" labels, captions (`.srt`), chapters | ~half a day |
| 6 | **Draft for your review**, then the final 1080p MP4, thumbnail, description and chapter list for YouTube | — |

### The order

1. You: a clean Mac account, a clean Ubuntu VM, and the narration. They can happen in parallel.
2. Me: steps 2 and 3, which don't need anything from you. Then step 1 with your OK, then 4 to 6.

### Still open

1. Private repository and in-app GitHub scenes, or public and github.com.
2. Background music: none, or a royalty-free track you choose.
