$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot '.cache/uv'
$env:PYTHONUTF8 = '1'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv: https://docs.astral.sh/uv/getting-started/installation/' }
if (-not (Test-Path .venv/Scripts/python.exe)) {
    uv venv --python 3.11 .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
}
uv pip install --python .venv/Scripts/python.exe 'torch==2.8.0' --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { throw 'PyTorch installation failed.' }
$requirements = if (Test-Path requirements.lock.txt) { 'requirements.lock.txt' } else { 'requirements.txt' }
uv pip install --python .venv/Scripts/python.exe -r $requirements
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& .venv/Scripts/python.exe -X utf8 scripts/download_models.py
if ($LASTEXITCODE -ne 0) { throw 'Model download failed.' }
& .venv/Scripts/python.exe -X utf8 scripts/prepare_bert.py
if ($LASTEXITCODE -ne 0) { throw 'BERT preparation failed.' }
Write-Host 'Setup complete. Double-click Start-STS.cmd.'
