@echo off
REM ============================================================
REM push_pricing_update.bat
REM Quick publish of updated pricing.json to GitHub
REM Run this after editing pricing.json with verified prices
REM ============================================================

cd /d "C:\Ian\Python\GetTextFromYouTube\DocAnalyzer_DEV"

echo.
echo  DocAnalyser - Publish Pricing Update
echo  =====================================
echo.

REM Show the current _updated date in pricing.json
for /f "tokens=2 delims=:" %%a in ('findstr "_updated" pricing.json') do (
    echo  Current date in pricing.json:%%a
)
echo.

REM Check if there are actually changes to pricing.json
git diff --quiet pricing.json
if %errorlevel%==0 (
    echo  No changes detected in pricing.json.
    echo  Edit the file first, then run this script.
    echo.
    pause
    exit /b 0
)

REM Show what changed
echo  Changes detected:
echo  -----------------
git diff --stat pricing.json
echo.

REM Confirm before pushing
set /p confirm="  Push these pricing changes to GitHub? (y/n): "
if /i not "%confirm%"=="y" (
    echo  Cancelled.
    pause
    exit /b 0
)

REM Get today's date for commit message
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set DATESTAMP=%datetime:~0,4%-%datetime:~4,2%-%datetime:~6,2%

REM Commit and push
git add pricing.json
git commit -m "Update pricing data - %DATESTAMP%"
git push

echo.
if %errorlevel%==0 (
    echo  ✅ Pricing update published to GitHub!
    echo  Users will receive it on their next app startup.
) else (
    echo  ❌ Push failed - check your git configuration.
)
echo.
pause
