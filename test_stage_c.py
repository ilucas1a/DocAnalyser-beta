"""
test_stage_c.py — Initialize DB, migrate prompts, verify, and activate SQLite.

Run from the DocAnalyzer_DEV directory:
    python test_stage_c.py

What it does:
  1. Creates docanalyser.db with all tables (in AppData)
  2. Loads default_prompts.json (tree format) into the database
  3. Rebuilds the folder structure
  4. Prints a verification report
  5. Activates USE_SQLITE_PROMPTS in prompt_db_adapter.py
"""

import os
import sys
import json

# Make sure we can import project modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DATA_DIR, PROMPTS_PATH

print("=" * 60)
print("  Stage C — SQLite Prompts Test Setup")
print("=" * 60)
print(f"  DATA_DIR:     {DATA_DIR}")
print(f"  PROMPTS_PATH: {PROMPTS_PATH}")


# ------------------------------------------------------------------
# Step 1: Initialise database
# ------------------------------------------------------------------
print("\n[Step 1] Initialising database...")
from db_manager import init_database, DB_PATH
init_database()
print(f"  ✅ Database ready at: {DB_PATH}")
print(f"  File size: {os.path.getsize(DB_PATH):,} bytes")


# ------------------------------------------------------------------
# Step 2: Load prompts.json (tree format)
# ------------------------------------------------------------------
print("\n[Step 2] Loading prompts from JSON...")

# Prefer the bundled default_prompts.json (known good structure)
# over the AppData prompts.json (which may have been corrupted)
bundled_path = os.path.join(os.path.dirname(__file__), "default_prompts.json")
source_path = None

if os.path.exists(bundled_path):
    with open(bundled_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and data.get("version") == "2.0":
        source_path = bundled_path
        print(f"  Using bundled: {bundled_path}")

if source_path is None and os.path.exists(PROMPTS_PATH):
    with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and data.get("version") == "2.0":
        source_path = PROMPTS_PATH
        print(f"  Using AppData: {PROMPTS_PATH}")

if source_path is None:
    print("  ❌ No valid v2.0 prompts.json found!")
    sys.exit(1)

root_folders = data.get("root_folders", {})
print(f"  Found {len(root_folders)} root folders: {', '.join(root_folders.keys())}")


# ------------------------------------------------------------------
# Step 3: Clear existing prompts (if re-running this script)
# ------------------------------------------------------------------
print("\n[Step 3] Clearing any existing prompt data...")
from db_manager import get_connection
conn = get_connection()

# Count existing
existing_prompts = conn.execute("SELECT COUNT(*) FROM prompts").fetchone()[0]
existing_folders = conn.execute(
    "SELECT COUNT(*) FROM folders WHERE library_type='prompt'"
).fetchone()[0]
print(f"  Existing: {existing_prompts} prompts, {existing_folders} folders")

if existing_prompts > 0 or existing_folders > 0:
    # Clear folder_items for prompt folders
    conn.execute("""
        DELETE FROM folder_items WHERE folder_id IN (
            SELECT id FROM folders WHERE library_type='prompt'
        )
    """)
    conn.execute("DELETE FROM folders WHERE library_type='prompt'")
    conn.execute("DELETE FROM prompt_versions")
    conn.execute("DELETE FROM prompts")
    conn.commit()
    print("  Cleared existing prompt data.")


# ------------------------------------------------------------------
# Step 4: Insert prompts and folder structure
# ------------------------------------------------------------------
print("\n[Step 4] Migrating prompts to SQLite...")

from db_manager import (
    db_add_prompt, db_save_prompt_version,
    db_create_folder, db_add_item_to_folder,
)

prompt_count = 0
version_count = 0
folder_count = 0


def insert_prompt_from_node(node):
    """Insert a single prompt from its JSON tree node."""
    global prompt_count, version_count

    name = node.get("name", "Unnamed")
    is_system = node.get("is_system_prompt", False)
    is_favorite = node.get("is_favorite", False)
    max_versions = node.get("max_versions", 10)
    versions = node.get("versions", [])
    current_idx = node.get("current_version_index", 0)

    # Get text for the initial version
    if versions:
        safe_idx = min(current_idx, len(versions) - 1)
        text = versions[safe_idx].get("text", "")
    else:
        text = ""

    # db_add_prompt creates the prompt + initial version (version 0)
    prompt_id = db_add_prompt(
        name=name,
        text=text,
        is_system=is_system,
        is_favorite=is_favorite,
        max_versions=max_versions,
    )
    prompt_count += 1
    version_count += 1  # initial version

    # If there are additional versions beyond the one we just inserted,
    # add them. (Most prompts only have 1 version.)
    if len(versions) > 1:
        for i, v in enumerate(versions):
            if i == current_idx:
                continue  # already inserted as the initial version
            v_text = v.get("text", "")
            v_note = v.get("note", f"Version {i}")
            db_save_prompt_version(prompt_id, v_text, v_note)
            version_count += 1

    return prompt_id


def process_folder(folder_data, parent_folder_id, position):
    """Recursively process a folder and its children."""
    global folder_count

    folder_name = folder_data.get("name", "Unknown")
    folder_id = db_create_folder(
        name=folder_name,
        library_type="prompt",
        parent_id=parent_folder_id,
        workspace_id=None,
        position=position,
    )
    folder_count += 1

    children = folder_data.get("children", {})
    child_pos = 0
    for child_name, child_data in children.items():
        child_type = child_data.get("type", "")

        if child_type == "folder":
            process_folder(child_data, folder_id, child_pos)
        elif child_type == "prompt":
            pid = insert_prompt_from_node(child_data)
            db_add_item_to_folder(folder_id, "prompt", str(pid), child_pos)

        child_pos += 1

    return folder_id


# Process each root folder
for idx, (folder_name, folder_data) in enumerate(root_folders.items()):
    process_folder(folder_data, None, idx)

conn.commit()

print(f"  ✅ Migrated: {prompt_count} prompts, {version_count} versions, "
      f"{folder_count} folders")


# ------------------------------------------------------------------
# Step 5: Verify
# ------------------------------------------------------------------
print("\n[Step 5] Verification...")

from db_manager import db_get_all_prompts, db_get_folder_tree

# Check prompts
all_prompts = db_get_all_prompts()
print(f"  Prompts in DB: {len(all_prompts)}")
for p in all_prompts[:5]:
    text_preview = p['text'][:50] + "..." if len(p['text']) > 50 else p['text']
    print(f"    [{p['id']}] {p['name']}: {text_preview}")
if len(all_prompts) > 5:
    print(f"    ... and {len(all_prompts) - 5} more")

# Check folder tree
tree = db_get_folder_tree("prompt")
print(f"\n  Folder tree ({len(tree)} root folders):")
for f in tree:
    items = f.get("items", [])
    children = f.get("children", [])
    print(f"    📁 {f['name']}  ({len(items)} prompts, "
          f"{len(children)} sub-folders)")
    for item in items:
        print(f"       📄 item_id={item['item_id']}")


# ------------------------------------------------------------------
# Step 6: Test the adapter round-trip
# ------------------------------------------------------------------
print("\n[Step 6] Testing adapter round-trip...")

from prompt_db_adapter import load_prompt_tree_from_sqlite, load_flat_prompts_from_sqlite

# Test full tree load
loaded_tree = load_prompt_tree_from_sqlite()
print(f"  Tree load: {len(loaded_tree.root_folders)} root folders")
for fname, folder in loaded_tree.root_folders.items():
    print(f"    📁 {fname}: {len(folder.children)} children")
    for cname, child in folder.children.items():
        ctype = child.get_type() if hasattr(child, 'get_type') else 'folder'
        if ctype == 'prompt':
            text_preview = child.get_current_text()[:40] + "..."
            print(f"       📄 {cname}: {text_preview}")

# Test flat list load
flat = load_flat_prompts_from_sqlite()
print(f"\n  Flat list: {len(flat)} prompts")
for p in flat[:3]:
    print(f"    {p['name']}: {p['text'][:40]}...")


# ------------------------------------------------------------------
# Step 7: Activate the flag
# ------------------------------------------------------------------
print("\n[Step 7] Activating USE_SQLITE_PROMPTS...")

adapter_path = os.path.join(os.path.dirname(__file__), "prompt_db_adapter.py")
with open(adapter_path, "r", encoding="utf-8") as f:
    content = f.read()

if "USE_SQLITE_PROMPTS = False" in content:
    content = content.replace(
        "USE_SQLITE_PROMPTS = False",
        "USE_SQLITE_PROMPTS = True",
    )
    with open(adapter_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("  ✅ USE_SQLITE_PROMPTS set to True")
else:
    if "USE_SQLITE_PROMPTS = True" in content:
        print("  ℹ️  Already set to True")
    else:
        print("  ⚠️  Could not find flag in adapter file!")


# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
print("\n" + "=" * 60)
print("  ✅ Stage C setup complete!")
print()
print("  Next steps:")
print("    1. Run: python main.py")
print("    2. Click 'Prompts Library'")
print("    3. Verify folders and prompts appear with text")
print("    4. Try editing a prompt and clicking 'Save All Changes'")
print("    5. Close and reopen Prompts Library to verify persistence")
print()
print("  To roll back: change USE_SQLITE_PROMPTS back to False")
print("    in prompt_db_adapter.py")
print("=" * 60)
