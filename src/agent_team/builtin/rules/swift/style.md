---
name: style
description: Swift
---
- Follow the Swift API Design Guidelines; value types by default.
- No force unwraps or `try!` outside tests; handle optionals and errors explicitly.
- Swift concurrency (`async`/`await`, actors) for asynchronous work; UI updates on the main actor.
- XCTest or Swift Testing for tests, one behaviour each.
