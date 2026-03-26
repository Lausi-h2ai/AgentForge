# Security Policy

## Reporting a vulnerability

Do not open a public issue for a suspected security problem.

Instead, contact the maintainers privately with:

- a short description of the issue
- affected files or components
- reproduction steps
- impact assessment

## Scope

Security-sensitive areas in this repository include:

- file and path handling in the tool layer
- prompt and tool execution boundaries
- environment-variable handling
- Git workspace mutation and rollback behavior
- any future network-enabled integrations

## Operational guidance

- Never commit real API keys, tokens, or private prompts.
- Keep `.env` local and use `.env.example` for documentation only.
- Treat generated projects and logs as runtime artifacts, not public source.
