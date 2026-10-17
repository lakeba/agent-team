---
name: style
description: Rust
---
- `cargo fmt` and `cargo clippy` clean.
- Return `Result` with meaningful error types; no `unwrap()`/`expect()` outside tests and proven invariants.
- Prefer borrowing to cloning; keep `unsafe` out unless reviewed and commented.
- Unit tests in the module, integration tests in `tests/`.
