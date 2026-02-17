Task type: `create_file`

Focus:
- Ensure parent directory exists (`create_directory` if needed).
- Use `write_file` with complete content in one pass when possible.
- If schema/style must match existing code, inspect nearby files first.

Done criteria:
- File exists at exact requested path.
- Content is runnable/usable, not placeholder text.
