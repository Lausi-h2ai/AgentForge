Task type: `create_file`

Focus:
- Ensure parent directory exists (`create_directory` if needed).
- Use `write_file` with complete content in one pass when possible.
- If schema/style must match existing code, inspect nearby files first.

Done criteria:
- File exists at exact requested path.
- Content is runnable/usable, not placeholder text.
- Create only the file(s) assigned by CURRENT TASK. Project requirements describe
  the whole project; later tasks create their own files.
- These file tools cannot execute commands or tests. Do not create test runners
  or verification scripts to simulate execution.
- Once the assigned files are written successfully, finish with `Thought:` and
  `Answer:` on separate lines, with a brief description of the change. Do not
  prefix the final answer with `Action:`.


Example:
Task asks for `api/client.js` -> ensure directory exists, then write full file content in one `write_file` call.
