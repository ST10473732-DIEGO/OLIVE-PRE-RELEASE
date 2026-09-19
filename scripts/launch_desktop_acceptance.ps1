# Explicit user entry point. Starts only isolated Electron; no target or input is automated.
param([switch]$AttachDiagnostics, [switch]$AccessibleTarget)
$ErrorActionPreference = 'Stop'
$acceptanceRoot = Split-Path -Parent $PSScriptRoot
$acceptanceIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$acceptancePrincipal = [Security.Principal.WindowsPrincipal]::new($acceptanceIdentity)
if ($acceptancePrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this acceptance session without administrator privileges.'
}
$acceptanceElectron = Join-Path $acceptanceRoot 'desktop/node_modules/electron/dist/electron.exe'
$acceptanceTarget = Join-Path $acceptanceRoot 'scripts/m2_desktop_acceptance_window.py'
if ($AccessibleTarget) {
    $acceptanceTarget = Join-Path $acceptanceRoot 'scripts/m2_accessible_acceptance_window.py'
}
if (!(Test-Path -LiteralPath $acceptanceElectron) -or !(Test-Path -LiteralPath $acceptanceTarget)) {
    throw 'Build the repository desktop application and verify the acceptance target first.'
}
$acceptanceProfile = Join-Path ([IO.Path]::GetTempPath()) ('olive-owned-desktop-live-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $acceptanceProfile | Out-Null
Write-Host "Isolated profile: $acceptanceProfile"
Write-Host "Target for the native file chooser: $acceptanceTarget"
if ($AccessibleTarget) {
    Write-Host 'Follow docs/releases/3.5.1/M2_ACCESSIBLE_INPUT.md. No target has been launched.'
    Write-Host 'Keyboard Ask only with user approval; mouse Deny; screen/vision off.'
} else {
    Write-Host 'Follow docs/releases/3.5.1/DESKTOP-OWNED-MANUAL-CHECK.md. No target has been launched.'
}
$acceptancePreviousProfile = $env:OLIVE_DATA_DIR
$acceptancePreviousDiagnostics = $env:OLIVE_ATTACH_DIAGNOSTICS
try {
    $env:OLIVE_DATA_DIR = $acceptanceProfile
    if ($AttachDiagnostics) { $env:OLIVE_ATTACH_DIAGNOSTICS = '1' }
    if ($AttachDiagnostics) {
        # Temporary loopback-only developer capture, never the default launcher.
        & $acceptanceElectron '--remote-debugging-address=127.0.0.1' '--remote-debugging-port=0' (Join-Path $acceptanceRoot 'desktop')
    } else {
        & $acceptanceElectron (Join-Path $acceptanceRoot 'desktop')
    }
} finally {
    $env:OLIVE_DATA_DIR = $acceptancePreviousProfile
    $env:OLIVE_ATTACH_DIAGNOSTICS = $acceptancePreviousDiagnostics
}
