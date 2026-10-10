$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$appArgs = $args
$python = Join-Path $PWD '.venv\Scripts\python.exe'

try {
    if (Test-Path $python) {
        & $python scripts/bootstrap.py --check
        if ($LASTEXITCODE -eq 0) {
            & $python launch.py @appArgs
            exit $LASTEXITCODE
        }
    }

    Write-Host 'First-time setup: preparing Python and dependencies. Keep this window open.'
    $env:UV_UNMANAGED_INSTALL = Join-Path $PWD '.bootstrap\bin'
    $env:UV_INSTALLER_GITHUB_BASE_URL = 'https://github.com'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $PWD '.bootstrap\python'
    $env:UV_CACHE_DIR = Join-Path $PWD '.bootstrap\cache'
    $env:UV_PYTHON_INSTALL_BIN = '0'
    $env:UV_PYTHON_INSTALL_REGISTRY = '0'
    $env:UV_NO_CONFIG = '1'
    $uv = Join-Path $env:UV_UNMANAGED_INSTALL 'uv.exe'
    if (-not (Test-Path $uv)) {
        New-Item -ItemType Directory -Force .bootstrap | Out-Null
        Invoke-WebRequest -UseBasicParsing 'https://astral.sh/uv/0.13.0/install.ps1' -OutFile .bootstrap/install-uv.ps1
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File .bootstrap/install-uv.ps1
        if ($LASTEXITCODE -ne 0) { throw 'Could not install the setup tool.' }
        Remove-Item .bootstrap/install-uv.ps1
    }
    Write-Host 'Preparing Python 3.12...'
    & $uv python install 3.12
    if ($LASTEXITCODE -ne 0) { throw 'Could not download Python. Check your connection and run start.bat again.' }
    $bootstrapPython = & $uv python find --managed-python --no-project --system 3.12
    if ($LASTEXITCODE -ne 0) { throw 'Could not locate Python 3.12.' }
    & $bootstrapPython scripts/bootstrap.py --uv $uv @appArgs
    exit $LASTEXITCODE
} catch {
    Write-Host "JingWei could not start: $_"
    Write-Host 'See Troubleshooting in README.md.'
    exit 1
}
