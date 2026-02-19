@echo off
REM Fix Python Cache Issue - Run this from DocAnalyser_DEV folder
REM This will clear Python's cached files and restart fresh

echo ============================================================
echo CLEARING PYTHON CACHE
echo ============================================================
echo.

REM Close any running Python processes
echo Checking for running Python processes...
tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I /N "python.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo WARNING: Python is currently running!
    echo Please close DocAnalyser app first, then run this script again.
    pause
    exit
)

echo No Python processes found - good!
echo.

REM Delete __pycache__ folders
echo Deleting __pycache__ folders...
if exist "__pycache__" (
    rmdir /s /q "__pycache__"
    echo   Deleted __pycache__
) else (
    echo   No __pycache__ folder found
)

REM Also check subdirectories
for /d %%i in (*) do (
    if exist "%%i\__pycache__" (
        rmdir /s /q "%%i\__pycache__"
        echo   Deleted %%i\__pycache__
    )
)

echo.
echo ============================================================
echo CACHE CLEARED SUCCESSFULLY!
echo ============================================================
echo.
echo Now you can start DocAnalyser and it will load the fresh code.
echo.
pause
