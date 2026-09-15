# Build the PhotoSync Windows release.
#   1. PyInstaller bundle -> dist\PhotoSync\
#   2. Inno Setup installer -> installer\output\  (if iscc is installed)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

& "$root\desktop\.venv\Scripts\pyinstaller" --noconfirm --distpath "$root\dist" `
    --workpath "$root\build" "$root\installer\photosync.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Write-Host "Bundle: $root\dist\PhotoSync\PhotoSync.exe"

$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if ($iscc) {
    & $iscc "$root\installer\PhotoSync.iss"
    Write-Host "Installer: $root\installer\output\"
} else {
    Write-Host "Inno Setup (iscc) not found - skipped installer compilation."
    Write-Host "Install from https://jrsoftware.org/isinfo.php and re-run."
}
