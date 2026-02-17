Task type: `refactor`

Focus:
- Improve structure/readability without changing behavior.
- Prefer mechanical-safe edits (rename/move/extract) using existing tools.
- Keep public interfaces stable unless explicitly requested.

Done criteria:
- Behavior preserved.
- Duplication/complexity reduced in changed scope.


Example:
Extract duplicated parsing logic into `parse_item()` while preserving public function signatures.
