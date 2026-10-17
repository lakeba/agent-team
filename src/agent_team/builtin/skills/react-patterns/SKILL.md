---
name: react-patterns
description: React patterns: components, hooks, state, effects, performance and forms
---
# React patterns

- Function components; one component per file when it's reused; props typed.
- State: local `useState` first; `useReducer` for complex transitions; context for rarely-changing
  app-wide values; a data library (TanStack Query, SWR, framework loaders) for server state.
- Effects synchronise with external systems only. Don't use them to derive state or respond to events;
  compute during render or handle in the event handler.
- Every effect lists its dependencies and cleans up subscriptions, timers and requests.
- Keys: stable ids, never array indexes for reorderable lists.
- Performance: measure with the Profiler first; then `memo`, `useMemo`, `useCallback` where it helps;
  virtualise long lists; split code by route.
- Forms: controlled inputs or a form library; labels for every field; errors announced.
