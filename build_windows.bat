@echo off
REM ============================================================
REM DocAnalyser Windows Build Script
REM ============================================================
REM This script builds the Windows installer for DocAnalyser
REM with bundled external tools (Tesseract, Poppler, FFmpeg)
REM
REM Prerequisites:
REM   1. Python with all dependencies installed
REM   2. PyInstaller: pip install pyinstaller
REM   3. Inno Setup: https://jrsoftware.org/isdl.php
REM   4. Bundled tools (run download_tools.py first)
REM
REM Usage: build_windows.bat
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo ============================================================
echo DocAnalyser Windows Build Script
echo ============================================================
echo.

REM Get script directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM Check for PyInstaller
echo [1/6] Checking for PyInstaller...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo      PyInstaller not found. Installing...
    pip install pyinstaller
    if errorlevel 1 (
        echo      ERROR: Failed to install PyInstaller
        goto :error
    )
)
echo      PyInstaller is installed.

REM Check for Inno Setup
echo.
echo [2/6] Checking for Inno Setup...
set "ISCC="
set "SKIP_INNO=0"
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
)

if "!ISCC!"=="" (
    echo      WARNING: Inno Setup not found.
    echo      The executable will be built but no installer will be created.
    echo      Download from: https://jrsoftware.org/isdl.php
    set "SKIP_INNO=1"
) else (
    echo      Inno Setup found: !ISCC!
)

REM Check for bundled tools
echo.
echo [3/6] Checking for bundled tools...
set "TOOLS_DIR=installer\bundled_tools"
set "TOOLS_MISSING=0"

if not exist "%TOOLS_DIR%\tesseract\tesseract.exe" (
    echo      WARNING: Tesseract not found in bundled_tools
    set "TOOLS_MISSING=1"
) else (
    echo      Tesseract: Found
)

set "POPPLER_FOUND=0"
if exist "%TOOLS_DIR%\poppler\Library\bin\pdftoppm.exe" (
    set "POPPLER_FOUND=1"
    echo      Poppler: Found
)
if exist "%TOOLS_DIR%\poppler\bin\pdftoppm.exe" (
    set "POPPLER_FOUND=1"
    echo      Poppler: Found
)
if "!POPPLER_FOUND!"=="0" (
    echo      WARNING: Poppler not found in bundled_tools
    set "TOOLS_MISSING=1"
)

if not exist "%TOOLS_DIR%\ffmpeg\bin\ffmpeg.exe" (
    echo      WARNING: FFmpeg not found in bundled_tools
    set "TOOLS_MISSING=1"
) else (
    echo      FFmpeg: Found
)

if "!TOOLS_MISSING!"=="1" (
    echo.
    echo      Some bundled tools are missing.
    echo      Run 'python installer\download_tools.py' to download them.
    echo.
    choice /C YN /M "      Continue without bundled tools?"
    if errorlevel 2 goto :end
    echo      Continuing without all bundled tools...
) else (
    echo      All bundled tools found!
)

REM Clean previous builds
echo.
echo [4/6] Cleaning previous builds...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
echo      Done.

REM Run PyInstaller
echo.
echo [5/6] Building executable with PyInstaller...
echo      This may take several minutes...
echo.
pyinstaller installer\DocAnalyser.spec --noconfirm
if errorlevel 1 (
    echo.
    echo      ERROR: PyInstaller failed!
    goto :error
)
echo.
echo      Executable built successfully.

REM Check if dist folder was created
if not exist "dist\DocAnalyser\DocAnalyser.exe" (
    echo      ERROR: Executable not found in dist folder!
    goto :error
)

REM PyInstaller 6.x puts data in _internal folder
set "INTERNAL_DIR=dist\DocAnalyser\_internal"

REM Show what was included
echo.
echo      Checking bundled content:
if exist "%INTERNAL_DIR%\tools\tesseract\tesseract.exe" (
    echo        [OK] Tesseract bundled
) else (
    echo        [--] Tesseract not bundled
)
if exist "%INTERNAL_DIR%\tools\poppler\Library\bin\pdftoppm.exe" (
    echo        [OK] Poppler bundled
) else if exist "%INTERNAL_DIR%\tools\poppler\bin\pdftoppm.exe" (
    echo        [OK] Poppler bundled
) else (
    echo        [--] Poppler not bundled
)
if exist "%INTERNAL_DIR%\tools\ffmpeg\bin\ffmpeg.exe" (
    echo        [OK] FFmpeg bundled
) else (
    echo        [--] FFmpeg not bundled
)

REM Calculate total size
echo.
set "TOTAL_SIZE=0"
for /r "dist\DocAnalyser" %%F in (*) do (
    set /a "TOTAL_SIZE+=%%~zF / 1024"
)
set /a "TOTAL_SIZE_MB=!TOTAL_SIZE! / 1024"
echo      Total build size: !TOTAL_SIZE_MB! MB

REM Run Inno Setup if available
if "!SKIP_INNO!"=="1" (
    echo.
    echo [6/6] Skipping installer creation - Inno Setup not installed
    goto :done_no_installer
)

echo.
echo [6/6] Creating installer with Inno Setup...
mkdir "dist\installer" 2>nul
"!ISCC!" installer\DocAnalyser_Setup.iss
if errorlevel 1 (
    echo.
    echo      ERROR: Inno Setup failed!
    goto :error
)

REM Find and show installer info
for %%A in ("dist\installer\DocAnalyser-*-Setup.exe") do (
    set "INSTALLER_PATH=%%~fA"
    set "INSTALLER_NAME=%%~nxA"
    set "INSTALLER_SIZE=%%~zA"
)
set /a "INSTALLER_SIZE_MB=!INSTALLER_SIZE! / 1048576"

echo.
echo ============================================================
echo BUILD COMPLETE!
echo ============================================================
echo.
echo Outputs:
echo   Executable: dist\DocAnalyser\DocAnalyser.exe
echo   Installer:  dist\installer\!INSTALLER_NAME!
echo              Size: !INSTALLER_SIZE_MB! MB
echo.
echo Bundled features:
if exist "%INTERNAL_DIR%\tools\tesseract\tesseract.exe" (
    echo   [OK] OCR - works out of the box
) else (
    echo   [--] OCR - users must install Tesseract + Poppler manually
)
if exist "%INTERNAL_DIR%\tools\ffmpeg\bin\ffmpeg.exe" (
    echo   [OK] Audio/Video transcription - works out of the box
) else (
    echo   [--] Audio/Video - users must install FFmpeg manually
)
echo.
echo Next steps:
echo   1. Test the installer on a clean machine
echo   2. Upload to GitHub Releases
echo   3. Update version.json with download URL
echo.
goto :end

:done_no_installer
echo.
echo ============================================================
echo BUILD COMPLETE (No Installer)
echo ============================================================
echo.
echo Output:
echo   Executable folder: dist\DocAnalyser\
echo   Main executable:   dist\DocAnalyser\DocAnalyser.exe
echo.
echo To create an installer:
echo   1. Install Inno Setup from https://jrsoftware.org/isdl.php
echo   2. Run this script again
echo.
goto :end

:error
echo.
echo ============================================================
echo BUILD FAILED
echo ============================================================
echo.
echo Check the error messages above for details.
echo.
pause
exit /b 1

:end
pause
