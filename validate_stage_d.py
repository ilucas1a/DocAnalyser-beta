"""
validate_stage_d.py — Pre-flight check for USE_SQLITE_DOCUMENTS = True

Run from DocAnalyzer_DEV folder:
    python validate_stage_d.py

Compares JSON library data with SQLite database data to verify
they match before switching over.
"""

import sys
import os
import json
import datetime

# Make sure we're in the right folder
if not os.path.exists("db_manager.py"):
    print("❌ Run this from the DocAnalyzer_DEV folder!")
    sys.exit(1)

# Import project modules
import db_manager as db
from document_library import (
    load_library, load_document_entries, get_document_by_id,
    get_all_documents, get_recent_documents, get_document_count,
    search_documents, get_processed_outputs_for_document,
    load_thread_from_document, get_response_branches_for_source,
    get_library_stats, rename_document, get_embedding_stats,
    DATA_DIR
)
from utils import load_json

print("=" * 70)
print("  DocAnalyser Stage D Validation")
print("  Comparing JSON <-> SQLite data")
print("=" * 70)

passed = 0
failed = 0
warnings = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name}")
        if detail:
            print(f"     {detail}")
        failed += 1

def warn(name, detail=""):
    global warnings
    print(f"  ⚠️  {name}")
    if detail:
        print(f"     {detail}")
    warnings += 1


# ── 1. Document counts ──────────────────────────────────────
print("\n── 1. Document Counts ──")
json_lib = load_library()
json_docs = json_lib.get("documents", [])
json_count = len(json_docs)

db_docs = db.db_get_all_documents()
db_count = len(db_docs)

check(f"Document count: JSON={json_count}, SQLite={db_count}", json_count == db_count,
      f"Difference of {abs(json_count - db_count)}")


# ── 2. Document IDs match ────────────────────────────────────
print("\n── 2. Document ID Coverage ──")
json_ids = set(d.get("id") for d in json_docs)
db_ids = set(d.get("id") for d in db_docs)

only_json = json_ids - db_ids
only_db = db_ids - json_ids

check(f"All JSON docs in SQLite ({len(json_ids - only_json)}/{len(json_ids)})",
      len(only_json) == 0,
      f"Missing from SQLite: {list(only_json)[:3]}")

if only_db:
    warn(f"{len(only_db)} docs in SQLite but not JSON (may be OK if migrated extra)")


# ── 3. Sample document fields ────────────────────────────────
print("\n── 3. Sample Document Fields (first 5) ──")
sample_ids = list(json_ids)[:5]
for doc_id in sample_ids:
    json_doc = next((d for d in json_docs if d.get("id") == doc_id), None)
    db_doc = db.db_get_document(doc_id)
    
    if json_doc and db_doc:
        title_match = json_doc.get("title") == db_doc.get("title")
        type_match = json_doc.get("type") == db_doc.get("doc_type", db_doc.get("type"))
        class_match = json_doc.get("document_class", "source") == db_doc.get("document_class", "source")
        
        if title_match and type_match and class_match:
            check(f"Doc {doc_id[:12]}... fields match", True)
        else:
            check(f"Doc {doc_id[:12]}... fields match", False,
                  f"title={'OK' if title_match else 'MISMATCH'} type={'OK' if type_match else 'MISMATCH'} class={'OK' if class_match else 'MISMATCH'}")


# ── 4. Entries round-trip ─────────────────────────────────────
print("\n── 4. Entry Round-Trip (sample 3 docs) ──")
test_docs = [d for d in json_docs if d.get("entry_count", 0) > 0][:3]
for jd in test_docs:
    doc_id = jd["id"]
    # Load entries from JSON file
    entries_file = os.path.join(DATA_DIR, f"doc_{doc_id}_entries.json")
    if os.path.exists(entries_file):
        json_entries = load_json(entries_file, [])
        db_entries = db.db_get_entries(doc_id)
        
        if db_entries is None:
            check(f"Entries for {doc_id[:12]}...", False, "No entries in SQLite")
            continue
        
        count_match = len(json_entries) == len(db_entries)
        # Check first entry text
        text_match = True
        if json_entries and db_entries:
            text_match = json_entries[0].get("text", "")[:100] == db_entries[0].get("text", "")[:100]
        
        check(f"Entries for {jd['title'][:35]}... (count={len(json_entries)})",
              count_match and text_match,
              f"JSON={len(json_entries)} SQLite={len(db_entries) if db_entries else 0}")
    else:
        warn(f"No entries file for {doc_id[:12]}...")


# ── 5. Conversations ─────────────────────────────────────────
print("\n── 5. Conversations ──")
docs_with_threads = [d for d in json_docs if d.get("conversation_thread")]
thread_count_json = len(docs_with_threads)

# Count conversations in DB
db_conv_count = len(db.get_connection().execute(
    "SELECT DISTINCT doc_id FROM conversations").fetchall())

check(f"Conversation count: JSON={thread_count_json}, SQLite={db_conv_count}",
      thread_count_json == db_conv_count,
      f"Difference of {abs(thread_count_json - db_conv_count)}")

# Sample a conversation
if docs_with_threads:
    sample = docs_with_threads[0]
    json_thread = sample.get("conversation_thread", [])
    db_conv = db.db_get_conversation(sample["id"])
    if db_conv:
        db_msgs = db_conv.get("messages", [])
        check(f"Sample thread msg count: JSON={len(json_thread)}, SQLite={len(db_msgs)}",
              len(json_thread) == len(db_msgs))
        if json_thread and db_msgs:
            check(f"Sample thread first msg role match",
                  json_thread[0].get("role") == db_msgs[0].get("role"))
    else:
        check(f"Sample conversation loaded from SQLite", False, "None returned")


# ── 6. Branches ───────────────────────────────────────────────
print("\n── 6. Response Branches ──")
source_docs = [d for d in json_docs
               if d.get("document_class", "source") == "source"
               and d.get("type") != "conversation_thread"]

branch_checked = 0
for sd in source_docs[:5]:
    doc_id = sd["id"]
    # JSON-based branch check
    json_branches = []
    for d in json_docs:
        meta = d.get("metadata", {})
        orig = meta.get("original_document_id") or meta.get("parent_document_id")
        if orig == doc_id:
            json_branches.append(d["id"])

    # SQLite branch check
    db_branches = db.db_get_branches_for_source(doc_id)
    db_branch_ids = [b["id"] for b in db_branches]

    if json_branches or db_branch_ids:
        check(f"Branches for {sd['title'][:35]}... JSON={len(json_branches)} SQLite={len(db_branch_ids)}",
              set(json_branches) == set(db_branch_ids))
        branch_checked += 1

if branch_checked == 0:
    warn("No documents with branches found to test")


# ── 7. Processed Outputs ─────────────────────────────────────
print("\n── 7. Processed Outputs ──")
db_po_count = db.get_connection().execute(
    "SELECT COUNT(*) as c FROM processed_outputs").fetchone()["c"]
json_po_count = sum(1 for d in json_docs
                    for _ in d.get("processed_outputs", []))
check(f"Processed outputs: JSON={json_po_count}, SQLite={db_po_count}",
      json_po_count == db_po_count)


# ── SUMMARY ───────────────────────────────────────────────────
print("\n" + "=" * 70)
print(f"  RESULTS: {passed} passed, {failed} failed, {warnings} warnings")
print("=" * 70)

if failed == 0:
    print("\n  ALL CHECKS PASSED!")
    print("  Safe to enable USE_SQLITE_DOCUMENTS = True")
    print(f"\n  Open document_library.py, change line 36:")
    print(f"    USE_SQLITE_DOCUMENTS = False  -->  USE_SQLITE_DOCUMENTS = True")
    print(f"\n  Then restart DocAnalyser and test these workflows:")
    print(f"    1. Open Documents Library - verify your docs appear")
    print(f"    2. Load a document - verify text appears correctly")
    print(f"    3. Run a prompt - verify AI response works")
    print(f"    4. Check Thread Viewer - verify conversation loads")
    print(f"    5. Load a doc with branches - verify branch picker works")
else:
    print(f"\n  {failed} checks failed - investigate before enabling")
    print(f"  You may need to re-run db_migration.py to refresh the database")

sys.exit(0 if failed == 0 else 1)
