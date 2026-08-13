param([switch]$Install)

$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot
try {
    $buildEnvironment = Join-Path $PSScriptRoot ".venv-build"
    $buildPython = Join-Path $buildEnvironment "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $buildPython)) {
        python -m venv $buildEnvironment
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create the isolated build environment."
        }
    }

    & $buildPython -m pip install --disable-pip-version-check -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Could not install the isolated build dependency."
    }

    & $buildPython -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --icon (Join-Path $PSScriptRoot "assets\app-icon-v2.ico") `
        --name "TI Chamados WhatsApp" `
        desktop_app.py
    if ($LASTEXITCODE -ne 0) {
        throw "The Windows build failed."
    }

    $builtExecutable = Join-Path $PSScriptRoot "dist\TI Chamados WhatsApp.exe"
    $smoke = Start-Process `
        -FilePath $builtExecutable `
        -ArgumentList "--smoke-test" `
        -WindowStyle Hidden `
        -Wait `
        -PassThru
    if ($smoke.ExitCode -ne 0) {
        throw "The packaged application failed its smoke test."
    }

    Write-Host "Build created and validated: dist\TI Chamados WhatsApp.exe"
    if ($Install) {
        & (Join-Path $PSScriptRoot "install_windows.ps1")
    }
}
finally {
    Pop-Location
}
