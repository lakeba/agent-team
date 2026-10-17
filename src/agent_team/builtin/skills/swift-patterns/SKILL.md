---
name: swift-patterns
description: Swift and SwiftUI patterns: value types, optionals, concurrency, state
---
# Swift patterns

- Structs and enums by default; classes when identity or reference semantics are needed.
- Optionals handled with `if let`/`guard let`; errors with `throws` and typed handling.
- Swift concurrency: `async`/`await`, `Task` groups, actors for shared mutable state, `@MainActor` for UI.
- SwiftUI: small views; state with `@State` for local, `@Observable` models for shared; no heavy work in `body`.
- Protocols for abstraction; extensions to organise conformances.
