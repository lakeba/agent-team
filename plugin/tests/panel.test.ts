// The panel, driven by a stand-in for the agent-team CLI: what it shows, and what it says when
// there is no team. Run with: claude plugin test plugin
import { expect, test } from 'claude-code/testing'

const STATUS = {
  version: '0.1.0',
  root: '/work/todo-py',
  project: { name: 'todo-py', repo: 'lakeba/todo-py' },
  members: [
    { name: 'Atlas', role: 'lead', kind: 'anthropic', model: 'claude-opus-5-5', url: '', owns: ['ROADMAP.md'], remote: false },
    { name: 'Forge', role: 'builder', kind: 'agent-http', model: '', url: 'http://studio:8765', owns: [], remote: true },
  ],
  missing_roles: { marketing: 'market' },
  runs: [{ workflow: 'build', title: 'Build: add a thing', started: null, outcome: 'approved after 1 round(s)' }],
  run_count: 34,
  spend: { total: { cost: 0.49, calls: 3 }, by_agent: {} },
  health: { Atlas: { ok: true, status: 'ok' }, Forge: { ok: false, status: 'FAILED: node down' } },
}

const result = (exitCode: number, stdout = '', stderr = '') =>
  ({ value: { exitCode, stdout, stderr, isStdoutTruncated: false, isStderrTruncated: false } })

for (const surface of ['desktop', 'terminal'] as const) {
  test(`shows the team, health, runs and spend (${surface})`, async ($, on) => {
    on('session.start', async (_$, e) => ({ cwd: e.cwd }))
    on('env.get', async () => ({ value: '/Users/someone' }))
    on('session.cwd', async () => ({ value: '/work/todo-py' }))
    on('command.register', async (_$, e) => ({ value: { command: e.name } }))
    on('ui.open', async () => ({ value: { isPlaced: true as const } }))
    on('process.run', async (_$, e) => {
      if (e.argv.includes('--version')) return result(0, 'agent-team 0.1.0')
      if (e.argv.join(' ').includes('status')) return result(0, JSON.stringify(STATUS))
      return result(1, '', 'unexpected command')
    })

    await $.session.start({ cwd: '/work/todo-py', surface, isInteractive: true })
    const pane = await $.ui.mount({ plugin: 'agent-team', surface, component: 'Pane', requestId: 'agent-team',
                                    props: { requestId: 'agent-team', title: 'agent-team' } })
    expect(await pane.find({ type: 'Text', text: 'todo-py' })).toBeTruthy()
    expect(await pane.find({ type: 'Text', text: /Atlas/ })).toBeTruthy()
    expect(await pane.find({ type: 'Text', text: /node http:\/\/studio:8765/ })).toBeTruthy()
    expect(await pane.find({ type: 'Text', text: /\$0\.49 spent/ })).toBeTruthy()
    expect(await pane.find({ type: 'Text', text: /No marketing member/ })).toBeTruthy()

    // Health appears after "Check health": a cross for the unreachable node, with its reason.
    await pane.press({ key: 'Check health' })
    expect(await pane.find({ type: 'Text', text: /✕ Forge/ })).toBeTruthy()
    expect(await pane.find({ type: 'Text', text: /node down/ })).toBeTruthy()
  })

  test(`explains when the project has no team (${surface})`, async ($, on) => {
    on('session.start', async (_$, e) => ({ cwd: e.cwd }))
    on('env.get', async () => ({ value: '/Users/someone' }))
    on('session.cwd', async () => ({ value: '/work/other' }))
    on('command.register', async (_$, e) => ({ value: { command: e.name } }))
    on('ui.open', async () => ({ value: { isPlaced: true as const } }))
    on('process.run', async (_$, e) => {
      if (e.argv.includes('--version')) return result(0, 'agent-team 0.1.0')
      return result(1, '', 'Config error: no .team.toml found in /work/other or its parents; run `agent-team init`')
    })

    await $.session.start({ cwd: '/work/other', surface, isInteractive: true })
    const pane = await $.ui.mount({ plugin: 'agent-team', surface, component: 'Pane', requestId: 'agent-team',
                                    props: { requestId: 'agent-team', title: 'agent-team' } })
    expect(await pane.find({ type: 'Text', text: /no \.team\.toml found/ })).toBeTruthy()
    expect(await pane.find({ type: 'Button', text: 'Refresh' })).toBeTruthy()
  })
}
