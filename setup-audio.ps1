$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot '.cache/uv'
$uv = (Get-Command uv -ErrorAction Stop).Source
if (!(Test-Path '.venv-audio/Scripts/python.exe')) {
    & $uv venv --python 3.12 .venv-audio
    if ($LASTEXITCODE) { throw 'Python環境の作成に失敗しました。' }
}
& $uv pip install --python .venv-audio/Scripts/python.exe torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE) { throw 'PyTorchの導入に失敗しました。' }
$requirements = if (Test-Path 'requirements-audio.lock.txt') { 'requirements-audio.lock.txt' } else { 'requirements-audio.txt' }
& $uv pip install --python .venv-audio/Scripts/python.exe -r $requirements
if ($LASTEXITCODE) { throw '音声ライブラリの導入に失敗しました。' }
& .venv-audio/Scripts/python.exe -X utf8 scripts/download_audio_models.py
if ($LASTEXITCODE) { throw 'モデルのダウンロードに失敗しました。' }
Write-Host '追加音声モデルを準備しました。Start-STS.cmd で起動できます。'
