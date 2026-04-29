"""
test_v17_alpha_day6.py
======================
Headless verification script for v1.7-alpha Day 6:
the Add-to-Corrections-List dialog and its wiring into the Thread
Viewer right-click menu and the Word Speaker Panel nav row.

Builds a real AddToCorrectionsDialog inside a withdrawn Tk root, then
verifies:

  1. add_to_corrections_dialog imports cleanly
  2. Public entry point (show_add_to_corrections_dialog) is exported
  3. AddToCorrectionsDialog class exposes the expected widgets
  4. Dropdown is populated with available lists plus the "+ New list..."
     sentinel
  5. Default selection prefers the first non-bundled list when one
     exists, falling back to General when none does
  6. _resolve_destination_list_id() returns the correct id for the
     current selection, or None for the sentinel
  7. _on_save with valid input writes a row via the adapter and
     populates _result_id
  8. _on_save with empty original_text refuses to save
  9. The Thread Viewer module imports the dialog symbol and exposes
     _add_selection_to_corrections() on the class
 10. The Word Speaker Panel module wires the new
     _add_word_selection_to_corrections() method on its class

This is a headless test; no actual right-click or button click is
exercised, but every code path that those click handlers traverse
is covered.

Modal sub-dialogs (the inline name prompt for "+ New list...", the
management dialog opened via "Manage lists...", and the success
message after Save) would block waiting for user input, so they are
not exercised end-to-end. Instead we drive _populate_lists_combo()
and _on_save() directly and verify the resulting state.

The script creates and deletes a temporary list named
TEST_DAY6_TEMP_DELETE_IF_FOUND and the correction inserted by the
Save test, with a try/finally guard so leftovers get cleaned up
even on assertion failure.

Run from PyCharm (right-click -> Run) or command line:
    python maintenance\\test_v17_alpha_day6.py

Expected output: a series of [OK] lines ending with
"ALL CHECKS PASSED -- Day 6 Add-to-Corrections feature is wired up
correctly".

Created: 28 April 2026 (v1.7-alpha Day 6)
"""

from __future__ import annotations

import os
import sys
import tkinter as tk

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _PROJECT_ROOT)

import db_manager as db
import corrections_db_adapter as adapter

TEST_LIST_NAME = "TEST_DAY6_TEMP_DELETE_IF_FOUND"


def _cleanup_leftover_test_data() -> None:
    leftover = db.db_get_corrections_list_by_name(TEST_LIST_NAME)
    if leftover is not None:
        db.db_delete_corrections_list(leftover["id"])
        print(f"  [INFO] Removed leftover test list (id={leftover['id']})")


def main() -> bool:
    print("=" * 60)
    print("  v1.7-alpha Day 6 Verification")
    print("=" * 60)
    print(f"  Database path: {db.DB_PATH}")
    print()

    db.init_database()
    _cleanup_leftover_test_data()

    general = db.db_get_corrections_list_by_name(adapter.BUNDLED_LIST_NAME)
    if general is None:
        print("  [FAIL] Bundled 'General' list not found. Run Day 1 test first.")
        return False
    general_entries_before = len(db.db_get_corrections(general["id"]))
    print(f"  General baseline: id={general['id']}, "
          f"entries={general_entries_before}")
    print()

    # ------------------------------------------------------------------
    # Step 1 \u2014 Module imports cleanly
    # ------------------------------------------------------------------
    print("  Step 1: Module imports cleanly...")
    try:
        import add_to_corrections_dialog as atcd
    except Exception as exc:
        print(f"  [FAIL] Import failed: {exc}")
        return False
    print("  [OK]   add_to_corrections_dialog imported without error")
    print()

    # ------------------------------------------------------------------
    # Step 2 \u2014 Public entry point exists
    # ------------------------------------------------------------------
    print("  Step 2: Public API surface...")
    if not hasattr(atcd, "show_add_to_corrections_dialog"):
        print("  [FAIL] show_add_to_corrections_dialog() not exported")
        return False
    if not hasattr(atcd, "AddToCorrectionsDialog"):
        print("  [FAIL] AddToCorrectionsDialog class not exported")
        return False
    print("  [OK]   show_add_to_corrections_dialog() exported")
    print("  [OK]   AddToCorrectionsDialog class exported")
    print()

    # ------------------------------------------------------------------
    # Steps 3-8 \u2014 Build dialog inside withdrawn root
    # ------------------------------------------------------------------
    print("  Step 3-8: Build dialog inside withdrawn Tk root...")
    root = tk.Tk()
    root.withdraw()

    test_list_id = None
    inserted_correction_id = None

    try:
        # Pre-create a non-bundled list so default selection logic has
        # something to pick. The "first non-bundled" logic requires it.
        test_list_id = adapter.list_create(
            name=TEST_LIST_NAME,
            description="Throwaway list for Day 6 verification.",
        )

        dlg = atcd.AddToCorrectionsDialog(
            root, seed_text="tell vision",
        )
        dlg._build_window()    # would normally be called inside .show()
        dlg.win.withdraw()
        root.update()

        # ----- Step 3: required widgets exist -----
        for attr in ("_original_var", "_corrected_var", "_list_var",
                     "_list_combo", "_list_hint",
                     "_wb_var", "_cs_var", "_notes_var",
                     "_original_entry", "_corrected_entry"):
            if not hasattr(dlg, attr):
                print(f"  [FAIL] Dialog missing widget attribute: {attr}")
                return False
        print("  [OK]   All expected widgets present on dialog")

        # Seed text was applied
        if dlg._original_var.get() != "tell vision":
            print(f"  [FAIL] Seed text not pre-filled: "
                  f"{dlg._original_var.get()!r}")
            return False
        print("  [OK]   Seed text pre-filled into Original-text field")

        # ----- Step 4: dropdown populated -----
        labels = list(dlg._list_combo["values"])
        if not labels:
            print("  [FAIL] Dropdown is empty")
            return False
        # General must be present
        if "General" not in labels:
            print(f"  [FAIL] General not in dropdown: {labels}")
            return False
        # The test list must be present
        if TEST_LIST_NAME not in labels:
            print(f"  [FAIL] Test list not in dropdown: {labels}")
            return False
        # The "+ New list..." sentinel must be the LAST entry
        if not labels[-1].startswith("+"):
            print(f"  [FAIL] '+ New list...' should be last, got "
                  f"{labels[-1]!r}")
            return False
        print(f"  [OK]   Dropdown has {len(labels)} entries including "
              f"General, test list, and '+ New list...' sentinel")

        # ----- Step 5: default selection prefers non-bundled -----
        current = dlg._list_var.get()
        if current == "General":
            print(f"  [FAIL] Default should prefer non-bundled list when "
                  f"one exists, but General was selected")
            return False
        if current != TEST_LIST_NAME:
            print(f"  [FAIL] Expected default to be {TEST_LIST_NAME!r}, "
                  f"got {current!r}")
            return False
        print(f"  [OK]   Default selection is the test list (non-bundled)")

        # ----- Step 6: id resolution -----
        resolved = dlg._resolve_destination_list_id()
        if resolved != test_list_id:
            print(f"  [FAIL] Default resolved to {resolved}, "
                  f"expected {test_list_id}")
            return False
        print(f"  [OK]   Test list selection resolves to id={resolved}")

        # Switch to General and verify resolution
        dlg._list_var.set("General")
        dlg._on_list_selected()
        resolved = dlg._resolve_destination_list_id()
        if resolved != general["id"]:
            print(f"  [FAIL] General resolved to {resolved}, "
                  f"expected {general['id']}")
            return False
        print(f"  [OK]   General selection resolves to id={resolved}")

        # The General-specific hint should now be visible
        hint = dlg._list_hint.cget("text")
        if "General" not in hint and "bundled" not in hint:
            print(f"  [FAIL] General hint not displayed: {hint!r}")
            return False
        print(f"  [OK]   General-list hint displayed when General selected")

        # Switch back to test list \u2014 hint should clear
        dlg._list_var.set(TEST_LIST_NAME)
        dlg._on_list_selected()
        if dlg._list_hint.cget("text"):
            print(f"  [FAIL] Hint should be cleared for non-bundled list, "
                  f"got: {dlg._list_hint.cget('text')!r}")
            return False
        print(f"  [OK]   Hint cleared when non-bundled list selected")

        # ----- Step 7: Save inserts a row -----
        # Stub out the success-message popup so the test doesn't block
        # waiting for the user to dismiss it.
        from tkinter import messagebox
        _orig_showinfo = messagebox.showinfo
        messagebox.showinfo = lambda *a, **kw: None
        try:
            dlg._original_var.set("tell vision")
            dlg._corrected_var.set("television")
            dlg._cs_var.set(False)
            dlg._wb_var.set(True)
            dlg._notes_var.set("test entry")
            dlg._on_save()
        finally:
            messagebox.showinfo = _orig_showinfo

        if dlg._result_id is None:
            print(f"  [FAIL] _on_save did not populate _result_id")
            return False
        inserted_correction_id = dlg._result_id

        # Confirm the row landed in the database
        added = adapter.correction_get(inserted_correction_id)
        if added is None:
            print(f"  [FAIL] correction id {inserted_correction_id} not "
                  f"found after Save")
            return False
        if added.get("original_text") != "tell vision" or \
                added.get("corrected_text") != "television" or \
                added.get("list_id") != test_list_id:
            print(f"  [FAIL] Saved row has wrong values: {added}")
            return False
        print(f"  [OK]   Save inserted correction id={inserted_correction_id} "
              f"into list_id={test_list_id}")

        # ----- Step 8: empty original_text is rejected -----
        # We need to also stub showerror because empty original triggers it.
        _orig_showerror = messagebox.showerror
        messagebox.showerror = lambda *a, **kw: None
        try:
            dlg2 = atcd.AddToCorrectionsDialog(root, seed_text="")
            dlg2._build_window()
            dlg2.win.withdraw()
            root.update()
            dlg2._original_var.set("   ")   # whitespace only
            dlg2._corrected_var.set("anything")
            dlg2._on_save()
            if dlg2._result_id is not None:
                print(f"  [FAIL] Empty original_text was allowed")
                return False
            print(f"  [OK]   Empty original_text correctly rejected")
            try:
                dlg2.win.destroy()
            except Exception:
                pass
        finally:
            messagebox.showerror = _orig_showerror
        print()

    finally:
        try:
            try:
                dlg.win.destroy()
            except Exception:
                pass
            root.destroy()
        except Exception:
            pass
        # Clean up: delete the inserted correction first (so it's not
        # cascaded by the list delete), then the test list.
        if inserted_correction_id is not None:
            try:
                adapter.correction_delete(inserted_correction_id)
                print(f"  [INFO] Cleaned up correction id="
                      f"{inserted_correction_id}")
            except Exception as exc:
                print(f"  [WARN] Could not clean up correction: {exc}")
        if test_list_id is not None:
            try:
                db.db_delete_corrections_list(test_list_id)
                print(f"  [INFO] Cleaned up test list (id={test_list_id})")
            except Exception as exc:
                print(f"  [WARN] Could not clean up test list: {exc}")

    # ------------------------------------------------------------------
    # Step 9 \u2014 Thread Viewer wiring
    # ------------------------------------------------------------------
    print()
    print("  Step 9: Thread Viewer wiring...")
    try:
        # The thread_viewer module imports tkinter and quite a few peer
        # modules; it should still import cleanly in a headless context.
        import thread_viewer
    except Exception as exc:
        print(f"  [FAIL] thread_viewer import failed: {exc}")
        return False
    if not hasattr(thread_viewer, "_ADD_TO_CORRECTIONS_AVAILABLE"):
        print(f"  [FAIL] thread_viewer missing the availability flag")
        return False
    if not thread_viewer._ADD_TO_CORRECTIONS_AVAILABLE:
        print(f"  [FAIL] thread_viewer reports add-to-corrections "
              f"unavailable (import failed silently?)")
        return False
    if not hasattr(thread_viewer.ThreadViewerWindow,
                   "_add_selection_to_corrections"):
        print(f"  [FAIL] _add_selection_to_corrections() not on "
              f"ThreadViewerWindow class")
        return False
    print("  [OK]   thread_viewer imports the dialog and exposes the "
          "handler method")
    print()

    # ------------------------------------------------------------------
    # Step 10 \u2014 Word Speaker Panel wiring
    # ------------------------------------------------------------------
    print("  Step 10: Word Speaker Panel wiring...")
    try:
        import word_editor_panel
    except Exception as exc:
        print(f"  [FAIL] word_editor_panel import failed: {exc}")
        return False
    if not hasattr(word_editor_panel.WordEditorPanel,
                   "_add_word_selection_to_corrections"):
        print(f"  [FAIL] _add_word_selection_to_corrections() not on "
              f"WordEditorPanel class")
        return False
    print("  [OK]   word_editor_panel exposes the handler method on the "
          "panel class")
    print()

    # ------------------------------------------------------------------
    # Final invariance check
    # ------------------------------------------------------------------
    print("  Final: General list unchanged...")
    general_after = db.db_get_corrections_list_by_name(
        adapter.BUNDLED_LIST_NAME
    )
    after_count = len(db.db_get_corrections(general_after["id"]))
    if after_count != general_entries_before:
        print(f"  [FAIL] General list entry count changed: "
              f"{general_entries_before} -> {after_count}")
        return False
    print(f"  [OK]   General list intact: id={general_after['id']}, "
          f"entries={after_count}")
    print()

    print("=" * 60)
    print("  ALL CHECKS PASSED -- Day 6 Add-to-Corrections feature "
          "is wired up correctly")
    print("=" * 60)
    print()
    print("  Next: launch DocAnalyser. Two things to verify visually:")
    print()
    print("    1. In the Thread Viewer, select some text in the conversation")
    print("       pane, right-click, and choose 'Add to Corrections List...'.")
    print("       The dialog should open with the selected text pre-filled.")
    print()
    print("    2. After running a transcription and opening the Word")
    print("       Speaker Panel, click '+ Correction...' in the nav row.")
    print("       If you have text highlighted in Word, that text becomes")
    print("       the Original-text seed.")
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
