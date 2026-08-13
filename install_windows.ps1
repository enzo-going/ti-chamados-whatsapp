$ErrorActionPreference = "Stop"

$source = Join-Path $PSScriptRoot "dist\TI Chamados WhatsApp.exe"
if (-not (Test-Path -LiteralPath $source)) {
    throw "Build not found. Run build_windows.ps1 first."
}
$iconSource = Join-Path $PSScriptRoot "assets\app-icon-v2.ico"
if (-not (Test-Path -LiteralPath $iconSource)) {
    throw "Application icon not found."
}

$installDirectory = Join-Path $env:LOCALAPPDATA "Programs\TI Chamados WhatsApp"
$target = Join-Path $installDirectory "TI Chamados WhatsApp.exe"
$iconTarget = Join-Path $installDirectory "app-icon-v2.ico"
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "TI Chamados WhatsApp.lnk"

New-Item -ItemType Directory -Force -Path $installDirectory | Out-Null
Copy-Item -LiteralPath $source -Destination $target -Force
Copy-Item -LiteralPath $iconSource -Destination $iconTarget -Force

if (Test-Path -LiteralPath $shortcutPath) {
    Remove-Item -LiteralPath $shortcutPath -Force
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $installDirectory
$shortcut.IconLocation = "$iconTarget,0"
$shortcut.Description = "Painel local do helpdesk de TI"
$shortcut.Save()

Write-Host "Installed: $target"
Write-Host "Desktop shortcut: $shortcutPath"
