"""
test_v17_alpha_day1.py
======================
Standalone verification script for v1.7-alpha Day 1 schema additions.

Run from PyCharm (right-click -> Run) or command line BEFORE launching
DocAnalyser to confirm the new schema additions and the General
Corrections List seeding worked correctly.

Does not modify the database in any destructive way — it only calls
init_database() (idempotent — safe to run repeatedly) and then runs
read-only verification queries.

Expected output: a series of green check marks ending with "ALL CHECKS
PASSED — safe to launch DocAnalyser". If anything is red, do NOT launch
DocAnalyser; the database backup taken before this work is the safe
fallback.

Created: 28 April 2026 (v1.7-alpha Day 1)
"""

from __future__ import annotations

import sys
import os

# Make sure we can import db_manager from the parent directory
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _PROJECT_ROOT)

import db_manager as db


def main() -> bool:
    print("=" * 60)
    print("  v1.7-alpha Day 1 Verification")
    print("=" * 60)
    print(f"  Database path: {db.DB_PATH}")
    print()

    # Step 1: run init_database — applies new schema and seeds if needed
    print("  Step 1: Running init_database()...")
    try:
        db.init_database()
    except Exception as exc:
        print(f"  [FAIL] init_database() raised: {exc}")
        return False
    print("  [OK]   init_database() completed without error")
    print()

    conn = db.get_connection()

    # Step 2: verify new tables exist
    print("  Step 2: Checking new tables exist...")
    new_tables = ["corrections_lists", "corrections"]
    for table in new_tables:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if row:
            print(f"  [OK]   Table '{table}' exists")
        else:
            print(f"  [FAIL] Table '{table}' MISSING")
            return False
    print()

    # Step 3: verify table schemas have the expected columns
    print("  Step 3: Checking column structures...")
    expected = {
        "corrections_lists": {
            "id", "name", "description", "workspace_id",
            "created_at", "updated_at",
        },
        "corrections": {
            "id", "list_id", "original_text", "corrected_text",
            "case_sensitive", "word_boundary", "notes", "created_at",
        },
    }
    for table, want_cols in expected.items():
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        got_cols = {row["name"] for row in rows}
        missing = want_cols - got_cols
        extra = got_cols - want_cols
        if missing:
            print(f"  [FAIL] {table}: missing columns {missing}")
            return False
        if extra:
            print(f"  [WARN] {table}: unexpected extra columns {extra}")
        print(f"  [OK]   {table}: all {len(want_cols)} expected columns present")
    print()

    # Step 4: verify General list was seeded
    print("  Step 4: Checking 'General' Corrections List was seeded...")
    list_row = conn.execute(
        "SELECT id, name, description FROM corrections_lists WHERE name = 'General'"
    ).fetchone()
    if not list_row:
        print("  [FAIL] 'General' list not found")
        return False
    list_id = list_row["id"]
    desc = list_row["description"] or ""
    print(f"  [OK]   'General' list exists (id={list_id})")
    print(f"         Description: {desc[:80]}{'...' if len(desc) > 80 else ''}")

    entry_count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM corrections WHERE list_id = ?",
        (list_id,),
    ).fetchone()["cnt"]
    print(f"  [OK]   {entry_count} entries seeded")
    print()

    # Step 5: show sample entries to confirm they look right
    print("  Step 5: Sample entries (first 3)...")
    sample = conn.execute(
        "SELECT original_text, corrected_text, case_sensitive, "
        "word_boundary, notes "
        "FROM corrections WHERE list_id = ? ORDER BY id LIMIT 3",
        (list_id,),
    ).fetchall()
    for i, row in enumerate(sample, 1):
        orig = repr(row["original_text"])
        corr = repr(row["corrected_text"])
        flags = []
        if row["case_sensitive"]:
            flags.append("case-sensitive")
        if row["word_boundary"]:
            flags.append("word-boundary")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        print(f"         {i}. {orig} -> {corr}{flag_str}")
        if row["notes"]:
            print(f"            ({row['notes']})")
    print()

    # Step 6: verify the seeding flag is set
    print("  Step 6: Checking seeding flag is set...")
    flag = conn.execute(
        "SELECT value FROM db_meta WHERE key = 'corrections_general_seeded'"
    ).fetchone()
    if flag and flag["value"] == "true":
        print("  [OK]   Flag 'corrections_general_seeded' = 'true'")
    else:
        print("  [FAIL] Flag not set — seeding did not complete")
        return False
    print()

    # Step 7: sanity check — existing data still intact
    print("  Step 7: Sanity check on existing data...")
    existing_tables = [
        "documents", "document_entries", "conversations", "messages",
        "processed_outputs", "prompts", "prompt_versions",
        "folders", "folder_items", "cost_log", "embeddings",
    ]
    for table in existing_tables:
        try:
            cnt = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM {table}"
            ).fetchone()["cnt"]
            print(f"         {table:22s}: {cnt:>6} rows")
        except Exception as exc:
            print(f"  [FAIL] Could not query {table}: {exc}")
            return False
    print()

    print("=" * 60)
    print("  ALL CHECKS PASSED -- safe to launch DocAnalyser")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
