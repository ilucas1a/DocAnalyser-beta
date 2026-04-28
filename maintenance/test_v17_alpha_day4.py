"""
test_v17_alpha_day4.py
======================
Headless verification script for v1.7-alpha Day 4:
the Corrections List dropdown wired into the cleanup dialog Section A.

Builds a real TranscriptCleanupDialog inside a withdrawn Tk root so no
window appears on screen, then verifies:

  1. Module imports cleanly (no syntax errors)
  2. The three new methods exist on the class
     (_populate_corrections_combo, _resolve_corrections_list_id,
     _on_edit_lists)
  3. The dropdown is populated with at least "(none)" and "General"
  4. Default selection is "General" (when present)
  5. _resolve_corrections_list_id() returns the correct id for each
     selection (None for "(none\u2014skip)", an int for "General")
  6. The "Edit lists\u2026" button exists and references _on_edit_lists
  7. The corrections_db_adapter is reachable from the cleanup dialog's
     import path

This is a headless test \u2014 no actual cleanup is run, no audio is
processed. Real-world verification is by launching DocAnalyser,
transcribing a short audio clip, and visually confirming:
  * The dropdown appears in Section A with "General" selected
  * The Edit lists\u2026 button shows a 'coming soon' message
  * After cleanup, the corrected text appears in the result

Run from PyCharm (right-click -> Run) or command line:
    python maintenance\\test_v17_alpha_day4.py

Expected output: a series of [OK] lines ending with
"ALL CHECKS PASSED -- Day 4 dropdown is wired up correctly".

Created: 28 April 2026 (v1.7-alpha Day 4)
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


def _build_test_entries():
    """Minimal dummy entries \u2014 dialog only inspects len() at construction."""
    return [
        {"start": 0.0, "end": 1.0, "text": "Test segment one."},
        {"start": 1.5, "end": 2.5, "text": "Test segment two."},
    ]


def main() -> bool:
    print("=" * 60)
    print("  v1.7-alpha Day 4 Verification")
    print("=" * 60)
    print(f"  Database path: {db.DB_PATH}")
    print()

    db.init_database()

    # Confirm the General list is present \u2014 needed for dropdown defaults
    general = db.db_get_corrections_list_by_name(adapter.BUNDLED_LIST_NAME)
    if general is None:
        print("  [FAIL] Bundled 'General' list not found. Run Day 1 test first.")
        return False
    print(f"  General list present: id={general['id']}")
    print()

    # --------------------------------------------------------------
    # Step 1 \u2014 Module imports cleanly
    # --------------------------------------------------------------
    print("  Step 1: Module imports cleanly...")
    try:
        import transcript_cleanup_dialog as tcd
    except Exception as exc:
        print(f"  [FAIL] Import failed: {exc}")
        return False
    print("  [OK]   transcript_cleanup_dialog imported without error")
    print()

    # --------------------------------------------------------------
    # Step 2 \u2014 Required new methods exist on the class
    # --------------------------------------------------------------
    print("  Step 2: Required new methods exist on TranscriptCleanupDialog...")
    required_methods = [
        "_populate_corrections_combo",
        "_resolve_corrections_list_id",
        "_on_edit_lists",
    ]
    for method in required_methods:
        if not hasattr(tcd.TranscriptCleanupDialog, method):
            print(f"  [FAIL] Missing method: {method}")
            return False
        print(f"  [OK]   {method}() defined on class")
    print()

    # --------------------------------------------------------------
    # Step 3-6 \u2014 Build a real dialog inside a withdrawn root
    # --------------------------------------------------------------
    print("  Step 3-6: Building dialog inside withdrawn Tk root...")
    root = tk.Tk()
    root.withdraw()  # Hide the root \u2014 no window appears

    dlg = None
    try:
        # Suppress the dialog window from appearing on screen
        dlg = tcd.TranscriptCleanupDialog(
            parent=root,
            entries=_build_test_entries(),
            audio_path=None,
            config={},
            result_callback=lambda result: None,
        )
        dlg.win.withdraw()  # Hide the cleanup dialog window
        root.update()  # Process pending Tk events so widgets are realised

        # ----- Step 3: dropdown populated -----
        labels = list(dlg._corrections_combo["values"])
        if not labels:
            print(f"  [FAIL] Dropdown is empty")
            return False
        print(f"  [OK]   Dropdown populated with {len(labels)} option(s): "
              f"{labels}")

        # The (none) option is always first
        none_label = "(none \u2014 skip)"
        if labels[0] != none_label:
            print(f"  [FAIL] First option should be {none_label!r}, "
                  f"got {labels[0]!r}")
            return False
        print(f"  [OK]   First option is {none_label!r}")

        # General must be in the list
        if "General" not in labels:
            print(f"  [FAIL] 'General' not in dropdown: {labels}")
            return False
        print(f"  [OK]   'General' present in dropdown")

        # ----- Step 4: default selection is General -----
        current_label = dlg._corrections_list_var.get()
        if current_label != "General":
            print(f"  [FAIL] Default selection should be 'General', "
                  f"got {current_label!r}")
            return False
        print(f"  [OK]   Default selection is 'General'")

        # ----- Step 5: resolution is correct -----
        # Default selection \u2192 General's id
        resolved = dlg._resolve_corrections_list_id()
        if resolved != general["id"]:
            print(f"  [FAIL] Default resolved to {resolved}, "
                  f"expected {general['id']}")
            return False
        print(f"  [OK]   'General' selection resolves to id={resolved}")

        # Switch to (none) and verify resolution
        dlg._corrections_list_var.set(none_label)
        resolved = dlg._resolve_corrections_list_id()
        if resolved is not None:
            print(f"  [FAIL] '(none)' resolved to {resolved}, expected None")
            return False
        print(f"  [OK]   '(none \u2014 skip)' selection resolves to None")

        # Restore default for any later checks
        dlg._corrections_list_var.set("General")

        # ----- Step 6: Edit lists button exists and is wired up -----
        if not hasattr(dlg, "_edit_lists_btn"):
            print(f"  [FAIL] _edit_lists_btn attribute missing")
            return False
        btn_command = dlg._edit_lists_btn.cget("command")
        if not btn_command:
            print(f"  [FAIL] Edit lists button has no command bound")
            return False
        print(f"  [OK]   'Edit lists\u2026' button exists with command bound")
        print()

    finally:
        # Clean teardown so the test exits cleanly
        if dlg is not None:
            try:
                dlg.win.destroy()
            except Exception:
                pass
        try:
            root.destroy()
        except Exception:
            pass

    # --------------------------------------------------------------
    # Step 7 \u2014 Adapter is reachable via the same import path
    # --------------------------------------------------------------
    print("  Step 7: Adapter reachable via dialog's import path...")
    try:
        from corrections_db_adapter import list_get_all
        all_lists = list_get_all()
        labels_via_adapter = [lst["name"] for lst in all_lists]
        if "General" not in labels_via_adapter:
            print(f"  [FAIL] 'General' not returned by list_get_all(): "
                  f"{labels_via_adapter}")
            return False
        print(f"  [OK]   list_get_all() returns {len(all_lists)} list(s) "
              f"including 'General'")
    except Exception as exc:
        print(f"  [FAIL] Could not import or call list_get_all: {exc}")
        return False
    print()

    print("=" * 60)
    print("  ALL CHECKS PASSED -- Day 4 dropdown is wired up correctly")
    print("=" * 60)
    print()
    print("  Next: launch DocAnalyser and run a real transcription to")
    print("  visually verify the dropdown appears in Section A and that")
    print("  cleanup applies the selected corrections list.")
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
