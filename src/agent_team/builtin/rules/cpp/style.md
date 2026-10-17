---
name: style
description: C++
---
- Modern C++ (C++17 or later): RAII, smart pointers, no owning raw pointers, no manual `new`/`delete`.
- `const` by default; pass large objects by const reference.
- No undefined behaviour: check bounds, initialise variables, avoid signed overflow.
- Build with warnings as errors and sanitizers in CI; tests with the project's framework.
