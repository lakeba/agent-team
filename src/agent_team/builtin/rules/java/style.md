---
name: style
description: Java
---
- Follow the project's formatter and naming conventions; small classes with one responsibility.
- Prefer immutable objects and `final` fields; use records for plain data.
- Don't return `null` for collections; use `Optional` for absent single values at API boundaries.
- Close resources with try-with-resources. Catch specific exceptions.
- JUnit 5 tests, one behaviour each, with descriptive names.
