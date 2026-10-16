// The panel, driven by a stand-in for the agent-team CLI: what it shows, and what it says when
// there is no team. Run with: claude plugin test plugin
import { expect, test } from 'claude-code/testing'

const STATUS = {
  version: '0.5.0',
  root: '/work/todo-py',
  project: { name: 'todo-py', repo: 'lakeba/todo-py' },
  members: [
    { name: 'Atlas', role: 'lead', kind: 'anthropic', model: 'claude-opus-5-5', url: '', owns: ['ROADMAP.md'], remote: false,
      skills: [{ name: 'api-style' }] },
    { name: 'Forge', role: 'builder', kind: 'agent-http', model: '', url: 'http://studio:8765', owns: [], remote: true },
  ],
  missing_roles: { marketing: 'market' },
  runs: [{ workflow: 'build', title: 'Build: add a thing', started: null, outcome: 'approved after 1 round(s)' }],
  run_count: 34,
  spend: { total: { cost: 0.49, calls: 3 }, by_agent: { Atlas: { cost: 0.42, calls: 2 } }, today: 0.1,
           limits: { per_run: 0, per_day: 5 } },
  approval_requests: [{ number: 9, title: 'Rotate tokens', sha: 'abc1234567', paths: ['auth/token.py'] }],
  release_proposal: { version: '0.2.0', notes: 'M1 fixes', by: 'Harbor' },
  attention: [{ name: 'key ANTHROPIC_API_KEY', detail: 'not found', fix: 'agent-team keys set ANTHROPIC_API_KEY' }],
  jobs: [{ id: 'build-20261015T000000-abcdef', workflow: 'build', status: 'succeeded', started: '2026-10-15T00:00:00Z',
           params: { task: 'add export' } }],
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
      if (e.argv.includes('--version')) return result(0, 'agent-team 0.5.0')
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
    expect(await pane.find({ type: 'Text', text: /\$0\.42/ })).toBeTruthy()           // per-member spend
    expect(await pane.find({ type: 'Text', text: /skills: api-style/ })).toBeTruthy()
    expect(await pane.find({ type: 'Text', text: /keys set ANTHROPIC_API_KEY/ })).toBeTruthy()   // needs attention
    expect(await pane.find({ type: 'Text', text: /This plugin is/ })).toBeFalsy()                // versions match
    expect(await pane.find({ type: 'Button', text: 'Approve v0.2.0' })).toBeTruthy()             // a proposed release
    expect(await pane.find({ type: 'Button', text: 'Approve #9' })).toBeTruthy()                 // a gated PR
    expect(await pane.find({ type: 'Text', text: /today \$0\.10 of \$5\.00/ })).toBeTruthy()
    expect(await pane.find({ type: 'Text', text: /add export/ })).toBeTruthy()       // a background run

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
      if (e.argv.includes('--version')) return result(0, 'agent-team 0.5.0')
      return result(1, '', 'Config error: no .team.toml found in /work/other or its parents; run `agent-team init`')
    })

    await $.session.start({ cwd: '/work/other', surface, isInteractive: true })
    const pane = await $.ui.mount({ plugin: 'agent-team', surface, component: 'Pane', requestId: 'agent-team',
                                    props: { requestId: 'agent-team', title: 'agent-team' } })
    expect(await pane.find({ type: 'Text', text: /no \.team\.toml found/ })).toBeTruthy()
    expect(await pane.find({ type: 'Button', text: 'Refresh' })).toBeTruthy()
  })

  test(`/team-run starts a background build (${surface})`, async ($, on) => {
    const started: string[][] = []
    on('session.start', async (_$, e) => ({ cwd: e.cwd }))
    on('env.get', async () => ({ value: '/bin/zsh' }))
    on('session.cwd', async () => ({ value: '/work/todo-py' }))
    on('command.register', async (_$, e) => ({ value: { command: e.name } }))
    on('ui.open', async () => ({ value: { isPlaced: true as const } }))
    on('process.run', async (_$, e) => {
      const line = e.argv.join(' ')
      if (e.argv.includes('--version')) return result(0, 'agent-team 0.5.0')
      if (line.includes('jobs') && line.includes('start')) {
        started.push([...e.argv])
        return result(0, '{"id": "build-20261015T000000-abcdef"}')
      }
      if (line.includes('status')) return result(0, JSON.stringify(STATUS))
      return result(1, '', 'unexpected command')
    })

    await $.session.start({ cwd: '/work/todo-py', surface, isInteractive: true })
    const r = await $.command.run({ command: 'team-run', args: 'build add an export command' })
    expect(r.text).toMatch(/Started build/)
    expect(started.length).toBe(1)
    expect(started[0]!.join(' ')).toMatch(/jobs.*start.*build.*--task.*add an export command/)

    const usage = await $.command.run({ command: 'team-run', args: 'build' })
    expect(usage.text).toMatch(/needs a task/)
  })
}
