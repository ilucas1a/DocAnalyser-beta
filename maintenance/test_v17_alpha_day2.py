"""
test_v17_alpha_day2.py
======================
Standalone verification script for v1.7-alpha Day 2 deliverables:
the corrections_db_adapter and corrections_engine modules.

Exercises the full CRUD path on a temporary list named
TEST_DAY2_TEMP_DELETE_IF_FOUND, plus JSON round-trip and the
apply_corrections_to_text() function. Cleans up after itself even
if checks fail; if a previous run crashed mid-way, leftover test
data is detected and removed at the start.

The bundled "General" list is treated as read-only by this script —
its row count is checked before and after to confirm nothing leaked.
The script is safe to run on the production database.

Run from PyCharm (right-click -> Run) or command line:
    python maintenance\\test_v17_alpha_day2.py

Expected output: a series of [OK] lines ending with
"ALL CHECKS PASSED -- Day 2 backend is wired up correctly".

Created: 28 April 2026 (v1.7-alpha Day 2)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

# Make sure we can import from the parent directory
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _PROJECT_ROOT)

import db_manager as db
import corrections_db_adapter as adapter
import corrections_engine as engine

TEST_LIST_NAME = "TEST_DAY2_TEMP_DELETE_IF_FOUND"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleanup_leftover_test_data() -> None:
    """Remove any leftover test list from a previous crashed run.
    Also cleans imported copies named TEST_LIST_NAME (imported [N])."""
    leftover = db.db_get_corrections_list_by_name(TEST_LIST_NAME)
    if leftover is not None:
        db.db_delete_corrections_list(leftover["id"])
        print(f"  [INFO] Removed leftover test list (id={leftover['id']})")
    # Also clean any leftover imported copies
    for lst in db.db_get_all_corrections_lists():
        if lst["name"].startswith(TEST_LIST_NAME) and lst["name"] != TEST_LIST_NAME:
            db.db_delete_corrections_list(lst["id"])
            print(f"  [INFO] Removed leftover imported copy: {lst['name']!r}")


def _general_baseline():
    """Snapshot the General list's id and entry count for invariance check."""
    g = db.db_get_corrections_list_by_name(adapter.BUNDLED_LIST_NAME)
    if g is None:
        return (-1, -1)
    cnt = len(db.db_get_corrections(g["id"]))
    return (g["id"], cnt)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> bool:
    print("=" * 60)
    print("  v1.7-alpha Day 2 Verification")
    print("=" * 60)
    print(f"  Database path: {db.DB_PATH}")
    print()

    # Ensure schema is in place (idempotent)
    db.init_database()

    # Pre-clean any leftover test data from a previous run
    _cleanup_leftover_test_data()

    # Snapshot General list before any changes
    general_before = _general_baseline()
    if general_before == (-1, -1):
        print("  [FAIL] Bundled 'General' list not found. Run Day 1 test first.")
        return False
    print(f"  General list baseline: id={general_before[0]}, "
          f"entries={general_before[1]}")
    print()

    list_id = None
    try:
        # --------------------------------------------------------------
        # Step 1 — List CRUD via adapter
        # --------------------------------------------------------------
        print("  Step 1: List CRUD via adapter...")
        list_id = adapter.list_create(
            name=TEST_LIST_NAME,
            description="Throwaway list for Day 2 verification.",
        )
        print(f"  [OK]   Created list (id={list_id})")

        got = adapter.list_get(list_id)
        assert got is not None and got["name"] == TEST_LIST_NAME, \
            "list_get returned wrong row"
        print("  [OK]   list_get returns the new list")

        all_lists = adapter.list_get_all()
        assert any(lst["id"] == list_id for lst in all_lists), \
            "list_get_all does not include the new list"
        print(f"  [OK]   list_get_all returns {len(all_lists)} lists "
              f"(includes new one)")

        ok = adapter.list_update(list_id, description="Updated description.")
        assert ok, "list_update returned False"
        got = adapter.list_get(list_id)
        assert got["description"] == "Updated description.", \
            "Description did not update"
        print("  [OK]   list_update modified description")

        # Duplicate-name guard
        try:
            adapter.list_create(name=TEST_LIST_NAME)
            print("  [FAIL] Duplicate name was allowed")
            return False
        except ValueError:
            print("  [OK]   Duplicate name correctly rejected")

        # Bundled-list protection
        general = db.db_get_corrections_list_by_name(adapter.BUNDLED_LIST_NAME)
        try:
            adapter.list_delete(general["id"])
            print("  [FAIL] Bundled list deletion was allowed")
            return False
        except ValueError:
            print("  [OK]   Bundled list deletion correctly rejected")

        try:
            adapter.list_update(general["id"], name="Renamed")
            print("  [FAIL] Bundled list rename was allowed")
            return False
        except ValueError:
            print("  [OK]   Bundled list rename correctly rejected")

        # Empty-name guard
        try:
            adapter.list_create(name="   ")
            print("  [FAIL] Whitespace-only name was allowed")
            return False
        except ValueError:
            print("  [OK]   Whitespace-only name correctly rejected")
        print()

        # --------------------------------------------------------------
        # Step 2 — Correction CRUD via adapter
        # --------------------------------------------------------------
        print("  Step 2: Correction CRUD via adapter...")
        c1 = adapter.correction_add(
            list_id, "Quang Tri", "Quang Tri (corrected)",
            case_sensitive=False, word_boundary=True,
            notes="Vietnamese province"
        )
        c2 = adapter.correction_add(
            list_id, "tell vision", "television",
            case_sensitive=False, word_boundary=True,
        )
        c3 = adapter.correction_add(
            list_id, " :", ":",
            case_sensitive=False, word_boundary=False,
            notes="space-before-colon"
        )
        print(f"  [OK]   Added 3 corrections (ids={c1},{c2},{c3})")

        entries = adapter.correction_get_all_for_list(list_id)
        assert len(entries) == 3, f"Expected 3 entries, got {len(entries)}"
        print(f"  [OK]   correction_get_all_for_list returns {len(entries)} entries")

        ok = adapter.correction_update(c1, notes="Updated note")
        assert ok, "correction_update returned False"
        got = adapter.correction_get(c1)
        assert got["notes"] == "Updated note", "Note did not update"
        print("  [OK]   correction_update modified notes")

        ok = adapter.correction_delete(c3)
        assert ok, "correction_delete returned False"
        entries = adapter.correction_get_all_for_list(list_id)
        assert len(entries) == 2, "Entry was not deleted"
        print("  [OK]   correction_delete removed entry")

        # Empty original_text guard
        try:
            adapter.correction_add(list_id, "", "something")
            print("  [FAIL] Empty original_text was allowed")
            return False
        except ValueError:
            print("  [OK]   Empty original_text correctly rejected")
        print()

        # --------------------------------------------------------------
        # Step 3 — JSON export/import round-trip
        # --------------------------------------------------------------
        print("  Step 3: JSON export/import round-trip...")
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = os.path.join(tmpdir, "test_export.json")
            adapter.list_export_json(list_id, json_path)
            assert os.path.exists(json_path), "Export file not created"
            with open(json_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            assert payload["name"] == TEST_LIST_NAME
            assert len(payload["entries"]) == 2
            print(f"  [OK]   Exported {len(payload['entries'])} entries to JSON")

            imported_id = adapter.list_import_json(json_path)
            imported = adapter.list_get(imported_id)
            assert imported["name"].startswith(TEST_LIST_NAME), \
                f"Unexpected imported name: {imported['name']!r}"
            assert imported["name"] != TEST_LIST_NAME, \
                "Imported name should have been disambiguated"
            imp_entries = adapter.correction_get_all_for_list(imported_id)
            assert len(imp_entries) == 2, "Imported entry count mismatch"
            print(f"  [OK]   Imported as {imported['name']!r} "
                  f"(id={imported_id}, {len(imp_entries)} entries)")

            # Tidy up the imported list before continuing
            db.db_delete_corrections_list(imported_id)
        print()

        # --------------------------------------------------------------
        # Step 4 — apply_corrections_to_text() core scenarios
        # --------------------------------------------------------------
        print("  Step 4: apply_corrections_to_text() scenarios...")
        general_id = general["id"]

        # 4a — Punctuation spacing using General list
        sample = "Hello , world . How are you ?"
        out = engine.apply_corrections_to_text(sample, general_id)
        expected = "Hello, world. How are you?"
        assert out == expected, \
            f"Punctuation: got {out!r} expected {expected!r}"
        print(f"  [OK]   Punctuation spacing: {sample!r} -> {out!r}")

        # 4b — Word-boundary protection (alot vs shallot)
        sample = "I watched alot of TV alot of times. The shallot was nice."
        out = engine.apply_corrections_to_text(sample, general_id)
        assert "a lot of TV a lot of times" in out, \
            f"alot replacement failed: {out!r}"
        assert "shallot" in out, \
            f"shallot was wrongly replaced: {out!r}"
        print(f"  [OK]   Word-boundary protected 'shallot' from 'alot' rule")

        # 4c — Multi-word phrase
        sample = "He said tell vision was bad."
        out = engine.apply_corrections_to_text(sample, general_id)
        assert "television was bad" in out, f"Multi-word: {out!r}"
        print(f"  [OK]   Multi-word phrase: {out!r}")

        # 4d — Case-insensitive default (Alot and alot both replaced)
        sample = "Alot of people say alot."
        out = engine.apply_corrections_to_text(sample, general_id)
        assert out.lower().count("a lot") == 2, \
            f"Case-insensitive count wrong: {out!r}"
        print(f"  [OK]   Case-insensitive: {sample!r} -> {out!r}")

        # 4e — Empty text
        assert engine.apply_corrections_to_text("", general_id) == ""
        print("  [OK]   Empty input returns empty string")

        # 4f — Non-existent list
        assert engine.apply_corrections_to_text("anything", 999999) == "anything"
        print("  [OK]   Non-existent list returns text unchanged")

        # 4g — Stats variant
        sample = "Hello , world . tell vision is great"
        out, stats = engine.apply_corrections_with_stats(sample, general_id)
        total_hits = sum(s["hits"] for s in stats)
        # Expected hits: " ," (1) + " ." (1) + "tell vision" (1) >= 3
        assert total_hits >= 3, f"Expected >= 3 hits, got {total_hits}"
        print(f"  [OK]   Stats: {len(stats)} entries reported, "
              f"{total_hits} total hits")
        print()

        # --------------------------------------------------------------
        # Step 5 — Longest-match-wins (synthetic test)
        # --------------------------------------------------------------
        print("  Step 5: Longest-match-wins (synthetic test)...")
        c_short = adapter.correction_add(list_id, "tell", "TELL",
                                         case_sensitive=False,
                                         word_boundary=True)
        c_long = adapter.correction_add(list_id, "tell vision", "television",
                                        case_sensitive=False,
                                        word_boundary=True)
        out = engine.apply_corrections_to_text(
            "Please tell vision now and tell me later.", list_id
        )
        assert "television now" in out, \
            f"Longest match did not win: {out!r}"
        assert "TELL me later" in out, \
            f"Shorter rule did not run: {out!r}"
        print(f"  [OK]   Longest match wins, shorter rule still applies:")
        print(f"         -> {out!r}")
        adapter.correction_delete(c_short)
        adapter.correction_delete(c_long)
        print()

        # --------------------------------------------------------------
        # Step 6 — General list invariance
        # --------------------------------------------------------------
        print("  Step 6: General list unchanged after all operations...")
        general_after = _general_baseline()
        assert general_after == general_before, \
            f"General list changed: before={general_before} after={general_after}"
        print(f"  [OK]   General list intact: id={general_after[0]}, "
              f"entries={general_after[1]}")
        print()

    finally:
        # --------------------------------------------------------------
        # Cleanup
        # --------------------------------------------------------------
        if list_id is not None:
            try:
                db.db_delete_corrections_list(list_id)
                print(f"  [INFO] Cleaned up test list (id={list_id})")
            except Exception as exc:
                print(f"  [WARN] Could not clean up test list: {exc}")
        # Also clean any imported copies that survived
        _cleanup_leftover_test_data()

    print()
    print("=" * 60)
    print("  ALL CHECKS PASSED -- Day 2 backend is wired up correctly")
    print("=" * 60)
    return True


if __name__ == "__main__":
    try:
        success = main()
    except AssertionError as exc:
        print(f"\n  [FAIL] Assertion failed: {exc}")
        success = False
    except Exception as exc:
        print(f"\n  [FAIL] Unexpected error: {exc}")
        import traceback
        traceback.print_exc()
        success = False
    sys.exit(0 if success else 1)
