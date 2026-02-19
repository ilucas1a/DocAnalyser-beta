"""
Prompt Dropdown Builder
=======================

Builds hierarchical dropdown lists for the Prompts Library.

This module keeps Main.py clean by handling all dropdown building logic.
Makes it easy to swap dropdown strategies in the future.

Usage in Main.py:
    from prompt_dropdown_builder import build_hierarchical_dropdown
    
    dropdown_entries = build_hierarchical_dropdown(self.prompts)
    self.prompt_combo['values'] = dropdown_entries
"""

from typing import List, Dict, Tuple


def build_hierarchical_dropdown(prompts: List[Dict]) -> Tuple[List[str], Dict[str, Dict]]:
    """
    Build hierarchical dropdown with favorites at top.
    
    Args:
        prompts: List of prompt dictionaries from prompts.json
                Each should have 'name', 'text', and optionally 'is_favorite', 'folder'
    
    Returns:
        Tuple of:
            - List of formatted strings for dropdown display
            - Dictionary mapping display names to prompt data
    
    Example output:
        [
            "⭐ FAVORITES",
            "  ⭐ Counter arguments",
            "  ⭐ Summary (200 words)",
            "────────────────────",
            "📁 General",
            "  Short 3-bullet summary",
            "  Detailed dotpoints",
            "────────────────────",
            "📁 Analysis",
            "  Distill and evaluate",
            ...
        ]
    """
    dropdown_list = []
    name_to_prompt = {}  # Maps display name -> full prompt data
    
    # Collect prompts by category
    favorites = []
    by_folder = {}  # folder_name -> [prompts]
    
    for prompt in prompts:
        # Skip if it's not actually a prompt dict
        if not isinstance(prompt, dict) or 'name' not in prompt:
            continue
        
        # Check if favorite
        is_fav = prompt.get('is_favorite', False)
        folder = prompt.get('folder', 'General')
        
        if is_fav:
            favorites.append(prompt)
        
        # Also add to folder list
        if folder not in by_folder:
            by_folder[folder] = []
        by_folder[folder].append(prompt)
    
    # Build the dropdown list
    
    # 1. FAVORITES SECTION (if any)
    if favorites:
        dropdown_list.append("⭐ FAVORITES")
        for fav in sorted(favorites, key=lambda p: p['name'].lower()):
            display_name = f"  {fav['name']}"
            dropdown_list.append(display_name)
            name_to_prompt[display_name] = fav
        
        # Separator after favorites
        dropdown_list.append("─" * 30)
    
    # 2. FOLDERS SECTIONS
    sorted_folders = sorted(by_folder.keys())
    
    for i, folder in enumerate(sorted_folders):
        # Folder header
        dropdown_list.append(f"📁 {folder}")
        
        # Prompts in this folder
        folder_prompts = sorted(by_folder[folder], key=lambda p: p['name'].lower())
        for prompt in folder_prompts:
            # Indent prompt names under folders
            display_name = f"  {prompt['name']}"
            dropdown_list.append(display_name)
            name_to_prompt[display_name] = prompt
        
        # Separator after each folder (except last)
        if i < len(sorted_folders) - 1:
            dropdown_list.append("─" * 30)
    
    return dropdown_list, name_to_prompt


def extract_prompt_name(display_name: str) -> str:
    """
    Extract the actual prompt name from a formatted dropdown entry.
    
    Args:
        display_name: Formatted string from dropdown (may have indents, icons)
    
    Returns:
        Clean prompt name
    
    Examples:
        "  Counter arguments" -> "Counter arguments"
        "  ⭐ Summary (200 words)" -> "Summary (200 words)"
        "📁 General" -> "General"
    """
    # Remove leading/trailing whitespace
    name = display_name.strip()
    
    # Remove folder icon if present
    if name.startswith("📁 "):
        name = name[2:].strip()
    
    # Remove star icon if present
    if name.startswith("⭐"):
        name = name[1:].strip()
    
    return name


def is_separator(entry: str) -> bool:
    """
    Check if a dropdown entry is a separator line.
    
    Args:
        entry: Dropdown entry string
    
    Returns:
        True if it's a separator (line of dashes)
    """
    return entry.strip().startswith("─")


def is_header(entry: str) -> bool:
    """
    Check if a dropdown entry is a section header.
    
    Args:
        entry: Dropdown entry string
    
    Returns:
        True if it's a header (FAVORITES or folder name)
    """
    stripped = entry.strip()
    return stripped.startswith("⭐ FAVORITES") or stripped.startswith("📁")


def find_prompt_in_list(prompt_name: str, prompts: List[Dict]) -> Dict:
    """
    Find a prompt by name in the prompts list.
    
    Args:
        prompt_name: Name of the prompt to find
        prompts: List of prompt dictionaries
    
    Returns:
        Prompt dictionary if found, or None
    """
    for prompt in prompts:
        if prompt.get('name') == prompt_name:
            return prompt
    return None


# ============================================================================
# TREE FORMAT SUPPORT
# ============================================================================

def build_hierarchical_dropdown_from_tree(tree_dict: Dict) -> Tuple[List[str], Dict[str, Dict]]:
    """
    Build hierarchical dropdown from tree format (version 2.0).
    
    Args:
        tree_dict: Dictionary with 'root_folders' containing folder structure
    
    Returns:
        Same as build_hierarchical_dropdown()
    """
    dropdown_list = []
    name_to_prompt = {}
    
    # Extract all prompts from tree structure
    favorites = []
    by_folder = {}
    
    root_folders = tree_dict.get('root_folders', {})
    
    for folder_name, folder_data in root_folders.items():
        if not isinstance(folder_data, dict):
            continue
        
        children = folder_data.get('children', {})
        
        for child_name, child_data in children.items():
            if child_data.get('type') != 'prompt':
                continue
            
            # Extract prompt info
            versions = child_data.get('versions', [])
            current_idx = child_data.get('current_version_index', 0)
            
            if not versions:
                continue
            
            current_text = versions[current_idx]['text'] if 0 <= current_idx < len(versions) else ""
            
            prompt_dict = {
                'name': child_name,
                'text': current_text,
                'is_favorite': child_data.get('is_favorite', False),
                'folder': folder_name
            }
            
            # Add to appropriate lists
            if prompt_dict['is_favorite']:
                favorites.append(prompt_dict)
            
            if folder_name not in by_folder:
                by_folder[folder_name] = []
            by_folder[folder_name].append(prompt_dict)
    
    # Build dropdown (same logic as flat version)
    
    # 1. FAVORITES SECTION
    if favorites:
        dropdown_list.append("⭐ FAVORITES")
        for fav in sorted(favorites, key=lambda p: p['name'].lower()):
            display_name = f"  {fav['name']}"
            dropdown_list.append(display_name)
            name_to_prompt[display_name] = fav
        
        dropdown_list.append("─" * 30)
    
    # 2. FOLDERS SECTIONS
    sorted_folders = sorted(by_folder.keys())
    
    for i, folder in enumerate(sorted_folders):
        dropdown_list.append(f"📁 {folder}")
        
        folder_prompts = sorted(by_folder[folder], key=lambda p: p['name'].lower())
        for prompt in folder_prompts:
            display_name = f"  {prompt['name']}"
            dropdown_list.append(display_name)
            name_to_prompt[display_name] = prompt
        
        if i < len(sorted_folders) - 1:
            dropdown_list.append("─" * 30)
    
    return dropdown_list, name_to_prompt


# ============================================================================
# AUTO-DETECT FORMAT
# ============================================================================

def build_dropdown_auto(data) -> Tuple[List[str], Dict[str, Dict]]:
    """
    Auto-detect format and build appropriate dropdown.
    
    Args:
        data: Either list of prompts (old format) or dict with 'root_folders' (new format)
    
    Returns:
        Same as build_hierarchical_dropdown()
    """
    if isinstance(data, list):
        return build_hierarchical_dropdown(data)
    elif isinstance(data, dict) and 'root_folders' in data:
        return build_hierarchical_dropdown_from_tree(data)
    else:
        # Fallback - treat as empty
        return [], {}
