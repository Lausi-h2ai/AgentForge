# Demo run (PowerShell)
# Usage: .\scripts\demo_run.ps1

$ErrorActionPreference = 'Stop'

$promptPath = Join-Path $PSScriptRoot '..\demo_prompt.txt'
@"
Build a tiny FastAPI app with one endpoint GET /health that returns {\"status\":\"ok\"}.
Add a README with setup instructions.
"@ | Set-Content -Encoding UTF8 $promptPath

python ..\orchestrator.py demo_project --prompt $promptPath --new
