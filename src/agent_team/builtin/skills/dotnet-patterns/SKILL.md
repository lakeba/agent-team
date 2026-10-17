---
name: dotnet-patterns
description: .NET and C# patterns: DI, async, options, EF Core, minimal APIs
---
# .NET patterns

- Nullable reference types enabled; treat warnings as errors in CI.
- Dependency injection through constructors; register lifetimes deliberately (singleton for stateless,
  scoped for per-request like DbContext, transient for light objects).
- Configuration via `IOptions<T>` bound and validated at start-up (`ValidateOnStart`).
- `async`/`await` end to end with `CancellationToken`; `ConfigureAwait(false)` in libraries.
- `IDisposable`/`IAsyncDisposable` with `using`; `IHttpClientFactory` instead of new `HttpClient`s.
- EF Core: no lazy loading surprises; project to DTOs; `AsNoTracking` for reads; migrations reviewed.
- Records for immutable data; pattern matching for variants.
- Logging with `ILogger<T>` and message templates, not string interpolation.
