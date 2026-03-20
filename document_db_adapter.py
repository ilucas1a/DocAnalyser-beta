"""
document_db_adapter.py — SQLite persistence for the Document Tree

Mirrors the pattern in prompt_db_adapter.py but is simpler because
documents themselves are already stored in the documents table (Stage D).
This adapter only manages the folder structure and folder ↔ document
assignments (library_type = 'document').

Set USE_SQLITE_DOCUMENT_TREE = True to activate.
The JSON file (document_library_tree.json) remains as fallback/backup.
"""

import datetime

# ── Feature flag ──────────────────────────────────────────────────────
# Reuses USE_SQLITE_DOCUMENTS from document_library so there's one
# switch for all document-related SQLite features.
try:
    from document_library import USE_SQLITE_DOCUMENTS as USE_SQLITE_DOCUMENT_TREE
except ImportError:
    USE_SQLITE_DOCUMENT_TREE = False


# =====================================================================
#  SAVE  —  TreeManager  →  SQLite
# =====================================================================

def save_document_tree_to_sqlite(tree_manager):
    """
    Persist the entire in-memory document tree to SQLite.

    Strategy:
    1. Wipe existing document-type folder structure.
    2. Rebuild folder structure from the in-memory tree.
       (Documents themselves are already in the documents table.)
    """
    from db_manager import (
        db_create_folder, db_delete_folder, db_get_folder_tree,
        db_add_item_to_folder,
    )
    from tree_manager_base import FolderNode
    from document_tree_manager import DocumentItem

    # ------------------------------------------------------------------
    # 1. Wipe existing document folder structure
    # ------------------------------------------------------------------
    for old_folder in db_get_folder_tree("document"):
        _delete_folder_recursive(old_folder, db_delete_folder)

    # ------------------------------------------------------------------
    # 2. Rebuild folder structure from the in-memory tree
    # ------------------------------------------------------------------
    folder_count = 0
    item_count = 0

    def _create_folder_recursive(folder_node, parent_id, position):
        nonlocal folder_count, item_count

        folder_id = db_create_folder(
            name=folder_node.name,
            library_type="document",
            parent_id=parent_id,
            workspace_id=None,
            position=position,
            is_expanded=getattr(folder_node, 'expanded', True),
        )
        folder_count += 1

        child_pos = 0
        for child_name, child in folder_node.children.items():
            if isinstance(child, FolderNode):
                _create_folder_recursive(child, folder_id, child_pos)
            elif isinstance(child, DocumentItem):
                db_add_item_to_folder(
                    folder_id, "document", child.doc_id, child_pos
                )
                item_count += 1
            child_pos += 1

    for idx, root_folder in enumerate(tree_manager.root_folders.values()):
        _create_folder_recursive(root_folder, None, idx)

    print(f"✅ Document tree saved to SQLite: "
          f"{folder_count} folders, {item_count} document placements")


# =====================================================================
#  LOAD  —  SQLite  →  TreeManager
# =====================================================================

def load_document_tree_from_sqlite():
    """
    Reconstruct a complete document TreeManager from SQLite.

    Returns:
        TreeManager with FolderNode / DocumentItem hierarchy,
        or None if no document folders exist yet.
    """
    from db_manager import db_get_folder_tree, db_get_document
    from tree_manager_base import TreeManager, FolderNode
    from document_tree_manager import DocumentItem
    from document_library import get_all_documents, load_thread_from_document

    # ------------------------------------------------------------------
    # 1. Load folder tree for library_type = 'document'
    # ------------------------------------------------------------------
    folder_tree = db_get_folder_tree("document")

    if not folder_tree:
        return None  # No document tree saved yet — caller will create default

    # ------------------------------------------------------------------
    # 2. Build a lookup of all documents (already in documents table)
    # ------------------------------------------------------------------
    all_docs = get_all_documents()
    doc_lookup = {d["id"]: d for d in all_docs}

    # ------------------------------------------------------------------
    # 3. Reconstruct TreeManager hierarchy
    # ------------------------------------------------------------------
    tree = TreeManager()
    placed_ids = set()

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

        # Then document items (sorted by position)
        items_sorted = sorted(
            db_folder.get("items", []),
            key=lambda i: i.get("position", 0),
        )
        for item_row in items_sorted:
            if item_row["item_type"] == "document":
                doc_id = item_row["item_id"]
                doc_data = doc_lookup.get(doc_id)
                if doc_data:
                    doc_item = DocumentItem(
                        doc_id=doc_id,
                        title=doc_data.get("title", "Untitled"),
                        doc_type=doc_data.get("type", "unknown"),
                        document_class=doc_data.get("document_class", "source"),
                    )
                    doc_item.source = doc_data.get("source")
                    doc_item.created = doc_data.get("created")
                    # Check for thread
                    try:
                        thread_data, _ = load_thread_from_document(doc_id)
                        doc_item.has_thread = bool(
                            thread_data and len(thread_data) > 0
                        )
                    except Exception:
                        doc_item.has_thread = False

                    folder.add_child(doc_item)
                    placed_ids.add(doc_id)

        return folder

    # Sort root folders by position
    folder_tree_sorted = sorted(
        folder_tree, key=lambda f: f.get("position", 0)
    )
    for db_folder in folder_tree_sorted:
        folder = _build_folder(db_folder)
        tree.add_root_folder(folder)

    # ------------------------------------------------------------------
    # 4. Handle unplaced documents (in DB but not in any folder)
    # ------------------------------------------------------------------
    unplaced = [d for d in all_docs if d["id"] not in placed_ids]
    if unplaced:
        general_name = "General"
        if general_name not in tree.root_folders:
            tree.add_root_folder(FolderNode(general_name))
        general = tree.root_folders[general_name]

        for doc_data in unplaced:
            doc_item = DocumentItem(
                doc_id=doc_data["id"],
                title=doc_data.get("title", "Untitled"),
                doc_type=doc_data.get("type", "unknown"),
                document_class=doc_data.get("document_class", "source"),
            )
            doc_item.source = doc_data.get("source")
            doc_item.created = doc_data.get("created")
            general.add_child(doc_item)

        print(f"ℹ️  {len(unplaced)} unplaced documents added to 'General'")

    print(f"✅ Document tree loaded from SQLite: "
          f"{len(tree.root_folders)} root folders, "
          f"{len(placed_ids)} placed documents")
    return tree


# =====================================================================
#  HELPERS
# =====================================================================

def _delete_folder_recursive(folder_dict, delete_fn):
    """
    Delete a folder and all its children depth-first.
    folder_dict comes from db_get_folder_tree() — has 'id' and 'children'.
    """
    for child in folder_dict.get("children", []):
        _delete_folder_recursive(child, delete_fn)
    delete_fn(folder_dict["id"])
