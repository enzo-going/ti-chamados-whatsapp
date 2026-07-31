$ErrorActionPreference = "Stop"

$source = Join-Path $PSScriptRoot "dist\TI Chamados WhatsApp.exe"
if (-not (Test-Path -LiteralPath $source)) {
    throw "Build not found. Run build_windows.ps1 first."
}

$installDirectory = Join-Path $env:LOCALAPPDATA "Programs\TI Chamados WhatsApp"
$target = Join-Path $installDirectory "TI Chamados WhatsApp.exe"
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "TI Chamados WhatsApp.lnk"

New-Item -ItemType Directory -Force -Path $installDirectory | Out-Null
Copy-Item -LiteralPath $source -Destination $target -Force

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $installDirectory
$shortcut.IconLocation = "$target,0"
$shortcut.Description = "Painel local do helpdesk de TI"
$shortcut.Save()

Write-Host "Installed: $target"
Write-Host "Desktop shortcut: $shortcutPath"
