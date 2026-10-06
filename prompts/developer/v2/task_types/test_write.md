Task type: `test_write`

Focus:
- Write deterministic tests with clear setup/assertions.
- Align test framework/style with repository conventions.
- Avoid flaky network/time-dependent behavior unless mocked.

Done criteria:
- Tests target explicit behavior from task.
- Assertions are specific and meaningful.
- Write only the test files assigned by CURRENT TASK. These file tools cannot
  execute tests; do not create helper scripts to simulate running them.
- After writing or inspecting the assigned tests, finish with `Thought:` and
  `Answer:` on separate lines. Do not prefix the final answer with `Action:`.


Example:
Add deterministic test: given invalid token, API returns 401 with stable error payload.
