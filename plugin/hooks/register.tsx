// The agent-team side panel: the project's team, each member's health, recent runs and spend,
// with buttons to refresh, check health and open the dashboard. Data comes from the agent-team CLI
// (`agent-team status --json`), run on this machine; nothing is sent anywhere else.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Health, Job, Snapshot } from '../types'

// Keep equal to plugin.json's version and the CLI's (a test checks): a mismatch means one of
// them wasn't updated, and the panel says so.
const PLUGIN_VERSION = '0.13.1'
const PANE = 'agent-team'
const TITLE = 'agent-team'
const snapshot = atom({ plugin: 'agent-team', key: 'snapshot' } as const, null)
const health = atom({ plugin: 'agent-team', key: 'health' } as const, null)
const busy = atom({ plugin: 'agent-team', key: 'busy' } as const, '')
const error = atom({ plugin: 'agent-team', key: 'error' } as const, '')
const dashboard = atom({ plugin: 'agent-team', key: 'dashboard' } as const, '')

let cliPath: string | null | undefined   // undefined: not looked for yet; null: not installed
let poll: { cancel: () => void } | null = null   // refreshes while a background run is going
const RUNNABLE = ['autopilot', 'build', 'fix', 'discuss', 'ship', 'market', 'doctor']

async function findCli($: EngineInterface): Promise<string | null> {
  if (cliPath !== undefined) return cliPath
  const home = (await $.env.get('HOME')) ?? ''
  for (const c of ['agent-team', `${home}/.local/bin/agent-team`, `${home}/.agent-team/venv/bin/agent-team`,
                   `${home}/agent-team/.venv/bin/agent-team`]) {
    try {
      const r = await $.process.run([c, '--version'], { timeoutMs: 15000 })
      if (r.exitCode === 0) return (cliPath = c)
    } catch {
      // not at this path; try the next
    }
  }
  return (cliPath = null)
}

// Through the person's login shell, so API keys set in their profile are visible, as in a terminal.
function shellQuote(s: string): string {
  return `'${s.replaceAll("'", `'\\''`)}'`
}
async function loginShell($: EngineInterface, command: string): Promise<string[]> {
  const shell = (await $.env.get('SHELL')) || '/bin/zsh'
  return [shell, '-ic', command]
}

function lastLine(text: string): string {
  return text.trim().split('\n').filter(Boolean).slice(-1)[0] ?? ''
}

async function refresh($: EngineInterface, withHealth = false): Promise<boolean> {
  const cli = await findCli($)
  if (!cli) {
    await update($, error, () => 'The agent-team CLI is not installed. See the agent-team README for the one-line installer.')
    return false
  }
  await update($, busy, () => (withHealth ? 'Checking every member…' : 'Refreshing…'))
  try {
    const cwd = await $.session.cwd()
    const args = ['status', '--json', '-C', cwd, ...(withHealth ? ['--health'] : [])]
    const argv = withHealth ? await loginShell($, [cli, ...args].map(shellQuote).join(' ')) : [cli, ...args]
    const r = await $.process.run(argv, { timeoutMs: withHealth ? 120000 : 30000 })
    if (r.exitCode !== 0) {
      await update($, error, () => lastLine(r.stderr) || 'agent-team status failed')
      return false
    }
    const data = JSON.parse(r.stdout.slice(r.stdout.indexOf('{'))) as Snapshot & { health: Record<string, Health> | null }
    await update($, snapshot, () => data)
    if (data.health) await update($, health, () => data.health)
    await update($, error, () => '')
    const running = (data.jobs ?? []).some(j => j.status === 'running')
    if (running && !poll) poll = $.clock.every(5000, () => void refresh($))
    if (!running && poll) {
      poll.cancel()
      poll = null
    }
    return true
  } catch (err) {
    await update($, error, () => `Couldn't read the team: ${String(err)}`)
    return false
  } finally {
    await update($, busy, () => '')
  }
}

// A background run: the same workflow as in a terminal, started through the login shell so it has
// the API keys from the person's profile. It keeps going if this session ends.
async function startJob($: EngineInterface, workflow: string, text = '', release = ''): Promise<string> {
  const cli = await findCli($)
  if (!cli) return 'The agent-team CLI is not installed.'
  const cwd = await $.session.cwd()
  const extra = workflow === 'build' ? ['--task', text] : workflow === 'discuss' ? ['--topic', text]
    : workflow === 'fix' ? ['--number', text.replace(/^#/, '')]
    : workflow === 'ship' && release ? ['--release', release]
    : workflow === 'autopilot' && text ? ['--milestone', text] : []
  const argv = await loginShell($, [cli, 'jobs', 'start', workflow, '--json', '-C', cwd, ...extra].map(shellQuote).join(' '))
  await update($, busy, () => `Starting ${workflow}…`)
  try {
    const r = await $.process.run(argv, { timeoutMs: 30000 })
    if (r.exitCode !== 0) return lastLine(r.stderr) || `Couldn't start ${workflow}.`
    await refresh($)
    return `Started ${workflow} in the background; the panel follows it.`
  } finally {
    await update($, busy, () => '')
  }
}

async function stopJob($: EngineInterface, id: string): Promise<void> {
  const cli = await findCli($)
  if (!cli) return
  await $.process.run([cli, 'jobs', 'stop', id, '-C', await $.session.cwd()], { timeoutMs: 15000 }).catch(() => undefined)
  await refresh($)
}

async function approveRelease($: EngineInterface, version: string): Promise<void> {
  let answer = ''
  try {
    answer = await $.ui.ask(`Publish v${version} on GitHub? A devops shift releases it (CI must be green on main).`,
                            [`Release v${version}`, 'Not now'])
  } catch {
    return
  }
  if (answer !== `Release v${version}`) return
  void $.ui.toast(await startJob($, 'ship', '', version))
}

async function approvePr($: EngineInterface, number: number, title: string): Promise<void> {
  let answer = ''
  try {
    answer = await $.ui.ask(`Approve PR #${number} (${title}) at its current commit? The next devops shift may then merge it.`,
                            [`Approve #${number}`, 'Not now'])
  } catch {
    return
  }
  if (answer !== `Approve #${number}`) return
  const cli = await findCli($)
  if (!cli) return
  const r = await $.process.run([cli, 'approve', String(number), '-C', await $.session.cwd()], { timeoutMs: 30000 })
  void $.ui.toast(r.exitCode === 0 ? `Approved PR #${number}.` : lastLine(r.stderr) || `Couldn't approve PR #${number}.`)
  await refresh($)
}

async function startShift($: EngineInterface): Promise<void> {
  let answer = ''
  try {
    answer = await $.ui.ask('Start a devops shift? It acts on GitHub (comments, merges, releases) within the team\'s rules.',
                            ['Start the shift', 'Not now'])
  } catch {
    return   // dismissed
  }
  if (answer !== 'Start the shift') return
  void $.ui.toast(await startJob($, 'ship'))
}

// Open a URL in the person's browser: `open` on macOS, `xdg-open` on Linux.
async function openUrl($: EngineInterface, url: string): Promise<void> {
  for (const opener of ['open', 'xdg-open']) {
    try {
      const r = await $.process.run([opener, url], { timeoutMs: 10000 })
      if (r.exitCode === 0) return
    } catch {
      // not on this system; try the next
    }
  }
}

async function openDashboard($: EngineInterface): Promise<void> {
  const running = await read($, dashboard)
  if (running) {
    await openUrl($, running)
    return
  }
  const cli = await findCli($)
  if (!cli) return
  const cwd = await $.session.cwd()
  await update($, busy, () => 'Starting the dashboard…')
  for (let port = 8790; port < 8800; port++) {
    const argv = await loginShell($, `exec ${[cli, 'ui', '--no-open', '--port', String(port), '-C', cwd].map(shellQuote).join(' ')}`)
    const url = await new Promise<string>(resolve => {
      // The child lives for the session: the loop keeps reading until it exits or the module unloads.
      void (async () => {
        let found = ''
        try {
          for await (const piece of $.process.spawn({ argv })) {
            const m = !found && 'text' in piece ? /http:\/\/127\.0\.0\.1:\d+\//.exec(piece.text) : null
            if (m) {
              found = m[0]
              resolve(found)
            }
          }
        } catch {
          // could not start: fall through
        }
        if (!found) resolve('')   // exited without serving: port taken, or a config error
        else await update($, dashboard, () => '')   // it stopped later
      })()
    })
    if (url) {
      await update($, dashboard, () => url)
      await update($, busy, () => '')
      await openUrl($, url)
      return
    }
  }
  await update($, busy, () => '')
  await update($, error, () => 'Could not start the dashboard on ports 8790–8799.')
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    await $.command.register({ name: 'team-panel', description: "Show the project's agent-team in a side panel" })
    await $.command.register({ name: 'team-run', description: 'Start an agent-team run in the background: autopilot [milestone], build <task>, fix <PR>, discuss <topic>, ship, market or doctor' })
    // Open the panel by itself only where the project has a team.
    if (e.isInteractive && (await refresh($))) void $.ui.open({ id: PANE, title: TITLE })
    return started
  })

  on('command.run', { command: 'team-panel' }, async $ => {
    await $.ui.open({ id: PANE, title: TITLE })
    const ok = await refresh($)
    return { text: ok ? 'agent-team panel opened.' : 'agent-team panel opened; see it for what is missing.' }
  })

  on('command.run', { command: 'team-run' }, async ($, e) => {
    const [workflow = '', ...rest] = e.args.trim().split(/\s+/)
    const text = rest.join(' ')
    if (!RUNNABLE.includes(workflow)) return { text: `Usage: /team-run ${RUNNABLE.join(' | ')} [task or topic]` }
    if ((workflow === 'build' || workflow === 'discuss') && !text) {
      return { text: `/team-run ${workflow} needs ${workflow === 'build' ? 'a task' : 'a topic'}.` }
    }
    if (workflow === 'fix' && !/^#?\d+$/.test(text)) return { text: '/team-run fix needs a pull request number, e.g. /team-run fix 12' }
    await $.ui.open({ id: PANE, title: TITLE })
    return { text: await startJob($, workflow, text) }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button, Link } = $.ui.resolve(e)
    const data = (await read($, snapshot)) as Snapshot | null
    const checks = (await read($, health)) as Record<string, Health> | null
    const working = await read($, busy)
    const problem = await read($, error)
    const url = await read($, dashboard)

    const buttons = (
      <Box flexDirection="row" gap={1}>
        <Button label="Refresh" hotkey="r" onPress={() => void refresh($)} />
        <Button label="Check health" hotkey="h" onPress={() => void refresh($, true)} />
        <Button label="Start a shift" hotkey="s" onPress={() => void startShift($)} />
        <Button label={url ? 'Open dashboard' : 'Start dashboard'} hotkey="d" variant="primary"
                onPress={() => void openDashboard($)} />
      </Box>
    )

    if (!data) {
      return (
        <Box flexDirection="column" gap={1}>
          <Text dimColor>{working || problem || 'No .team.toml in this project. Run /team-init to set up a team.'}</Text>
          {buttons}
        </Box>
      )
    }

    const mark = (name: string): string => {
      const c = checks?.[name]
      return c === undefined ? '·' : c.ok ? '✓' : '✕'
    }
    const failing = Object.entries(checks ?? {}).filter(([, c]) => !c.ok)
    const missing = Object.keys(data.missing_roles)
    const jobs: Job[] = data.jobs ?? []
    const cost = (name: string): string => `$${(data.spend.by_agent?.[name]?.cost ?? 0).toFixed(2)}`
    const limits = data.spend.limits
    const today = data.spend.today === undefined ? ''
      : ` · today $${data.spend.today.toFixed(2)}${limits?.per_day ? ` of $${limits.per_day.toFixed(2)}` : ''}`

    return (
      <Box flexDirection="column" gap={1}>
        <Box flexDirection="column">
          <Text bold>{data.project.name}</Text>
          <Text dimColor>{data.project.repo || 'no GitHub repo'} · {data.members.length} members · ${data.spend.total.cost.toFixed(2)} spent{today}</Text>
          {data.schedule && <Text dimColor>Shifts run {data.schedule.every ? `every ${Math.round(data.schedule.every / 60)} min` : 'on a schedule'}</Text>}
        </Box>

        {data.version !== PLUGIN_VERSION && (
          <Text dimColor>
            ! This plugin is {PLUGIN_VERSION} and the agent-team CLI is {data.version}. Rerun the installer, then
            /reload-plugins (or start a new session).
          </Text>
        )}
        {(data.approval_requests ?? []).map(r => (
          <Box flexDirection="column">
            <Text bold>PR #{r.number} is waiting for your approval</Text>
            <Text dimColor>{r.title} · {r.paths.slice(0, 3).join(', ')}</Text>
            <Button label={`Approve #${r.number}`} onPress={() => void approvePr($, r.number, r.title)} />
          </Box>
        ))}
        {data.release_proposal && (
          <Box flexDirection="column">
            <Text bold>Release v{data.release_proposal.version} is waiting for your approval</Text>
            <Button label={`Approve v${data.release_proposal.version}`} hotkey="a"
                    onPress={() => void approveRelease($, data.release_proposal!.version)} />
          </Box>
        )}
        {(data.attention ?? []).length > 0 && (
          <Box flexDirection="column">
            <Text bold>Needs attention</Text>
            {(data.attention ?? []).map(a => (
              <Text>
                ✕ {a.name} <Text dimColor>{a.detail}{a.fix ? ` · fix: ${a.fix}` : ''}</Text>
              </Text>
            ))}
          </Box>
        )}

        <Box flexDirection="column">
          <Text bold>Team</Text>
          {data.members.map(m => (
            <Text>
              {mark(m.name)} {m.name} <Text dimColor>{m.role} · {m.kind === 'agent-http' ? `node ${m.url}` : m.model || m.kind} · {cost(m.name)}{m.skills?.length ? ` · skills: ${m.skills.map(s => s.name).join(', ')}` : ''}</Text>
            </Text>
          ))}
          {checks === null && <Text dimColor>Press Check health to test every member.</Text>}
          {failing.map(([name, c]) => <Text dimColor>{name}: {c.status}</Text>)}
          {data.members.filter(m => m.skills_problem).map(m => <Text dimColor>{m.name}: {m.skills_problem}</Text>)}
          {missing.length > 0 && <Text dimColor>No {missing.join(', ')} member: some workflows won't run.</Text>}
        </Box>

        {jobs.length > 0 && (
          <Box flexDirection="column">
            <Text bold>Background runs</Text>
            {jobs.map(j => (
              <Box flexDirection="row" gap={1}>
                <Text>
                  {j.status === 'running' ? '…' : j.status === 'succeeded' ? '✓' : '✕'} {j.workflow} <Text dimColor>{j.status}{j.params.task || j.params.topic ? ` · ${(j.params.task || j.params.topic || '').slice(0, 40)}` : j.params.number ? ` · PR #${j.params.number}` : ''}</Text>
                </Text>
                {j.status === 'running' && <Button label="Stop" onPress={() => void stopJob($, j.id)} />}
              </Box>
            ))}
          </Box>
        )}

        <Box flexDirection="column">
          <Text bold>Recent runs <Text dimColor>({data.run_count})</Text></Text>
          {data.runs.length === 0 && <Text dimColor>None yet.</Text>}
          {data.runs.slice(0, 5).map(r => (
            <Text>
              {r.workflow} <Text dimColor>{r.outcome || '—'}</Text>
            </Text>
          ))}
        </Box>

        {buttons}
        {url && <Link href={url} label={`Dashboard: ${url}`} />}
        {(working || problem) && <Text dimColor>{working || problem}</Text>}
      </Box>
    )
  })
}
