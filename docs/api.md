# The dashboard API, for programs

`agent-team ui` is a web page backed by a small local HTTP API. A program, such as the LakebaOS desktop
client, can start a dashboard of its own and use the same API without a browser. This page is the
contract it can rely on.

## Starting a dashboard from a program

```sh
AGENT_TEAM_CLIENT_TOKEN=<32+ random characters> agent-team ui --client --port 0 -C <project folder>
```

- **`--port 0`** picks a free port. The dashboard answers only on `127.0.0.1` and only to requests
  whose `Host` is `127.0.0.1:<port>` or `localhost:<port>`.
- **When it's ready**, it prints one JSON line on stdout:
  `{"event": "ready", "url": "http://127.0.0.1:<port>/", "port": <port>, "version": "0.13.9", "api": 1, "project": "<root or empty>"}`.
  An empty `project` means the folder has no team yet, and the page shows the guided setup.
- **POST requests** carry `Authorization: Bearer <token>`. The page itself uses a same-origin `Origin` and a
  session token instead; both ways stay open. The token is taken out of the environment, so the runs the
  dashboard starts never see it.
- **It stops when its stdin closes**, so it never outlives the program that started it. Runs started
  from it are separate processes and keep going.
- **It never reuses a busy port.** Without `--client`, `ui` shows a dashboard already running on its port
  instead; with `--client` it exits with an error.

Over SSH, where the environment and argv of a remote command aren't private, add `--client-token-stdin`:
the token is then the first line the program writes to the dashboard's stdin (feature `client-token-stdin`).

`agent-team projects --json` lists the projects agent-team knows, without a dashboard.

## Versions

`GET /api/meta` answers with or without a project:

```json
{"version": "0.13.9", "api": 1, "features": ["meta", "client-token", "jobs.offset", ...], "project": "/path", "setup": false}
```

`api` goes up only when a route changes in a way that breaks a program using it. New routes and new
fields don't change it. Check `features` before using a route added after `api` 1.

## Routes

GET routes need no token. POST routes take a JSON body. Errors come back as `{"error": "..."}` with a
4xx or 5xx status. A dashboard with no project yet answers the routes that need one with 409 and
`"setup": true`.

| Route | What it returns or does |
|---|---|
| `GET /api/meta` | Version, API version, features (above) |
| `GET /api/team` | The team: members, roles, models, `approval_requests`, `release_proposal`, `version` |
| `GET /api/health` | Whether each member's model answers (slow: it reaches every model) |
| `GET /api/setup/ready` | The readiness checklist, each item with its fix |
| `GET /api/runs` | Finished runs from the logs, newest first |
| `GET /api/jobs` | Background runs: `{"jobs": [{"id", "workflow", "status", "started", "params", ...}]}` |
| `GET /api/jobs/<id>?offset=N` | One run and its output from byte `N`: `text`, the next `offset`, `status` |
| `GET /api/story/<id>` | A run's progress in plain words |
| `POST /api/jobs/start` | `{"workflow", "params"}`: starts a run. Spend limits and guardrails apply here. |
| `POST /api/jobs/stop` | `{"id"}`: stops a run at its next step |
| `GET /api/estimate?workflow=&cycles=` | What a run would cost |
| `GET /api/usage` | Spend: `total`, `today`, `limits` (`per_run`, `per_day`), `by_day`, `by_agent`, `by_model`, `by_run`, `unpriced_models`; `resets_at` (when the daily limit resets: the next UTC midnight) and `remaining_today` (null without a daily limit). Feature `usage.resets` |
| `GET /api/schedule` | `{"schedules": {"ship": {"every", "where"} or null, "doctor": ...}}`. Feature `schedule` |
| `POST /api/schedule` | `{"workflow": "ship" or "doctor", "every": "6h"}`: installs it with the system scheduler (launchd or cron) |
| `POST /api/schedule/remove` | `{"workflow"}`: removes it |
| `GET /api/pr/<n>` | `{"number", "title", "state", "url", "head_sha", "files": [{"path", "status", "patch"}]}`; patches past 300 kB come back empty. Feature `pr.review` |
| `POST /api/pr/<n>/comments` | `{"comments": [{"path", "line", "body"}], "start_fix": bool}`: posts the owner's line comments as one review (event COMMENT) from their gh account, then optionally starts a `fix` run. Checked: an open PR, a changed file, a positive line, 1 to 4000 characters, 1 to 50 comments |
| `GET /api/metrics` | The team's numbers |
| `GET /api/config` | The team file's data and its `sha` |
| `POST /api/config/preview` | `{"data"}`: the diff a save would make |
| `POST /api/config/save` | `{"data", "sha"}`: saves it, keeping `.team.toml.bak`; refused if the file changed since `sha` |
| `POST /api/approve` | `{"number"}`: approves a pull request's current commit. The owner's action: a program must only send it after the person confirms. |
| `POST /api/release/approve` | `{"version"}`: approves the release the devops shift proposed (`release_proposal` in `/api/team`), and only that version; starts the shift that publishes it and returns the run. The owner's action, as above. Feature `release.approve`. `POST /api/jobs/start` refuses a `release` parameter. |
| `GET /api/inspiration` | `{"apps": [{"app", "url", "brief", "confirmed", "pages", "journeys", "updated"}], "statement"}`: the apps explored by `agent-team inspire`, and the confirmation statement. Feature `inspiration` |
| `GET /api/inspiration/<app>` | `{"app", "url", "confirmed", "brief", "pages", "journeys", "skipped", "notes", "asked"}`: the brief (Markdown, or null), each page and journey step with its `url`, `problem` and `shot`, and the journeys asked for |
| `GET /api/inspiration/<app>/shot/<name>` | One screenshot (PNG), by a `shot` name from the route above (`pages/NN.png`, `journeys/J-K.png`); any other name is 404 |
| `POST /api/inspiration/confirm` | `{"url"}`: the owner confirms they use the app and may look at it this way (`statement`). The owner's action: a program must only send it after the person confirms. `POST /api/jobs/start` with `inspire` (`{"url", "journeys": [[step, ...]], "max_pages"}`) is refused for an app that isn't confirmed. Never offered over MCP |
| `POST /api/inspiration/forget` | `{"app"}`: deletes the app's captures and brief |
| `GET /api/github` | Open PRs, issues and releases (cached for 60 s) |
| `GET /api/projects` | Every known project, summarised |

The MCP server (`agent-team mcp`) offers no approvals and can't approve a release. Approvals belong
only in a program's own UI, after an explicit confirmation by the person.
