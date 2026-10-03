# tools/watchdog.ps1 — 引擎看门狗（计划任务每 5 分钟调用）
# 逻辑：心跳文件超 300s 且无引擎进程 → 拉起 supervisor（脱离会话）
# 手动注册：
#   schtasks /Create /TN "ShenjiWatchdog" /SC MINUTE /MO 5 /TR "powershell.exe -ExecutionPolicy Bypass -File 'D:\backup\BaoBao\PythonProgram\shenjiMT5\tools\watchdog.ps1'" /F

$repo = "D:\backup\BaoBao\PythonProgram\shenjiMT5"
$hb = Join-Path $repo "logs\heartbeat.txt"
$wdlog = Join-Path $repo "logs\watchdog.log"
$durationSec = 1209600   # 与影子运行 supervisor 一致（14 天）

function Log($msg) {
    "$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss')) $msg" | Out-File $wdlog -Append -Encoding utf8
}

$stale = $true
if (Test-Path $hb) {
    $age = ((Get-Date) - (Get-Item $hb).LastWriteTime).TotalSeconds
    $stale = $age -gt 300
}

if (-not $stale) { exit 0 }   # 引擎活着，无事可做

$running = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -match "run_engine|supervise_engine" }
if ($running) {
    Log "心跳陈旧但进程仍在（可能卡死），不重复拉起——人工检查"
    exit 0
}

Log "心跳陈旧且无引擎进程 → 拉起 supervisor"
Start-Process -FilePath python `
    -ArgumentList "tools/supervise_engine.py --smoke --followave --duration $durationSec" `
    -WorkingDirectory $repo -WindowStyle Hidden
