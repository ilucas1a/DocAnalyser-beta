@echo off
REM ============================================================
REM run_pricing_check.bat
REM Called by Windows Task Scheduler weekly to check AI pricing
REM Runs pricing_checker.py which emails you a report
REM ============================================================

cd /d "C:\Ian\Python\GetTextFromYouTube\DocAnalyzer_DEV\maintenance"

REM Activate the virtual environment
call "C:\Ian\Python\GetTextFromYouTube\DocAnalyzer_DEV\.venv\Scripts\activate.bat"

REM Run the pricing checker (sends email report)
python pricing_checker.py

REM Log the run
echo %date% %time% - Pricing check completed >> pricing_check_log.txt

deactivate
