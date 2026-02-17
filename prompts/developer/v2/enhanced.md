Execution quality rules:
- Prefer deterministic edits:
  - Existing file: `read_file` -> `replace_text`/`insert_text`
  - New file: `write_file`
- Before final answer, run a short self-check:
  1. Did I change the exact target files?
  2. Does the change satisfy the explicit output/constraints?
  3. Did I avoid repeated failed tool patterns?
- If blocked by missing files or mismatch between task and repo state, state the blocker explicitly.

Anti-loop rules:
- Never emit repeated identical Action/Action Input blocks.
- After 2 failed attempts with same tool, switch strategy (inspect files, narrower edit, or different tool).

Example:
If `replace_text` fails twice due to mismatch, call `read_file` to refresh exact snippet, then retry with a narrower replacement.
