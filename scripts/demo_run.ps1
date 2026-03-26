# Demo run (PowerShell)
# Usage: .\scripts\demo_run.ps1

$ErrorActionPreference = 'Stop'

$rootPath = Resolve-Path (Join-Path $PSScriptRoot '..')
$promptPath = Join-Path $rootPath 'examples\prompts\demo_prompt.txt'

if (-not (Test-Path $promptPath)) {
    throw "Demo prompt not found at $promptPath"
}

python (Join-Path $rootPath 'orchestrator.py') demo_project --prompt $promptPath --new
