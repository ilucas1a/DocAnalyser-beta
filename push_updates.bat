@echo off
REM ============================================================
REM push_updates.bat
REM Publish updated pricing.json and/or models.json to GitHub
REM Run this after editing either file with verified changes
REM ============================================================

cd /d "C:\Ian\Python\GetTextFromYouTube\DocAnalyzer_DEV"

echo.
echo  DocAnalyser - Publish Pricing, Model ^& Guide Updates
echo  ======================================================
echo.

REM Show current dates in all files
for /f "tokens=2 delims=:" %%a in ('findstr "_updated" pricing.json 2^>nul') do (
    echo  pricing.json date:%%a
)
for /f "tokens=2 delims=:" %%a in ('findstr "_updated" models.json 2^>nul') do (
    echo  models.json date: %%a
)
for /f "tokens=2 delims=:" %%a in ('findstr "_updated" model_info.json 2^>nul') do (
    echo  model_info.json:  %%a
)
echo.

REM Check for changes in each file
set PRICING_CHANGED=0
set MODELS_CHANGED=0
set INFO_CHANGED=0

git diff --quiet pricing.json 2>nul
if %errorlevel% neq 0 set PRICING_CHANGED=1

git diff --quiet models.json 2>nul
if %errorlevel% neq 0 set MODELS_CHANGED=1

git diff --quiet model_info.json 2>nul
if %errorlevel% neq 0 set INFO_CHANGED=1

REM Also check for untracked files (first time)
git ls-files --error-unmatch models.json >nul 2>&1
if %errorlevel% neq 0 (
    if exist models.json set MODELS_CHANGED=1
)
git ls-files --error-unmatch model_info.json >nul 2>&1
if %errorlevel% neq 0 (
    if exist model_info.json set INFO_CHANGED=1
)

if %PRICING_CHANGED%==0 if %MODELS_CHANGED%==0 if %INFO_CHANGED%==0 (
    echo  No changes detected in pricing.json, models.json, or model_info.json.
    echo  Edit the files first, then run this script.
    echo.
    pause
    exit /b 0
)

REM Show what changed
echo  Changes detected:
echo  -----------------
if %PRICING_CHANGED%==1 (
    echo  [*] pricing.json
    git diff --stat pricing.json 2>nul
)
if %MODELS_CHANGED%==1 (
    echo  [*] models.json
    git diff --stat models.json 2>nul
)
if %INFO_CHANGED%==1 (
    echo  [*] model_info.json
    git diff --stat model_info.json 2>nul
)
echo.

REM Confirm before pushing
set /p confirm="  Push these changes to GitHub? (y/n): "
if /i not "%confirm%"=="y" (
    echo  Cancelled.
    pause
    exit /b 0
)

REM Get today's date for commit message
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set DATESTAMP=%datetime:~0,4%-%datetime:~4,2%-%datetime:~6,2%

REM Build commit message (just use a generic one for simplicity)
set MSG=Update model and pricing data - %DATESTAMP%

REM Commit and push
if %PRICING_CHANGED%==1 git add pricing.json
if %MODELS_CHANGED%==1 git add models.json
if %INFO_CHANGED%==1 git add model_info.json
git commit -m "%MSG%"
git push

echo.
if %errorlevel%==0 (
    echo  ✅ Updates published to GitHub!
    echo  Users will receive them on their next app startup.
) else (
    echo  ❌ Push failed - check your git configuration.
)
echo.
pause
