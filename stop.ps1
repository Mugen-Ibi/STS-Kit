$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') -X utf8 (Join-Path $PSScriptRoot 'scripts/stop.py')
if ($LASTEXITCODE -ne 0) { throw 'Could not stop the managed STS processes.' }
