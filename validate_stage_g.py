"""
validate_stage_g.py — Validate document folder tree SQLite integration

Run from DocAnalyzer_DEV:
    python validate_stage_g.py
"""

import os, sys, json

if not os.path.exists("db_manager.py"):
    print("Run from DocAnalyzer_DEV folder!")
    sys.exit(1)

import db_manager as db
db.init_database()
conn = db.get_connection()

passed = failed = 0

def check(label, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {label}")
    else:
        failed += 1
        print(f"  ❌ {label}" + (f" — {detail}" if detail else ""))

print("=" * 60)
print("  Stage G: Document Folder Tree Validation")
print("=" * 60)

# 1. Check if document_db_adapter imports correctly
print("\n── Import Check ──")
try:
    from document_db_adapter import (
        USE_SQLITE_DOCUMENT_TREE,
        save_document_tree_to_sqlite,
        load_document_tree_from_sqlite,
    )
    check("document_db_adapter imports OK", True)
    check(f"USE_SQLITE_DOCUMENT_TREE = {USE_SQLITE_DOCUMENT_TREE}", USE_SQLITE_DOCUMENT_TREE)
except Exception as e:
    check("document_db_adapter imports", False, str(e))
    sys.exit(1)

# 2. Check current state of document folders in DB
print("\n── Current DB State ──")
doc_folders = conn.execute(
    "SELECT COUNT(*) as cnt FROM folders WHERE library_type = 'document'"
).fetchone()["cnt"]
prompt_folders = conn.execute(
    "SELECT COUNT(*) as cnt FROM folders WHERE library_type = 'prompt'"
).fetchone()["cnt"]
doc_items = conn.execute("""
    SELECT COUNT(*) as cnt FROM folder_items fi
    JOIN folders f ON fi.folder_id = f.id
    WHERE f.library_type = 'document'
""").fetchone()["cnt"]

print(f"  Document folders in DB: {doc_folders}")
print(f"  Document folder items:  {doc_items}")
print(f"  Prompt folders in DB:   {prompt_folders} (for reference)")

# 3. Test round-trip: create tree, save, load, compare
print("\n── Round-Trip Test ──")
from tree_manager_base import TreeManager, FolderNode
from document_tree_manager import DocumentItem

# Build a test tree
test_tree = TreeManager()
sources = FolderNode("Sources")
responses = FolderNode("AI Responses")

# Get some actual document IDs from the DB
docs = conn.execute(
    "SELECT id, title, doc_type, document_class FROM documents WHERE is_deleted = 0 LIMIT 5"
).fetchall()

source_docs = [d for d in docs if d["document_class"] == "source"]
response_docs = [d for d in docs if d["document_class"] != "source"]

for d in source_docs[:3]:
    item = DocumentItem(d["id"], d["title"], d["doc_type"], d["document_class"])
    sources.add_child(item)

for d in response_docs[:2]:
    item = DocumentItem(d["id"], d["title"], d["doc_type"], d["document_class"])
    responses.add_child(item)

test_tree.add_root_folder(sources)
test_tree.add_root_folder(responses)

items_saved = len(source_docs[:3]) + len(response_docs[:2])
print(f"  Built test tree: 2 folders, {items_saved} items")

# Save
try:
    save_document_tree_to_sqlite(test_tree)
    check("Save to SQLite succeeded", True)
except Exception as e:
    check("Save to SQLite", False, str(e))

# Verify DB state
doc_folders_after = conn.execute(
    "SELECT COUNT(*) as cnt FROM folders WHERE library_type = 'document'"
).fetchone()["cnt"]
doc_items_after = conn.execute("""
    SELECT COUNT(*) as cnt FROM folder_items fi
    JOIN folders f ON fi.folder_id = f.id
    WHERE f.library_type = 'document'
""").fetchone()["cnt"]

check(f"Document folders created: {doc_folders_after}", doc_folders_after == 2)
check(f"Document items placed: {doc_items_after}", doc_items_after == items_saved,
      f"expected {items_saved}")

# Load
try:
    loaded_tree = load_document_tree_from_sqlite()
    check("Load from SQLite succeeded", loaded_tree is not None)
except Exception as e:
    check("Load from SQLite", False, str(e))
    loaded_tree = None

if loaded_tree:
    # Note: loaded tree may have extra folders from unplaced docs
    loaded_folder_names = list(loaded_tree.root_folders.keys())
    check("'Sources' folder loaded", "Sources" in loaded_folder_names)
    check("'AI Responses' folder loaded", "AI Responses" in loaded_folder_names)

    # Count items in Sources folder
    sources_loaded = loaded_tree.root_folders.get("Sources")
    if sources_loaded:
        source_items = [c for c in sources_loaded.children.values()
                        if isinstance(c, DocumentItem)]
        check(f"Sources has {len(source_items)} items",
              len(source_items) == len(source_docs[:3]),
              f"expected {len(source_docs[:3])}")

    # Count items in AI Responses folder
    responses_loaded = loaded_tree.root_folders.get("AI Responses")
    if responses_loaded:
        resp_items = [c for c in responses_loaded.children.values()
                      if isinstance(c, DocumentItem)]
        check(f"AI Responses has {len(resp_items)} items",
              len(resp_items) == len(response_docs[:2]),
              f"expected {len(response_docs[:2])}")

# 4. Verify prompt folders were NOT affected
print("\n── Prompt Folders Preserved ──")
prompt_folders_after = conn.execute(
    "SELECT COUNT(*) as cnt FROM folders WHERE library_type = 'prompt'"
).fetchone()["cnt"]
check(f"Prompt folders unchanged: {prompt_folders_after}",
      prompt_folders_after == prompt_folders,
      f"was {prompt_folders}, now {prompt_folders_after}")

# 5. Clean up test data (wipe document folders so real tree can be built on first use)
print("\n── Cleanup ──")
for f in db.db_get_folder_tree("document"):
    from document_db_adapter import _delete_folder_recursive
    _delete_folder_recursive(f, db.db_delete_folder)
cleanup_count = conn.execute(
    "SELECT COUNT(*) as cnt FROM folders WHERE library_type = 'document'"
).fetchone()["cnt"]
check("Test folders cleaned up", cleanup_count == 0)

print("\n" + "=" * 60)
print(f"  Results: {passed} passed, {failed} failed")
print("=" * 60)
