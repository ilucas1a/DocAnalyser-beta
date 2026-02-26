"""
config_manager.py - Configuration Management (SAFE VERSION)
This version does NOT reset prompts.json to defaults on errors!
"""

import os
import sys
import json
from typing import Dict, List
from pathlib import Path

# Import from our modules
from config import *
from utils import save_json_atomic

# Path to the GitHub-sourced models.json (in the app install directory,
# downloaded by pricing_updater.py alongside pricing.json on startup)
GITHUB_MODELS_PATH = Path(__file__).parent / "models.json"


# -------------------------
# Configuration Management
# -------------------------

def ensure_config():
    """Ensure config file exists with default values"""
    if not os.path.exists(CONFIG_PATH):
        save_json_atomic(CONFIG_PATH, DEFAULT_CONFIG)


def load_config() -> Dict:
    """
    Load configuration from disk with migration support

    Returns:
        Configuration dictionary
    """
    try:
        ensure_config()
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        updated = False

        # Ensure all top-level keys exist
        for k, v in DEFAULT_CONFIG.items():
            if k not in cfg:
                cfg[k] = v
                updated = True

        # Migration: Add any new providers to keys and last_model
        for provider in DEFAULT_MODELS.keys():
            if provider not in cfg["keys"]:
                cfg["keys"][provider] = ""
                updated = True
            if provider not in cfg["last_model"]:
                cfg["last_model"][provider] = ""
                updated = True

        if updated:
            save_config(cfg)

        return cfg
    except Exception:
        save_json_atomic(CONFIG_PATH, DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()


def save_config(cfg: Dict):
    """
    Save configuration to disk

    Args:
        cfg: Configuration dictionary to save
    """
    save_json_atomic(CONFIG_PATH, cfg)


# -------------------------
# Prompts Management
# -------------------------

def _get_bundled_prompts_path():
    """Get the path to the bundled default_prompts.json."""
    if getattr(sys, 'frozen', False):
        app_dir = sys._MEIPASS
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(app_dir, 'default_prompts.json')


def _is_minimal_defaults(prompts_path):
    """Check if existing prompts.json contains only the old minimal defaults.
    
    Returns True if the file holds just the 3 starter prompts that shipped
    before the curated library was added, so we can auto-upgrade them.
    """
    MINIMAL_NAMES = {
        "Detailed dotpoint summary (quotes+timestamps)",
        "Short 3-bullet summary",
        "Key takeaways (5)",
    }
    try:
        with open(prompts_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Flat list format (old style)
        if isinstance(data, list):
            names = {p.get('name', '') for p in data if isinstance(p, dict)}
            return names == MINIMAL_NAMES
        
        # Tree format (new style) - collect all prompt names from the tree
        if isinstance(data, dict) and data.get('version') == '3.0':
            prompt_names = set()
            def _collect_names(folders):
                for folder in folders:
                    if isinstance(folder, dict):
                        for item in folder.get('prompts', []):
                            if isinstance(item, dict):
                                prompt_names.add(item.get('name', ''))
                        _collect_names(folder.get('subfolders', []))
            _collect_names(data.get('folders', []))
            return prompt_names == MINIMAL_NAMES
        
    except Exception as e:
        print(f"DEBUG _is_minimal_defaults: Error checking prompts: {e}")
    
    return False


def ensure_prompts():
    """Ensure prompts file exists - uses bundled default_prompts.json for new installs.
    
    Also upgrades stale minimal defaults to the curated library if a bundled
    default_prompts.json is available.
    """
    bundled_prompts = _get_bundled_prompts_path()
    print(f"DEBUG ensure_prompts: Looking for bundled prompts at: {bundled_prompts}")
    print(f"DEBUG ensure_prompts: Exists: {os.path.exists(bundled_prompts)}")
    
    if not os.path.exists(PROMPTS_PATH):
        # No prompts file at all - fresh install
        if os.path.exists(bundled_prompts):
            try:
                import shutil
                shutil.copy2(bundled_prompts, PROMPTS_PATH)
                print(f"✅ Installed starter prompts from default_prompts.json")
                return
            except Exception as e:
                print(f"⚠️ Could not copy default_prompts.json: {e}")
        
        # Fallback: create minimal defaults
        save_json_atomic(PROMPTS_PATH, DEFAULT_PROMPTS)
        return
    
    # Prompts file exists - check if it's just the old minimal defaults
    if os.path.exists(bundled_prompts) and _is_minimal_defaults(PROMPTS_PATH):
        try:
            import shutil
            shutil.copy2(bundled_prompts, PROMPTS_PATH)
            print(f"✅ Upgraded minimal default prompts to curated library")
        except Exception as e:
            print(f"⚠️ Could not upgrade prompts: {e}")


def load_prompts() -> List[Dict]:
    """
    Load prompts from disk, handling both old flat format and new tree format.
    
    SAFE VERSION: Does NOT reset to defaults on errors - preserves user data!

    Returns:
        List of prompt dictionaries with 'name' and 'text' keys
    """
    print(f"DEBUG load_prompts: Starting to load from {PROMPTS_PATH}")

    try:
        ensure_prompts()

        # Check if file exists
        if not os.path.exists(PROMPTS_PATH):
            print(f"DEBUG load_prompts: File doesn't exist, using defaults")
            save_json_atomic(PROMPTS_PATH, DEFAULT_PROMPTS)
            return DEFAULT_PROMPTS.copy()

        # Read file
        with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        print(f"DEBUG load_prompts: Loaded data type: {type(data)}")

        # Check if it's new tree format (version 2.0)
        if isinstance(data, dict):
            version = data.get('version')
            print(f"DEBUG load_prompts: Dict format detected, version: {version}")

            if version == '2.0':
                # New tree format - convert to flat list for backwards compatibility
                print(f"DEBUG load_prompts: Converting tree format to flat list")
                try:
                    # Import the correct classes
                    from prompt_tree_manager import PromptItem
                    from tree_manager_base import TreeManager, FolderNode
                    
                    print(f"DEBUG load_prompts: Imports successful")
                    
                    # Create node factory
                    def node_factory(child_data):
                        return PromptItem.from_dict(child_data)
                    
                    print(f"DEBUG load_prompts: Loading tree from dict...")
                    # Load tree
                    tree = TreeManager.from_dict(data, node_factory)
                    print(f"DEBUG load_prompts: Tree loaded, {len(tree.root_folders)} root folders")
                    
                    # Convert to flat list WITH folder and favorite info
                    flat_list = []
                    
                    def collect_prompts(folder, folder_name):
                        for child in folder.children.values():
                            if isinstance(child, PromptItem):
                                flat_list.append({
                                    'name': child.name,
                                    'text': child.get_current_text(),
                                    'folder': folder_name,
                                    'is_favorite': child.is_favorite
                                })
                            elif isinstance(child, FolderNode):
                                collect_prompts(child, child.name)
                    
                    for folder in tree.root_folders.values():
                        collect_prompts(folder, folder.name)
                    
                    print(f"DEBUG load_prompts: Converted to {len(flat_list)} prompts")
                    return flat_list
                    
                except ImportError as e:
                    print(f"⚠️  WARNING: Could not import prompt tree modules: {e}")
                    print(f"⚠️  Tree format prompts will not be available!")
                    print(f"⚠️  Returning defaults but NOT overwriting your file!")
                    # Return defaults but DON'T save them over the user's tree format file!
                    return DEFAULT_PROMPTS.copy()
                    
                except Exception as e:
                    print(f"⚠️  WARNING: Error loading tree format: {e}")
                    import traceback
                    traceback.print_exc()
                    print(f"⚠️  Your prompts file is preserved at: {PROMPTS_PATH}")
                    print(f"⚠️  Returning defaults but NOT overwriting your file!")
                    # Return defaults but DON'T save them over the user's file!
                    return DEFAULT_PROMPTS.copy()

        # Check if it's old flat list format
        elif isinstance(data, list):
            print(f"DEBUG load_prompts: List format detected with {len(data)} items")
            if all(isinstance(p, dict) and 'name' in p and 'text' in p for p in data):
                print(f"DEBUG load_prompts: Valid flat list format")
                return data
            else:
                print(f"⚠️  WARNING: Invalid flat list format in prompts file!")
                print(f"⚠️  Your prompts file is preserved at: {PROMPTS_PATH}")
                print(f"⚠️  Returning defaults but NOT overwriting your file!")
                return DEFAULT_PROMPTS.copy()

    except Exception as e:
        print(f"⚠️  WARNING: Exception during load: {e}")
        import traceback
        traceback.print_exc()
        print(f"⚠️  Your prompts file is preserved at: {PROMPTS_PATH}")
        print(f"⚠️  Returning defaults but NOT overwriting your file!")
        return DEFAULT_PROMPTS.copy()

    # If we got here, something weird happened but don't destroy the file!
    print(f"⚠️  WARNING: Unexpected prompts file format")
    print(f"⚠️  Your prompts file is preserved at: {PROMPTS_PATH}")
    print(f"⚠️  Returning defaults but NOT overwriting your file!")
    return DEFAULT_PROMPTS.copy()


def save_prompts(prompts):
    """
    Save prompts to disk
    
    IMPORTANT: This function handles BOTH formats:
    - Tree format (dict with 'version' key) - saves as-is
    - Flat list format (list of dicts) - saves as-is
    
    The Prompts Library manager calls this with tree format (dict).
    Main.py may call this with flat format (list) for backwards compatibility.

    Args:
        prompts: Either dict (tree format) or list (flat format)
    """
    print(f"DEBUG save_prompts: Saving type: {type(prompts)}")
    
    if isinstance(prompts, dict):
        print(f"DEBUG save_prompts: Tree format, version: {prompts.get('version', 'unknown')}")
    elif isinstance(prompts, list):
        print(f"DEBUG save_prompts: Flat list format, {len(prompts)} prompts")
    
    save_json_atomic(PROMPTS_PATH, prompts)
    print(f"DEBUG save_prompts: Saved to {PROMPTS_PATH}")


# -------------------------
# Models Management
# -------------------------

# How many days before models are considered stale
MODELS_STALE_DAYS = 30


def _load_github_models() -> dict:
    """
    Load curated model lists from the GitHub-sourced models.json file.
    This file lives in the app install directory (alongside pricing.json)
    and is kept up to date by pricing_updater.py on app startup.
    Returns dict of {provider_name: [model_list]} or empty dict.
    """
    try:
        if GITHUB_MODELS_PATH.exists():
            with open(GITHUB_MODELS_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            providers = data.get("providers", {})
            if isinstance(providers, dict) and len(providers) >= 2:
                return providers
    except Exception:
        pass
    return {}


def ensure_models():
    """Ensure models file exists with default values"""
    if not os.path.exists(MODELS_PATH):
        save_json_atomic(MODELS_PATH, {"models": DEFAULT_MODELS, "last_refreshed": None})


def load_models() -> Dict:
    """
    Load models from disk with migration support.

    Priority order (highest wins):
        1. GitHub-sourced models.json (curated by developer, pushed via GitHub)
        2. Locally cached models (from API refresh via model_updater.py)
        3. DEFAULT_MODELS (hardcoded fallback in config.py)

    Returns:
        Dictionary mapping provider names to lists of model names
    """
    ensure_models()
    try:
        with open(MODELS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Handle new format with timestamp
        if isinstance(data, dict) and "models" in data:
            models = data["models"]
        else:
            # Old format - just the models dict directly
            models = data
            # Migrate to new format
            save_models(models)

        # Migration: Add any new providers from DEFAULT_MODELS that don't exist yet
        updated = False
        for provider, model_list in DEFAULT_MODELS.items():
            if provider not in models:
                models[provider] = model_list
                updated = True

        # Merge in GitHub-sourced curated models (highest priority).
        # The GitHub list defines the preferred order; any locally-discovered
        # models not in the GitHub list are appended at the end.
        github_models = _load_github_models()
        if github_models:
            for provider, github_list in github_models.items():
                if provider == "Ollama (Local)":
                    continue  # Ollama models are managed locally, skip
                if not isinstance(github_list, list) or not github_list:
                    continue

                existing = models.get(provider, [])

                # GitHub list goes first (curated order), then append any
                # locally-discovered models that aren't in the GitHub list
                merged = list(github_list)
                for model in existing:
                    if model not in merged:
                        merged.append(model)

                if merged != existing:
                    models[provider] = merged
                    updated = True

        # Save if we added new providers or merged GitHub models
        if updated:
            save_models(models)

        return models
    except Exception:
        save_json_atomic(MODELS_PATH, {"models": DEFAULT_MODELS, "last_refreshed": None})
        return DEFAULT_MODELS.copy()


def apply_curated_models(current_models: Dict) -> tuple:
    """
    Apply GitHub-sourced curated models to an existing models dict.
    Called from the startup callback when models.json is freshly downloaded.

    Args:
        current_models: The app's current models dict {provider: [model_list]}

    Returns:
        (updated_models, changed): The merged dict and whether anything changed
    """
    github_models = _load_github_models()
    if not github_models:
        return current_models, False

    updated = dict(current_models)
    changed = False

    for provider, github_list in github_models.items():
        if provider == "Ollama (Local)":
            continue
        if not isinstance(github_list, list) or not github_list:
            continue

        existing = updated.get(provider, [])
        merged = list(github_list)
        for model in existing:
            if model not in merged:
                merged.append(model)

        if merged != existing:
            updated[provider] = merged
            changed = True

    if changed:
        save_models(updated)

    return updated, changed


def save_models(models: Dict):
    """
    Save models to disk with timestamp

    Args:
        models: Dictionary mapping provider names to model lists
    """
    from datetime import datetime
    data = {
        "models": models,
        "last_refreshed": datetime.now().isoformat()
    }
    save_json_atomic(MODELS_PATH, data)


def get_models_last_refreshed():
    """
    Get the timestamp of when models were last refreshed.
    
    Returns:
        datetime object or None if never refreshed
    """
    from datetime import datetime
    
    if not os.path.exists(MODELS_PATH):
        return None
    
    try:
        with open(MODELS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if isinstance(data, dict) and "last_refreshed" in data:
            timestamp = data.get("last_refreshed")
            if timestamp:
                return datetime.fromisoformat(timestamp)
        return None
    except Exception:
        return None


def are_models_stale() -> bool:
    """
    Check if the cached models are older than MODELS_STALE_DAYS.
    
    Returns:
        True if models should be refreshed, False otherwise
    """
    from datetime import datetime, timedelta
    
    last_refreshed = get_models_last_refreshed()
    
    if last_refreshed is None:
        # Never refreshed - consider stale
        return True
    
    age = datetime.now() - last_refreshed
    return age > timedelta(days=MODELS_STALE_DAYS)


def get_models_age_days() -> int:
    """
    Get the age of cached models in days.
    
    Returns:
        Number of days since last refresh, or -1 if never refreshed
    """
    from datetime import datetime
    
    last_refreshed = get_models_last_refreshed()
    
    if last_refreshed is None:
        return -1
    
    age = datetime.now() - last_refreshed
    return age.days


# -------------------------
# Utility Functions
# -------------------------

def reset_config():
    """Reset configuration to default values"""
    save_json_atomic(CONFIG_PATH, DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def reset_prompts():
    """Reset prompts to default values"""
    save_json_atomic(PROMPTS_PATH, DEFAULT_PROMPTS)
    return DEFAULT_PROMPTS.copy()


def reset_models():
    """Reset models to default values"""
    save_json_atomic(MODELS_PATH, DEFAULT_MODELS)
    return DEFAULT_MODELS.copy()


def get_config_info() -> Dict:
    """
    Get information about configuration files

    Returns:
        Dictionary with paths and status
    """
    return {
        "config_path": CONFIG_PATH,
        "config_exists": os.path.exists(CONFIG_PATH),
        "prompts_path": PROMPTS_PATH,
        "prompts_exists": os.path.exists(PROMPTS_PATH),
        "models_path": MODELS_PATH,
        "models_exists": os.path.exists(MODELS_PATH),
        "data_dir": DATA_DIR,
        "data_dir_exists": os.path.exists(DATA_DIR)
    }


def backup_config(backup_dir: str = None) -> bool:
    """
    Create a backup of all configuration files

    Args:
        backup_dir: Directory to save backups (default: DATA_DIR/backups)

    Returns:
        True if successful, False otherwise
    """
    import shutil
    from datetime import datetime

    if backup_dir is None:
        backup_dir = os.path.join(DATA_DIR, "backups")

    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        # Backup config
        if os.path.exists(CONFIG_PATH):
            backup_path = os.path.join(backup_dir, f"config_{timestamp}.json")
            shutil.copy2(CONFIG_PATH, backup_path)

        # Backup prompts
        if os.path.exists(PROMPTS_PATH):
            backup_path = os.path.join(backup_dir, f"prompts_{timestamp}.json")
            shutil.copy2(PROMPTS_PATH, backup_path)

        # Backup models
        if os.path.exists(MODELS_PATH):
            backup_path = os.path.join(backup_dir, f"models_{timestamp}.json")
            shutil.copy2(MODELS_PATH, backup_path)

        return True
    except Exception as e:
        print(f"Backup failed: {e}")
        return False


def restore_config_from_backup(backup_file: str) -> bool:
    """
    Restore configuration from a backup file

    Args:
        backup_file: Path to backup file

    Returns:
        True if successful, False otherwise
    """
    import shutil

    try:
        if not os.path.exists(backup_file):
            return False

        # Determine which type of file this is
        if "config_" in os.path.basename(backup_file):
            shutil.copy2(backup_file, CONFIG_PATH)
        elif "prompts_" in os.path.basename(backup_file):
            shutil.copy2(backup_file, PROMPTS_PATH)
        elif "models_" in os.path.basename(backup_file):
            shutil.copy2(backup_file, MODELS_PATH)
        else:
            return False

        return True
    except Exception as e:
        print(f"Restore failed: {e}")
        return False
