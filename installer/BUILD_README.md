# DocAnalyser Windows Build Instructions

## Prerequisites

1. **Python** with all dependencies installed (run `pip install -r requirements.txt`)

2. **PyInstaller** - Bundles Python into an executable
   ```
   pip install pyinstaller
   ```

3. **Inno Setup** - Creates the Windows installer (optional but recommended)
   - Download from: https://jrsoftware.org/isdl.php
   - Install with default options

## Building with Bundled Tools (Recommended)

This creates a "batteries included" installer where OCR and audio/video transcription work out of the box.

### Step 1: Download External Tools

Run the tool download script:
```
cd C:\Ian\Python\GetTextFromYouTube\DocAnalyser_DEV
python installer\download_tools.py
```

This will download Poppler and FFmpeg automatically. 

**For Tesseract**, you need to manually copy it:
1. Install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki
2. Copy the entire `C:\Program Files\Tesseract-OCR\` folder to:
   ```
   installer\bundled_tools\tesseract\
   ```

Your `installer\bundled_tools\` folder should look like:
```
bundled_tools/
├── tesseract/
│   ├── tesseract.exe
│   ├── tessdata/
│   │   └── eng.traineddata
│   └── (other DLLs)
├── poppler/
│   └── Library/
│       └── bin/
│           └── pdftoppm.exe (and others)
└── ffmpeg/
    └── bin/
        └── ffmpeg.exe
```

### Step 2: Build

```
build_windows.bat
```

This will:
1. Check prerequisites
2. Verify bundled tools
3. Build the .exe with PyInstaller (includes bundled tools)
4. Create the installer with Inno Setup

## Building Without Bundled Tools

If you don't want to bundle tools (smaller installer, but users must install tools themselves):

Simply run `build_windows.bat` without downloading the tools first. The script will warn you and ask if you want to continue.

## Output Files

After building:
- `dist\DocAnalyser\` - The standalone application folder
- `dist\DocAnalyser\DocAnalyser.exe` - The main executable
- `dist\DocAnalyser\tools\` - Bundled external tools (if included)
- `dist\installer\DocAnalyser-1.0.0-Windows-Setup.exe` - The installer

## Size Estimates

| Build Type | Installer Size |
|------------|---------------|
| Without bundled tools | ~80-100 MB |
| With Poppler + FFmpeg | ~200-250 MB |
| With all tools (incl. Tesseract) | ~280-350 MB |

## Testing

Before distributing:
1. Copy `dist\DocAnalyser\` to a test machine (or VM)
2. Run `DocAnalyser.exe` directly
3. Open System Check to verify all features are detected
4. Test OCR on a scanned PDF
5. Test audio transcription on a video file

## Troubleshooting

### "Module not found" errors at runtime
- Add the missing module to `hiddenimports` in `DocAnalyser.spec`
- Rebuild

### Bundled tools not detected
- Check that tools are in the `tools\` subfolder in the build output
- Verify the expected executables exist (tesseract.exe, pdftoppm.exe, ffmpeg.exe)

### Executable is too large
- Check `excludes` in `DocAnalyser.spec` to exclude unnecessary packages
- Consider building without bundled tools

### Antivirus flags the executable
- This is common with PyInstaller executables
- Sign the executable with a code signing certificate (optional)
- Or instruct users to add an exception

## Updating Version

When releasing a new version:
1. Update `VERSION` in `version.py`
2. Update `MyAppVersion` in `installer\installer.iss`
3. Rebuild
4. Upload to GitHub Releases
5. Update `version.json` on GitHub with new download URL

## What Users Get

With the "batteries included" build, users get:

| Feature | Status |
|---------|--------|
| YouTube Transcripts | ✅ Works immediately |
| Web Articles | ✅ Works immediately |
| PDF/DOCX/TXT files | ✅ Works immediately |
| AI Analysis (Cloud) | ✅ Works (just enter API keys) |
| OCR (Scanned docs) | ✅ Works immediately (bundled) |
| Audio/Video Transcription | ✅ Works immediately (bundled) |
| Local AI (LM Studio) | ⚠️ User installs separately |
| Local Whisper | ⚠️ User installs faster-whisper |
