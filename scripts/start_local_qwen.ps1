param(
    [int]$Port = 8080,
    [int]$ContextSize = 16384,
    [int]$GpuLayers = 28,
    [switch]$Background
)
$ErrorActionPreference = 'Stop'
if ($Port -lt 1 -or $Port -gt 65535 -or $ContextSize -lt 2048 -or $GpuLayers -lt 0) {
    throw 'Invalid port, context size, or GPU layer count.'
}
$root = Split-Path $PSScriptRoot -Parent
$runtime = Join-Path $root 'artifacts/local-llm'
$server = Join-Path $runtime 'llama-b11438/llama-server.exe'
$model = Join-Path $runtime 'models/Qwen3.5-9B-Q4_K_M.gguf'
if (!(Test-Path -LiteralPath $server) -or !(Test-Path -LiteralPath $model)) {
    throw 'Run ./scripts/setup_local_qwen.ps1 -InstallPython first.'
}
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use. Check the existing server or choose -Port."
}
$serverArgs = @(
    '--model', $model, '--alias', 'qwen3.5-9b-q4_k_m',
    '--host', '127.0.0.1', '--port', $Port,
    '--ctx-size', $ContextSize, '--parallel', '1',
    '--n-gpu-layers', $GpuLayers, '--threads', '8',
    '--batch-size', '256', '--ubatch-size', '128', '--flash-attn', 'on',
    '--reasoning', 'off', '--temp', '0.7', '--top-p', '0.8',
    '--top-k', '20', '--min-p', '0'
)
if ($Background) {
    $launchArgs = $serverArgs | ForEach-Object {
        if ("$_" -match '\s') { "`"$_`"" } else { "$_" }
    }
    $process = Start-Process -FilePath $server -ArgumentList $launchArgs -WorkingDirectory $runtime `
        -WindowStyle Hidden -PassThru -RedirectStandardOutput "$runtime/server.stdout.log" `
        -RedirectStandardError "$runtime/server.stderr.log"
    $process.Id | Set-Content "$runtime/server.pid"
    Write-Host "Started PID $($process.Id). Health: http://127.0.0.1:$Port/health"
} else {
    & $server @serverArgs
    if ($LASTEXITCODE -ne 0) { throw "llama-server exited with code $LASTEXITCODE" }
}
