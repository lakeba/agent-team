---
name: frontend-patterns
description: Front-end structure: components, state, data fetching, forms and performance
---
# Front-end patterns

- Components small and focused; presentational components free of data fetching.
- State lives as close to where it's used as possible; server state in a data-fetching layer
  (cache, revalidation), not copied into global stores.
- Forms: one source of truth, validation shared with the server's schema, accessible errors.
- Loading, empty and error states designed for every view.
- Performance: split code by route, lazy-load heavy parts, optimise images, avoid layout shift,
  measure with real-user metrics (LCP, INP, CLS).
- Styles from design tokens; no magic values.
