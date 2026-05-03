"""
add_to_corrections_dialog.py — Quick "Add to Corrections List" dialog (v1.7-alpha)

Modal dialog used from Thread Viewer right-click and from the Word
Speaker Panel's "+ Correction" button. Lets the user add a new
correction entry without leaving the document they're editing.

Design intent:
  * Pre-fill the "Original text" field with whatever the user had
    selected in the source surface (highlighted text in Thread Viewer
    or the current Word selection).  Saves them retyping it.
  * Let the user pick the destination list from a dropdown OR create
    a new list inline (most users will only have one or two custom
    lists, so a quick "+ New list..." entry in the dropdown is faster
    than opening the full management dialog).
  * Same Whole-word / Match-case / Notes options as the full
    CorrectionEntryEditor in the management dialog, for consistency.
  * "Manage lists..." button as a side door to the full management
    dialog when the user wants to do more than just add one entry.
  * The bundled "General" list is selectable but a small note warns
    the user that General is shared across all DocAnalyser users on
    upgrade and recommends using a personal list for their own terms.

Usage:
    from add_to_corrections_dialog import show_add_to_corrections_dialog
    show_add_to_corrections_dialog(parent, seed_text="tell vision")

The function is fire-and-forget — the dialog handles its own writes
via corrections_db_adapter and reports success/failure via standard
messageboxes. Returns the new correction id on success, None if the
user cancelled.

Author: DocAnalyser Development Team
Date: 28 April 2026 (v1.7-alpha Day 6)
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Optional

import corrections_db_adapter as adapter

logger = logging.getLogger(__name__)


# =============================================================================
# Screen-position helper
# =============================================================================

def _clamp_to_screen(parent, win, w: int, h: int) -> tuple[int, int]:
    """
    Compute (x, y) coordinates that centre `win` over `parent` while
    keeping the entire window inside the screen bounds.

    The simple "centre over parent" calculation can place a dialog
    partially off-screen when the parent is docked to a screen edge
    (e.g. the Word Speaker Panel pinned to the right). This function
    centres first, then clamps so that:
      * x + w <= screen_width   (right edge stays on screen)
      * y + h <= screen_height  (bottom edge stays on screen)
      * x >= 0 and y >= 0       (top-left stays on screen)

    Falls back to (0, 0) if any geometry query raises (e.g. parent
    not yet mapped). Used by both the Add-to-Corrections dialog and
    its confirmation popup so neither can drift off-screen.
    """
    try:
        # Prefer parent-relative centring.
        px = parent.winfo_x() + (parent.winfo_width()  - w) // 2
        py = parent.winfo_y() + (parent.winfo_height() - h) // 2
        # Clamp to screen bounds. winfo_screenwidth/height come from
        # the window we're positioning (Tk caches the screen the
        # toplevel is on), which handles multi-monitor setups
        # reasonably for the common case.
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        # Right/bottom: never let the window edge exceed screen edge,
        # leaving a small 8 px margin so the window frame isn't flush.
        px = min(px, sw - w - 8)
        py = min(py, sh - h - 8)
        # Left/top: never let the window origin go negative, with the
        # same 8 px margin from the screen edge.
        px = max(8, px)
        py = max(8, py)
        return px, py
    except Exception:
        return 0, 0


# Special label used as a sentinel "+ New list..." entry at the bottom
# of the destination-list dropdown. Picking it triggers an inline name
# prompt rather than selecting an existing list.
_NEW_LIST_LABEL = "+  New list\u2026"


# =============================================================================
# Custom confirmation popup
# =============================================================================

def _show_confirmation_popup(parent, title: str, message: str) -> None:
    """
    Show a small modal confirmation popup with predictable dimensions
    and a guaranteed-visible OK button.

    Replaces messagebox.showinfo for the post-Save "Correction added"
    confirmation. The OS-native messagebox sizes itself based on text
    length and platform conventions; on some screens (Windows DPI
    scaling, secondary monitors, narrow desktops) the OK button can end
    up below the visible area or behind another window. This popup
    uses a fixed Toplevel with the OK button packed at the bottom of a
    BOTH/expand container so it remains in view regardless of message
    length.

    Pressing Enter, Escape, or clicking the X button all close the
    popup the same way the OK button does.

    parent:  Tk window to parent the popup to. Used for centring and
             modal grab.
    title:   Window title bar text.
    message: Body text. Newlines are preserved; the label wraps at
             ~420 px so long messages don't blow out the width.
    """
    win = tk.Toplevel(parent)
    win.title(title)
    win.resizable(False, False)

    # Fixed dimensions sized to comfortably hold a 4-5 line message
    # plus the button row. Generous height accommodates the rule-summary
    # block ("  yeah  \u2192  yes") and a two-line apply-now tail.
    w, h = 480, 260
    try:
        px, py = _clamp_to_screen(parent, win, w, h)
        win.geometry(f"{w}x{h}+{px}+{py}")
    except Exception:
        win.geometry(f"{w}x{h}")

    def _close():
        try:
            win.destroy()
        except Exception:
            pass

    # CRITICAL packing order: button row FIRST with side=tk.BOTTOM, then
    # the body. Tk's pack manager assigns space in the order widgets are
    # packed, so packing the body first with expand=True would consume
    # all vertical space and push the button row off the bottom edge.
    # Packing the button row first reserves its space at the bottom; the
    # body then fills only the remaining area. This guarantees the OK
    # button is always visible regardless of message length.
    btn_row = tk.Frame(win, pady=12)
    btn_row.pack(side=tk.BOTTOM, fill=tk.X)

    ok_btn = tk.Button(
        btn_row, text="OK", width=10, command=_close, default=tk.ACTIVE,
    )
    ok_btn.pack(side=tk.RIGHT, padx=20)

    # Body packs into whatever remains above the button row.
    body = tk.Frame(win, padx=18, pady=14)
    body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    # Title bar already says "Correction added"; no need for a duplicate
    # heading inside the popup. We use a single Label with wraplength so
    # long messages flow naturally rather than overflowing.
    msg_label = tk.Label(
        body,
        text=message,
        wraplength=w - 50,
        justify="left",
        anchor="nw",
    )
    msg_label.pack(fill=tk.BOTH, expand=True)

    win.bind("<Return>", lambda _e: _close())
    win.bind("<Escape>", lambda _e: _close())
    win.protocol("WM_DELETE_WINDOW", _close)

    try:
        win.transient(parent)
        win.grab_set()
    except Exception:
        pass
    ok_btn.focus_set()

    try:
        win.wait_window()
    except Exception:
        pass


# =============================================================================
# Public entry point
# =============================================================================

def show_add_to_corrections_dialog(
        parent,
        seed_text: str = "",
        default_corrected: str = "",
        apply_now_callback: Optional["callable"] = None,
        apply_now_label: Optional[str] = None,
) -> Optional[int]:
    """
    Open the modal "Add to Corrections List" dialog.

    parent:             The Tk window that owns the dialog (Thread Viewer
                        Toplevel, or the Word Speaker Panel window).
    seed_text:          Text to pre-fill the "Original text" field with
                        (e.g. the user's current selection).
    default_corrected:  Optional initial value for the "Replace with"
                        field. Usually empty — users typically know what
                        was misheard and type the correct form here.
    apply_now_callback: Optional callable taking a single dict argument
                        with keys: original_text, corrected_text,
                        case_sensitive, word_boundary. When provided, the
                        dialog renders an "Also apply to this document
                        now" checkbox; if the user ticks it, the callback
                        is invoked AFTER the rule has been saved to the
                        list, and is responsible for retroactively
                        applying the correction to the current document.
                        Pass None to suppress the checkbox entirely.
    apply_now_label:    Optional label override for the checkbox (e.g.
                        'Also apply to this conversation now'). When None,
                        defaults to 'Also apply to this document now'.

    Returns the new correction id on Save, or None on Cancel.
    """
    dlg = AddToCorrectionsDialog(
        parent,
        seed_text=seed_text,
        default_corrected=default_corrected,
        apply_now_callback=apply_now_callback,
        apply_now_label=apply_now_label,
    )
    return dlg.show()


# =============================================================================
# Dialog
# =============================================================================

class AddToCorrectionsDialog:
    """
    Modal dialog for adding a single correction to an existing or
    newly-created Corrections List.

    Public flow:
        dlg = AddToCorrectionsDialog(parent, seed_text="...")
        new_id = dlg.show()      # blocks until user clicks Save/Cancel
    """

    def __init__(
            self,
            parent,
            seed_text: str = "",
            default_corrected: str = "",
            apply_now_callback: Optional["callable"] = None,
            apply_now_label: Optional[str] = None,
    ):
        self._parent             = parent
        self._seed_text          = (seed_text or "").strip()
        self._default_corrected  = default_corrected or ""
        self._apply_now_callback = apply_now_callback
        self._apply_now_label    = (
            apply_now_label
            or "Also apply to this document now"
        )
        self._result_id: Optional[int] = None
        # (label, list_id) pairs in dropdown order. Populated by
        # _populate_lists_combo. The "+  New list..." sentinel is
        # appended last and stored with id=None.
        self._available_lists: list[tuple[str, Optional[int]]] = []

    # ----- Public API --------------------------------------------------------

    def show(self) -> Optional[int]:
        """Build the dialog, run modally, return result id (or None)."""
        self._build_window()
        self.win.transient(self._parent)
        self.win.grab_set()
        self.win.focus_set()
        # Focus on the corrected-text field if seed was provided (user
        # already knows what they're correcting); otherwise focus on the
        # original-text field so they can type it.
        if self._seed_text:
            self._corrected_entry.focus_set()
        else:
            self._original_entry.focus_set()
        self.win.wait_window()
        return self._result_id

    # ----- Construction ------------------------------------------------------

    def _build_window(self):
        self.win = tk.Toplevel(self._parent)
        self.win.title("Add to Corrections List")
        # Resizable as a defensive measure: the dialog is sized to fit
        # all controls comfortably, but on extreme DPI scaling the user
        # can still drag the edge if anything clips. min_size is set
        # large enough that every control stays visible.
        self.win.resizable(True, True)
        self.win.minsize(460, 540)
        self.win.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.win.update_idletasks()
        # Default height generous enough for: 2 text entries, list row,
        # hint label (up to 2 lines), Options frame, Notes entry,
        # apply-now checkbox, and button row — with breathing room.
        w, h = 500, 560
        try:
            px, py = _clamp_to_screen(self._parent, self.win, w, h)
            self.win.geometry(f"{w}x{h}+{px}+{py}")
        except Exception:
            self.win.geometry(f"{w}x{h}")

        # CRITICAL packing order: button row FIRST with side=tk.BOTTOM
        # so it reserves space at the bottom of the window before any
        # of the content widgets claim vertical space. Tk's pack manager
        # is order-sensitive: if the content frame were packed first
        # with expand=True, it would consume all available space and
        # push the button row off the bottom edge. Packing buttons
        # first guarantees Save/Cancel are always visible regardless
        # of how much content sits above them.
        self._build_button_row()

        outer = tk.Frame(self.win, padx=14, pady=12)
        outer.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # ----- Original text -----
        tk.Label(outer, text="Original text (what to find):",
                 anchor="w").pack(fill=tk.X)
        self._original_var = tk.StringVar(value=self._seed_text)
        self._original_entry = tk.Entry(
            outer, textvariable=self._original_var, width=50,
        )
        self._original_entry.pack(fill=tk.X, pady=(2, 8))

        # ----- Corrected text -----
        tk.Label(outer, text="Replace with (leave blank to delete the match):",
                 anchor="w").pack(fill=tk.X)
        self._corrected_var = tk.StringVar(value=self._default_corrected)
        self._corrected_entry = tk.Entry(
            outer, textvariable=self._corrected_var, width=50,
        )
        self._corrected_entry.pack(fill=tk.X, pady=(2, 8))

        # ----- Destination list -----
        list_row = tk.Frame(outer)
        list_row.pack(fill=tk.X, pady=(0, 4))
        tk.Label(list_row, text="Add to list:", anchor="w").pack(side=tk.LEFT)

        self._list_var = tk.StringVar()
        self._list_combo = ttk.Combobox(
            list_row,
            textvariable=self._list_var,
            state="readonly",
            width=28,
        )
        self._list_combo.pack(side=tk.LEFT, padx=(6, 6))
        self._list_combo.bind("<<ComboboxSelected>>",
                              lambda _e: self._on_list_selected())

        tk.Button(
            list_row, text="Manage lists\u2026",
            command=self._on_manage_lists,
        ).pack(side=tk.LEFT)

        # Hint shown when "General" is selected (it's the bundled list
        # and gets re-seeded on app upgrades; users should prefer their
        # own lists for personal terms).
        self._list_hint = tk.Label(
            outer,
            text="",
            font=("Segoe UI", 8, "italic"),
            fg="#777777",
            anchor="w",
            justify="left",
            wraplength=440,
        )
        self._list_hint.pack(fill=tk.X, pady=(0, 6))

        self._populate_lists_combo()

        # ----- Options -----
        opts = tk.LabelFrame(outer, text=" Options ", padx=8, pady=4)
        opts.pack(fill=tk.X, pady=(2, 8))

        self._wb_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opts, text="Match whole words only",
            variable=self._wb_var,
        ).pack(anchor="w")

        self._cs_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            opts, text="Case-sensitive",
            variable=self._cs_var,
        ).pack(anchor="w")

        # ----- Notes -----
        tk.Label(outer, text="Notes (optional):", anchor="w").pack(fill=tk.X)
        self._notes_var = tk.StringVar(value="")
        tk.Entry(
            outer, textvariable=self._notes_var, width=50,
        ).pack(fill=tk.X, pady=(2, 0))

        # ----- Apply-now checkbox (v1.7-alpha) -----
        # Only rendered when a callback is supplied by the caller.
        # When ticked, the callback is invoked AFTER the rule has been
        # saved to the corrections list. It is responsible for
        # retroactively applying the correction to the current document.
        # Default UNTICKED so the conservative "rules are for future
        # cleanup runs" behaviour holds unless the user opts in.
        self._apply_now_var = tk.BooleanVar(value=False)
        if self._apply_now_callback is not None:
            tk.Checkbutton(
                outer,
                text=self._apply_now_label,
                variable=self._apply_now_var,
                anchor="w",
            ).pack(fill=tk.X, pady=(8, 0))

        # NOTE: the Save/Cancel button row is built separately by
        # _build_button_row() and packed with side=tk.BOTTOM BEFORE
        # this content frame. See the comment in _build_window().

        # ----- Keyboard bindings -----
        self.win.bind("<Return>", lambda _e: self._on_save())
        self.win.bind("<Escape>", lambda _e: self._on_cancel())

    def _build_button_row(self):
        """
        Build the Save / Cancel button row and pack it at the bottom
        of the dialog. Called from _build_window() BEFORE the content
        frame is packed, so this row reserves its vertical space at
        the bottom of the window and the content frame fills only the
        space above it. This guarantees the buttons stay visible even
        if the content is taller than expected.
        """
        btn_row = tk.Frame(self.win, padx=14, pady=10)
        btn_row.pack(side=tk.BOTTOM, fill=tk.X)

        tk.Button(
            btn_row, text="Cancel", width=10, command=self._on_cancel,
        ).pack(side=tk.RIGHT, padx=(6, 0))
        tk.Button(
            btn_row, text="Save", width=10, command=self._on_save,
            default=tk.ACTIVE,
        ).pack(side=tk.RIGHT)

    # ----- Lists dropdown ---------------------------------------------------

    def _populate_lists_combo(self, select_id: Optional[int] = None):
        """
        Load all corrections lists into the dropdown plus the
        "+ New list..." sentinel.

        Default selection logic:
          * select_id provided  -> select that list (used after creating
                                    a new one inline so it's pre-picked)
          * Lists exist that aren't "General" -> select the most recently
            updated non-bundled list (most likely the one they want)
          * Otherwise           -> select General
        """
        self._available_lists = []
        try:
            for lst in adapter.list_get_all():
                self._available_lists.append((lst["name"], lst["id"]))
        except Exception as exc:
            logger.warning("Could not load corrections lists: %s", exc)
        # Append the sentinel
        self._available_lists.append((_NEW_LIST_LABEL, None))

        labels = [label for label, _ in self._available_lists]
        self._list_combo["values"] = labels

        # Decide which list to default to
        target_label: Optional[str] = None
        if select_id is not None:
            for label, lst_id in self._available_lists:
                if lst_id == select_id:
                    target_label = label
                    break
        if target_label is None:
            # Prefer the first non-bundled list, fall back to General.
            for label, lst_id in self._available_lists:
                if lst_id is not None and label != adapter.BUNDLED_LIST_NAME:
                    target_label = label
                    break
        if target_label is None:
            for label, lst_id in self._available_lists:
                if lst_id is not None:
                    target_label = label
                    break

        if target_label is not None:
            self._list_var.set(target_label)
        elif labels:
            self._list_var.set(labels[0])

        self._on_list_selected()

    def _on_list_selected(self):
        """
        Dropdown selection changed.

        If the sentinel "+ New list..." was picked, prompt for a name
        and create the list immediately, then re-select to it.
        Otherwise update the hint label based on whether "General" or a
        user list is selected.
        """
        label = self._list_var.get()

        if label == _NEW_LIST_LABEL:
            self._handle_inline_new_list()
            return

        if label == adapter.BUNDLED_LIST_NAME:
            self._list_hint.config(
                text=(
                    "\u2139 General is the bundled starter list. It can "
                    "be edited but app upgrades may re-seed missing "
                    "default rules. Consider creating your own list for "
                    "personal terms via \u201cManage lists\u2026\u201d."
                )
            )
        else:
            self._list_hint.config(text="")

    def _handle_inline_new_list(self):
        """
        Sentinel "+ New list..." was picked from the dropdown.
        Prompt for a name, create the list, re-populate the dropdown
        with the new list selected. If the user cancels the prompt or
        creation fails, restore the prior selection.
        """
        # Remember whatever was previously selected so we can roll back
        # if the user cancels the name prompt.
        prior_id: Optional[int] = None
        prior_label: Optional[str] = None
        for label, lst_id in self._available_lists:
            if lst_id is not None and label != _NEW_LIST_LABEL:
                # First real list seen — use it as fallback if needed.
                prior_id = lst_id
                prior_label = label
                break

        name = simpledialog.askstring(
            "New corrections list",
            "Name for the new list:",
            parent=self.win,
        )
        if name is None or not name.strip():
            # Cancelled or empty — fall back to prior selection.
            if prior_label is not None:
                self._list_var.set(prior_label)
            self._on_list_selected()
            return

        try:
            new_id = adapter.list_create(name=name.strip())
        except ValueError as exc:
            messagebox.showerror("Cannot create list", str(exc),
                                 parent=self.win)
            if prior_label is not None:
                self._list_var.set(prior_label)
            self._on_list_selected()
            return
        except Exception as exc:
            logger.error("list_create failed: %s", exc)
            messagebox.showerror("Database error", str(exc),
                                 parent=self.win)
            if prior_label is not None:
                self._list_var.set(prior_label)
            self._on_list_selected()
            return

        # Re-populate with the new list selected.
        self._populate_lists_combo(select_id=new_id)

    def _resolve_destination_list_id(self) -> Optional[int]:
        """
        Translate the current dropdown label to a list_id.
        Returns None if the sentinel is somehow selected at Save time
        (shouldn't happen, but defensive).
        """
        label = self._list_var.get()
        for lst_label, lst_id in self._available_lists:
            if lst_label == label:
                return lst_id
        return None

    # ----- Manage lists side door --------------------------------------------

    def _on_manage_lists(self):
        """
        Open the full management dialog as a side door for users who
        want to do more than just add one entry. We keep our own dialog
        open underneath so the user can return to finish their entry
        once they've, say, renamed a list or imported a JSON.

        Refreshes the dropdown when the management dialog closes so any
        new/renamed/deleted lists appear immediately.
        """
        try:
            from corrections_management_dialog import (
                show_corrections_management_dialog,
            )
        except ImportError as exc:
            logger.error(
                "Management dialog not available: %s", exc
            )
            messagebox.showerror(
                "Not available",
                "The corrections list management dialog could not be "
                "loaded. You can still add to existing lists or create "
                "new ones using \u201c+ New list\u2026\u201d in the "
                "dropdown.",
                parent=self.win,
            )
            return

        try:
            show_corrections_management_dialog(
                self.win,
                on_close=lambda: self._populate_lists_combo(
                    select_id=self._resolve_destination_list_id()
                ),
            )
        except Exception as exc:
            logger.exception(
                "Failed to open corrections management dialog"
            )
            messagebox.showerror(
                "Could not open management dialog",
                f"The management dialog could not be opened:\n\n{exc}",
                parent=self.win,
            )
        finally:
            # Management dialog is modal (G2-fix, May 2026) and takes
            # the input grab while open. When it closes, the grab is
            # released and our Add dialog is left non-modal until we
            # reclaim it. Wrapped in try/except in case the Add dialog
            # was itself closed while management was open.
            try:
                self.win.grab_set()
            except Exception:
                pass

    # ----- Save / Cancel -----------------------------------------------------

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

        list_id = self._resolve_destination_list_id()
        if list_id is None:
            messagebox.showerror(
                "Choose a list",
                "Please pick a destination list (or create a new one).",
                parent=self.win,
            )
            return

        notes = self._notes_var.get().strip() or None
        try:
            new_id = adapter.correction_add(
                list_id=list_id,
                original_text=original,
                corrected_text=self._corrected_var.get(),
                case_sensitive=bool(self._cs_var.get()),
                word_boundary=bool(self._wb_var.get()),
                notes=notes,
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

        self._result_id = new_id
        # Capture values before destroying the window since they read
        # from Tk variables.
        list_label = self._list_var.get()
        original   = original.strip()
        replaced   = self._corrected_var.get()
        apply_now  = bool(self._apply_now_var.get())
        case_sens  = bool(self._cs_var.get())
        word_b     = bool(self._wb_var.get())

        # Tear down the dialog FIRST, then run the optional apply-now
        # callback and show the confirmation popup. Both are parented
        # to the original caller (Thread Viewer or Speaker Panel) so
        # they render reliably after self.win is gone.
        try:
            self.win.destroy()
        except Exception:
            pass

        # Run the apply-now callback if requested. Errors here are
        # surfaced to the user but don't roll back the rule — the rule
        # is already saved and would still apply to future cleanups.
        apply_now_result = None
        if apply_now and self._apply_now_callback is not None:
            try:
                apply_now_result = self._apply_now_callback({
                    "original_text":  original,
                    "corrected_text": replaced,
                    "case_sensitive": case_sens,
                    "word_boundary":  word_b,
                })
            except Exception as exc:
                logger.exception("apply_now_callback failed")
                try:
                    messagebox.showerror(
                        "Could not apply correction now",
                        f"The rule was added to the list, but applying it "
                        f"to the current document failed:\n\n{exc}",
                        parent=self._parent,
                    )
                except Exception:
                    pass

        try:
            arrow = "\u2192"
            if replaced:
                head = (
                    f"Added to list \u201c{list_label}\u201d:\n\n"
                    f"  {original}  {arrow}  {replaced}"
                )
            else:
                head = (
                    f"Added to list \u201c{list_label}\u201d:\n\n"
                    f"  {original}  {arrow}  (deletes match)"
                )
            # Append a summary of the apply-now result if provided.
            tail = ""
            if apply_now and apply_now_result is not None:
                # Callbacks may return either a plain int hit count or
                # a dict with a 'hits' key plus optional 'detail'.
                if isinstance(apply_now_result, dict):
                    hits   = int(apply_now_result.get("hits", 0))
                    detail = apply_now_result.get("detail")
                else:
                    hits   = int(apply_now_result or 0)
                    detail = None
                if hits > 0:
                    tail = (
                        f"\n\nAlso applied to the current document: "
                        f"{hits} occurrence"
                        f"{'s' if hits != 1 else ''} replaced."
                    )
                    if detail:
                        tail += f"\n{detail}"
                else:
                    # Zero hits. Prefer the callback's detail message if
                    # one was supplied (e.g. "Could not load entries:
                    # ..."), otherwise fall back to the generic message.
                    if detail:
                        tail = f"\n\nCould not apply now: {detail}"
                    else:
                        tail = (
                            "\n\nNo occurrences were found in the current "
                            "document, so nothing was changed there."
                        )
            elif apply_now and self._apply_now_callback is not None:
                # Callback ran but returned None — still confirm.
                tail = (
                    "\n\nApplied to the current document."
                )
            # Use our custom confirmation popup rather than
            # messagebox.showinfo, which on some screens / DPI settings
            # sizes itself such that the OK button drifts off-screen or
            # behind other windows. Our popup uses fixed dimensions and
            # a Tk.Label with wraplength so the OK button is always
            # visible inside the bounds.
            _show_confirmation_popup(
                self._parent,
                title="Correction added",
                message=head + tail,
            )
        except Exception:
            pass

    def _on_cancel(self):
        self._result_id = None
        try:
            self.win.destroy()
        except Exception:
            pass
