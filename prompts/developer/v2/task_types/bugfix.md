Task type: `bugfix`

Focus:
- Identify failing path from task context and impacted file(s).
- Apply root-cause fix, not symptom-only patch.
- Add or update tests if task scope includes tests.

Done criteria:
- Fix addresses described failure path.
- Edge case handling is explicit where relevant.


Example:
Bug: null `routes` causes crash. Fix initialization path and add guard for empty input.
