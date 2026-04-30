"""
backups_dialog.py — UI for listing, restoring, and deleting document
backups (v1.7-alpha Day 7 sub-task 6).

Public API
----------
    show_backups_dialog(
        parent,
        document_id,
        document_title,
        current_entries,
        current_metadata_subset=None,
        on_restore_complete=None,
    )

Opens a modal Toplevel listing every backup row that exists for the
given document, newest first. The user can:

  * Restore a backup. Before the restore swaps the entries in,
    backups_manager.restore_backup() automatically creates a
    counter-backup of the current state (TRIGGER_PRE_RESTORE) so a
    misclick is itself recoverable.
  * Delete a backup permanently.
  * Close the dialog.

Contract for `on_restore_complete`
----------------------------------
    callback(payload: dict) -> None

    Called once, only after a successful restore. The dialog has by
    that point already created the counter-backup but has NOT written
    the restored entries back to the documents/document_entries tables
    — that is the caller's responsibility, because only the caller
    knows how its in-memory state and dependent widgets need to be
    updated. The payload dict has the canonical shape produced by
    backups_manager._deserialise_payload:

        {
            "version":          int,           # payload schema version
            "entries":          list[dict],    # the restored entries
            "metadata_subset":  dict,          # the restored metadata subset
        }

    Typical caller responsibilities (e.g. inside thread_viewer.py):
        1. self.current_entries = payload["entries"]
        2. update_transcript_entries(doc_id, payload["entries"])
        3. apply payload["metadata_subset"] back onto self.metadata
        4. refresh any dependent UI (paragraph editor, speaker filter,
           player position, etc.)

Author: DocAnalyser Development Team
Date:   30 April 2026 (v1.7-alpha Day 7 sub-task 6)
"""

from __future__ import annotations

import logging
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Optional

import backups_manager


# ---------------------------------------------------------------------------
# Trigger-type display labels
# ---------------------------------------------------------------------------
# Friendly user-facing names for the TRIGGER_* constants in
# backups_manager. Unknown trigger types fall through as their raw
# string, so a future trigger added by appending to backups_manager
# will still render readably even before this map is updated.

TRIGGER_LABELS: Dict[str, str] = {
    backups_manager.TRIGGER_CLEANUP_OPEN: "Before cleanup",
    backups_manager.TRIGGER_PRE_RESTORE:  "Before restore",
    backups_manager.TRIGGER_MANUAL:       "Manual backup",
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def show_backups_dialog(
    parent: tk.Misc,
    document_id: str,
    document_title: str,
    current_entries: List[Dict[str, Any]],
    current_metadata_subset: Optional[Dict[str, Any]] = None,
    on_restore_complete: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> None:
    """
    Open the modal Backups dialog. See module docstring for the
    on_restore_complete contract.
    """
    BackupsDialog(
        parent=parent,
        document_id=document_id,
        document_title=document_title,
        current_entries=current_entries,
        current_metadata_subset=current_metadata_subset,
        on_restore_complete=on_restore_complete,
    )


# ---------------------------------------------------------------------------
# Dialog class
# ---------------------------------------------------------------------------

class BackupsDialog:
    """
    Modal Toplevel for browsing, restoring, and deleting backups for
    a single document. One instance per invocation; the public
    `show_backups_dialog()` is the entry point — direct instantiation
    is allowed but not the expected usage.
    """

    # Layout constants — kept at the top so visual tweaks are easy.
    _MIN_WIDTH  = 600
    _MIN_HEIGHT = 340
    _COL_WIDTHS = {"created": 160, "trigger": 130, "label": 280}
    _ROW_HEIGHT = 10        # Treeview rows visible by default
    _OUTER_PAD  = 14

    def __init__(
        self,
        parent: tk.Misc,
        document_id: str,
        document_title: str,
        current_entries: List[Dict[str, Any]],
        current_metadata_subset: Optional[Dict[str, Any]],
        on_restore_complete: Optional[Callable[[Dict[str, Any]], None]],
    ) -> None:
        self.parent                  = parent
        self.document_id             = document_id
        self.document_title          = document_title or "(untitled)"
        self.current_entries         = current_entries or []
        self.current_metadata_subset = current_metadata_subset
        self.on_restore_complete     = on_restore_complete

        self.window = tk.Toplevel(parent)
        self.window.title("Document backups")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.resizable(True, True)
        self.window.minsize(self._MIN_WIDTH, self._MIN_HEIGHT)
        self.window.protocol("WM_DELETE_WINDOW", self._close)

        self._build_ui()
        self._load_backups()
        self._centre_on_parent()

    # -----------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------

    def _build_ui(self) -> None:
        # Header — title + document name
        header = tk.Frame(self.window, padx=self._OUTER_PAD, pady=10)
        header.pack(fill=tk.X)

        tk.Label(
            header,
            text="Backup history",
            font=("Arial", 12, "bold"),
            anchor="w",
        ).pack(fill=tk.X)

        # Truncate very long titles for the header — full title still
        # available via the window title bar.
        title_display = self.document_title
        if len(title_display) > 90:
            title_display = title_display[:87] + "..."
        tk.Label(
            header,
            text=f"For: {title_display}",
            font=("Arial", 9),
            fg="#444",
            anchor="w",
            wraplength=self._MIN_WIDTH - 40,
            justify="left",
        ).pack(fill=tk.X, pady=(2, 0))

        # Treeview
        # NOTE: pady on a widget option must be a single number; the
        # tuple form (top, bottom) is only valid for pack(). Python
        # 3.13's Tk binding raises TclError("bad screen distance") on
        # the tuple form, so we use a single value here.
        tree_frame = tk.Frame(self.window, padx=self._OUTER_PAD, pady=4)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("created", "trigger", "label")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=self._ROW_HEIGHT,
        )
        self.tree.heading("created", text="Created")
        self.tree.heading("trigger", text="Reason")
        self.tree.heading("label",   text="Label")
        self.tree.column("created", width=self._COL_WIDTHS["created"], anchor="w")
        self.tree.column("trigger", width=self._COL_WIDTHS["trigger"], anchor="w")
        self.tree.column("label",   width=self._COL_WIDTHS["label"],   anchor="w")

        vscroll = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=vscroll.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_select_change)
        # Double-click as a shortcut for Restore.
        self.tree.bind("<Double-Button-1>", lambda _e: self._on_restore())

        # Status / info line
        self.status_var = tk.StringVar(value="")
        tk.Label(
            self.window,
            textvariable=self.status_var,
            anchor="w",
            font=("Arial", 9),
            fg="#666",
            padx=self._OUTER_PAD,
        ).pack(fill=tk.X)

        # Button row
        btns = tk.Frame(self.window, padx=self._OUTER_PAD, pady=10)
        btns.pack(fill=tk.X)

        ttk.Button(
            btns, text="Close", command=self._close, width=10
        ).pack(side=tk.RIGHT)

        self.restore_btn = ttk.Button(
            btns,
            text="Restore",
            command=self._on_restore,
            width=10,
            state=tk.DISABLED,
        )
        self.restore_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.delete_btn = ttk.Button(
            btns,
            text="Delete",
            command=self._on_delete,
            width=10,
            state=tk.DISABLED,
        )
        self.delete_btn.pack(side=tk.LEFT)

    # -----------------------------------------------------------------
    # Data loading
    # -----------------------------------------------------------------

    def _load_backups(self) -> None:
        """
        Refresh the Treeview from db. Called once on dialog open and
        after every successful Delete.
        """
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        try:
            backups = backups_manager.list_backups(self.document_id)
        except Exception as exc:
            logging.error(f"backups_dialog: list_backups failed: {exc}")
            messagebox.showerror(
                "Error loading backups",
                f"Could not load the backup list:\n{exc}",
                parent=self.window,
            )
            backups = []

        if not backups:
            self.status_var.set(
                "No backups exist for this document yet."
            )
            self._on_select_change()  # disable buttons
            return

        for row in backups:
            self.tree.insert(
                "",
                tk.END,
                iid=str(row["id"]),
                values=(
                    self._format_timestamp(row.get("created_at", "")),
                    TRIGGER_LABELS.get(
                        row.get("trigger_type", ""),
                        row.get("trigger_type", ""),
                    ),
                    row.get("label") or "—",
                ),
            )

        n   = len(backups)
        cap = backups_manager.MAX_BACKUPS_PER_DOCUMENT
        self.status_var.set(
            f"{n} backup{'s' if n != 1 else ''}  "
            f"(retention cap: {cap} most recent per document)"
        )

        # Pre-select the newest so a single Enter or button-click
        # restores the most likely target.
        first = self.tree.get_children()
        if first:
            self.tree.selection_set(first[0])
            self.tree.focus(first[0])

    @staticmethod
    def _format_timestamp(raw: str) -> str:
        """
        Convert db_manager._now()'s ISO-format timestamp
        ('YYYY-MM-DDTHH:MM:SS.ffffff') to a human-readable form.
        Falls back to the raw string on parse failure so a malformed
        row never causes an empty cell.
        """
        if not raw:
            return ""
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%f",   # default: isoformat() with µs
            "%Y-%m-%dT%H:%M:%S",      # isoformat() without µs
            "%Y-%m-%d %H:%M:%S.%f",   # SQLite default with µs
            "%Y-%m-%d %H:%M:%S",      # SQLite default without µs
        ):
            try:
                return datetime.strptime(raw, fmt).strftime(
                    "%d %b %Y  %H:%M:%S"
                )
            except ValueError:
                continue
        return str(raw)

    # -----------------------------------------------------------------
    # Selection state
    # -----------------------------------------------------------------

    def _on_select_change(self, _event: Optional[tk.Event] = None) -> None:
        has_selection = bool(self.tree.selection())
        state = tk.NORMAL if has_selection else tk.DISABLED
        self.restore_btn.config(state=state)
        self.delete_btn.config(state=state)

    def _selected_backup_id(self) -> Optional[int]:
        sel = self.tree.selection()
        if not sel:
            return None
        try:
            return int(sel[0])
        except (TypeError, ValueError):
            return None

    # -----------------------------------------------------------------
    # Actions — Restore
    # -----------------------------------------------------------------

    def _on_restore(self) -> None:
        backup_id = self._selected_backup_id()
        if backup_id is None:
            return

        # Pull display info from the row for the confirmation message.
        values = self.tree.item(str(backup_id), "values")
        created_display = values[0] if values else f"#{backup_id}"
        trigger_display = values[1] if len(values) > 1 else ""

        confirm = (
            f"Restore the backup from {created_display}?\n"
            f"({trigger_display})\n\n"
            "This will replace the current transcript entries with the "
            "snapshot from that backup.\n\n"
            "Before the swap, a safety backup of the current state will "
            "be created automatically — so this action is itself "
            "reversible."
        )
        if not messagebox.askyesno(
            "Restore backup", confirm, parent=self.window
        ):
            return

        try:
            result = backups_manager.restore_backup(
                backup_id=backup_id,
                current_entries=self.current_entries,
                current_metadata_subset=self.current_metadata_subset,
            )
        except ValueError as exc:
            # Backup not found, or payload corrupted. backups_manager
            # short-circuits before creating the counter-backup in
            # both cases.
            messagebox.showerror(
                "Restore failed",
                f"Could not restore the backup:\n{exc}",
                parent=self.window,
            )
            return
        except Exception as exc:
            logging.error(f"backups_dialog: restore_backup failed: {exc}")
            messagebox.showerror(
                "Restore failed",
                f"Unexpected error:\n{exc}",
                parent=self.window,
            )
            return

        # Hand the restored payload back to the caller so the host
        # viewer can apply it to its in-memory state, persist to the
        # documents table, and refresh dependent widgets.
        if self.on_restore_complete is not None:
            try:
                self.on_restore_complete(result["restored_payload"])
            except Exception as exc:
                logging.error(
                    f"backups_dialog: on_restore_complete callback "
                    f"failed: {exc}"
                )
                messagebox.showwarning(
                    "Restored, but display refresh failed",
                    "The backup was restored to the database, but the "
                    f"viewer could not refresh:\n{exc}\n\n"
                    "Try closing and reopening the document.",
                    parent=self.window,
                )
                # Even on callback failure, treat the restore as
                # done — the DB state is what it is, and the user's
                # next action (close/reopen) will resync the viewer.

        messagebox.showinfo(
            "Backup restored",
            f"Restored from backup created {created_display}.\n\n"
            f"A safety backup of the previous state was created "
            f"(backup id {result['counter_backup_id']}) and is "
            "available in this dialog the next time you open it.",
            parent=self.window,
        )
        self._close()

    # -----------------------------------------------------------------
    # Actions — Delete
    # -----------------------------------------------------------------

    def _on_delete(self) -> None:
        backup_id = self._selected_backup_id()
        if backup_id is None:
            return

        values = self.tree.item(str(backup_id), "values")
        created_display = values[0] if values else f"#{backup_id}"

        if not messagebox.askyesno(
            "Delete backup",
            f"Permanently delete the backup from {created_display}?\n\n"
            "This cannot be undone.",
            parent=self.window,
        ):
            return

        try:
            ok = backups_manager.delete_backup(backup_id)
        except Exception as exc:
            logging.error(f"backups_dialog: delete_backup failed: {exc}")
            messagebox.showerror(
                "Delete failed",
                f"Could not delete the backup:\n{exc}",
                parent=self.window,
            )
            return

        if not ok:
            # Race condition — another process or a prior delete
            # already removed this row. Refresh and move on.
            messagebox.showwarning(
                "Nothing to delete",
                "That backup no longer exists. The list will refresh.",
                parent=self.window,
            )

        self._load_backups()

    # -----------------------------------------------------------------
    # Window mechanics
    # -----------------------------------------------------------------

    def _centre_on_parent(self) -> None:
        """Place the dialog near the centre of its parent window."""
        self.window.update_idletasks()
        try:
            px = self.parent.winfo_rootx()
            py = self.parent.winfo_rooty()
            pw = self.parent.winfo_width()
            ph = self.parent.winfo_height()
            ww = self.window.winfo_width()
            wh = self.window.winfo_height()
            x = px + max(0, (pw - ww) // 2)
            y = py + max(0, (ph - wh) // 3)
            self.window.geometry(f"+{x}+{y}")
        except Exception:
            # Centring is best-effort. A failure here (e.g. parent
            # not yet mapped) is not worth surfacing.
            pass

    def _close(self) -> None:
        try:
            self.window.grab_release()
        except Exception:
            pass
        self.window.destroy()
