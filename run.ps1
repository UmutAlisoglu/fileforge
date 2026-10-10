param([switch]$Browser)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$envPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $envPython)) {
    $basePython = Get-Command python -ErrorAction SilentlyContinue
    if (-not $basePython) { throw 'Install Python 3.12 or newer, then run this launcher again.' }
    & $basePython.Source -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
    & $envPython -m pip install -r (Join-Path $PSScriptRoot 'requirements-desktop.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
if ($Browser) {
    Write-Host 'FileForge: http://127.0.0.1:8765'
    & $envPython -m uvicorn app.main:app --host 127.0.0.1 --port 8765
} else {
    & $envPython (Join-Path $PSScriptRoot 'desktop.py')
}
