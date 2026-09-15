# Build the PhotoSync Windows release.
#   1. PyInstaller bundle -> dist\PhotoSync\
#   2. Inno Setup installer -> installer\output\  (if iscc is installed)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

& "$root\desktop\.venv\Scripts\pyinstaller" --noconfirm --distpath "$root\dist" `
    --workpath "$root\build" "$root\installer\photosync.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Write-Host "Bundle: $root\dist\PhotoSync\PhotoSync.exe"

$canSign = $env:CODESIGN_THUMBPRINT -or $env:CODESIGN_PFX
if ($canSign) {
    & powershell -File "$root\installer\sign.ps1" "$root\dist\PhotoSync\PhotoSync.exe"
} else {
    Write-Host "No CODESIGN_* credentials set - exe left unsigned (SmartScreen will warn)."
}

$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if ($iscc) {
    & $iscc "$root\installer\PhotoSync.iss"
    $setup = Get-ChildItem "$root\installer\output\PhotoSync-*-Setup.exe" |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($canSign -and $setup) {
        & powershell -File "$root\installer\sign.ps1" $setup.FullName
    }
    Write-Host "Installer: $root\installer\output\"
} else {
    Write-Host "Inno Setup (iscc) not found - skipped installer compilation."
    Write-Host "Install from https://jrsoftware.org/isinfo.php and re-run."
}
