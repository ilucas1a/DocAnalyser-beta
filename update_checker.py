"""
update_checker.py - Application Update System
Checks for updates from GitHub and manages the update process
"""

import os
import sys
import json
import threading
import webbrowser
import tempfile
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from version import VERSION, is_newer_version, GITHUB_REPO


@dataclass
class UpdateInfo:
    """Information about an available update"""
    available: bool
    current_version: str
    latest_version: str
    download_url: str = ""
    changelog: str = ""
    release_date: str = ""
    required: bool = False  # Force update if True
    error: str = ""


# -------------------------
# Update Checking
# -------------------------

def get_update_url() -> str:
    """Get the URL to check for updates"""
    if not GITHUB_REPO:
        return ""
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/version.json"


def check_for_updates(timeout: int = 10) -> UpdateInfo:
    """
    Check GitHub for available updates.
    Returns UpdateInfo with details about any available update.
    """
    if not REQUESTS_AVAILABLE:
        return UpdateInfo(
            available=False,
            current_version=VERSION,
            latest_version=VERSION,
            error="requests library not available"
        )
    
    update_url = get_update_url()
    if not update_url:
        return UpdateInfo(
            available=False,
            current_version=VERSION,
            latest_version=VERSION,
            error="Update URL not configured (GITHUB_REPO not set)"
        )
    
    try:
        response = requests.get(update_url, timeout=timeout)
        response.raise_for_status()
        
        data = response.json()
        latest_version = data.get("latest_version", VERSION)
        
        # Determine download URL based on platform
        if sys.platform.startswith("win"):
            download_url = data.get("download_url_windows", "")
        elif sys.platform == "darwin":
            download_url = data.get("download_url_mac", "")
        else:
            download_url = data.get("download_url_linux", "")
        
        return UpdateInfo(
            available=is_newer_version(latest_version),
            current_version=VERSION,
            latest_version=latest_version,
            download_url=download_url,
            changelog=data.get("changelog", ""),
            release_date=data.get("release_date", ""),
            required=data.get("required", False)
        )
        
    except requests.exceptions.Timeout:
        return UpdateInfo(
            available=False,
            current_version=VERSION,
            latest_version=VERSION,
            error="Update check timed out"
        )
    except requests.exceptions.RequestException as e:
        return UpdateInfo(
            available=False,
            current_version=VERSION,
            latest_version=VERSION,
            error=f"Network error: {str(e)}"
        )
    except json.JSONDecodeError:
        return UpdateInfo(
            available=False,
            current_version=VERSION,
            latest_version=VERSION,
            error="Invalid update data received"
        )
    except Exception as e:
        return UpdateInfo(
            available=False,
            current_version=VERSION,
            latest_version=VERSION,
            error=f"Update check failed: {str(e)}"
        )


def check_for_updates_async(callback: Callable[[UpdateInfo], None]) -> threading.Thread:
    """
    Check for updates in background thread.
    Calls callback(UpdateInfo) when complete.
    """
    def worker():
        result = check_for_updates()
        callback(result)
    
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread


# -------------------------
# Update Actions
# -------------------------

def open_download_page(update_info: UpdateInfo) -> bool:
    """Open the download page in user's browser"""
    if update_info.download_url:
        webbrowser.open(update_info.download_url)
        return True
    elif GITHUB_REPO:
        # Fallback to releases page
        webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases")
        return True
    return False


def download_update(update_info: UpdateInfo, 
                   progress_callback: Optional[Callable[[int, int], None]] = None,
                   dest_folder: Optional[str] = None) -> Optional[str]:
    """
    Download the update installer.
    
    Args:
        update_info: UpdateInfo with download URL
        progress_callback: Optional function(bytes_downloaded, total_bytes)
        dest_folder: Folder to save download (default: user's Downloads)
    
    Returns:
        Path to downloaded file, or None if failed
    """
    if not REQUESTS_AVAILABLE:
        return None
    
    if not update_info.download_url:
        return None
    
    # Determine destination
    if dest_folder is None:
        # Try to find Downloads folder
        if sys.platform.startswith("win"):
            dest_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        elif sys.platform == "darwin":
            dest_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        else:
            dest_folder = os.path.expanduser("~")
    
    # Extract filename from URL
    filename = update_info.download_url.split("/")[-1]
    if not filename:
        filename = f"DocAnalyser-{update_info.latest_version}-update"
        if sys.platform.startswith("win"):
            filename += ".exe"
        elif sys.platform == "darwin":
            filename += ".dmg"
    
    dest_path = os.path.join(dest_folder, filename)
    
    try:
        response = requests.get(update_info.download_url, stream=True, timeout=300)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total_size)
        
        return dest_path
        
    except Exception as e:
        print(f"Download failed: {e}")
        # Clean up partial download
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except:
                pass
        return None


# -------------------------
# Configuration
# -------------------------

def should_check_for_updates(config: dict) -> bool:
    """
    Determine if we should check for updates based on config.
    """
    # Check if updates are disabled
    if not config.get("check_for_updates", True):
        return False
    
    # Check if GITHUB_REPO is configured
    if not GITHUB_REPO:
        return False
    
    # Could add: check last update time, only check once per day, etc.
    
    return True


def get_update_config_defaults() -> dict:
    """Get default update configuration settings"""
    return {
        "check_for_updates": True,
        "check_on_startup": True,
        "last_update_check": None,
        "skipped_version": None,  # Version user chose to skip
    }


# -------------------------
# Update Dialog Helper
# -------------------------

def format_changelog(changelog: str, max_lines: int = 10) -> str:
    """Format changelog for display in dialog"""
    lines = changelog.strip().split('\n')
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["...(see release notes for more)"]
    return '\n'.join(lines)


def create_update_message(update_info: UpdateInfo) -> str:
    """Create user-friendly update notification message"""
    msg = f"A new version of DocAnalyser is available!\n\n"
    msg += f"Current version: {update_info.current_version}\n"
    msg += f"New version: {update_info.latest_version}\n"
    
    if update_info.release_date:
        msg += f"Released: {update_info.release_date}\n"
    
    if update_info.changelog:
        msg += f"\nWhat's New:\n{format_changelog(update_info.changelog)}"
    
    return msg


# -------------------------
# Quick Test
# -------------------------

if __name__ == "__main__":
    print("DocAnalyser Update Checker")
    print("=" * 50)
    print(f"Current version: {VERSION}")
    print(f"GitHub repo: {GITHUB_REPO or '(not configured)'}")
    print(f"Update URL: {get_update_url() or '(not configured)'}")
    print()
    
    if not GITHUB_REPO:
        print("⚠️ GITHUB_REPO not set in version.py")
        print("   Set this to your repository (e.g., 'username/DocAnalyser')")
        print("   to enable update checking.")
    else:
        print("Checking for updates...")
        result = check_for_updates()
        
        if result.error:
            print(f"❌ Error: {result.error}")
        elif result.available:
            print(f"✅ Update available: v{result.latest_version}")
            print(f"   Download: {result.download_url}")
            if result.changelog:
                print(f"   Changes:\n{result.changelog}")
        else:
            print("✅ You're running the latest version!")
