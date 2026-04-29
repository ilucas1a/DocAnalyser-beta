"""
corrections_management_dialog.py — Manage Corrections Lists (v1.7-alpha)

Two-pane dialog for creating, editing and organising Corrections Lists.

Left pane  — list of Corrections Lists with New / Rename / Delete /
             Duplicate / Import / Export buttons. The bundled "General"
             list is protected: Rename and Delete are disabled when it
             is selected. Users wanting to customise General use
             Duplicate instead.

Right pane — Treeview of entries in the currently-selected list, with
             Add / Edit / Delete buttons. Each entry shows: original
             text, corrected text, whether word-boundary matching is
             on, whether the rule is case-sensitive, and any notes.
             Adding or editing opens a modal sub-dialog
             (CorrectionEntryEditor) that returns the new/updated
             values to the parent dialog on Save.

The dialog is non-modal so DocAnalyser remains usable while it is
open. When the user closes it (X button or Close button), the optional
on_close callback is fired so callers like transcript_cleanup_dialog
can refresh their dropdowns to pick up new lists or renamed lists.

Usage:
    from corrections_management_dialog import (
        show_corrections_management_dialog,
    )
    show_corrections_management_dialog(
        parent, on_close=lambda: cleanup_dialog._populate_corrections_combo()
    )

Author: DocAnalyser Development Team
Date: 28 April 2026 (v1.7-alpha Day 5)
"""

from __future__ import annotations

import logging
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from typing import Callable, Optional, List, Dict

import corrections_db_adapter as adapter

logger = logging.getLogger(__name__)


# =============================================================================
# Public entry point
# =============================================================================

def show_corrections_management_dialog(
        parent,
        on_close: Optional[Callable[[], None]] = None,
) -> "CorrectionsManagementDialog":
    """
    Open the Corrections Lists management dialog (non-modal).

    on_close, if provided, is invoked when the dialog closes \u2014 used
    by the cleanup dialog so it can refresh its dropdown to reflect
    any new/renamed/deleted lists.
    """
    return CorrectionsManagementDialog(parent, on_close=on_close)


# =============================================================================
# Main dialog
# =============================================================================

class CorrectionsManagementDialog:
    """
    Two-pane Corrections Lists manager.

    Layout:
      Title                                                          [x]
      Description
      \u2554\u2550\u2550\u2550\u2550\u2550 Lists \u2550\u2550\u2550\u2550\u2550\u2557\u2554\u2550\u2550 Entries in '<name>' \u2550\u2550\u2557
      \u2551 General        \u2551\u2551 Original | Corrected | WB ...   \u2551
      \u2551 My list 1      \u2551\u2551 ...                              \u2551
      \u2551                \u2551\u2551                                  \u2551
      \u2560\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2563\u2560\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2563
      \u2551 [New] [Rename] \u2551\u2551 [Add] [Edit] [Delete]            \u2551
      \u2551 [Delete] [Dup] \u2551\u2551                                  \u2551
      \u2551 [Import][Export]\u2551\u2551                                  \u2551
      \u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d
                                                          [Close]
    """

    # Column ids and headings for the entries Treeview.
    # Labels follow the convention from Word's Find & Replace dialog
    # and most text editors so they're immediately recognisable.
    # Single-line: ttk.Treeview heading on Windows uses native vista
    # theming that doesn't respect padding for height, so multi-line
    # headings render with the second line clipped. Keep it simple.
    _COLUMNS = ("original", "corrected", "wb", "cs", "notes")
    _COL_HEADINGS = {
        "original":  "Find",
        "corrected": "Replace with",
        "wb":        "Whole word",
        "cs":        "Match case",
        "notes":     "Notes",
    }
    _COL_WIDTHS = {
        "original":  150,
        "corrected": 150,
        "wb":         85,
        "cs":         85,
        "notes":     130,
    }

    def __init__(
            self,
            parent,
            on_close: Optional[Callable[[], None]] = None,
    ):
        self._parent   = parent
        self._on_close = on_close

        self._lists: List[Dict] = []          # rows from adapter.list_get_all()
        self._selected_list_id: Optional[int] = None

        self._build_window()
        self._reload_lists()

    # =========================================================================
    # Window construction
    # =========================================================================

    def _build_window(self):
        self.win = tk.Toplevel(self._parent)
        self.win.title("Corrections Lists")
        self.win.minsize(640, 460)
        self.win.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Position abutting the LEFT border of the main UI window.
        # Two cases handled:
        #   * Parent is another dialog (e.g. opened from the cleanup
        #     dialog) — share the parent's RIGHT edge so we abut the
        #     same target the parent abuts (main UI's left edge).
        #   * Parent is the main UI itself — abut its LEFT edge
        #     directly.
        # Width auto-shrinks if it would extend off-screen left.
        # Height matches the parent's height when sensible so the
        # dialog visually aligns with the main UI.
        self.win.update_idletasks()
        w = 760           # narrower than the previous 820
        h = 580           # natural content size; resizable beyond this
        try:
            anchor = self._parent
            a_x = anchor.winfo_x()
            a_y = anchor.winfo_y()
            a_w = anchor.winfo_width()
            a_h = anchor.winfo_height()
            if a_h > 100:                       # ignore withdrawn-root sentinel
                h = max(h, a_h)
            if isinstance(anchor, tk.Toplevel):
                # Opened from another dialog — share its right edge.
                target_right = a_x + a_w
                px = target_right - w
            else:
                # Opened from main UI — abut its left edge.
                target_right = a_x
                px = a_x - w
            py = a_y
            if px < 8:
                # Would extend off-screen left — cap at 8px from screen
                # edge and shrink width to fit. Width has a soft floor
                # so the two-pane layout stays legible.
                w = max(480, target_right - 8)
                px = 8
            self.win.geometry(f"{w}x{h}+{max(0, px)}+{max(0, py)}")
        except Exception:
            self.win.geometry(f"{w}x{h}")

        outer = tk.Frame(self.win, padx=12, pady=10)
        outer.pack(fill=tk.BOTH, expand=True)

        # Header
        tk.Label(
            outer,
            text="Corrections Lists",
            font=("Segoe UI", 12, "bold"),
            anchor="w",
        ).pack(fill=tk.X)

        tk.Label(
            outer,
            text=(
                "Find-and-replace rules applied during transcript cleanup. "
                "The bundled \"General\" list contains starter rules for "
                "common transcription errors; create your own lists for "
                "domain-specific terms."
            ),
            font=("Segoe UI", 9),
            fg="#555555",
            anchor="w",
            justify="left",
            wraplength=780,
        ).pack(fill=tk.X, pady=(0, 8))

        # Main horizontal split — a PanedWindow lets users adjust the
        # lists/entries pane ratio for longer entries or wider notes.
        split = ttk.PanedWindow(outer, orient=tk.HORIZONTAL)
        split.pack(fill=tk.BOTH, expand=True)

        self._build_lists_pane(split)
        self._build_entries_pane(split)

        # Bottom button row
        bottom = tk.Frame(outer)
        bottom.pack(fill=tk.X, pady=(10, 0))

        tk.Button(
            bottom, text="Close", width=10, command=self._on_window_close
        ).pack(side=tk.RIGHT)

    # -------------------------------------------------------------------------
    # Left pane \u2014 lists
    # -------------------------------------------------------------------------

    def _build_lists_pane(self, parent):
        frame = tk.LabelFrame(parent, text=" Lists ", padx=8, pady=6)
        # Added to the PanedWindow rather than packed; weight controls
        # how spare space is distributed when the user resizes the dialog.
        parent.add(frame, weight=1)

        # Listbox + scrollbar
        lb_frame = tk.Frame(frame)
        lb_frame.pack(fill=tk.BOTH, expand=True)

        self._lists_listbox = tk.Listbox(
            lb_frame,
            width=24,
            height=14,
            exportselection=False,
            font=("Segoe UI", 10),
        )
        self._lists_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sb = tk.Scrollbar(lb_frame, command=self._lists_listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._lists_listbox.config(yscrollcommand=sb.set)

        self._lists_listbox.bind("<<ListboxSelect>>",
                                 lambda _e: self._on_list_selected())

        # Note about bundled list
        self._bundled_note = tk.Label(
            frame,
            text="",
            font=("Segoe UI", 8, "italic"),
            fg="#777777",
            wraplength=220,
            justify="left",
            anchor="w",
        )
        self._bundled_note.pack(fill=tk.X, pady=(4, 4))

        # Button rows
        btn_row1 = tk.Frame(frame)
        btn_row1.pack(fill=tk.X, pady=(2, 0))
        self._new_btn = tk.Button(
            btn_row1, text="New\u2026", width=10, command=self._on_new_list
        )
        self._new_btn.pack(side=tk.LEFT, padx=(0, 4))
        self._rename_btn = tk.Button(
            btn_row1, text="Rename\u2026", width=10,
            command=self._on_rename_list,
        )
        self._rename_btn.pack(side=tk.LEFT)

        btn_row2 = tk.Frame(frame)
        btn_row2.pack(fill=tk.X, pady=(4, 0))
        self._delete_btn = tk.Button(
            btn_row2, text="Delete", width=10,
            command=self._on_delete_list,
        )
        self._delete_btn.pack(side=tk.LEFT, padx=(0, 4))
        self._duplicate_btn = tk.Button(
            btn_row2, text="Duplicate\u2026", width=10,
            command=self._on_duplicate_list,
        )
        self._duplicate_btn.pack(side=tk.LEFT)

        btn_row3 = tk.Frame(frame)
        btn_row3.pack(fill=tk.X, pady=(8, 0))
        self._import_btn = tk.Button(
            btn_row3, text="Import\u2026", width=10,
            command=self._on_import_list,
        )
        self._import_btn.pack(side=tk.LEFT, padx=(0, 4))
        self._export_btn = tk.Button(
            btn_row3, text="Export\u2026", width=10,
            command=self._on_export_list,
        )
        self._export_btn.pack(side=tk.LEFT)

    # -------------------------------------------------------------------------
    # Right pane \u2014 entries
    # -------------------------------------------------------------------------

    def _build_entries_pane(self, parent):
        frame = tk.LabelFrame(parent, text=" Entries ", padx=8, pady=6)
        # Larger weight so spare space goes to entries pane by default.
        parent.add(frame, weight=3)

        # Header label that updates with the selected list name
        self._entries_header_var = tk.StringVar(value="(select a list)")
        tk.Label(
            frame,
            textvariable=self._entries_header_var,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 4))

        # Treeview + scrollbar
        tv_frame = tk.Frame(frame)
        tv_frame.pack(fill=tk.BOTH, expand=True)

        self._entries_tv = ttk.Treeview(
            tv_frame,
            columns=self._COLUMNS,
            show="headings",
            selectmode="browse",
            height=14,
        )
        for col in self._COLUMNS:
            self._entries_tv.heading(col, text=self._COL_HEADINGS[col])
            anchor = "center" if col in ("wb", "cs") else "w"
            stretch = tk.NO if col in ("wb", "cs") else tk.YES
            self._entries_tv.column(
                col, width=self._COL_WIDTHS[col], anchor=anchor,
                stretch=stretch, minwidth=50,
            )
        self._entries_tv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tv_sb = tk.Scrollbar(tv_frame, command=self._entries_tv.yview)
        tv_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._entries_tv.config(yscrollcommand=tv_sb.set)

        # Double-click row to edit
        self._entries_tv.bind("<Double-1>",
                              lambda _e: self._on_edit_entry())

        # Buttons
        btn_row = tk.Frame(frame)
        btn_row.pack(fill=tk.X, pady=(6, 0))
        self._add_entry_btn = tk.Button(
            btn_row, text="Add\u2026", width=10,
            command=self._on_add_entry,
        )
        self._add_entry_btn.pack(side=tk.LEFT, padx=(0, 4))
        self._edit_entry_btn = tk.Button(
            btn_row, text="Edit\u2026", width=10,
            command=self._on_edit_entry,
        )
        self._edit_entry_btn.pack(side=tk.LEFT, padx=(0, 4))
        self._delete_entry_btn = tk.Button(
            btn_row, text="Delete", width=10,
            command=self._on_delete_entry,
        )
        self._delete_entry_btn.pack(side=tk.LEFT)

    # =========================================================================
    # Lists pane \u2014 actions and state
    # =========================================================================

    def _reload_lists(self, select_id: Optional[int] = None):
        """
        Re-fetch all lists from the database and repopulate the listbox.
        If select_id is provided, that list is selected after the reload;
        otherwise the previous selection is preserved if possible.
        """
        if select_id is None:
            select_id = self._selected_list_id

        try:
            self._lists = adapter.list_get_all()
        except Exception as exc:
            logger.error("Could not load corrections lists: %s", exc)
            messagebox.showerror(
                "Database error",
                f"Could not load corrections lists:\n\n{exc}",
                parent=self.win,
            )
            self._lists = []

        self._lists_listbox.delete(0, tk.END)
        target_index = 0
        for i, lst in enumerate(self._lists):
            label = lst["name"]
            if lst["name"] == adapter.BUNDLED_LIST_NAME:
                label = f"{label}  (bundled)"
            self._lists_listbox.insert(tk.END, label)
            if lst["id"] == select_id:
                target_index = i

        if self._lists:
            self._lists_listbox.selection_clear(0, tk.END)
            self._lists_listbox.selection_set(target_index)
            self._lists_listbox.activate(target_index)
            self._lists_listbox.see(target_index)
            self._on_list_selected()
        else:
            self._selected_list_id = None
            self._refresh_entries_pane([])
            self._update_button_states()

    def _on_list_selected(self):
        """Listbox selection changed \u2014 update right pane and button states."""
        sel = self._lists_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self._lists):
            return

        lst = self._lists[idx]
        self._selected_list_id = lst["id"]
        self._entries_header_var.set(f"Entries in '{lst['name']}'")

        is_bundled = (lst["name"] == adapter.BUNDLED_LIST_NAME)
        if is_bundled:
            self._bundled_note.config(
                text="Bundled list \u2014 cannot be renamed or deleted. "
                     "Use Duplicate to make an editable copy."
            )
        else:
            self._bundled_note.config(text="")

        try:
            entries = adapter.correction_get_all_for_list(lst["id"])
        except Exception as exc:
            logger.error("Could not load entries for list %d: %s",
                         lst["id"], exc)
            entries = []

        self._refresh_entries_pane(entries)
        self._update_button_states()

    def _update_button_states(self):
        """
        Enable/disable list-pane buttons based on selection.
        General list cannot be renamed or deleted.
        """
        has_selection = self._selected_list_id is not None
        is_bundled = self._is_selected_bundled()

        # New / Import / Export are always available when at least one list
        # exists (export and the right-pane buttons require a selection).
        self._new_btn.config(state=tk.NORMAL)
        self._import_btn.config(state=tk.NORMAL)

        self._rename_btn.config(
            state=(tk.NORMAL if has_selection and not is_bundled
                   else tk.DISABLED)
        )
        self._delete_btn.config(
            state=(tk.NORMAL if has_selection and not is_bundled
                   else tk.DISABLED)
        )
        self._duplicate_btn.config(
            state=tk.NORMAL if has_selection else tk.DISABLED
        )
        self._export_btn.config(
            state=tk.NORMAL if has_selection else tk.DISABLED
        )
        self._add_entry_btn.config(
            state=tk.NORMAL if has_selection else tk.DISABLED
        )
        self._edit_entry_btn.config(
            state=tk.NORMAL if has_selection else tk.DISABLED
        )
        self._delete_entry_btn.config(
            state=tk.NORMAL if has_selection else tk.DISABLED
        )

    def _is_selected_bundled(self) -> bool:
        if self._selected_list_id is None:
            return False
        for lst in self._lists:
            if lst["id"] == self._selected_list_id:
                return lst["name"] == adapter.BUNDLED_LIST_NAME
        return False

    def _selected_list_name(self) -> Optional[str]:
        if self._selected_list_id is None:
            return None
        for lst in self._lists:
            if lst["id"] == self._selected_list_id:
                return lst["name"]
        return None

    # ------ List buttons -----------------------------------------------------

    def _on_new_list(self):
        """Prompt for a name and create a new (empty) list."""
        name = simpledialog.askstring(
            "New corrections list",
            "Name for the new list:",
            parent=self.win,
        )
        if name is None:
            return  # user cancelled
        try:
            new_id = adapter.list_create(name=name.strip())
        except ValueError as exc:
            messagebox.showerror("Cannot create list", str(exc),
                                 parent=self.win)
            return
        except Exception as exc:
            logger.error("list_create failed: %s", exc)
            messagebox.showerror("Database error", str(exc),
                                 parent=self.win)
            return
        self._reload_lists(select_id=new_id)

    def _on_rename_list(self):
        """Prompt for a new name for the selected (non-bundled) list."""
        if self._selected_list_id is None:
            return
        if self._is_selected_bundled():
            return  # button should be disabled, defensive
        current = self._selected_list_name() or ""
        new_name = simpledialog.askstring(
            "Rename list",
            "New name:",
            initialvalue=current,
            parent=self.win,
        )
        if new_name is None or new_name.strip() == current:
            return
        try:
            adapter.list_update(self._selected_list_id, name=new_name.strip())
        except ValueError as exc:
            messagebox.showerror("Cannot rename list", str(exc),
                                 parent=self.win)
            return
        except Exception as exc:
            logger.error("list_update failed: %s", exc)
            messagebox.showerror("Database error", str(exc),
                                 parent=self.win)
            return
        self._reload_lists(select_id=self._selected_list_id)

    def _on_delete_list(self):
        """Confirm and delete the selected (non-bundled) list."""
        if self._selected_list_id is None:
            return
        if self._is_selected_bundled():
            return  # defensive
        name = self._selected_list_name() or ""
        n_entries = len(adapter.correction_get_all_for_list(
            self._selected_list_id
        ))
        confirm = messagebox.askyesno(
            "Delete list",
            f"Delete the list \"{name}\" and its {n_entries} "
            f"correction{'s' if n_entries != 1 else ''}?\n\n"
            "This cannot be undone.",
            parent=self.win,
        )
        if not confirm:
            return
        try:
            adapter.list_delete(self._selected_list_id)
        except ValueError as exc:
            messagebox.showerror("Cannot delete list", str(exc),
                                 parent=self.win)
            return
        except Exception as exc:
            logger.error("list_delete failed: %s", exc)
            messagebox.showerror("Database error", str(exc),
                                 parent=self.win)
            return
        self._selected_list_id = None
        self._reload_lists()

    def _on_duplicate_list(self):
        """Prompt for a name and duplicate the selected list."""
        if self._selected_list_id is None:
            return
        current = self._selected_list_name() or "List"
        proposed = f"{current} (copy)"
        new_name = simpledialog.askstring(
            "Duplicate list",
            "Name for the duplicate:",
            initialvalue=proposed,
            parent=self.win,
        )
        if new_name is None:
            return
        try:
            new_id = adapter.list_duplicate(
                self._selected_list_id, new_name.strip()
            )
        except ValueError as exc:
            messagebox.showerror("Cannot duplicate list", str(exc),
                                 parent=self.win)
            return
        except Exception as exc:
            logger.error("list_duplicate failed: %s", exc)
            messagebox.showerror("Database error", str(exc),
                                 parent=self.win)
            return
        self._reload_lists(select_id=new_id)

    def _on_import_list(self):
        """Choose a .json file and import it as a new list."""
        path = filedialog.askopenfilename(
            parent=self.win,
            title="Import Corrections List",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            new_id = adapter.list_import_json(path)
        except Exception as exc:
            logger.error("list_import_json failed: %s", exc)
            messagebox.showerror(
                "Import failed",
                f"Could not import the file:\n\n{exc}",
                parent=self.win,
            )
            return
        self._reload_lists(select_id=new_id)
        n_entries = len(adapter.correction_get_all_for_list(new_id))
        messagebox.showinfo(
            "Import complete",
            f"Imported {n_entries} "
            f"correction{'s' if n_entries != 1 else ''} into a new list.",
            parent=self.win,
        )

    def _on_export_list(self):
        """Choose a destination file and export the selected list."""
        if self._selected_list_id is None:
            return
        name = self._selected_list_name() or "list"
        # Sanitise the proposed filename
        safe_name = "".join(
            c if c.isalnum() or c in (" ", "-", "_") else "_"
            for c in name
        ).strip() or "list"
        path = filedialog.asksaveasfilename(
            parent=self.win,
            title="Export Corrections List",
            defaultextension=".json",
            initialfile=f"{safe_name}.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            adapter.list_export_json(self._selected_list_id, path)
        except Exception as exc:
            logger.error("list_export_json failed: %s", exc)
            messagebox.showerror(
                "Export failed",
                f"Could not export the list:\n\n{exc}",
                parent=self.win,
            )
            return
        messagebox.showinfo(
            "Export complete",
            f"Exported to:\n{os.path.abspath(path)}",
            parent=self.win,
        )

    # =========================================================================
    # Entries pane \u2014 actions and state
    # =========================================================================

    def _refresh_entries_pane(self, entries: List[Dict]):
        """Repopulate the entries Treeview with the supplied rows."""
        for iid in self._entries_tv.get_children():
            self._entries_tv.delete(iid)
        for entry in entries:
            wb = "\u2713" if entry.get("word_boundary") else ""
            cs = "\u2713" if entry.get("case_sensitive") else ""
            corrected = entry.get("corrected_text", "")
            # Empty-string corrections are valid (deletion); show them as
            # a hint rather than a blank cell so users can see what's there.
            display_corrected = (
                corrected if corrected != "" else "\u2014 (deletes match)"
            )
            self._entries_tv.insert(
                "", tk.END,
                iid=str(entry["id"]),
                values=(
                    entry.get("original_text", ""),
                    display_corrected,
                    wb,
                    cs,
                    entry.get("notes") or "",
                ),
            )

    def _selected_entry_id(self) -> Optional[int]:
        sel = self._entries_tv.selection()
        if not sel:
            return None
        try:
            return int(sel[0])
        except ValueError:
            return None

    def _on_add_entry(self):
        """Open the entry editor sub-dialog to add a new entry."""
        if self._selected_list_id is None:
            return
        editor = CorrectionEntryEditor(self.win, title="Add correction")
        result = editor.show()
        if result is None:
            return
        try:
            adapter.correction_add(
                list_id=self._selected_list_id,
                original_text=result["original_text"],
                corrected_text=result["corrected_text"],
                case_sensitive=result["case_sensitive"],
                word_boundary=result["word_boundary"],
                notes=result["notes"],
            )
        except ValueError as exc:
            messagebox.showerror("Cannot add correction", str(exc),
                                 parent=self.win)
            return
        except Exception as exc:
            logger.error("correction_add failed: %s", exc)
            messagebox.showerror("Database error", str(exc),
                                 parent=self.win)
            return
        # Reload current list's entries
        entries = adapter.correction_get_all_for_list(
            self._selected_list_id
        )
        self._refresh_entries_pane(entries)

    def _on_edit_entry(self):
        """Open the entry editor sub-dialog to edit the selected entry."""
        entry_id = self._selected_entry_id()
        if entry_id is None:
            return
        existing = adapter.correction_get(entry_id)
        if existing is None:
            messagebox.showerror(
                "Entry not found",
                "This correction is no longer in the database.",
                parent=self.win,
            )
            self._on_list_selected()  # refresh
            return
        editor = CorrectionEntryEditor(
            self.win, title="Edit correction", initial=existing
        )
        result = editor.show()
        if result is None:
            return
        try:
            adapter.correction_update(
                entry_id,
                original_text=result["original_text"],
                corrected_text=result["corrected_text"],
                case_sensitive=result["case_sensitive"],
                word_boundary=result["word_boundary"],
                notes=result["notes"],
            )
        except ValueError as exc:
            messagebox.showerror("Cannot update correction", str(exc),
                                 parent=self.win)
            return
        except Exception as exc:
            logger.error("correction_update failed: %s", exc)
            messagebox.showerror("Database error", str(exc),
                                 parent=self.win)
            return
        entries = adapter.correction_get_all_for_list(
            self._selected_list_id
        )
        self._refresh_entries_pane(entries)
        # Re-select the edited row
        try:
            self._entries_tv.selection_set(str(entry_id))
            self._entries_tv.see(str(entry_id))
        except tk.TclError:
            pass

    def _on_delete_entry(self):
        """Confirm and delete the selected entry."""
        entry_id = self._selected_entry_id()
        if entry_id is None:
            return
        existing = adapter.correction_get(entry_id)
        if existing is None:
            self._on_list_selected()
            return
        confirm = messagebox.askyesno(
            "Delete correction",
            f"Delete this correction?\n\n"
            f"  {existing.get('original_text', '')!r}  \u2192  "
            f"{existing.get('corrected_text', '')!r}",
            parent=self.win,
        )
        if not confirm:
            return
        try:
            adapter.correction_delete(entry_id)
        except Exception as exc:
            logger.error("correction_delete failed: %s", exc)
            messagebox.showerror("Database error", str(exc),
                                 parent=self.win)
            return
        entries = adapter.correction_get_all_for_list(
            self._selected_list_id
        )
        self._refresh_entries_pane(entries)

    # =========================================================================
    # Close handling
    # =========================================================================

    def _on_window_close(self):
        """Window closing \u2014 fire on_close callback then destroy."""
        try:
            self.win.destroy()
        except Exception:
            pass
        if self._on_close is not None:
            try:
                self._on_close()
            except Exception:
                logger.exception(
                    "on_close callback raised in management dialog"
                )


# =============================================================================
# Entry editor sub-dialog
# =============================================================================

class CorrectionEntryEditor:
    """
    Modal sub-dialog for adding or editing a single correction entry.

    Usage:
        editor = CorrectionEntryEditor(parent, title=..., initial=row_dict)
        result = editor.show()
        # result is None if user cancelled, otherwise a dict:
        # {
        #     "original_text":  str,
        #     "corrected_text": str,
        #     "case_sensitive": bool,
        #     "word_boundary":  bool,
        #     "notes":          str or None,
        # }
    """

    def __init__(
            self,
            parent,
            title: str = "Add correction",
            initial: Optional[Dict] = None,
    ):
        self._parent = parent
        self._title  = title
        self._initial = initial or {}
        self._result: Optional[Dict] = None

    # ----- Public API --------------------------------------------------------

    def show(self) -> Optional[Dict]:
        """Build the dialog, run modally, return result dict (or None)."""
        self._build_window()
        self.win.transient(self._parent)
        self.win.grab_set()
        self.win.focus_set()
        self._original_entry.focus_set()
        self.win.wait_window()
        return self._result

    # ----- Construction ------------------------------------------------------

    def _build_window(self):
        self.win = tk.Toplevel(self._parent)
        self.win.title(self._title)
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.win.update_idletasks()
        w, h = 460, 320
        try:
            px = self._parent.winfo_x() + (self._parent.winfo_width()  - w) // 2
            py = self._parent.winfo_y() + (self._parent.winfo_height() - h) // 2
            self.win.geometry(f"{w}x{h}+{max(0, px)}+{max(0, py)}")
        except Exception:
            self.win.geometry(f"{w}x{h}")

        outer = tk.Frame(self.win, padx=14, pady=12)
        outer.pack(fill=tk.BOTH, expand=True)

        # Original text
        tk.Label(outer, text="Original text (what to find):",
                 anchor="w").pack(fill=tk.X)
        self._original_var = tk.StringVar(
            value=self._initial.get("original_text", "")
        )
        self._original_entry = tk.Entry(
            outer, textvariable=self._original_var, width=50,
        )
        self._original_entry.pack(fill=tk.X, pady=(2, 8))

        # Corrected text
        tk.Label(outer, text="Replace with (leave blank to delete the match):",
                 anchor="w").pack(fill=tk.X)
        self._corrected_var = tk.StringVar(
            value=self._initial.get("corrected_text", "")
        )
        self._corrected_entry = tk.Entry(
            outer, textvariable=self._corrected_var, width=50,
        )
        self._corrected_entry.pack(fill=tk.X, pady=(2, 8))

        # Options
        opts = tk.LabelFrame(outer, text=" Options ", padx=8, pady=4)
        opts.pack(fill=tk.X, pady=(2, 8))

        self._wb_var = tk.BooleanVar(
            value=bool(self._initial.get("word_boundary", True))
        )
        tk.Checkbutton(
            opts, text="Match whole words only",
            variable=self._wb_var,
        ).pack(anchor="w")

        self._cs_var = tk.BooleanVar(
            value=bool(self._initial.get("case_sensitive", False))
        )
        tk.Checkbutton(
            opts, text="Case-sensitive",
            variable=self._cs_var,
        ).pack(anchor="w")

        # Notes
        tk.Label(outer, text="Notes (optional):", anchor="w").pack(fill=tk.X)
        self._notes_var = tk.StringVar(
            value=self._initial.get("notes") or ""
        )
        tk.Entry(
            outer, textvariable=self._notes_var, width=50,
        ).pack(fill=tk.X, pady=(2, 0))

        # Buttons
        btn_row = tk.Frame(outer)
        btn_row.pack(fill=tk.X, pady=(12, 0))

        tk.Button(
            btn_row, text="Cancel", width=10, command=self._on_cancel
        ).pack(side=tk.RIGHT, padx=(4, 0))
        tk.Button(
            btn_row, text="Save", width=10, command=self._on_save,
            default=tk.ACTIVE,
        ).pack(side=tk.RIGHT)

        # Keyboard bindings
        self.win.bind("<Return>", lambda _e: self._on_save())
        self.win.bind("<Escape>", lambda _e: self._on_cancel())

    # ----- Actions -----------------------------------------------------------

    def _on_save(self):
        original = self._original_var.get()
        if not original or not original.strip():
            messagebox.showerror(
                "Original text required",
                "Original text cannot be empty.",
                parent=self.win,
            )
            self._original_entry.focus_set()
            return
        notes = self._notes_var.get().strip()
        self._result = {
            "original_text":  original,           # keep as-typed; spaces matter
            "corrected_text": self._corrected_var.get(),
            "case_sensitive": bool(self._cs_var.get()),
            "word_boundary":  bool(self._wb_var.get()),
            "notes":          notes if notes else None,
        }
        self.win.destroy()

    def _on_cancel(self):
        self._result = None
        try:
            self.win.destroy()
        except Exception:
            pass
