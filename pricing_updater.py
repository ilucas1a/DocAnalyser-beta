"""
pricing_updater.py - Automatic Pricing & Model Data Updates
============================================================
Silently checks GitHub for updated pricing.json and models.json on
app startup. If newer versions are found, downloads and replaces
the local copies.

This ensures all users have current AI pricing data AND current
model lists without any manual intervention. You (the developer)
update these files in the GitHub repo, and all installed copies
update themselves automatically.

Architecture:
    1. Developer runs pricing_checker.py weekly → reviews report
    2. Developer updates pricing.json and/or models.json in GitHub repo
    3. User's app checks GitHub on startup (this module)
    4. If remote files are newer → download and replace local copies
    5. App uses updated prices for cost tracking + updated model lists

Usage (called from Main.py startup):
    from pricing_updater import check_all_updates_async
    check_all_updates_async()  # runs in background thread

    # Or individually:
    from pricing_updater import check_pricing_update_async, check_models_update_async
"""

import json
import shutil
import threading
import datetime
import logging
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

def _get_remote_url(filename: str) -> str:
    """Build the raw GitHub URL for a file on the main branch."""
    if not GITHUB_REPO:
        return ""
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{filename}"


# Local file paths (same directory as this script)
LOCAL_PRICING_PATH = Path(__file__).parent / "pricing.json"
BACKUP_PRICING_PATH = Path(__file__).parent / "pricing_backup.json"

LOCAL_MODELS_PATH = Path(__file__).parent / "models.json"
BACKUP_MODELS_PATH = Path(__file__).parent / "models_backup.json"

LOCAL_MODEL_INFO_PATH = Path(__file__).parent / "model_info.json"
BACKUP_MODEL_INFO_PATH = Path(__file__).parent / "model_info_backup.json"

# Timeout for network requests (seconds)
REQUEST_TIMEOUT = 15


# ============================================================
# SHARED HELPERS
# ============================================================

def _get_local_date(filepath: Path) -> Optional[str]:
    """Read the _updated date from a local JSON file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
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
        return False
    if not local_date:
        return True

    try:
        local_dt = datetime.date.fromisoformat(local_date)
        remote_dt = datetime.date.fromisoformat(remote_date)
        return remote_dt > local_dt
    except (ValueError, TypeError):
        return False


def _fetch_remote_json(filename: str, quiet: bool = True) -> Optional[dict]:
    """
    Fetch a JSON file from GitHub.
    Returns parsed dict or None on failure.
    """
    if not REQUESTS_AVAILABLE:
        return None

    remote_url = _get_remote_url(filename)
    if not remote_url:
        if not quiet:
            print(f"  {filename}: GitHub repo not configured")
        return None

    try:
        response = requests.get(remote_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        if not quiet:
            print(f"  {filename}: timed out")
    except requests.exceptions.ConnectionError:
        if not quiet:
            print(f"  {filename}: no network")
    except requests.exceptions.RequestException as e:
        if not quiet:
            print(f"  {filename}: network error ({e})")
    except json.JSONDecodeError:
        if not quiet:
            print(f"  {filename}: invalid JSON from GitHub")
    return None


def _safe_write(data: dict, local_path: Path, backup_path: Path) -> bool:
    """Write JSON data to file with backup/restore on failure."""
    # Create backup
    try:
        if local_path.exists():
            shutil.copy2(local_path, backup_path)
    except Exception as e:
        logging.debug(f"Couldn't create backup of {local_path.name}: {e}")

    # Write new data
    try:
        with open(local_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        logging.error(f"Failed to write {local_path.name}: {e}")
        # Restore backup
        try:
            if backup_path.exists():
                shutil.copy2(backup_path, local_path)
                logging.info(f"Restored backup of {local_path.name}")
        except Exception:
            pass
        return False


# ============================================================
# PRICING UPDATE
# ============================================================

def _validate_pricing_data(data: dict) -> bool:
    """Basic validation that downloaded data is a valid pricing.json."""
    if not isinstance(data, dict):
        return False
    if "providers" not in data:
        return False
    providers = data["providers"]
    if not isinstance(providers, dict) or len(providers) < 2:
        return False

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
    Returns: "updated", "current", "skipped", or "error: ..."
    """
    remote_data = _fetch_remote_json("pricing.json", quiet)
    if remote_data is None:
        return "skipped"

    local_date = _get_local_date(LOCAL_PRICING_PATH)
    remote_date = remote_data.get("_updated", None)

    if not _is_remote_newer(local_date, remote_date):
        if not quiet:
            print(f"💰 Pricing data is current (local: {local_date})")
        return "current"

    if not _validate_pricing_data(remote_data):
        print("💰 Pricing update: remote data failed validation — skipping")
        return "error: validation failed"

    if _safe_write(remote_data, LOCAL_PRICING_PATH, BACKUP_PRICING_PATH):
        print(f"💰 Pricing data updated: {local_date} → {remote_date}")
        return "updated"
    else:
        return "error: write failed"


# ============================================================
# MODELS UPDATE
# ============================================================

def _validate_models_data(data: dict) -> bool:
    """Basic validation that downloaded data is a valid models.json."""
    if not isinstance(data, dict):
        return False
    if "providers" not in data:
        return False
    providers = data["providers"]
    if not isinstance(providers, dict) or len(providers) < 2:
        return False

    # Check at least one provider has a non-empty list
    for provider_name, model_list in providers.items():
        if isinstance(model_list, list) and len(model_list) > 0:
            return True
    return False


def check_models_update(quiet: bool = True) -> str:
    """
    Check GitHub for updated model lists and apply if newer.
    Returns: "updated", "current", "skipped", or "error: ..."
    """
    remote_data = _fetch_remote_json("models.json", quiet)
    if remote_data is None:
        return "skipped"

    local_date = _get_local_date(LOCAL_MODELS_PATH)
    remote_date = remote_data.get("_updated", None)

    if not _is_remote_newer(local_date, remote_date):
        if not quiet:
            print(f"📋 Model lists are current (local: {local_date})")
        return "current"

    if not _validate_models_data(remote_data):
        print("📋 Models update: remote data failed validation — skipping")
        return "error: validation failed"

    if _safe_write(remote_data, LOCAL_MODELS_PATH, BACKUP_MODELS_PATH):
        print(f"📋 Model lists updated: {local_date} → {remote_date}")
        return "updated"
    else:
        return "error: write failed"


def get_remote_models() -> Optional[dict]:
    """
    Load model lists from the local models.json (which is kept
    up to date from GitHub). Returns dict of provider -> [model_list]
    or None if file doesn't exist or is invalid.
    """
    try:
        with open(LOCAL_MODELS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        providers = data.get("providers", {})
        if providers and isinstance(providers, dict):
            return providers
    except Exception:
        pass
    return None


# ============================================================
# MODEL INFO UPDATE
# ============================================================

def _validate_model_info_data(data: dict) -> bool:
    """Basic validation that downloaded data is a valid model_info.json."""
    if not isinstance(data, dict):
        return False
    # Should have at least a couple of provider keys (top-level, not nested under "providers")
    provider_count = sum(1 for k in data if not k.startswith("_"))
    if provider_count < 2:
        return False

    # Check at least one provider has a models dict with entries
    for key, value in data.items():
        if key.startswith("_"):
            continue
        if isinstance(value, dict):
            models = value.get("models", {})
            if isinstance(models, dict) and len(models) > 0:
                return True
    return False


def check_model_info_update(quiet: bool = True) -> str:
    """
    Check GitHub for updated model info data and apply if newer.
    Returns: "updated", "current", "skipped", or "error: ..."
    """
    remote_data = _fetch_remote_json("model_info.json", quiet)
    if remote_data is None:
        return "skipped"

    local_date = _get_local_date(LOCAL_MODEL_INFO_PATH)
    remote_date = remote_data.get("_updated", None)

    if not _is_remote_newer(local_date, remote_date):
        if not quiet:
            print(f"📖 Model info is current (local: {local_date})")
        return "current"

    if not _validate_model_info_data(remote_data):
        print("📖 Model info update: remote data failed validation — skipping")
        return "error: validation failed"

    if _safe_write(remote_data, LOCAL_MODEL_INFO_PATH, BACKUP_MODEL_INFO_PATH):
        print(f"📖 Model info updated: {local_date} → {remote_date}")
        return "updated"
    else:
        return "error: write failed"


# ============================================================
# COMBINED UPDATE (both pricing + models in one call)
# ============================================================

def check_all_updates(quiet: bool = True) -> dict:
    """
    Check GitHub for updates to pricing.json, models.json, and model_info.json.
    Returns dict: {"pricing": status_str, "models": status_str, "model_info": status_str}
    """
    return {
        "pricing": check_pricing_update(quiet=quiet),
        "models": check_models_update(quiet=quiet),
        "model_info": check_model_info_update(quiet=quiet),
    }


def check_all_updates_async(callback=None, quiet: bool = True):
    """
    Check for all updates in a background thread.
    Non-blocking — safe to call from UI startup.

    Args:
        callback: Optional function(results_dict) called when complete.
        quiet: If True, only print on update or error.
    """
    def worker():
        results = check_all_updates(quiet=quiet)
        if callback:
            callback(results)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread


# Keep the old function name working for backwards compatibility
def check_pricing_update_async(callback=None, quiet: bool = True):
    """Legacy wrapper — checks pricing only."""
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
    print("DocAnalyser Remote Updater")
    print("=" * 40)
    print(f"GitHub repo:    {GITHUB_REPO or '(not configured)'}")
    print(f"Pricing URL:    {_get_remote_url('pricing.json') or '(not configured)'}")
    print(f"Models URL:     {_get_remote_url('models.json') or '(not configured)'}")
    print(f"Model Info URL: {_get_remote_url('model_info.json') or '(not configured)'}")
    print(f"Local pricing:  {LOCAL_PRICING_PATH} (date: {_get_local_date(LOCAL_PRICING_PATH) or 'not found'})")
    print(f"Local models:   {LOCAL_MODELS_PATH} (date: {_get_local_date(LOCAL_MODELS_PATH) or 'not found'})")
    print(f"Local info:     {LOCAL_MODEL_INFO_PATH} (date: {_get_local_date(LOCAL_MODEL_INFO_PATH) or 'not found'})")
    print()

    if not GITHUB_REPO:
        print("⚠️  GITHUB_REPO not set in version.py — can't check for updates")
    else:
        print("Checking for updates...")
        results = check_all_updates(quiet=False)
        print(f"\nResults: {results}")
