// The agent-team side panel: the project's team, each member's health, recent runs and spend,
// with buttons to refresh, check health and open the dashboard. Data comes from the agent-team CLI
// (`agent-team status --json`), run on this machine; nothing is sent anywhere else.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Health, Snapshot } from '../types'

const PANE = 'agent-team'
const TITLE = 'agent-team'
const snapshot = atom({ plugin: 'agent-team', key: 'snapshot' } as const, null)
const health = atom({ plugin: 'agent-team', key: 'health' } as const, null)
const busy = atom({ plugin: 'agent-team', key: 'busy' } as const, '')
const error = atom({ plugin: 'agent-team', key: 'error' } as const, '')
const dashboard = atom({ plugin: 'agent-team', key: 'dashboard' } as const, '')

let cliPath: string | null | undefined   // undefined: not looked for yet; null: not installed

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
    return true
  } catch (err) {
    await update($, error, () => `Couldn't read the team: ${String(err)}`)
    return false
  } finally {
    await update($, busy, () => '')
  }
}

async function openDashboard($: EngineInterface): Promise<void> {
  const running = await read($, dashboard)
  if (running) {
    await $.process.run(['open', running]).catch(() => undefined)
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
      await $.process.run(['open', url]).catch(() => undefined)
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
    // Open the panel by itself only where the project has a team.
    if (e.isInteractive && (await refresh($))) void $.ui.open({ id: PANE, title: TITLE })
    return started
  })

  on('command.run', { command: 'team-panel' }, async $ => {
    await $.ui.open({ id: PANE, title: TITLE })
    const ok = await refresh($)
    return { text: ok ? 'agent-team panel opened.' : 'agent-team panel opened; see it for what is missing.' }
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

    return (
      <Box flexDirection="column" gap={1}>
        <Box flexDirection="column">
          <Text bold>{data.project.name}</Text>
          <Text dimColor>{data.project.repo || 'no GitHub repo'} · {data.members.length} members · ${data.spend.total.cost.toFixed(2)} spent</Text>
        </Box>

        <Box flexDirection="column">
          <Text bold>Team</Text>
          {data.members.map(m => (
            <Text>
              {mark(m.name)} {m.name} <Text dimColor>{m.role} · {m.kind === 'agent-http' ? `node ${m.url}` : m.model || m.kind}</Text>
            </Text>
          ))}
          {checks === null && <Text dimColor>Press Check health to test every member.</Text>}
          {failing.map(([name, c]) => <Text dimColor>{name}: {c.status}</Text>)}
          {missing.length > 0 && <Text dimColor>No {missing.join(', ')} member: some workflows won't run.</Text>}
        </Box>

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
