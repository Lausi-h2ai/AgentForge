# Demo Run

The fastest way to try the orchestrator is to run the included public demo prompt.

## Command

```bash
python orchestrator.py demo_project --prompt examples/prompts/demo_prompt.txt --new
```

## PowerShell helper

From the repo root:

```powershell
.\scripts\demo_run.ps1
```

## Expected outcome

- a generated project workspace under `projects/demo_project/workspace/`
- saved state and checkpoints under `projects/demo_project/`
- logs under `logs/`

## Notes

- Add `--with-tests` to run the optional testing stage.
- Add `--google` to switch providers if you installed the Google extra and configured credentials.
- Use the prompt in `examples/prompts/demo_prompt.txt` as a starting point for your own experiments.
