"""
version.py - Application Version Information
Central location for version tracking and update checking
"""

# -------------------------
# Version Information
# -------------------------
VERSION = "1.2.0"
VERSION_TUPLE = (1, 2, 0)  # For programmatic comparison
BUILD_DATE = "2025-01-01"
RELEASE_TYPE = "beta"  # "alpha", "beta", "stable"

# Application metadata
APP_DISPLAY_NAME = "DocAnalyser"
APP_INTERNAL_NAME = "DocAnalyser_Beta"  # Used for data folders (maintain compatibility)
APP_AUTHOR = "Ian"
APP_DESCRIPTION = "Universal Document Analyser with AI-powered summarisation"

# Update server configuration
GITHUB_REPO = "ilucas1a/DocAnalyser-beta"
UPDATE_CHECK_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/version.json"

# -------------------------
# Version Utilities
# -------------------------

def get_version_string() -> str:
    """Get formatted version string for display"""
    if RELEASE_TYPE == "stable":
        return f"v{VERSION}"
    else:
        return f"v{VERSION} ({RELEASE_TYPE})"


def parse_version(version_str: str) -> tuple:
    """Parse version string like '1.2.3' into tuple (1, 2, 3)"""
    try:
        parts = version_str.strip().lstrip('v').split('.')
        return tuple(int(p) for p in parts[:3])
    except (ValueError, AttributeError):
        return (0, 0, 0)


def compare_versions(v1: str, v2: str) -> int:
    """
    Compare two version strings.
    Returns:
        -1 if v1 < v2
         0 if v1 == v2
         1 if v1 > v2
    """
    t1 = parse_version(v1)
    t2 = parse_version(v2)
    
    if t1 < t2:
        return -1
    elif t1 > t2:
        return 1
    else:
        return 0


def is_newer_version(remote_version: str) -> bool:
    """Check if remote version is newer than current version"""
    return compare_versions(remote_version, VERSION) > 0
