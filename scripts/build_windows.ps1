$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "Create .venv and install the packaging extra first; see README.md."
}

& $PythonPath -m pytest -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Push-Location (Join-Path $ProjectRoot "packaging")
try {
    & $PythonPath -m PyInstaller --noconfirm --clean --distpath "..\dist" --workpath "..\build" "SilverStar_FLP.spec"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
