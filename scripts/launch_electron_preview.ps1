$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repository '.venv\Scripts\python.exe'
$electron = Join-Path $repository 'desktop\node_modules\electron\dist\electron.exe'
if (-not (Test-Path -LiteralPath $electron)) { throw 'Install the pinned desktop dependencies and provision Electron first.' }
if (-not (Test-Path -LiteralPath (Join-Path $repository 'desktop\out\electron\main.cjs'))) { throw 'Run npm run build in desktop first.' }
$previewProfile = Join-Path ([IO.Path]::GetTempPath()) ('olive-electron-preview-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $previewProfile | Out-Null
& $python (Join-Path $repository 'scripts\seed_electron_fixture.py') $previewProfile
if ($LASTEXITCODE -ne 0) { throw 'Fixture creation failed.' }
$previousProfile = $env:OLIVE_DATA_DIR
try {
    $env:OLIVE_DATA_DIR = $previewProfile
    # This is the explicitly requested interactive preview, not a background helper.
    Start-Process -FilePath $electron -ArgumentList ('"' + (Join-Path $repository 'desktop') + '"') -WorkingDirectory $repository -WindowStyle Normal
} finally { $env:OLIVE_DATA_DIR = $previousProfile }
Write-Output 'Opened OLIVE Electron with a separate synthetic preview profile. The default Qt launcher is unchanged.'
