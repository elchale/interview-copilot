# Remove the Interview Copilot scheduled task
$taskName = "WinAudioSvc"
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Scheduled task '$taskName' removed." -ForegroundColor Green
