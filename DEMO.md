# Demo: 60-Second Smoke Run

This demo runs a tiny project through the pipeline to show planning, dev, review, and state saving.

## 1) Create a tiny prompt
```
Build a tiny FastAPI app with one endpoint GET /health that returns {"status":"ok"}.
Add a README with setup instructions.
```

Save as `demo_prompt.txt`.

## 2) Run orchestrator
```
python orchestrator.py demo_project --prompt demo_prompt.txt --new
```

Optional: use different models for planning vs execution
```
python orchestrator.py demo_project --prompt demo_prompt.txt --new \
  --planning-model qwen2.5:latest \
  --execution-model qwen3-coder:latest
```

## 3) Inspect output
- Project code: `projects/demo_project/workspace/`
- State: `projects/demo_project/state.json`
- Logs: `logs/`

## Expected outcome
- `backend/app/main.py` (or equivalent) with `/health` endpoint
- README created
- Review completed with confidence score
