export type Member = { name: string; role: string; kind: string; model: string; url: string; owns: string[]; remote: boolean }
export type Run = { workflow: string; title: string; started: string | null; outcome: string }
export type Health = { ok: boolean; status: string }
export type Job = { id: string; workflow: string; status: string; started: string; params: { task?: string; topic?: string } }
export type Cost = { cost: number; calls: number }
export type Snapshot = {
  version: string
  project: { name: string; repo: string }
  members: Member[]
  missing_roles: Record<string, string>
  runs: Run[]
  run_count: number
  spend: { total: Cost; by_agent: Record<string, Cost>; today?: number; limits?: { per_run: number; per_day: number } }
  jobs?: Job[]
  schedule?: { workflow: string; every: number | null; where: string } | null
}

declare module 'claude-code' {
  interface PluginState {
    'agent-team': {
      snapshot: Snapshot | null
      health: Record<string, Health> | null
      busy: string
      error: string
      dashboard: string
    }
  }
}
