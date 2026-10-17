---
name: style
description: C# and .NET
---
- Follow the .NET naming conventions and the project's `.editorconfig`.
- Nullable reference types on; don't silence warnings with `!` without reason.
- `async` all the way: no `.Result` or `.Wait()`; pass `CancellationToken` through.
- Dispose what you open (`using`); prefer `IOptions`/DI over static configuration.
- Tests with the project's framework (xUnit, NUnit, MSTest); one behaviour per test.
