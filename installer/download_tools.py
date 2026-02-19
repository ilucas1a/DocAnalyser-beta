"""
download_tools.py - Download external tools for bundling
Downloads Tesseract, Poppler, and FFmpeg for inclusion in the installer

Run this before building to get the latest tool versions.
"""

import os
import sys
import zipfile
import shutil
import urllib.request
import tempfile
from pathlib import Path

# Tool download URLs (portable/zip versions)
TOOLS = {
    'tesseract': {
        'url': 'https://github.com/UB-Mannheim/tesseract/releases/download/v5.3.3/tesseract-ocr-w64-setup-5.3.3.20231005.exe',
        'type': 'installer',  # We'll extract from installer
        'alt_url': 'https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.3.3.20231005.exe',
    },
    'poppler': {
        'url': 'https://github.com/oschwartz10612/poppler-windows/releases/download/v24.02.0-0/Release-24.02.0-0.zip',
        'type': 'zip',
        'extract_subdir': 'poppler-24.02.0',  # Folder inside ZIP
    },
    'ffmpeg': {
        'url': 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip',
        'type': 'zip',
        'extract_subdir': 'ffmpeg-master-latest-win64-gpl',  # Folder inside ZIP
    },
}

# Where to store downloaded tools
TOOLS_DIR = Path(__file__).parent / 'bundled_tools'


def download_file(url: str, dest: Path, desc: str = "") -> bool:
    """Download a file with progress indication."""
    print(f"  Downloading {desc or url}...")
    try:
        # Create a simple progress indicator
        def report_progress(block_num, block_size, total_size):
            if total_size > 0:
                percent = min(100, block_num * block_size * 100 // total_size)
                print(f"\r  Progress: {percent}%", end='', flush=True)
        
        urllib.request.urlretrieve(url, dest, reporthook=report_progress)
        print()  # New line after progress
        return True
    except Exception as e:
        print(f"\n  ERROR: {e}")
        return False


def extract_zip(zip_path: Path, dest_dir: Path, subdir: str = None):
    """Extract a ZIP file, optionally from a subdirectory."""
    print(f"  Extracting to {dest_dir}...")
    
    with zipfile.ZipFile(zip_path, 'r') as zf:
        if subdir:
            # Extract only contents of subdir
            prefix = subdir + '/'
            for member in zf.namelist():
                if member.startswith(prefix):
                    # Remove prefix from path
                    rel_path = member[len(prefix):]
                    if rel_path:  # Skip the directory itself
                        target = dest_dir / rel_path
                        if member.endswith('/'):
                            target.mkdir(parents=True, exist_ok=True)
                        else:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(member) as src, open(target, 'wb') as dst:
                                dst.write(src.read())
        else:
            zf.extractall(dest_dir)


def download_tesseract():
    """
    Download Tesseract OCR.
    Note: Tesseract is distributed as an installer, not a ZIP.
    We'll provide instructions for manual extraction or use a portable version.
    """
    print("\n[Tesseract OCR]")
    
    dest_dir = TOOLS_DIR / 'tesseract'
    
    # Check if already exists
    if (dest_dir / 'tesseract.exe').exists():
        print("  Already downloaded. Skipping.")
        return True
    
    print("  NOTE: Tesseract requires manual setup for bundling.")
    print("  ")
    print("  Option 1: Install Tesseract normally, then copy:")
    print("    From: C:\\Program Files\\Tesseract-OCR\\")
    print("    To:   installer\\bundled_tools\\tesseract\\")
    print("  ")
    print("  Option 2: Download portable version:")
    print("    1. Go to: https://github.com/UB-Mannheim/tesseract/wiki")
    print("    2. Download the ZIP/portable version if available")
    print("    3. Extract to: installer\\bundled_tools\\tesseract\\")
    print("  ")
    print("  Required files in tesseract folder:")
    print("    - tesseract.exe")
    print("    - tessdata\\ folder (with eng.traineddata at minimum)")
    print("    - Various DLLs")
    
    # Create directory for user to populate
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    return False


def download_poppler():
    """Download Poppler PDF tools."""
    print("\n[Poppler]")
    
    dest_dir = TOOLS_DIR / 'poppler'
    
    # Check if already exists
    if (dest_dir / 'bin' / 'pdftoppm.exe').exists():
        print("  Already downloaded. Skipping.")
        return True
    
    # Download
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / 'poppler.zip'
        
        if not download_file(TOOLS['poppler']['url'], zip_path, "Poppler"):
            return False
        
        # Extract
        dest_dir.mkdir(parents=True, exist_ok=True)
        extract_zip(zip_path, dest_dir, TOOLS['poppler'].get('extract_subdir'))
    
    # Verify
    if (dest_dir / 'Library' / 'bin' / 'pdftoppm.exe').exists():
        print("  ✅ Poppler downloaded successfully")
        return True
    elif (dest_dir / 'bin' / 'pdftoppm.exe').exists():
        print("  ✅ Poppler downloaded successfully")
        return True
    else:
        print("  ⚠️ Download complete but pdftoppm.exe not found in expected location")
        print(f"     Check contents of: {dest_dir}")
        return False


def download_ffmpeg():
    """Download FFmpeg."""
    print("\n[FFmpeg]")
    
    dest_dir = TOOLS_DIR / 'ffmpeg'
    
    # Check if already exists
    if (dest_dir / 'bin' / 'ffmpeg.exe').exists():
        print("  Already downloaded. Skipping.")
        return True
    
    # Download
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / 'ffmpeg.zip'
        
        if not download_file(TOOLS['ffmpeg']['url'], zip_path, "FFmpeg"):
            return False
        
        # Extract
        dest_dir.mkdir(parents=True, exist_ok=True)
        extract_zip(zip_path, dest_dir, TOOLS['ffmpeg'].get('extract_subdir'))
    
    # Verify
    if (dest_dir / 'bin' / 'ffmpeg.exe').exists():
        print("  ✅ FFmpeg downloaded successfully")
        return True
    else:
        print("  ⚠️ Download complete but ffmpeg.exe not found")
        print(f"     Check contents of: {dest_dir}")
        return False


def check_tools_status():
    """Check which tools are already downloaded."""
    print("\n" + "=" * 50)
    print("Bundled Tools Status")
    print("=" * 50)
    
    status = {}
    
    # Tesseract
    tess_dir = TOOLS_DIR / 'tesseract'
    if (tess_dir / 'tesseract.exe').exists():
        status['tesseract'] = True
        print("✅ Tesseract: Ready")
    else:
        status['tesseract'] = False
        print("❌ Tesseract: Not found")
    
    # Poppler
    pop_dir = TOOLS_DIR / 'poppler'
    if (pop_dir / 'Library' / 'bin' / 'pdftoppm.exe').exists():
        status['poppler'] = True
        print("✅ Poppler: Ready")
    elif (pop_dir / 'bin' / 'pdftoppm.exe').exists():
        status['poppler'] = True
        print("✅ Poppler: Ready")
    else:
        status['poppler'] = False
        print("❌ Poppler: Not found")
    
    # FFmpeg
    ff_dir = TOOLS_DIR / 'ffmpeg'
    if (ff_dir / 'bin' / 'ffmpeg.exe').exists():
        status['ffmpeg'] = True
        print("✅ FFmpeg: Ready")
    else:
        status['ffmpeg'] = False
        print("❌ FFmpeg: Not found")
    
    return status


def main():
    print("=" * 50)
    print("DocAnalyser - Download Bundled Tools")
    print("=" * 50)
    print(f"\nTools will be downloaded to:")
    print(f"  {TOOLS_DIR}")
    
    # Create tools directory
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Download each tool
    results = {
        'tesseract': download_tesseract(),
        'poppler': download_poppler(),
        'ffmpeg': download_ffmpeg(),
    }
    
    # Summary
    print("\n" + "=" * 50)
    print("Summary")
    print("=" * 50)
    
    all_ready = True
    for tool, success in results.items():
        status = "✅ Ready" if success else "❌ Needs attention"
        print(f"  {tool}: {status}")
        if not success:
            all_ready = False
    
    if all_ready:
        print("\n✅ All tools ready! You can now run build_windows.bat")
    else:
        print("\n⚠️ Some tools need manual setup. See instructions above.")
        print("   After setup, run this script again to verify.")
    
    return 0 if all_ready else 1


if __name__ == '__main__':
    sys.exit(main())
