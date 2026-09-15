# Authenticode-sign a file with signtool.
#
# Configure ONE of these (environment variables, never committed):
#   CODESIGN_THUMBPRINT       SHA-1 thumbprint of a cert in the CurrentUser
#                             store (EV token, or Azure Trusted Signing cert)
#   CODESIGN_PFX +            path to a .pfx file and its password
#   CODESIGN_PFX_PASSWORD
#
# Usage:  powershell -File installer\sign.ps1 <file> [<file> ...]
param([Parameter(Mandatory, ValueFromRemainingArguments)][string[]]$Files)
$ErrorActionPreference = "Stop"

function Find-SignTool {
    $cmd = Get-Command signtool -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $kits = "C:\Program Files (x86)\Windows Kits\10\bin"
    if (Test-Path $kits) {
        $found = Get-ChildItem "$kits\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending | Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    throw "signtool.exe not found. Install the Windows SDK (Signing Tools component)."
}

$signtool = Find-SignTool
$timestamp = "http://timestamp.digicert.com"

foreach ($file in $Files) {
    if (-not (Test-Path $file)) { throw "Not found: $file" }
    if ($env:CODESIGN_THUMBPRINT) {
        & $signtool sign /fd SHA256 /td SHA256 /tr $timestamp `
            /sha1 $env:CODESIGN_THUMBPRINT $file
    } elseif ($env:CODESIGN_PFX) {
        & $signtool sign /fd SHA256 /td SHA256 /tr $timestamp `
            /f $env:CODESIGN_PFX /p $env:CODESIGN_PFX_PASSWORD $file
    } else {
        throw "No signing credentials. Set CODESIGN_THUMBPRINT or CODESIGN_PFX (+_PASSWORD)."
    }
    if ($LASTEXITCODE -ne 0) { throw "Signing failed for $file" }
    & $signtool verify /pa $file
    Write-Host "Signed: $file"
}
