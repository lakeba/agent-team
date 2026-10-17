---
name: dotnet-testing
description: Testing .NET code with xUnit, NUnit or MSTest
---
# .NET testing

- Match the project's framework. Arrange-act-assert, one behaviour per test, names like
  `Method_State_Expected`.
- `[Theory]`/`[InlineData]` (xUnit) or `[TestCase]` (NUnit) for tables.
- Integration tests for ASP.NET Core with `WebApplicationFactory`; databases with Testcontainers or
  SQLite in-memory where behaviour matches.
- Fakes for time (`TimeProvider`) and external services; avoid mocking `DbContext`.
- Async tests return `Task`; never `.Result`.
