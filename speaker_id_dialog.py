"""
speaker_id_dialog.py
====================
Unified speaker identification panel for DocAnalyser audio transcripts.

Replaces the previous two-dialog system (SpeakerNameDialog + SpeakerIdentifyPanel)
with a single non-modal SpeakerPanel that handles the entire workflow:

  - Speaker names are added and renamed directly inside the panel at any time,
    without a separate naming pre-step.
  - On a fresh transcript (no names yet) the panel opens with an "Add first
    speaker" prompt.  On a returning session it loads existing names immediately
    and opens ready to continue where the user left off.
  - Paragraphs are assigned by clicking them in the transcript and then clicking
    the correct speaker button.
  - "Identify all" bulk-assigns remaining SPEAKER_X paragraphs using
    neighbour-based inference.
  - After assigning, the panel stays on the current paragraph so the user
    can confirm the change before moving on.  Use Skip or click another
    paragraph to move to a different paragraph.
  - Double-clicking any speaker button renames that speaker everywhere in the
    transcript.

Rendering note:
    transcript_paragraph_editor.py renders heuristic (provisional) labels
    in muted grey italic and confirmed names in normal weight/colour.

Entry point:
    start_speaker_identification(parent, editor, player, text_widget, on_complete)
"""
from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Callable

_HEURISTIC_PAT = re.compile(r'^SPEAKER_[A-Z0-9]+$', re.IGNORECASE)


def _is_heuristic(speaker: str) -> bool:
    return bool(_HEURISTIC_PAT.match(speaker.strip()))


def _discover_heuristic_speakers(entries: List[Dict]) -> List[str]:
    """Return ordered unique heuristic SPEAKER_X labels still in entries."""
    seen: List[str] = []
    for e in entries:
        sp = e.get('speaker', '').strip()
        if sp and _is_heuristic(sp) and sp not in seen:
            seen.append(sp)
    return seen


def _discover_real_names(entries: List[Dict]) -> List[str]:
    """Return ordered unique real (non-heuristic) speaker names in entries."""
    seen: List[str] = []
    for e in entries:
        sp = e.get('speaker', '').strip()
        if sp and not _is_heuristic(sp) and sp not in seen:
            seen.append(sp)
    return seen


def _infer_name_map(entries: List[Dict]) -> Dict[str, str]:
    """
    Infer SPEAKER_X -> real name from already-resolved neighbouring entries.
    Returns only mappings that are >=70% consistent across a +-5-entry window.
    """
    votes: Dict[str, Counter] = defaultdict(Counter)
    n = len(entries)
    for i, e in enumerate(entries):
        real = e.get('speaker', '').strip()
        if not real or _is_heuristic(real):
            continue
        for j in range(max(0, i - 5), min(n, i + 6)):
            nb = entries[j].get('speaker', '').strip()
            if nb and _is_heuristic(nb):
                votes[nb][real] += 1

    result: Dict[str, str] = {}
    for label, counter in votes.items():
        if counter:
            best, count = counter.most_common(1)[0]
            total = sum(counter.values())
            if count / total >= 0.70:
                result[label] = best
    return result


def _bookmark_first_entry(editor, name_map: Dict[str, str]) -> bool:
    """
    Apply name_map to the FIRST entry carrying each heuristic label only.
    Ensures real names survive in the database for the next session without
    mass-assigning all paragraphs before the user has reviewed them.
    """
    bookmarked: set = set()
    applied = False
    for entry in editor._entries:
        sp = entry.get('speaker', '').strip()
        if sp and _is_heuristic(sp) and sp not in bookmarked:
            real = name_map.get(sp)
            if real and not _is_heuristic(real):
                entry['speaker']     = real
                entry['provisional'] = True
                bookmarked.add(sp)
                applied = True
    if applied:
        try:
            editor._save_to_library()
        except Exception:
            pass
    return applied


# ============================================================================
# Unified panel
# ============================================================================

class SpeakerPanel:
    """
    Single non-modal panel for the complete speaker identification workflow.

    Fresh session (no names yet)
    ----------------------------
    The panel opens with an "Add first speaker" prompt.  The assignment
    buttons are disabled until at least one name exists.  Once a name is
    added the user can click paragraphs and assign immediately.

    Returning session (names already in data)
    -----------------------------------------
    Existing names are loaded automatically.  The panel opens ready to
    continue: assignment buttons are enabled, counts show the current state.

    Speaker management (any time)
    ------------------------------
    • Click "＋" to add a new speaker.
    • Double-click any speaker button to rename that speaker everywhere.
    • Renaming is reflected immediately in both the panel and the transcript.
    """

    def __init__(
        self,
        parent:      tk.Misc,
        editor,
        player=None,
        text_widget: tk.Text = None,
        on_complete: Optional[Callable] = None,
    ):
        self._parent      = parent
        self._editor      = editor
        self._entries     = editor._entries
        self._player      = player
        self._tw          = text_widget
        self._on_complete = on_complete

        self._current_idx:   Optional[int] = None
        self._last_assigned: Optional[str] = None
        self._paused:        bool          = False

        # Load speaker names already present in the data
        self._all_names: List[str] = _discover_real_names(self._entries)

        # Inferred SPEAKER_X -> real-name map (used by "Identify all")
        self._name_map: Dict[str, str] = _infer_name_map(self._entries)

        self._editor.paragraph_click_callback = self._on_paragraph_clicked

        self._build_ui(parent)
        self._update_counts()

        # Pre-populate with the paragraph the user had already clicked before
        # opening the panel, so buttons are immediately active without a second click.
        last_idx = getattr(editor, 'last_clicked_entry_idx', None)
        if last_idx is not None and last_idx < len(self._entries):
            self._dlg.after(50, lambda: self._show_entry(last_idx))

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, parent: tk.Misc):
        dlg = tk.Toplevel(parent)
        dlg.title("Identify speakers")
        dlg.resizable(True, False)
        dlg.transient(parent)
        dlg.protocol("WM_DELETE_WINDOW", self._on_finish)
        self._dlg = dlg

        # ── Unresolved count + auto-play ──────────────────────────────────
        top = ttk.Frame(dlg, padding=(10, 8, 10, 4))
        top.pack(fill=tk.X)
        self._unresolved_var = tk.StringVar()
        ttk.Label(top, textvariable=self._unresolved_var,
                  font=('Arial', 9, 'bold')).pack(side=tk.LEFT)

        ttk.Separator(dlg, orient='horizontal').pack(fill=tk.X, padx=10)

        # ── Current paragraph: timestamp + label ──────────────────────────
        info = ttk.Frame(dlg, padding=(10, 4, 10, 0))
        info.pack(fill=tk.X)
        self._ts_var  = tk.StringVar(value="")
        self._lbl_var = tk.StringVar(value="")
        ttk.Label(info, textvariable=self._ts_var,
                  font=('Consolas', 9), foreground='#666666').pack(side=tk.LEFT)
        ttk.Label(info, textvariable=self._lbl_var,
                  font=('Arial', 9, 'italic'),
                  foreground='#555555').pack(side=tk.LEFT, padx=(8, 0))

        # ── Paragraph text preview ────────────────────────────────────────
        txt_frame = ttk.Frame(dlg, padding=(10, 4, 10, 6))
        txt_frame.pack(fill=tk.BOTH, expand=True)
        self._para_text = tk.Text(
            txt_frame, height=5, wrap=tk.WORD,
            font=('Arial', 10), relief=tk.GROOVE, bd=1,
            state=tk.DISABLED, cursor='arrow', bg='#f8f8f8',
        )
        sb = ttk.Scrollbar(txt_frame, command=self._para_text.yview)
        self._para_text.configure(yscrollcommand=sb.set)
        self._para_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._set_para_text(
            "Click any paragraph in the transcript\nto identify its speaker."
        )

        # ── "Who is speaking?" label ──────────────────────────────────────
        self._who_label = ttk.Label(dlg, text="",
                                    font=('Arial', 9), padding=(10, 2, 10, 0))
        self._who_label.pack(anchor='w')

        # ── Speaker assignment buttons ────────────────────────────────────
        # _btn_outer is a stable container; _btn_row inside it is rebuilt
        # whenever speakers are added or renamed.
        self._btn_outer = ttk.Frame(dlg, padding=(10, 0, 10, 2))
        self._btn_outer.pack(fill=tk.X)
        self._btn_row:  Optional[tk.Frame]       = None
        self._name_btns: Dict[str, tk.Button]    = {}
        self._rebuild_name_buttons()

        # ── Same ↑ / Skip + rename hint ──────────────────────────────────
        nav2 = ttk.Frame(dlg, padding=(10, 2, 10, 6))
        nav2.pack(fill=tk.X)
        self._same_btn = ttk.Button(nav2, text="Same ↑",
                                    command=self._assign_same,
                                    state=tk.DISABLED)
        self._same_btn.pack(side=tk.LEFT, padx=(0, 6))
        self._skip_btn = ttk.Button(nav2, text="Skip",
                                    command=self._skip,
                                    state=tk.DISABLED)
        self._skip_btn.pack(side=tk.LEFT)
        ttk.Label(nav2,
                  text="  Double-click a name button to rename that speaker",
                  font=('Arial', 8), foreground='#999999').pack(
            side=tk.LEFT, padx=(12, 0))

        ttk.Separator(dlg, orient='horizontal').pack(fill=tk.X, padx=10)

        # ── Identify all ──────────────────────────────────────────────────
        id_frame = ttk.Frame(dlg, padding=(10, 6, 10, 4))
        id_frame.pack(fill=tk.X)
        self._identify_all_btn = ttk.Button(
            id_frame, text="Identify all",
            command=self._identify_all,
            state=tk.DISABLED,
        )
        self._identify_all_btn.pack(side=tk.LEFT, anchor='n')
        ttk.Label(id_frame,
                  text="  Bulk-assigns all remaining SPEAKER_A / B paragraphs\n"
                       "  using neighbour inference.  Use when the auto-labels\n"
                       "  look mostly correct in the transcript.",
                  font=('Arial', 8), foreground='#666666',
                  justify=tk.LEFT).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Separator(dlg, orient='horizontal').pack(fill=tk.X, padx=10)

        # ── Per-speaker counts ────────────────────────────────────────────
        self._status_frame = ttk.Frame(dlg, padding=(10, 4, 10, 4))
        self._status_frame.pack(fill=tk.X)

        # ── Pause / Finish ────────────────────────────────────────────────
        bot = ttk.Frame(dlg, padding=(10, 2, 10, 10))
        bot.pack(fill=tk.X)
        ttk.Button(bot, text="Finish & save",
                   command=self._on_finish).pack(side=tk.RIGHT)
        self._pause_btn = ttk.Button(bot, text="⏸ Pause",
                                     command=self._toggle_pause)
        self._pause_btn.pack(side=tk.RIGHT, padx=(0, 8))
        self._pause_lbl = ttk.Label(bot, text="",
                                    font=('Arial', 8), foreground='#cc6600')
        self._pause_lbl.pack(side=tk.LEFT)

        # Global keyboard shortcuts
        dlg.bind('<space>',  lambda e: self._assign_same() or 'break')
        dlg.bind('s',        lambda e: self._skip())
        dlg.bind('<Escape>', lambda e: self._on_finish())
        self._bind_number_shortcuts()

        dlg.update_idletasks()
        dlg_h = dlg.winfo_reqheight()
        # Place immediately to the right of the Thread Viewer window.
        # No fallback: winfo_reqwidth() can overestimate width due to long
        # label text, causing the old fallback to fire and put the dialog
        # at x=0 covering the transcript.  Overlapping the DocAnalyser
        # window is acceptable; obscuring the transcript is not.
        px = parent.winfo_rootx() + parent.winfo_width() + 8
        py = parent.winfo_rooty() + 40
        dlg.geometry(f"450x{dlg_h}+{px}+{max(0, py)}")

    # ------------------------------------------------------------------
    # Speaker management
    # ------------------------------------------------------------------

    def _rebuild_name_buttons(self):
        """Tear down and recreate the speaker button row from self._all_names."""
        if self._btn_row is not None:
            self._btn_row.destroy()

        self._btn_row = tk.Frame(self._btn_outer)
        self._btn_row.pack(fill=tk.X)
        self._name_btns = {}

        if not self._all_names:
            # ── Fresh transcript: no speakers yet ────────────────────────
            tk.Label(
                self._btn_row,
                text="No speakers yet — ",
                font=('Arial', 9), fg='#888888',
            ).pack(side=tk.LEFT)
            tk.Button(
                self._btn_row,
                text="＋ Add first speaker",
                font=('Arial', 9, 'bold'),
                bg='#c8e6c9', activebackground='#a5d6a7',
                relief=tk.FLAT, padx=8, pady=3,
                command=self._add_speaker,
            ).pack(side=tk.LEFT)
        else:
            # ── Speaker assignment buttons ────────────────────────────────
            for name in self._all_names:
                btn = tk.Button(
                    self._btn_row, text=name,
                    font=('Arial', 10, 'bold'),
                    bg='#ddeeff', activebackground='#bbddff',
                    relief=tk.RAISED, padx=10, pady=4,
                    state=tk.DISABLED,
                    command=lambda n=name: self._assign(n),
                )
                btn.pack(side=tk.LEFT, padx=(0, 6))
                btn.bind('<Double-Button-1>',
                         lambda e, n=name: self._rename_speaker(n))
                self._name_btns[name] = btn

            # Small "＋" add button after the speaker buttons
            tk.Button(
                self._btn_row,
                text="＋",
                font=('Arial', 10),
                bg='#e8f5e9', activebackground='#c8e6c9',
                relief=tk.FLAT, padx=6, pady=4,
                command=self._add_speaker,
            ).pack(side=tk.LEFT, padx=(4, 0))

        # Re-enable buttons if a paragraph is already loaded
        if self._current_idx is not None and self._all_names:
            self._set_buttons_enabled(True)

        self._bind_number_shortcuts()

    def _add_speaker(self):
        """Prompt for a new speaker name and add it to the panel."""
        name = simpledialog.askstring(
            "Add speaker",
            "Enter the speaker's name:",
            parent=self._dlg,
        )
        if not name or not name.strip():
            return
        name = name.strip()
        if name in self._all_names:
            messagebox.showinfo(
                "Already exists",
                f'"{name}" is already in the speaker list.',
                parent=self._dlg,
            )
            return
        self._all_names.append(name)
        # Ensure the name has a foothold in the database so it survives
        # _discover_real_names on the next panel open.  We write it
        # provisionally to the first entry that doesn't already have a
        # confirmed real-name speaker.
        self._write_name_foothold(name)
        # Also attempt heuristic SPEAKER_X bookmarking if applicable.
        self._name_map = _infer_name_map(self._entries)
        _bookmark_first_entry(self._editor, self._name_map)
        self._rebuild_name_buttons()
        self._update_counts()

    def _write_name_foothold(self, name: str):
        """
        Write 'name' as a provisional assignment to the first entry that
        has no confirmed real-name speaker.  This ensures the name appears
        in _discover_real_names when the panel is next opened, even if the
        user hasn't yet assigned any paragraphs to that speaker.
        """
        for entry in self._entries:
            sp = entry.get('speaker', '').strip()
            # Skip entries already carrying a confirmed real name
            if sp and not _is_heuristic(sp) and sp != name:
                continue
            # Skip entries already carrying THIS name
            if sp == name:
                return   # already has a foothold, nothing to do
            # Write provisional foothold
            entry['speaker']     = name
            entry['provisional'] = True
            try:
                self._editor._save_to_library()
            except Exception:
                pass
            return

    def _rename_speaker(self, old_name: str):
        """Rename a speaker throughout the entries and update the panel."""
        new_name = simpledialog.askstring(
            "Rename speaker",
            f'Rename "{old_name}" to:',
            initialvalue=old_name,
            parent=self._dlg,
        )
        if not new_name or not new_name.strip():
            return
        new_name = new_name.strip()
        if new_name == old_name:
            return
        if new_name in self._all_names:
            messagebox.showinfo(
                "Already exists",
                f'"{new_name}" is already in the speaker list.',
                parent=self._dlg,
            )
            return
        # Update every entry that carries the old name
        for entry in self._entries:
            if entry.get('speaker', '').strip() == old_name:
                entry['speaker'] = new_name
        # Update the name list in place (preserves order)
        idx = self._all_names.index(old_name)
        self._all_names[idx] = new_name
        # Persist immediately
        try:
            self._editor._save_to_library()
        except Exception:
            pass
        # Refresh UI
        if self._last_assigned == old_name:
            self._last_assigned = new_name
        self._rebuild_name_buttons()
        self._update_counts()
        if self._editor:
            try:
                scroll_pos = self._editor.tw.yview()[0]
                self._editor.render(restore_scroll=scroll_pos, lock_scroll=False)
            except Exception:
                pass
        # Update the label in the panel if the current paragraph was affected
        if self._current_idx is not None:
            entry = self._entries[self._current_idx]
            self._lbl_var.set(f"  Current label: {entry.get('speaker', '?')}")

    def _bind_number_shortcuts(self):
        """Bind digit keys 1-9 to speaker assignment buttons."""
        for i in range(1, 10):
            self._dlg.unbind(str(i))
        for i, name in enumerate(self._all_names[:9]):
            self._dlg.bind(str(i + 1), lambda e, n=name: self._assign(n))

    # ------------------------------------------------------------------
    # Paragraph display
    # ------------------------------------------------------------------

    def _set_para_text(self, text: str):
        self._para_text.config(state=tk.NORMAL)
        self._para_text.delete('1.0', tk.END)
        self._para_text.insert(tk.END, text)
        self._para_text.config(state=tk.DISABLED)

    def _set_buttons_enabled(self, enabled: bool):
        state = tk.NORMAL if enabled else tk.DISABLED
        for btn in self._name_btns.values():
            btn.config(state=state)
        self._skip_btn.config(state=state)
        self._who_label.config(text="Who is speaking?" if enabled else "")
        if enabled and self._last_assigned:
            self._same_btn.config(state=tk.NORMAL)
        elif not enabled:
            self._same_btn.config(state=tk.DISABLED)

    def _fmt_ts(self, start: float) -> str:
        s = int(start)
        if s >= 3600:
            return f"[{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}]"
        return f"[{s // 60:02d}:{s % 60:02d}]"

    def _show_entry(self, entry_idx: int):
        if entry_idx is None or entry_idx >= len(self._entries):
            return
        self._current_idx = entry_idx
        entry = self._entries[entry_idx]
        self._ts_var.set(self._fmt_ts(entry.get('start', 0.0)))
        self._lbl_var.set(f"  Current label: {entry.get('speaker', '?')}")
        self._set_para_text(entry.get('text', ''))
        self._set_buttons_enabled(bool(self._all_names))

    def _on_paragraph_clicked(self, entry_idx: int):
        """Called by the editor when the user clicks any paragraph.
        Always refreshes _entries first in case a split or merge replaced the list.
        """
        self._entries = self._editor._entries
        self._show_entry(entry_idx)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------------

    def _assign(self, name: str):
        self._entries = self._editor._entries   # refresh in case split/merge replaced list
        if self._current_idx is None:
            return
        self._entries[self._current_idx]['speaker']     = name
        self._entries[self._current_idx]['provisional'] = False
        self._last_assigned = name
        self._same_btn.config(state=tk.NORMAL)
        self._update_counts()
        # Update only the header label in the transcript — no full re-render,
        # no scroll, no widget-state change.
        if self._editor is not None:
            try:
                self._editor.update_entry_speaker_display(self._current_idx)
            except Exception:
                pass
        # Persist immediately so assignments survive if the app closes before
        # the user clicks "Finish & save".
        if self._editor is not None:
            try:
                self._editor._save_to_library()
            except Exception:
                pass
        # Stay on this paragraph — user moves manually by clicking.
        self._lbl_var.set(f"  Current label: {name}")

    def _assign_same(self):
        if self._last_assigned:
            self._assign(self._last_assigned)

    def _skip(self):
        """Move to the next paragraph without assigning."""
        if self._current_idx is None:
            return
        nxt = self._current_idx + 1
        if nxt < len(self._entries):
            self._show_entry(nxt)
        else:
            self._current_idx = None
            self._ts_var.set("")
            self._lbl_var.set("")
            self._set_para_text(
                "End of transcript reached.\n"
                "Click any paragraph to review or correct it."
            )
            self._set_buttons_enabled(False)

    # ------------------------------------------------------------------
    # Identify all
    # ------------------------------------------------------------------

    def _identify_all(self):
        if not self._all_names:
            messagebox.showinfo(
                "No speakers defined",
                "Add at least one speaker name first.",
                parent=self._dlg,
            )
            return
        self._name_map = _infer_name_map(self._entries)
        count = 0
        for entry in self._entries:
            sp = entry.get('speaker', '').strip()
            if _is_heuristic(sp) and sp in self._name_map:
                real = self._name_map[sp]
                if not _is_heuristic(real):
                    entry['speaker']     = real
                    entry['provisional'] = False
                    count += 1
        self._update_counts()
        if self._tw:
            self._tw.yview_moveto(0)
        if self._editor:
            try:
                self._editor.render(None)
            except Exception:
                pass
        self._current_idx = None
        self._ts_var.set("")
        self._lbl_var.set("")
        self._set_para_text(
            f"{count} paragraph{'s' if count != 1 else ''} assigned.\n"
            "Review the transcript from the top.\n"
            "Click any paragraph to correct it."
        )
        self._set_buttons_enabled(False)

    # ------------------------------------------------------------------
    # Counts / status
    # ------------------------------------------------------------------

    def _update_counts(self):
        self._entries = self._editor._entries   # always count from the live list
        counter    = Counter()
        unresolved = 0
        for e in self._entries:
            sp = e.get('speaker', '').strip()
            if not sp or _is_heuristic(sp):
                unresolved += 1
            else:
                counter[sp] += 1

        total = len(self._entries)
        self._unresolved_var.set(
            f"{unresolved} of {total} "
            f"paragraph{'s' if total != 1 else ''} unresolved"
        )

        # Enable "Identify all" when inference is possible and speakers exist
        self._name_map = _infer_name_map(self._entries)
        can_identify = bool(self._name_map) and bool(self._all_names)
        self._identify_all_btn.config(
            state=tk.NORMAL if can_identify else tk.DISABLED
        )

        # Rebuild per-speaker count row
        for w in self._status_frame.winfo_children():
            w.destroy()
        for name, cnt in sorted(counter.items()):
            ttk.Label(self._status_frame,
                      text=f"{name}: {cnt}",
                      font=('Arial', 9),
                      foreground='#333333').pack(side=tk.LEFT, padx=(0, 12))
        if unresolved:
            ttk.Label(self._status_frame,
                      text=f"Unresolved: {unresolved}",
                      font=('Arial', 9),
                      foreground='#cc4400').pack(side=tk.LEFT)

    # ------------------------------------------------------------------
    # Finish / Pause / Resume
    # ------------------------------------------------------------------

    def _finish(self):
        if self._editor:
            self._editor.paragraph_click_callback = None
        if self._player:
            try:
                self._player.stop()
            except Exception:
                pass
        if self._editor:
            try:
                self._editor._save_to_library()
                _scroll = self._editor.tw.yview()[0] if self._tw else None
                self._editor.render(restore_scroll=_scroll)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).error(
                    f"Speaker ID save error: {exc}")
        if self._on_complete:
            try:
                self._on_complete()
            except Exception:
                pass

        # Build summary for the closing message
        counter    = Counter()
        unresolved = 0
        for e in self._entries:
            sp = e.get('speaker', '').strip()
            if not sp or _is_heuristic(sp):
                unresolved += 1
            else:
                counter[sp] += 1
        parts = [f"{name}: {cnt} paragraph{'s' if cnt != 1 else ''}"
                 for name, cnt in sorted(counter.items())]
        if unresolved:
            parts.append(f"Unresolved: {unresolved}")

        self._dlg.destroy()
        messagebox.showinfo(
            "Speaker identification complete",
            "\n".join(parts) if parts else "No changes made.",
            parent=self._parent,
        )

    def _on_finish(self):
        self._finish()

    def _toggle_pause(self):
        if self._paused:
            self._resume()
        else:
            self._pause()

    def _pause(self):
        """Deregister click callback so the transcript is free to edit."""
        self._paused = True
        self._editor.paragraph_click_callback = None
        self._pause_btn.config(text="▶ Resume")
        self._pause_lbl.config(
            text="Paused — edit the transcript freely, then Resume."
        )
        self._set_buttons_enabled(False)
        if self._player:
            try:
                self._player.stop()
            except Exception:
                pass

    def _resume(self):
        """Re-register click callback to continue identification."""
        self._paused = False
        self._editor.paragraph_click_callback = self._on_paragraph_clicked
        self._pause_btn.config(text="⏸ Pause")
        self._pause_lbl.config(text="")
        if self._current_idx is not None and self._all_names:
            self._set_buttons_enabled(True)
        # Refresh entries reference in case edits changed content
        self._entries = self._editor._entries
        self._update_counts()


# ============================================================================
# Public entry point
# ============================================================================

def start_speaker_identification(
    parent:      tk.Misc,
    editor,
    player=None,
    text_widget: tk.Text = None,
    on_complete: Optional[Callable] = None,
):
    """
    Open the unified speaker identification panel.
    Called by ThreadViewerWindow._start_speaker_identification().
    """
    if editor is None:
        messagebox.showinfo(
            "Identify speakers",
            "The transcript editor is not available.",
            parent=parent,
        )
        return

    if not editor._entries:
        messagebox.showinfo(
            "Identify speakers",
            "No transcript content found.",
            parent=parent,
        )
        return

    SpeakerPanel(
        parent=parent,
        editor=editor,
        player=player,
        text_widget=text_widget,
        on_complete=on_complete,
    )
