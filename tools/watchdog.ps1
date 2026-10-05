# tools/watchdog.ps1 - engine watchdog (scheduled task, every 5 min)
# Logic: heartbeat stale (>300s) AND no engine process -> start supervisor detached.
# Register:
#   schtasks /Create /TN "ShenjiWatchdog" /SC MINUTE /MO 5 /TR "powershell.exe -ExecutionPolicy Bypass -File 'D:\backup\BaoBao\PythonProgram\shenjiMT5\tools\watchdog.ps1'" /F
# NOTE: ASCII only. PowerShell 5.1 misreads non-BOM UTF-8 comments and breaks parsing.

$repo = "D:\backup\BaoBao\PythonProgram\shenjiMT5"
$hb = Join-Path $repo "logs\heartbeat.txt"
$wdlog = Join-Path $repo "logs\watchdog.log"
$durationSec = 1209600   # 14 days shadow run

function Log($msg) {
    "$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss')) $msg" | Out-File $wdlog -Append -Encoding utf8
}

$stale = $true
if (Test-Path $hb) {
    $age = ((Get-Date) - (Get-Item $hb).LastWriteTime).TotalSeconds
    $stale = $age -gt 300
}

if (-not $stale) { exit 0 }

$running = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -match "run_engine|supervise_engine" }
if ($running) {
    Log "heartbeat stale but engine process alive (possible hang) - manual check"
    exit 0
}

Log "heartbeat stale and no engine process -> starting supervisor"
Start-Process -FilePath python `
    -ArgumentList "tools/supervise_engine.py --smoke --followave --duration $durationSec" `
    -WorkingDirectory $repo -WindowStyle Hidden
