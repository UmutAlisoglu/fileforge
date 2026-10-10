param([string]$Python = '.venv/Scripts/python.exe', [string]$WorkDirectory = '.build')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$resolvedPython = (Resolve-Path -LiteralPath $Python).Path
New-Item -ItemType Directory -Force -Path $WorkDirectory | Out-Null
$resolvedWork = (Resolve-Path -LiteralPath $WorkDirectory).Path
$staticArgument = (Join-Path $PSScriptRoot 'app/static') + ';app/static'
& $resolvedPython (Join-Path $PSScriptRoot 'tools/make_icon.py')
& $resolvedPython -m PyInstaller --noconfirm --onefile --windowed --name FileForge --icon (Join-Path $PSScriptRoot 'assets/fileforge.ico') --distpath (Join-Path $PSScriptRoot 'release') --workpath (Join-Path $resolvedWork 'pyinstaller') --specpath $resolvedWork --add-data $staticArgument --collect-data reportlab --hidden-import uvicorn.logging --hidden-import uvicorn.loops.auto --hidden-import uvicorn.protocols.http.h11_impl --hidden-import uvicorn.lifespan.on --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module PySide2 --exclude-module PySide6 --exclude-module pandas --exclude-module matplotlib --exclude-module scipy --exclude-module numpy --exclude-module IPython (Join-Path $PSScriptRoot 'desktop.py')
if ($LASTEXITCODE -ne 0) { throw 'Windows executable build failed.' }
& $resolvedPython (Join-Path $PSScriptRoot 'tools/third_party_notices.py')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'installer/install.cmd'), (Join-Path $PSScriptRoot 'installer/install.ps1'), (Join-Path $PSScriptRoot 'installer/uninstall.ps1') -Destination (Join-Path $PSScriptRoot 'release')
Write-Host 'Build complete. Open release/install.cmd to install FileForge.'
