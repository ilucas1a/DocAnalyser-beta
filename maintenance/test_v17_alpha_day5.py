"""
test_v17_alpha_day5.py
======================
Headless verification script for v1.7-alpha Day 5:
the Corrections Lists management dialog.

Builds a real CorrectionsManagementDialog inside a withdrawn Tk root so
no window appears on screen, then verifies:

  1. Module imports cleanly
  2. show_corrections_management_dialog() public entry point exists
  3. Dialog constructs without error and has all expected widgets
  4. Listbox is populated with at least the General list
  5. Selecting General disables Rename and Delete (bundled-list protection)
  6. Selecting a non-bundled test list enables Rename and Delete
  7. Right-pane Treeview reflects the selected list's entries
  8. on_close callback fires when the dialog closes
  9. CorrectionEntryEditor sub-dialog can be constructed and its
     _on_save / _on_cancel paths produce the expected result dict
 10. The cleanup dialog's "Edit lists\u2026" button now resolves to the
     real management dialog (no more 'Coming soon' fallback)

Modal sub-dialogs (CorrectionEntryEditor.show() and the simpledialog/
filedialog/messagebox prompts inside the management dialog's button
handlers) are NOT exercised end-to-end \u2014 those would block waiting
for user input. Instead, the test pokes the underlying state and
methods directly and verifies the editor sub-dialog independently.

The script creates and deletes a temporary list named
TEST_DAY5_TEMP_DELETE_IF_FOUND, with a try/finally guard so leftovers
get cleaned up even on assertion failure.

Run from PyCharm (right-click -> Run) or command line:
    python maintenance\\test_v17_alpha_day5.py

Expected output: a series of [OK] lines ending with
"ALL CHECKS PASSED -- Day 5 management dialog is wired up correctly".

Created: 28 April 2026 (v1.7-alpha Day 5)
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

TEST_LIST_NAME = "TEST_DAY5_TEMP_DELETE_IF_FOUND"


def _cleanup_leftover_test_data() -> None:
    """Remove any leftover test list from a previous crashed run."""
    leftover = db.db_get_corrections_list_by_name(TEST_LIST_NAME)
    if leftover is not None:
        db.db_delete_corrections_list(leftover["id"])
        print(f"  [INFO] Removed leftover test list (id={leftover['id']})")


def _general_baseline():
    g = db.db_get_corrections_list_by_name(adapter.BUNDLED_LIST_NAME)
    if g is None:
        return (-1, -1)
    return (g["id"], len(db.db_get_corrections(g["id"])))


def main() -> bool:
    print("=" * 60)
    print("  v1.7-alpha Day 5 Verification")
    print("=" * 60)
    print(f"  Database path: {db.DB_PATH}")
    print()

    db.init_database()
    _cleanup_leftover_test_data()

    general_before = _general_baseline()
    if general_before == (-1, -1):
        print("  [FAIL] Bundled 'General' list not found. Run Day 1 test first.")
        return False
    print(f"  General baseline: id={general_before[0]}, "
          f"entries={general_before[1]}")
    print()

    test_list_id: int | None = None

    # ------------------------------------------------------------------
    # Step 1 \u2014 Module imports cleanly
    # ------------------------------------------------------------------
    print("  Step 1: Module imports cleanly...")
    try:
        import corrections_management_dialog as cmd
    except Exception as exc:
        print(f"  [FAIL] Import failed: {exc}")
        return False
    print("  [OK]   corrections_management_dialog imported without error")
    print()

    # ------------------------------------------------------------------
    # Step 2 \u2014 Public entry point exists
    # ------------------------------------------------------------------
    print("  Step 2: Public entry point exists...")
    if not hasattr(cmd, "show_corrections_management_dialog"):
        print("  [FAIL] show_corrections_management_dialog() not exported")
        return False
    if not hasattr(cmd, "CorrectionsManagementDialog"):
        print("  [FAIL] CorrectionsManagementDialog class not exported")
        return False
    if not hasattr(cmd, "CorrectionEntryEditor"):
        print("  [FAIL] CorrectionEntryEditor class not exported")
        return False
    print("  [OK]   show_corrections_management_dialog() exported")
    print("  [OK]   CorrectionsManagementDialog class exported")
    print("  [OK]   CorrectionEntryEditor class exported")
    print()

    # ------------------------------------------------------------------
    # Steps 3-8 \u2014 Build dialog inside withdrawn root
    # ------------------------------------------------------------------
    print("  Step 3-8: Build dialog inside withdrawn Tk root...")
    root = tk.Tk()
    root.withdraw()

    callback_fired = {"count": 0}
    def _callback():
        callback_fired["count"] += 1

    dlg = None
    try:
        dlg = cmd.CorrectionsManagementDialog(
            parent=root, on_close=_callback
        )
        dlg.win.withdraw()
        root.update()

        # ----- Step 3: required widgets exist -----
        for attr in ("_lists_listbox", "_entries_tv", "_new_btn",
                     "_rename_btn", "_delete_btn", "_duplicate_btn",
                     "_import_btn", "_export_btn",
                     "_add_entry_btn", "_edit_entry_btn",
                     "_delete_entry_btn", "_bundled_note",
                     "_entries_header_var"):
            if not hasattr(dlg, attr):
                print(f"  [FAIL] Dialog missing widget attribute: {attr}")
                return False
        print("  [OK]   All expected widgets present on dialog")

        # ----- Step 4: listbox populated with General -----
        labels = [
            dlg._lists_listbox.get(i)
            for i in range(dlg._lists_listbox.size())
        ]
        if not any("General" in lbl for lbl in labels):
            print(f"  [FAIL] 'General' not in listbox: {labels}")
            return False
        print(f"  [OK]   Listbox populated with {len(labels)} entry(ies): "
              f"{labels}")

        # General must be selected and Rename/Delete disabled
        sel = dlg._lists_listbox.curselection()
        if not sel:
            print("  [FAIL] No initial listbox selection")
            return False

        # ----- Step 5: General selected -> Rename/Delete disabled -----
        # Find General's index, select it explicitly
        general_idx = next(
            (i for i, lbl in enumerate(labels) if lbl.startswith("General")),
            -1,
        )
        if general_idx < 0:
            print(f"  [FAIL] Could not find General in listbox")
            return False
        dlg._lists_listbox.selection_clear(0, tk.END)
        dlg._lists_listbox.selection_set(general_idx)
        dlg._on_list_selected()
        root.update()

        if str(dlg._rename_btn.cget("state")) != "disabled":
            print(f"  [FAIL] Rename button should be disabled when General "
                  f"selected, got {dlg._rename_btn.cget('state')!r}")
            return False
        if str(dlg._delete_btn.cget("state")) != "disabled":
            print(f"  [FAIL] Delete button should be disabled when General "
                  f"selected, got {dlg._delete_btn.cget('state')!r}")
            return False
        if str(dlg._duplicate_btn.cget("state")) != "normal":
            print(f"  [FAIL] Duplicate button should be enabled when General "
                  f"selected, got {dlg._duplicate_btn.cget('state')!r}")
            return False
        print("  [OK]   General selected: Rename/Delete disabled, "
              "Duplicate enabled")

        # General's entries should appear in the right pane
        n_rows_general = len(dlg._entries_tv.get_children())
        if n_rows_general != general_before[1]:
            print(f"  [FAIL] Right-pane row count mismatch: "
                  f"expected {general_before[1]}, got {n_rows_general}")
            return False
        print(f"  [OK]   Right pane shows {n_rows_general} entries for General")

        # The bundled-list explanatory note should be visible
        note_text = dlg._bundled_note.cget("text")
        if "Bundled" not in note_text and "bundled" not in note_text:
            print(f"  [FAIL] Bundled-list note not shown: {note_text!r}")
            return False
        print(f"  [OK]   Bundled-list note displayed when General selected")

        # ----- Step 6: create non-bundled test list directly via adapter -----
        test_list_id = adapter.list_create(
            name=TEST_LIST_NAME,
            description="Throwaway list for Day 5 verification.",
        )
        # Add a couple of entries so the right pane has something to show
        adapter.correction_add(
            test_list_id, "foo", "FOO",
            case_sensitive=False, word_boundary=True,
        )
        adapter.correction_add(
            test_list_id, "bar", "",
            case_sensitive=False, word_boundary=True,
            notes="deletion rule",
        )

        dlg._reload_lists(select_id=test_list_id)
        root.update()

        # Selecting the test list should enable Rename and Delete
        if str(dlg._rename_btn.cget("state")) != "normal":
            print(f"  [FAIL] Rename should be enabled for non-bundled list")
            return False
        if str(dlg._delete_btn.cget("state")) != "normal":
            print(f"  [FAIL] Delete should be enabled for non-bundled list")
            return False
        print(f"  [OK]   Rename/Delete enabled for non-bundled test list")

        # Bundled note should be cleared
        if dlg._bundled_note.cget("text"):
            print(f"  [FAIL] Bundled note should be empty for non-bundled list, "
                  f"got: {dlg._bundled_note.cget('text')!r}")
            return False
        print(f"  [OK]   Bundled note cleared for non-bundled list")

        # ----- Step 7: right-pane reflects test list's entries -----
        rows = dlg._entries_tv.get_children()
        if len(rows) != 2:
            print(f"  [FAIL] Expected 2 rows for test list, got {len(rows)}")
            return False
        # Verify column values for the first row
        values = dlg._entries_tv.item(rows[0])["values"]
        if values[0] != "foo":
            print(f"  [FAIL] First row original_text expected 'foo', "
                  f"got {values[0]!r}")
            return False
        # Empty corrected_text should be displayed as "\u2014 (deletes match)"
        values_b = dlg._entries_tv.item(rows[1])["values"]
        if "delete" not in str(values_b[1]).lower() and \
                "\u2014" not in str(values_b[1]):
            print(f"  [FAIL] Empty corrected_text should be shown with hint, "
                  f"got {values_b[1]!r}")
            return False
        print(f"  [OK]   Right pane shows test list's 2 entries correctly")
        print(f"  [OK]   Empty corrected_text displayed as deletion hint")

        # Header text reflects selected list
        header = dlg._entries_header_var.get()
        if TEST_LIST_NAME not in header:
            print(f"  [FAIL] Right-pane header should contain test list name, "
                  f"got {header!r}")
            return False
        print(f"  [OK]   Right-pane header reflects selection: {header!r}")

        # ----- Step 8: on_close callback -----
        callback_fired["count"] = 0
        dlg._on_window_close()
        root.update()
        if callback_fired["count"] != 1:
            print(f"  [FAIL] on_close callback should fire exactly once, "
                  f"got {callback_fired['count']}")
            return False
        print(f"  [OK]   on_close callback fired on dialog close")
        print()

    finally:
        try:
            if dlg is not None:
                try:
                    dlg.win.destroy()
                except Exception:
                    pass
            root.destroy()
        except Exception:
            pass
        if test_list_id is not None:
            try:
                db.db_delete_corrections_list(test_list_id)
                print(f"  [INFO] Cleaned up test list (id={test_list_id})")
            except Exception as exc:
                print(f"  [WARN] Could not clean up test list: {exc}")

    # ------------------------------------------------------------------
    # Step 9 \u2014 CorrectionEntryEditor sub-dialog
    # ------------------------------------------------------------------
    print()
    print("  Step 9: CorrectionEntryEditor sub-dialog...")
    root2 = tk.Tk()
    root2.withdraw()
    try:
        # 9a \u2014 build with no initial values
        editor = cmd.CorrectionEntryEditor(root2, title="Test add")
        editor._build_window()
        editor.win.withdraw()
        root2.update()

        # Default values
        if editor._original_var.get() != "":
            print(f"  [FAIL] Original should be empty by default, "
                  f"got {editor._original_var.get()!r}")
            return False
        if editor._wb_var.get() is not True:
            print(f"  [FAIL] word_boundary should default to True")
            return False
        if editor._cs_var.get() is not False:
            print(f"  [FAIL] case_sensitive should default to False")
            return False
        print(f"  [OK]   Editor builds with correct default values")

        # Simulate entering text and saving
        editor._original_var.set("widget")
        editor._corrected_var.set("Widget")
        editor._cs_var.set(True)
        editor._notes_var.set("Capitalised brand name")
        editor._on_save()

        if editor._result is None:
            print(f"  [FAIL] _on_save should populate _result with values")
            return False
        if editor._result["original_text"] != "widget":
            print(f"  [FAIL] result['original_text'] expected 'widget', "
                  f"got {editor._result['original_text']!r}")
            return False
        if editor._result["corrected_text"] != "Widget":
            print(f"  [FAIL] result['corrected_text'] expected 'Widget', "
                  f"got {editor._result['corrected_text']!r}")
            return False
        if editor._result["case_sensitive"] is not True:
            print(f"  [FAIL] result['case_sensitive'] expected True")
            return False
        if editor._result["notes"] != "Capitalised brand name":
            print(f"  [FAIL] result['notes'] expected 'Capitalised brand name'")
            return False
        print(f"  [OK]   Editor save produces correct result dict")

        # 9b \u2014 build with initial values
        editor2 = cmd.CorrectionEntryEditor(
            root2, title="Test edit",
            initial={
                "original_text":  "tell vision",
                "corrected_text": "television",
                "case_sensitive": False,
                "word_boundary":  True,
                "notes":          "Whisper mishearing",
            },
        )
        editor2._build_window()
        editor2.win.withdraw()
        root2.update()
        if editor2._original_var.get() != "tell vision":
            print(f"  [FAIL] Initial original_text not loaded")
            return False
        if editor2._notes_var.get() != "Whisper mishearing":
            print(f"  [FAIL] Initial notes not loaded")
            return False
        print(f"  [OK]   Editor pre-populates fields from initial values")

        # 9c \u2014 cancel produces None result
        editor2._on_cancel()
        if editor2._result is not None:
            print(f"  [FAIL] _on_cancel should leave _result as None")
            return False
        print(f"  [OK]   Editor cancel leaves result as None")

    finally:
        try:
            root2.destroy()
        except Exception:
            pass
    print()

    # ------------------------------------------------------------------
    # Step 10 \u2014 Cleanup dialog's Edit lists button now wires through
    # ------------------------------------------------------------------
    print("  Step 10: Cleanup dialog 'Edit lists\u2026' wiring...")
    try:
        from transcript_cleanup_dialog import TranscriptCleanupDialog
        # The cleanup dialog's _on_edit_lists method imports
        # corrections_management_dialog. We can't easily test the
        # button click headlessly because it shows a real dialog,
        # but we CAN verify that the import succeeds, meaning the
        # 'Coming soon' fallback path will no longer fire.
        from corrections_management_dialog import (
            show_corrections_management_dialog as _smd,
        )
        if not callable(_smd):
            print(f"  [FAIL] show_corrections_management_dialog not callable")
            return False
        print(f"  [OK]   corrections_management_dialog importable from "
              f"cleanup dialog's path")
        print(f"  [OK]   'Edit lists\u2026' button will now open the real "
              f"management dialog")
    except Exception as exc:
        print(f"  [FAIL] Wiring check failed: {exc}")
        return False
    print()

    # ------------------------------------------------------------------
    # Final invariance check
    # ------------------------------------------------------------------
    print("  Final: General list unchanged...")
    general_after = _general_baseline()
    if general_after != general_before:
        print(f"  [FAIL] General list changed: {general_before} -> "
              f"{general_after}")
        return False
    print(f"  [OK]   General list intact: id={general_after[0]}, "
          f"entries={general_after[1]}")
    print()

    print("=" * 60)
    print("  ALL CHECKS PASSED -- Day 5 management dialog is wired up correctly")
    print("=" * 60)
    print()
    print("  Next: launch DocAnalyser, run a transcription, and click")
    print("  'Edit lists\u2026' in the cleanup dialog. You should now see")
    print("  the real management dialog with the General list and any")
    print("  others you've created. Try New, Duplicate, Add entry, etc.")
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
