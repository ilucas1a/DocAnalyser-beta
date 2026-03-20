"""
prompt_db_adapter.py - SQLite adapter for Prompts Library (Stage C)

Bridges between prompt_tree_manager.py (TreeManager/PromptItem/FolderNode)
and db_manager.py (SQLite database functions).

The hooks in prompt_tree_manager.py already reference this module:
  - save_tree()                -> save_prompt_tree_to_sqlite()
  - load_prompts_from_file()   -> load_flat_prompts_from_sqlite()
  - open_prompt_tree_manager() -> load_prompt_tree_from_sqlite()

Set USE_SQLITE_PROMPTS = True to activate.  JSON file remains as backup.

Author: DocAnalyser Development Team
Date: February 28, 2026
"""

import datetime
import traceback

# ============================================================================
# FEATURE FLAG - flip to True when ready to switch over
# ============================================================================
USE_SQLITE_PROMPTS = True


# ============================================================================
# SAVE - tree_manager  ->  SQLite
# ============================================================================

def save_prompt_tree_to_sqlite(tree_manager):
    """
    Persist the entire in-memory prompt tree to SQLite.

    Strategy (full sync on every save):
    1. Walk tree, collect every PromptItem.
    2. For each prompt:
       - If it already has a _db_id, update metadata and push a new
         version only when the current text differs from what the DB holds.
       - Otherwise insert a brand-new prompt row.
    3. Delete any DB prompts that are no longer in the tree.
    4. Wipe the prompt folder structure and rebuild it from scratch
       (folders are purely structural - no version history to preserve).
    """
    from db_manager import (
        db_add_prompt, db_get_prompt, db_get_all_prompts,
        db_update_prompt, db_delete_prompt,
        db_save_prompt_version, db_get_prompt_versions,
        db_create_folder, db_delete_folder, db_get_folder_tree,
        db_add_item_to_folder,
    )
    from tree_manager_base import FolderNode

    # Import PromptItem locally to avoid circular imports
    from prompt_tree_manager import PromptItem

    # ------------------------------------------------------------------
    # 1. Collect every prompt from the in-memory tree
    # ------------------------------------------------------------------
    tree_prompts = {}          # name  ->  PromptItem
    tree_prompts_ordered = []  # preserve walk order

    def _collect(folder):
        for child in folder.children.values():
            if isinstance(child, PromptItem):
                tree_prompts[child.name] = child
                tree_prompts_ordered.append(child)
            elif isinstance(child, FolderNode):
                _collect(child)

    for root_folder in tree_manager.root_folders.values():
        _collect(root_folder)

    # ------------------------------------------------------------------
    # 2. Build a mapping of existing DB prompts  (by id AND by name)
    # ------------------------------------------------------------------
    existing_by_id = {}    # db_id (int)  ->  db row dict
    existing_by_name = {}  # name  (str)  ->  db row dict

    for p in db_get_all_prompts():
        existing_by_id[p["id"]] = p
        existing_by_name[p["name"]] = p

    # ------------------------------------------------------------------
    # 3. Upsert prompts
    # ------------------------------------------------------------------
    prompt_id_map = {}  # prompt.name  ->  db_id  (used for folder_items)

    for prompt in tree_prompts_ordered:
        current_text = prompt.get_current_text()
        db_id = getattr(prompt, "_db_id", None)

        # --- Try to match to an existing DB row ---
        matched_row = None
        if db_id and db_id in existing_by_id:
            matched_row = existing_by_id[db_id]
        elif prompt.name in existing_by_name:
            matched_row = existing_by_name[prompt.name]
            db_id = matched_row["id"]

        if matched_row:
            # ---- UPDATE existing prompt ----
            db_update_prompt(
                db_id,
                name=prompt.name,
                is_system=prompt.is_system_prompt,
                is_favorite=prompt.is_favorite,
                max_versions=prompt.max_versions,
                last_used=prompt.last_used,
            )

            # Push a new version only if the current text differs
            db_text = matched_row.get("text", "")
            if current_text != db_text:
                db_save_prompt_version(db_id, current_text, "Saved from Prompts Library")

            prompt._db_id = db_id
            prompt_id_map[prompt.name] = db_id

        else:
            # ---- INSERT new prompt ----
            db_id = db_add_prompt(
                name=prompt.name,
                text=current_text,
                is_system=prompt.is_system_prompt,
                is_favorite=prompt.is_favorite,
                max_versions=prompt.max_versions,
            )

            # If the in-memory prompt has extra historical versions beyond
            # the initial one, replicate them into the DB so version history
            # is preserved on the very first save.
            if len(prompt.versions) > 1:
                # versions[0] was already inserted by db_add_prompt as
                # version 0. Append the rest in chronological order,
                # EXCEPT the last one if its text matches what
                # db_add_prompt stored (avoid duplicate).
                for i, v in enumerate(prompt.versions[1:], start=1):
                    # Skip the last version if it matches current_text
                    # (already stored as initial version by db_add_prompt)
                    if i == len(prompt.versions) - 1 and v.text == current_text:
                        continue
                    db_save_prompt_version(db_id, v.text, v.note or f"Version {i}")

                # Ensure the "current" text is the newest version in the DB.
                # If current_version_index points to something other than
                # the last entry, add it as the top version.
                if prompt.current_version_index != len(prompt.versions) - 1:
                    db_save_prompt_version(db_id, current_text, "Active version")

            prompt._db_id = db_id
            prompt_id_map[prompt.name] = db_id

    # ------------------------------------------------------------------
    # 4. Delete DB prompts that are no longer in the tree
    # ------------------------------------------------------------------
    tree_db_ids = set(prompt_id_map.values())

    for db_id, row in existing_by_id.items():
        if db_id not in tree_db_ids:
            print(f"DEBUG adapter: deleting orphaned prompt id={db_id} "
                  f"name={row['name']}")
            db_delete_prompt(db_id)

    # ------------------------------------------------------------------
    # 5. Wipe existing prompt folder structure
    # ------------------------------------------------------------------
    for old_folder in db_get_folder_tree("prompt"):
        _delete_folder_recursive(old_folder, db_delete_folder)

    # ------------------------------------------------------------------
    # 6. Rebuild folder structure from the in-memory tree
    # ------------------------------------------------------------------
    def _create_folder_recursive(folder_node, parent_id, position):
        folder_id = db_create_folder(
            name=folder_node.name,
            library_type="prompt",
            parent_id=parent_id,
            workspace_id=None,
            position=position,
            is_expanded=getattr(folder_node, 'expanded', True),
        )
        child_pos = 0
        for child_name, child in folder_node.children.items():
            if isinstance(child, FolderNode):
                _create_folder_recursive(child, folder_id, child_pos)
            elif isinstance(child, PromptItem):
                pid = prompt_id_map.get(child.name)
                if pid is not None:
                    db_add_item_to_folder(
                        folder_id, "prompt", str(pid), child_pos
                    )
            child_pos += 1

    for idx, root_folder in enumerate(tree_manager.root_folders.values()):
        _create_folder_recursive(root_folder, None, idx)

    print(f"DEBUG adapter: saved {len(prompt_id_map)} prompts, "
          f"{len(tree_manager.root_folders)} root folders to SQLite")


# ============================================================================
# LOAD (full tree) - SQLite  ->  TreeManager
# ============================================================================

def load_prompt_tree_from_sqlite():
    """
    Reconstruct a complete TreeManager from SQLite.

    Used by open_prompt_tree_manager() to populate the Prompts Library window.

    Returns:
        TreeManager with FolderNode / PromptItem hierarchy
    """
    from db_manager import (
        db_get_all_prompts, db_get_prompt_versions, db_get_folder_tree,
    )
    from tree_manager_base import TreeManager, FolderNode
    from prompt_tree_manager import PromptItem, PromptVersion

    # ------------------------------------------------------------------
    # 1. Load all prompts and their version histories
    # ------------------------------------------------------------------
    all_prompts = db_get_all_prompts()
    prompt_map = {}  # str(db_id) -> PromptItem

    for p in all_prompts:
        # Build PromptItem (constructor auto-creates one initial version,
        # so we replace it with the real versions below)
        item = PromptItem(
            name=p["name"],
            text="",  # placeholder - replaced below
            is_system_prompt=p["is_system"],
            is_favorite=p["is_favorite"],
        )
        item.max_versions = p.get("max_versions", 10)
        item.last_used = p.get("last_used")
        item._db_id = p["id"]

        # Fetch full version history  (newest first from DB)
        db_versions = db_get_prompt_versions(p["id"])

        # Rebuild the versions list in chronological order (oldest -> newest)
        item.versions = []
        for v in reversed(db_versions):
            pv = PromptVersion(
                text=v["text"],
                note=v.get("note", ""),
                is_default=(v.get("version_num", 0) == 0 and p["is_system"]),
                is_system=p["is_system"],
            )
            pv.timestamp = v.get("created_at",
                                 datetime.datetime.now().isoformat())
            pv.user_modified = not p["is_system"]
            item.versions.append(pv)

        # Fallback: if no versions found, create one from the summary text
        if not item.versions:
            pv = PromptVersion(
                text=p.get("text", ""),
                note="Initial version",
                is_default=p["is_system"],
                is_system=p["is_system"],
            )
            item.versions.append(pv)

        # Current version = latest (highest version_num = last in our list)
        item.current_version_index = len(item.versions) - 1

        prompt_map[str(p["id"])] = item

    # ------------------------------------------------------------------
    # 2. Load folder tree for library_type = 'prompt'
    # ------------------------------------------------------------------
    folder_tree = db_get_folder_tree("prompt")

    # ------------------------------------------------------------------
    # 3. Reconstruct TreeManager hierarchy
    # ------------------------------------------------------------------
    tree = TreeManager()
    placed_ids = set()  # track which prompts were placed in folders

    def _build_folder(db_folder):
        folder = FolderNode(db_folder["name"])
        folder.expanded = bool(db_folder.get("is_expanded", 1))

        # Child sub-folders first (sorted by position)
        children_sorted = sorted(
            db_folder.get("children", []),
            key=lambda c: c.get("position", 0),
        )
        for child_f in children_sorted:
            child_folder = _build_folder(child_f)
            folder.add_child(child_folder)

        # Then items (prompts), also sorted by position
        items_sorted = sorted(
            db_folder.get("items", []),
            key=lambda i: i.get("position", 0),
        )
        for item_row in items_sorted:
            if item_row["item_type"] == "prompt":
                prompt_item = prompt_map.get(str(item_row["item_id"]))
                if prompt_item:
                    folder.add_child(prompt_item)
                    placed_ids.add(str(item_row["item_id"]))

        return folder

    # Sort root folders by position
    folder_tree_sorted = sorted(
        folder_tree, key=lambda f: f.get("position", 0)
    )
    for db_folder in folder_tree_sorted:
        folder = _build_folder(db_folder)
        tree.add_root_folder(folder)

    # ------------------------------------------------------------------
    # 4. Handle orphaned prompts (in DB but not placed in any folder)
    # ------------------------------------------------------------------
    orphans = [p for pid, p in prompt_map.items()
               if pid not in placed_ids]
    if orphans:
        orphan_folder = FolderNode("Uncategorised")
        for p in orphans:
            orphan_folder.add_child(p)
        tree.add_root_folder(orphan_folder)
        print(f"DEBUG adapter: {len(orphans)} orphaned prompts "
              f"placed in 'Uncategorised'")

    print(f"DEBUG adapter: loaded {len(prompt_map)} prompts, "
          f"{len(tree.root_folders)} root folders from SQLite")
    return tree


# ============================================================================
# LOAD (flat list) - SQLite  ->  [{name, text}, ...]
# ============================================================================

def load_flat_prompts_from_sqlite():
    """
    Return a simple flat list of prompts for Main.py dropdown compatibility.

    Used by load_prompts_from_file() when USE_SQLITE_PROMPTS is True.

    Returns:
        list of dicts: [{"name": "...", "text": "..."}, ...]
    """
    from db_manager import db_get_all_prompts

    results = []
    for p in db_get_all_prompts():
        results.append({
            "name": p["name"],
            "text": p.get("text", ""),
        })
    return results


# ============================================================================
# HELPERS
# ============================================================================

def _delete_folder_recursive(folder_dict, delete_fn):
    """
    Delete a folder and all its children depth-first.
    folder_dict comes from db_get_folder_tree() - has 'id' and 'children'.
    """
    for child in folder_dict.get("children", []):
        _delete_folder_recursive(child, delete_fn)
    delete_fn(folder_dict["id"])
