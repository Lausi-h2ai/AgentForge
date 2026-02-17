Task type: `refactor`

Review focus:
- Behavior preservation (no semantic drift).
- Improved readability/structure in changed scope.
- No accidental API/signature break unless requested.


Example:
Extract duplicated parsing logic into `parse_item()` while preserving public function signatures.
