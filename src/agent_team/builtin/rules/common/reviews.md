---
name: reviews
description: What a review checks
---
- Does the change do what the task asked, and nothing it didn't ask?
- Is it correct at the edges: empty input, very large input, errors, concurrency, time zones?
- Is every new behaviour tested, and would the tests fail if the code were wrong?
- Is anything security-sensitive touched (input handling, auth, secrets, files, shell)?
- Will the next person understand it? Names, structure, a comment where the why isn't obvious.
- Block for correctness, security and missing tests. Style preferences are notes, not blockers.
