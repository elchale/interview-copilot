# Install Interview Copilot as a scheduled task (runs at logon, hidden)
$exePath = Join-Path $PSScriptRoot "..\dist\WinAudioSvc.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "ERROR: Build the exe first: pyinstaller build.spec" -ForegroundColor Red
    exit 1
}

$taskName = "WinAudioSvc"
$action = New-ScheduledTaskAction -Execute $exePath
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit 0
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
Write-Host "Scheduled task '$taskName' registered — will run at logon." -ForegroundColor Green
