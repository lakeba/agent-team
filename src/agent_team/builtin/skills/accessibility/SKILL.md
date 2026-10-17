---
name: accessibility
description: Building accessible interfaces: semantics, keyboard, focus, contrast, testing
---
# Accessibility

- Use semantic HTML first: `button` for actions, `a` for navigation, `label` for inputs, headings in order,
  lists for lists, `table` for tabular data. ARIA only where HTML has no equivalent.
- Every interactive element: reachable by Tab in a logical order, operable with Enter/Space,
  with a visible focus style and an accessible name.
- Dialogs trap focus while open and return it on close; Escape closes them.
- Contrast: 4.5:1 for text, 3:1 for large text and UI parts. Never rely on colour alone.
- Images: meaningful `alt`, or `alt=""` if decorative. Icons-only buttons get `aria-label`.
- Forms: errors next to the field, linked with `aria-describedby`, announced, and keep the input.
- Respect `prefers-reduced-motion`.
- Test with the keyboard only, a screen reader, and an automated checker (axe); automated tools catch
  only part of the problems.
