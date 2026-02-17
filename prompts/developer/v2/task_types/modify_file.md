Task type: `modify_file`

Focus:
- Read target file before editing.
- Make the smallest safe edit that satisfies task constraints.
- Preserve surrounding behavior unless task asks otherwise.

Done criteria:
- Target behavior is changed exactly as requested.
- No unrelated churn.


Example:
Read `service.py`, then use `replace_text` to update only the target function without unrelated edits.
