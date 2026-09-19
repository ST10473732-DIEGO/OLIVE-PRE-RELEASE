param([ValidateSet('Start','Stop')][string]$Action='Start')
$ErrorActionPreference='Stop'
$mediaRoot=Join-Path (Split-Path $PSScriptRoot -Parent) '.media-runtime'
$runtime=Join-Path $mediaRoot 'ComfyUI_windows_portable'
$python=Join-Path $runtime 'python_embeded\python.exe'
$recordPath=Join-Path $mediaRoot 'engine-process.json'
$endpoint='http://127.0.0.1:8188'
if (!(Test-Path -LiteralPath $python)) { throw 'Install the approved portable media runtime first.' }
$owned=$null
if (Test-Path -LiteralPath $recordPath) {
    $record=Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
    $candidate=Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$record.pid)"
    if ($candidate -and $candidate.ExecutablePath -eq $python -and
        $candidate.CommandLine -like '*ComfyUI\main.py*' -and
        $candidate.CommandLine -like '*--listen 127.0.0.1 --port 8188*' -and
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
if (Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8188 belongs to another process; it was not stopped or reused.'
}
$arguments=@('-s','ComfyUI\main.py','--windows-standalone-build','--disable-auto-launch',
    '--disable-all-custom-nodes','--disable-api-nodes','--listen','127.0.0.1','--port','8188',
    '--preview-method','none','--cache-none','--disable-smart-memory','--disable-cuda-malloc','--disable-dynamic-vram')
$process=Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $runtime -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $mediaRoot 'engine.stdout.log') -RedirectStandardError (Join-Path $mediaRoot 'engine.stderr.log')
@{pid=$process.Id;endpoint=$endpoint;runtime='ComfyUI v0.35.0';started=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding UTF8
Write-Output "Started approved local media process $($process.Id). Logs: .media-runtime/engine.stderr.log"
