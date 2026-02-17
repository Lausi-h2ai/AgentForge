Task type: `bugfix`

Review focus:
- Fix addresses likely root cause.
- Error handling and boundary cases are covered.
- No silent failure path introduced.


Example:
Bug: null `routes` causes crash. Fix initialization path and add guard for empty input.
