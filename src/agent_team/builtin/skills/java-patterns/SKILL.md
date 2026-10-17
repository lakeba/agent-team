---
name: java-patterns
description: Java patterns: immutability, records, streams, exceptions, Spring
---
# Java patterns

- Records for immutable data; `final` fields; defensive copies of collections (`List.copyOf`).
- Optional for absent return values, never for fields or parameters.
- Streams for clear transformations; plain loops when they read better or performance matters.
- Checked exceptions for recoverable conditions callers must handle; runtime exceptions for bugs.
- try-with-resources for anything closeable.
- Spring: constructor injection, configuration properties classes, transactions on service methods,
  no business logic in controllers.
