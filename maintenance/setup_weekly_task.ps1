# ============================================================
# setup_weekly_task.ps1
# Creates a Windows Task Scheduler task to run pricing_checker.py
# weekly on Sunday mornings at 9:00 AM
#
# Run this ONCE from PowerShell (as Administrator):
#   cd C:\Ian\Python\GetTextFromYouTube\DocAnalyzer_DEV\maintenance
#   powershell -ExecutionPolicy Bypass -File setup_weekly_task.ps1
# ============================================================

$taskName = "DocAnalyser_PricingCheck"
$description = "Weekly check of AI model pricing for DocAnalyser. Sends email report if prices have changed."
$batFile = "C:\Ian\Python\GetTextFromYouTube\DocAnalyzer_DEV\maintenance\run_pricing_check.bat"

# Check if task already exists
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host ""
    Write-Host "Task '$taskName' already exists." -ForegroundColor Yellow
    $confirm = Read-Host "Replace it? (y/n)"
    if ($confirm -ne 'y') {
        Write-Host "Cancelled."
        exit
    }
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Create the trigger: every Sunday at 9:00 AM
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 9:00AM

# Create the action: run the batch file
$action = New-ScheduledTaskAction -Execute $batFile -WorkingDirectory "C:\Ian\Python\GetTextFromYouTube\DocAnalyzer_DEV\maintenance"

# Settings: run whether logged in or not, don't stop if on battery, 
# start even if missed (e.g. PC was off on Sunday morning)
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

# Register the task (runs as current user)
Register-ScheduledTask `
    -TaskName $taskName `
    -Description $description `
    -Trigger $trigger `
    -Action $action `
    -Settings $settings `
    -RunLevel Limited

Write-Host ""
Write-Host "Task '$taskName' created successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "  Schedule:  Every Sunday at 9:00 AM"
Write-Host "  Action:    Runs pricing_checker.py and emails report"
Write-Host "  Catch-up:  Yes (runs on next boot if PC was off)"
Write-Host ""
Write-Host "To test it now, run:"
Write-Host "  Start-ScheduledTask -TaskName '$taskName'"
Write-Host ""
Write-Host "To remove it later:"
Write-Host "  Unregister-ScheduledTask -TaskName '$taskName'"
Write-Host ""
