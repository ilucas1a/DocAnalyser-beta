"""
test_v17_alpha_day3.py
======================
Standalone verification script for v1.7-alpha Day 3:
the wiring of apply_corrections_list() into transcript_cleaner.clean_transcript()
as the new Phase 3.

Verifies that:
  1. Default behaviour (no corrections_list_id) is unchanged.
  2. Passing a valid list id applies corrections and reports the count.
  3. Multi-word phrases that span across whisper-segment boundaries are
     correctly unified by Phase 2 and then corrected by Phase 3.
  4. corrections_list_id=None is identical to omitting the parameter.
  5. Invalid list ids are silently no-ops (no crash, no changes).
  6. Empty lists are no-ops.
  7. Renumbered downstream phases still produce structurally valid output.

Run from PyCharm (right-click -> Run) or command line:
    python maintenance\\test_v17_alpha_day3.py

Expected output: a series of [OK] lines ending with
"ALL CHECKS PASSED -- Day 3 pipeline integration works".

This script does not modify the production database in any way.

Created: 28 April 2026 (v1.7-alpha Day 3)
"""

from __future__ import annotations

import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _PROJECT_ROOT)

import db_manager as db
import corrections_db_adapter as adapter
import transcript_cleaner as cleaner

EMPTY_TEST_LIST_NAME = "TEST_DAY3_EMPTY_TEMP_DELETE_IF_FOUND"


def _cleanup_leftover_test_data() -> None:
    """Remove any leftover test list from a previous crashed run."""
    leftover = db.db_get_corrections_list_by_name(EMPTY_TEST_LIST_NAME)
    if leftover is not None:
        db.db_delete_corrections_list(leftover["id"])
        print(f"  [INFO] Removed leftover test list (id={leftover['id']})")


def _build_test_entries():
    """
    Build a fixture of whisper-style entries containing transcription
    errors that the bundled General list knows how to fix:

      * 'tell vision' deliberately split across two segments — verifies
        Phase 2 unifies it before Phase 3 sees it.
      * 'alot' inline — verifies straightforward word-boundary correction.
      * Spaces before punctuation — verifies the punctuation-spacing
        entries fire correctly.

    Sentence-gap threshold is 1.2s, so consecutive entries within that
    gap will consolidate into one sentence at Phase 2.
    """
    return [
        {"start": 0.0, "end": 0.4, "text": "I was watching tell"},
        {"start": 0.5, "end": 1.0, "text": "vision yesterday"},
        {"start": 1.2, "end": 2.0, "text": "and saw alot of news ."},
    ]


def main() -> bool:
    print("=" * 60)
    print("  v1.7-alpha Day 3 Verification")
    print("=" * 60)
    print(f"  Database path: {db.DB_PATH}")
    print()

    db.init_database()
    _cleanup_leftover_test_data()

    # Locate the bundled General list
    general = db.db_get_corrections_list_by_name(adapter.BUNDLED_LIST_NAME)
    if general is None:
        print("  [FAIL] Bundled 'General' list not found. Run Day 1 test first.")
        return False
    general_id = general["id"]
    general_entry_count = len(db.db_get_corrections(general_id))
    print(f"  Using General list (id={general_id}, "
          f"{general_entry_count} entries)")
    print()

    empty_id = None
    try:
        # --------------------------------------------------------------
        # Step 1 — Baseline: no corrections list passed
        # --------------------------------------------------------------
        print("  Step 1: clean_transcript without corrections_list_id...")
        baseline = cleaner.clean_transcript(entries=_build_test_entries())
        assert baseline.get("corrections_applied", -1) == 0, \
            f"Expected corrections_applied=0, got {baseline.get('corrections_applied')}"
        baseline_text = " ".join(p["text"] for p in baseline["paragraphs"])
        assert "tell vision" in baseline_text, \
            f"Baseline should still contain 'tell vision': {baseline_text!r}"
        assert "alot" in baseline_text, \
            f"Baseline should still contain 'alot': {baseline_text!r}"
        print(f"  [OK]   Baseline text: {baseline_text!r}")
        print(f"  [OK]   corrections_applied = 0")
        print()

        # --------------------------------------------------------------
        # Step 2 — corrections_list_id=None matches default behaviour
        # --------------------------------------------------------------
        print("  Step 2: corrections_list_id=None matches default behaviour...")
        none_result = cleaner.clean_transcript(
            entries=_build_test_entries(),
            corrections_list_id=None,
        )
        none_text = " ".join(p["text"] for p in none_result["paragraphs"])
        assert none_text == baseline_text, \
            f"None should match baseline.\n  baseline: {baseline_text!r}\n  None:     {none_text!r}"
        assert none_result.get("corrections_applied", -1) == 0
        print(f"  [OK]   corrections_list_id=None gives baseline output")
        print()

        # --------------------------------------------------------------
        # Step 3 — General list applied
        # --------------------------------------------------------------
        print("  Step 3: clean_transcript with corrections_list_id=General...")
        result = cleaner.clean_transcript(
            entries=_build_test_entries(),
            corrections_list_id=general_id,
        )
        hits = result.get("corrections_applied", 0)
        assert hits > 0, f"Expected hits > 0, got {hits}"
        cleaned_text = " ".join(p["text"] for p in result["paragraphs"])

        # Multi-word phrase split across segments must have been unified
        # by Phase 2 and then corrected by Phase 3
        assert "television" in cleaned_text, \
            f"Multi-word 'tell vision' (split across 2 segments) should " \
            f"have been corrected: {cleaned_text!r}"
        assert "tell vision" not in cleaned_text, \
            f"'tell vision' should be gone: {cleaned_text!r}"

        # In-segment word with word-boundary rule
        assert "a lot" in cleaned_text, \
            f"'alot' should have been corrected to 'a lot': {cleaned_text!r}"
        assert "alot" not in cleaned_text, \
            f"'alot' should be gone: {cleaned_text!r}"

        # Punctuation spacing
        assert " ." not in cleaned_text, \
            f"' .' (space-before-period) should have been fixed: {cleaned_text!r}"

        print(f"  [OK]   Cleaned text: {cleaned_text!r}")
        print(f"  [OK]   corrections_applied = {hits}")
        print(f"  [OK]   Multi-word phrase split across segments unified "
              f"and corrected")
        print()

        # --------------------------------------------------------------
        # Step 4 — Invalid list id is a silent no-op
        # --------------------------------------------------------------
        print("  Step 4: invalid corrections_list_id is a no-op...")
        bad_result = cleaner.clean_transcript(
            entries=_build_test_entries(),
            corrections_list_id=999999,
        )
        bad_text = " ".join(p["text"] for p in bad_result["paragraphs"])
        assert bad_text == baseline_text, \
            f"Invalid id should not change text:\n  baseline: {baseline_text!r}\n  bad:      {bad_text!r}"
        assert bad_result.get("corrections_applied", -1) == 0
        print(f"  [OK]   Invalid id leaves text unchanged, no exception raised")
        print()

        # --------------------------------------------------------------
        # Step 5 — Empty list is a no-op
        # --------------------------------------------------------------
        print("  Step 5: empty corrections list is a no-op...")
        empty_id = adapter.list_create(
            EMPTY_TEST_LIST_NAME,
            description="Empty test list (no entries) for Day 3 verification."
        )
        empty_result = cleaner.clean_transcript(
            entries=_build_test_entries(),
            corrections_list_id=empty_id,
        )
        empty_text = " ".join(p["text"] for p in empty_result["paragraphs"])
        assert empty_text == baseline_text, \
            f"Empty list should not change text:\n  baseline: {baseline_text!r}\n  empty:    {empty_text!r}"
        assert empty_result.get("corrections_applied", -1) == 0
        print(f"  [OK]   Empty list leaves text unchanged")
        print()

        # --------------------------------------------------------------
        # Step 6 — Pipeline structure intact (renumbered phases all work)
        # --------------------------------------------------------------
        print("  Step 6: pipeline structure intact after renumbering...")
        for key in ("paragraphs", "fillers_removed", "corrections_applied",
                    "diarization_used", "speaker_ids", "warnings"):
            assert key in result, f"Missing key in return dict: {key}"
        assert len(result["paragraphs"]) > 0, "No paragraphs produced"
        p = result["paragraphs"][0]
        for key in ("start", "end", "text", "timestamp", "speaker", "provisional"):
            assert key in p, f"Missing key in paragraph dict: {key}"
        assert p["start"] >= 0.0
        assert p["end"] >= p["start"]
        print(f"  [OK]   Return dict has all 6 expected keys")
        print(f"  [OK]   {len(result['paragraphs'])} paragraph(s) produced "
              f"with full structure")
        print()

        # --------------------------------------------------------------
        # Step 7 — Module-level apply_corrections_list() callable directly
        # --------------------------------------------------------------
        print("  Step 7: apply_corrections_list() callable as a Phase 3 unit...")
        # Build sentences as Phase 2 would produce them
        synthetic_sentences = [
            {"start": 0.0, "end": 1.0, "text": "I was watching tell vision.",
             "timestamp": "[00:00:00]", "speaker": "", "provisional": False},
            {"start": 1.5, "end": 2.5, "text": "It had alot of ads.",
             "timestamp": "[00:00:01]", "speaker": "", "provisional": False},
        ]
        modified, total = cleaner.apply_corrections_list(
            synthetic_sentences, general_id
        )
        assert total > 0, f"Expected > 0 hits, got {total}"
        assert "television" in modified[0]["text"], \
            f"Sentence 1 not corrected: {modified[0]['text']!r}"
        assert "a lot" in modified[1]["text"], \
            f"Sentence 2 not corrected: {modified[1]['text']!r}"
        # Original timestamps and metadata preserved
        assert modified[0]["start"] == 0.0
        assert modified[1]["timestamp"] == "[00:00:01]"
        print(f"  [OK]   apply_corrections_list({{2 sentences}}, general) "
              f"-> {total} hits, timestamps preserved")
        print()

        # --------------------------------------------------------------
        # Step 8 — General list invariance
        # --------------------------------------------------------------
        print("  Step 8: General list unchanged after all operations...")
        after_count = len(db.db_get_corrections(general_id))
        assert after_count == general_entry_count, \
            f"General list entry count changed: {general_entry_count} -> {after_count}"
        print(f"  [OK]   General list intact: id={general_id}, "
              f"entries={after_count}")
        print()

    finally:
        if empty_id is not None:
            try:
                db.db_delete_corrections_list(empty_id)
                print(f"  [INFO] Cleaned up empty test list (id={empty_id})")
            except Exception as exc:
                print(f"  [WARN] Could not clean up empty test list: {exc}")

    print()
    print("=" * 60)
    print("  ALL CHECKS PASSED -- Day 3 pipeline integration works")
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
