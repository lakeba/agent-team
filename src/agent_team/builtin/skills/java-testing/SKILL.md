---
name: java-testing
description: Testing Java with JUnit 5, AssertJ and Mockito
---
# Java testing

- JUnit 5 with descriptive `@DisplayName` or method names; `@ParameterizedTest` for tables.
- AssertJ for readable assertions.
- Mockito at boundaries; verify interactions only when the interaction is the behaviour.
- Spring: slice tests (`@WebMvcTest`, `@DataJpaTest`) before full `@SpringBootTest`; Testcontainers for real databases.
