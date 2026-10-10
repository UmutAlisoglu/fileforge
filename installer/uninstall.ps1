$ErrorActionPreference = 'Stop'
$installRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$markerPath = Join-Path $installRoot '.fileforge-install'
if (-not (Test-Path -LiteralPath $markerPath)) { throw 'This is not a verified FileForge installation folder.' }
$marker = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json
if ($marker.app -ne 'FileForge' -or [System.IO.Path]::GetFullPath($marker.installPath) -ne $installRoot) {
    throw 'Installation path verification failed. No files were removed.'
}
$running = Get-Process -Name FileForge -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq (Join-Path $installRoot 'FileForge.exe') }
if ($running) { throw 'Close FileForge before uninstalling it.' }
$reply = Read-Host 'Uninstall FileForge? Type YES to continue'
if ($reply -ne 'YES') { exit }
$shortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'FileForge.lnk'
if (Test-Path -LiteralPath $shortcut) {
    $shellObject = New-Object -ComObject WScript.Shell
    if ($shellObject.CreateShortcut($shortcut).TargetPath -eq (Join-Path $installRoot 'FileForge.exe')) { Remove-Item -LiteralPath $shortcut -Force }
}
$registryPath = 'HKCU:/Software/Microsoft/Windows/CurrentVersion/Uninstall/FileForge'
if (Test-Path -LiteralPath $registryPath) {
    if ((Get-ItemProperty -Path $registryPath).InstallLocation -eq $installRoot) { Remove-Item -LiteralPath $registryPath -Recurse }
}
# Resolved absolute directory matched the installation marker before this recursive removal.
Remove-Item -LiteralPath $installRoot -Recurse -Force
Write-Host 'FileForge uninstalled.'
