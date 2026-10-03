param([ValidateSet('Start','Stop')][string]$Action='Start',
      [ValidateSet('Image','Video')][string]$Kind='Image',
      [string]$Root='')
# Manual start/stop of an OLIVE ComfyUI runtime on Windows (developer tool).
# OLIVE itself starts these on demand (olive/services/local_comfy_runtime.py) from the
# locations in runtime discovery; this script uses the same locations:
#   Image  %LOCALAPPDATA%\OLIVE\runtime\comfy\ComfyUI_windows_portable        port 8188
#   Video  %LOCALAPPDATA%\OLIVE\runtime\video-comfy\ComfyUI_windows_portable  port 8190
# A source checkout's legacy .media-runtime\ComfyUI_windows_portable is used for Image
# when the per-user runtime is absent. Video keeps only its reviewed GGUF loader
# (LTX 2.3 needs it); every other custom node stays disabled.
# Unvalidated on the current tree: see docs/install/windows.md.
$ErrorActionPreference='Stop'
$folder=if ($Kind -eq 'Video') {'video-comfy'} else {'comfy'}
$port=if ($Kind -eq 'Video') {8190} else {8188}
if (-not $Root) {
    $Root=Join-Path (Join-Path (Join-Path $env:LOCALAPPDATA 'OLIVE\runtime') $folder) 'ComfyUI_windows_portable'
    $legacy=Join-Path (Join-Path (Split-Path $PSScriptRoot -Parent) '.media-runtime') 'ComfyUI_windows_portable'
    if ($Kind -eq 'Image' -and -not (Test-Path -LiteralPath $Root) -and (Test-Path -LiteralPath $legacy)) { $Root=$legacy }
}
$runtime=$Root
$state=Join-Path $env:LOCALAPPDATA "OLIVE\runtime\logs"
New-Item -ItemType Directory -Force -Path $state | Out-Null
$python=Join-Path $runtime 'python_embeded\python.exe'
$recordPath=Join-Path $state "$folder-engine-process.json"
$endpoint="http://127.0.0.1:$port"
if (!(Test-Path -LiteralPath $python)) { throw "Install the $Kind ComfyUI runtime first (expected $python)." }
$owned=$null
if (Test-Path -LiteralPath $recordPath) {
    $record=Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
    $candidate=Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$record.pid)"
    if ($candidate -and $candidate.ExecutablePath -eq $python -and
        $candidate.CommandLine -like '*ComfyUI\main.py*' -and
        $candidate.CommandLine -like "*--listen 127.0.0.1 --port $port*" -and
        $candidate.CommandLine -like '*--disable-all-custom-nodes*' -and
        $candidate.CommandLine -like '*--disable-api-nodes*') { $owned=$candidate }
}
if ($Action -eq 'Stop') {
    if (!$owned) { throw 'No verified OLIVE-owned media process is running.' }
    $queue=Invoke-RestMethod "$endpoint/queue" -TimeoutSec 5
    if ($queue.queue_running.Count -or $queue.queue_pending.Count) { throw 'Cancel active media jobs before stopping the engine.' }
    Stop-Process -Id $owned.ProcessId
    Write-Output 'Stopped the verified local media process.'
    exit
}
if ($owned) { Write-Output "Media engine already running: $endpoint"; exit }
if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $port belongs to another process; it was not stopped or reused."
}
$arguments=@('-s','ComfyUI\main.py','--windows-standalone-build','--disable-auto-launch',
    '--disable-all-custom-nodes','--disable-api-nodes','--listen','127.0.0.1','--port',"$port",
    '--preview-method','none','--cache-none')
if ($Kind -eq 'Video') {
    $arguments+=@('--whitelist-custom-nodes','ComfyUI-GGUF-Loader')
} else {
    $arguments+=@('--disable-smart-memory','--disable-cuda-malloc','--disable-dynamic-vram')
}
$process=Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $runtime -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $state "$folder-engine.stdout.log") -RedirectStandardError (Join-Path $state "$folder-engine.stderr.log")
@{pid=$process.Id;endpoint=$endpoint;kind=$Kind;started=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding UTF8
Write-Output "Started local $Kind media process $($process.Id) on $endpoint. Logs: $state"
