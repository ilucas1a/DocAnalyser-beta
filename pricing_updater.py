"""
pricing_updater.py - Automatic Pricing Data Updates
====================================================
Silently checks GitHub for updated pricing.json on app startup.
If a newer version is found, it downloads and replaces the local copy.

This ensures all users have current AI pricing data without any
manual intervention. You (the developer) update pricing.json in
the GitHub repo after verifying changes from pricing_checker.py,
and all installed copies update themselves automatically.

Architecture:
    1. Developer runs pricing_checker.py weekly → reviews report
    2. Developer updates pricing.json in GitHub repo if needed
    3. User's app checks GitHub on startup (this module)
    4. If remote pricing.json is newer → download and replace local copy
    5. App uses updated prices for cost tracking

Usage (called from Main.py startup):
    from pricing_updater import check_pricing_update_async
    check_pricing_update_async()  # runs in background thread
"""

import json
import shutil
import threading
import datetime
from pathlib import Path
from typing import Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from version import GITHUB_REPO


# ============================================================
# CONFIGURATION
# ============================================================

# Raw GitHub URL for pricing.json on main branch
def _get_remote_pricing_url() -> str:
    """Build the raw GitHub URL for pricing.json."""
    if not GITHUB_REPO:
        return ""
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/pricing.json"


# Local pricing.json path (same directory as this script)
LOCAL_PRICING_PATH = Path(__file__).parent / "pricing.json"

# Backup path (in case download is corrupted)
BACKUP_PRICING_PATH = Path(__file__).parent / "pricing_backup.json"

# Timeout for network requests (seconds)
REQUEST_TIMEOUT = 15


# ============================================================
# CORE LOGIC
# ============================================================

def _get_local_date() -> Optional[str]:
    """Read the _updated date from the local pricing.json."""
    try:
        with open(LOCAL_PRICING_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get("_updated", None)
    except Exception:
        return None


def _is_remote_newer(local_date: Optional[str], remote_date: Optional[str]) -> bool:
    """
    Compare date strings (YYYY-MM-DD format).
    Returns True if remote is strictly newer than local.
    """
    if not remote_date:
        return False  # Can't determine — don't update
    if not local_date:
        return True   # No local date — assume remote is newer

    try:
        local_dt = datetime.date.fromisoformat(local_date)
        remote_dt = datetime.date.fromisoformat(remote_date)
        return remote_dt > local_dt
    except (ValueError, TypeError):
        return False  # Malformed dates — don't update


def _validate_pricing_data(data: dict) -> bool:
    """
    Basic validation that downloaded data is a valid pricing.json.
    Prevents corrupted or empty downloads from overwriting good data.
    """
    if not isinstance(data, dict):
        return False
    if "providers" not in data:
        return False
    providers = data["providers"]
    if not isinstance(providers, dict) or len(providers) < 2:
        return False  # Should have at least a couple of providers

    # Check at least one provider has models with input/output prices
    for provider_name, pdata in providers.items():
        models = pdata.get("models", {})
        if models:
            first_model = next(iter(models.values()))
            if "input" in first_model and "output" in first_model:
                return True

    return False


def check_pricing_update(quiet: bool = True) -> str:
    """
    Check GitHub for updated pricing data and apply if newer.

    Args:
        quiet: If True, only print on update or error. If False, print status.

    Returns:
        Status string: "updated", "current", "skipped", or "error: ..."
    """
    if not REQUESTS_AVAILABLE:
        return "skipped"

    remote_url = _get_remote_pricing_url()
    if not remote_url:
        if not quiet:
            print("💰 Pricing update: GitHub repo not configured")
        return "skipped"

    local_date = _get_local_date()

    try:
        # Fetch remote pricing.json
        response = requests.get(remote_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        remote_data = response.json()

    except requests.exceptions.Timeout:
        if not quiet:
            print("💰 Pricing update: timed out (will retry next startup)")
        return "error: timeout"
    except requests.exceptions.ConnectionError:
        if not quiet:
            print("💰 Pricing update: no network (will retry next startup)")
        return "error: no network"
    except requests.exceptions.RequestException as e:
        if not quiet:
            print(f"💰 Pricing update: network error ({e})")
        return f"error: {e}"
    except json.JSONDecodeError:
        if not quiet:
            print("💰 Pricing update: invalid JSON from GitHub")
        return "error: invalid JSON"

    # Compare dates
    remote_date = remote_data.get("_updated", None)
    if not _is_remote_newer(local_date, remote_date):
        if not quiet:
            print(f"💰 Pricing data is current (local: {local_date})")
        return "current"

    # Validate before overwriting
    if not _validate_pricing_data(remote_data):
        print("💰 Pricing update: remote data failed validation — skipping")
        return "error: validation failed"

    # Create backup of current pricing.json
    try:
        if LOCAL_PRICING_PATH.exists():
            shutil.copy2(LOCAL_PRICING_PATH, BACKUP_PRICING_PATH)
    except Exception as e:
        print(f"💰 Pricing update: couldn't create backup ({e}) — updating anyway")

    # Write the new pricing.json
    try:
        with open(LOCAL_PRICING_PATH, 'w', encoding='utf-8') as f:
            json.dump(remote_data, f, indent=4, ensure_ascii=False)

        print(f"💰 Pricing data updated: {local_date} → {remote_date}")
        return "updated"

    except Exception as e:
        # Try to restore backup
        print(f"💰 Pricing update: write failed ({e})")
        try:
            if BACKUP_PRICING_PATH.exists():
                shutil.copy2(BACKUP_PRICING_PATH, LOCAL_PRICING_PATH)
                print("💰 Pricing update: restored backup")
        except Exception:
            pass
        return f"error: write failed ({e})"


def check_pricing_update_async(callback=None, quiet: bool = True):
    """
    Check for pricing updates in a background thread.
    Non-blocking — safe to call from UI startup.

    Args:
        callback: Optional function(status_str) called when complete.
        quiet: If True, only print on update or error.
    """
    def worker():
        result = check_pricing_update(quiet=quiet)
        if callback:
            callback(result)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread


# ============================================================
# STANDALONE TESTING
# ============================================================

if __name__ == "__main__":
    print("DocAnalyser Pricing Updater")
    print("=" * 40)
    print(f"GitHub repo: {GITHUB_REPO or '(not configured)'}")
    print(f"Remote URL:  {_get_remote_pricing_url() or '(not configured)'}")
    print(f"Local file:  {LOCAL_PRICING_PATH}")
    print(f"Local date:  {_get_local_date() or '(not found)'}")
    print()

    if not GITHUB_REPO:
        print("⚠️  GITHUB_REPO not set in version.py — can't check for updates")
    else:
        print("Checking for pricing updates...")
        result = check_pricing_update(quiet=False)
        print(f"\nResult: {result}")
