param(
    [string]$InstallDirectory = (Join-Path $env:LOCALAPPDATA 'Programs/FileForge'),
    [switch]$SkipShortcuts,
    [switch]$SkipLaunch,
    [switch]$SkipRegistration
)
$ErrorActionPreference = 'Stop'
$sourceExe = Join-Path $PSScriptRoot 'FileForge.exe'
if (-not (Test-Path -LiteralPath $sourceExe)) { throw 'Keep install.cmd beside FileForge.exe in the release folder.' }
$workspaceSource = Join-Path $PSScriptRoot 'workspace'
if (-not (Test-Path -LiteralPath (Join-Path $workspaceSource 'workspace-manifest.json'))) { throw 'Keep the workspace folder beside FileForge.exe. Extract the complete ZIP first.' }
$installRoot = [System.IO.Path]::GetFullPath($InstallDirectory)
$marker = Join-Path $installRoot '.fileforge-install'
if ((Test-Path -LiteralPath $installRoot) -and -not (Test-Path -LiteralPath $marker) -and @(Get-ChildItem -LiteralPath $installRoot -Force).Count -gt 0) {
    throw 'The installation folder contains unrelated files. Choose an empty folder.'
}
New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
$runningApp = Get-Process -Name FileForge -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq (Join-Path $installRoot 'FileForge.exe') }
if ($runningApp) { throw 'Close FileForge before installing this update.' }
Copy-Item -LiteralPath $sourceExe -Destination (Join-Path $installRoot 'FileForge.exe') -Force
Copy-Item -LiteralPath $workspaceSource -Destination $installRoot -Recurse -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'uninstall.ps1') -Destination $installRoot -Force
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'THIRD_PARTY_NOTICES.txt')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'THIRD_PARTY_NOTICES.txt') -Destination $installRoot -Force
}
@{ installPath = $installRoot; app = 'FileForge'; version = '0.3.0' } | ConvertTo-Json | Set-Content -LiteralPath $marker -Encoding UTF8
if (-not $SkipShortcuts) {
    $shellObject = New-Object -ComObject WScript.Shell
    $startMenu = [Environment]::GetFolderPath('Programs')
    $shortcut = $shellObject.CreateShortcut((Join-Path $startMenu 'FileForge.lnk'))
    $shortcut.TargetPath = Join-Path $installRoot 'FileForge.exe'
    $shortcut.WorkingDirectory = $installRoot
    $shortcut.Description = 'Private video, spreadsheet, image and PDF tools'
    $shortcut.Save()
}
if (-not $SkipRegistration) {
    $registryPath = 'HKCU:/Software/Microsoft/Windows/CurrentVersion/Uninstall/FileForge'
    New-Item -Path $registryPath -Force | Out-Null
    New-ItemProperty -Path $registryPath -Name DisplayName -Value 'FileForge' -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $registryPath -Name DisplayVersion -Value '0.3.0' -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $registryPath -Name InstallLocation -Value $installRoot -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $registryPath -Name DisplayIcon -Value (Join-Path $installRoot 'FileForge.exe') -PropertyType String -Force | Out-Null
    $uninstallCommand = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $installRoot 'uninstall.ps1') + '"'
    New-ItemProperty -Path $registryPath -Name UninstallString -Value $uninstallCommand -PropertyType String -Force | Out-Null
}
Write-Host "FileForge installed in $installRoot"
if (-not $SkipLaunch) { Start-Process -FilePath (Join-Path $installRoot 'FileForge.exe') -WindowStyle Hidden }
