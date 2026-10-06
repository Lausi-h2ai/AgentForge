param([switch]$InstallPython)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$runtime = Join-Path $root 'artifacts/local-llm'
$build = 'b11438'
$modelName = 'Qwen3.5-9B-Q4_K_M.gguf'
$modelHash = '03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8'
New-Item -ItemType Directory -Force "$runtime/models", "$runtime/downloads", "$runtime/llama-$build" | Out-Null
function Get-Download($url, $path, $expectedBytes) {
    if ((Test-Path -LiteralPath $path) -and (Get-Item -LiteralPath $path).Length -eq $expectedBytes) {
        return
    }
    & curl.exe --location --fail --retry 5 --continue-at - --output $path $url
    if ($LASTEXITCODE -ne 0) { throw "Download failed: $url" }
}
$model = Join-Path $runtime "models/$modelName"
Get-Download "https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/$modelName" $model 5680522464
if ((Get-FileHash -LiteralPath $model -Algorithm SHA256).Hash.ToLowerInvariant() -ne $modelHash) {
    throw 'Model checksum mismatch. Remove the corrupt GGUF and run setup again.'
}
$archives = @{
    'llama-cuda.zip' = "llama-$build-bin-win-cuda-12.4-x64.zip"
    'cudart.zip' = 'cudart-llama-bin-win-cuda-12.4-x64.zip'
}
$archiveSizes = @{'llama-cuda.zip' = 264473590; 'cudart.zip' = 391443627}
foreach ($name in $archives.Keys) {
    $archive = Join-Path $runtime "downloads/$name"
    Get-Download "https://github.com/ggml-org/llama.cpp/releases/download/$build/$($archives[$name])" $archive $archiveSizes[$name]
    $marker = if ($name -eq 'llama-cuda.zip') { 'ggml-cuda.dll' } else { 'cublas64_12.dll' }
    if (!(Test-Path -LiteralPath "$runtime/llama-$build/$marker")) {
        Expand-Archive -LiteralPath $archive -DestinationPath "$runtime/llama-$build" -Force
    }
}
if ($InstallPython) {
    Push-Location $root
    try {
        if (!(Test-Path .venv/Scripts/python.exe)) {
            & uv venv .venv --python 3.12
            if ($LASTEXITCODE -ne 0) { throw 'Virtual environment setup failed.' }
        }
        & uv pip install --python .venv/Scripts/python.exe -e '.[dev,openai]' pillow pip
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    } finally { Pop-Location }
}
Write-Host 'Setup complete. Start with ./scripts/start_local_qwen.ps1'
