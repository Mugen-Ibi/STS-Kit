$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot '.cache/uv'
$uv = (Get-Command uv -ErrorAction Stop).Source
$revision = '074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc'
if (!(Test-Path 'vendor/CosyVoice/.git')) {
    git clone https://github.com/QwenAudio/CosyVoice.git vendor/CosyVoice
    if ($LASTEXITCODE) { throw 'CosyVoiceコードの取得に失敗しました。' }
    git -C vendor/CosyVoice checkout $revision
    if ($LASTEXITCODE) { throw '固定リビジョンの取得に失敗しました。' }
}
$actual = git -C vendor/CosyVoice rev-parse HEAD
if ($actual -ne $revision) { throw 'vendor/CosyVoiceのリビジョンが異なります。ローカル変更を確認してください。' }
git -C vendor/CosyVoice submodule update --init --recursive
if ($LASTEXITCODE) { throw '依存コードの取得に失敗しました。' }
if (!(Test-Path '.venv-cosy/Scripts/python.exe')) {
    & $uv venv --python 3.12 .venv-cosy
    if ($LASTEXITCODE) { throw '環境作成に失敗しました。' }
}
& $uv pip install --python .venv-cosy/Scripts/python.exe torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE) { throw 'PyTorch導入に失敗しました。' }
$requirements = if (Test-Path 'requirements-cosy.lock.txt') { 'requirements-cosy.lock.txt' } else { 'requirements-cosy.txt' }
& $uv pip install --python .venv-cosy/Scripts/python.exe -r $requirements --build-constraint constraints-cosy-build.txt
if ($LASTEXITCODE) { throw '依存ライブラリの導入に失敗しました。' }
& .venv-cosy/Scripts/python.exe -X utf8 scripts/download_cosyvoice.py
if ($LASTEXITCODE) { throw 'モデルの取得に失敗しました。' }
& .venv/Scripts/python.exe -X utf8 scripts/prepare_cosy_reference.py
if ($LASTEXITCODE) { throw '合成参照音声の準備に失敗しました。先にsetup.ps1を実行してください。' }
Write-Host 'CosyVoice3を準備しました。アプリを再起動して選択してください。'
