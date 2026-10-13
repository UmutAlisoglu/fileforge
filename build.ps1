param([string]$Python = '.venv/Scripts/python.exe', [string]$WorkDirectory = '.build')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$resolvedPython = (Resolve-Path -LiteralPath $Python).Path
New-Item -ItemType Directory -Force -Path $WorkDirectory | Out-Null
$resolvedWork = (Resolve-Path -LiteralPath $WorkDirectory).Path
$staticArgument = (Join-Path $PSScriptRoot 'app/static') + ';app/static'
$modelsDirectory = Join-Path $PSScriptRoot 'app/models'
$modelPath = Join-Path $modelsDirectory 'u2netp.onnx'
if (-not (Test-Path -LiteralPath $modelPath)) { throw 'The offline background model is missing. See app/models/README.md.' }
if ((Get-FileHash -LiteralPath $modelPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne '309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8') { throw 'The background model checksum does not match the published model.' }
$modelsArgument = $modelsDirectory + ';app/models'
& $resolvedPython (Join-Path $PSScriptRoot 'tools/make_icon.py')
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed.' }
& $resolvedPython -m PyInstaller --noconfirm --onefile --windowed --name FileForge --icon (Join-Path $PSScriptRoot 'assets/fileforge.ico') --distpath (Join-Path $PSScriptRoot 'release') --workpath (Join-Path $resolvedWork 'pyinstaller') --specpath $resolvedWork --add-data $staticArgument --add-data $modelsArgument --collect-data reportlab --collect-binaries onnxruntime --collect-data onnxruntime --collect-binaries vtracer --collect-data vtracer --collect-binaries pypdfium2_raw --collect-data pypdfium2_raw --hidden-import vtracer.vtracer --hidden-import pypdfium2_raw --hidden-import uvicorn.logging --hidden-import uvicorn.loops.auto --hidden-import uvicorn.protocols.http.h11_impl --hidden-import uvicorn.lifespan.on --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module PySide2 --exclude-module PySide6 --exclude-module pandas --exclude-module matplotlib --exclude-module scipy --exclude-module IPython (Join-Path $PSScriptRoot 'desktop.py')
if ($LASTEXITCODE -ne 0) { throw 'Windows executable build failed.' }
& $resolvedPython (Join-Path $PSScriptRoot 'tools/third_party_notices.py')
if ($LASTEXITCODE -ne 0) { throw 'Third-party notice generation failed.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'installer/install.cmd'), (Join-Path $PSScriptRoot 'installer/install.ps1'), (Join-Path $PSScriptRoot 'installer/uninstall.ps1') -Destination (Join-Path $PSScriptRoot 'release')
Write-Host 'Build complete. Open release/install.cmd to install FileForge.'
