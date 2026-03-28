"""
speaker_id_dialog.py
====================
Two-phase speaker identification workflow for DocAnalyser audio transcripts.

Phase 1 — SpeakerNameDialog  (modal)
    Asks the user to name each speaker found in the transcript.
    Fields are labelled "Speaker 1", "Speaker 2" etc. (not SPEAKER_A/B).
    Pre-fills names inferred from previous sessions.
    Offers "+ Add speaker" for recordings with more speakers than labels found.

Phase 2 — SpeakerIdentifyPanel  (non-modal, persistent)
    A floating panel alongside the transcript.
    The user drives identification by clicking paragraphs — the panel
    responds to each click, not the other way round.
    After assigning a name, focus drops automatically to the next paragraph
    (or next unresolved paragraph — toggled by a radio button in the panel).
    "Identify all" bulk-assigns all still-SPEAKER_X entries using the Phase 1
    mapping, scrolls the transcript to the top, and shows a per-speaker count.
    The user can click any paragraph at any time to review or correct it.

Rendering note:
    transcript_paragraph_editor.py renders heuristic (provisional) labels
    in muted grey italic and confirmed names in normal weight/colour.

Entry point:
    start_speaker_identification(parent, editor, player, text_widget, on_complete)
"""
from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk, messagebox
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
    """Return ordered unique confirmed real names already in entries."""
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


# ============================================================================
# Phase 1 — Name the speakers
# ============================================================================

class SpeakerNameDialog:
    """
    Modal dialog: collects a real name for each speaker found in the transcript.

    Fields are labelled "Speaker 1", "Speaker 2" etc. — not SPEAKER_A/B —
    so the user is naming roles, not confirming machine labels.

    After parent.wait_window() returns, inspect .result:
        None                             — user cancelled
        (name_map, all_names, autoplay)
            name_map:  {"SPEAKER_A": "Chris", "SPEAKER_B": "Tony", ...}
            all_names: ["Chris", "Tony", ...]  (all names including extras)
            autoplay:  bool
    """

    def __init__(self, parent: tk.Misc, heuristic_speakers: List[str],
                 existing_names: List[str], prefilled: Dict[str, str] = None):
        self.result: Optional[tuple] = None
        self._speakers  = heuristic_speakers
        self._existing  = existing_names
        self._prefilled = prefilled or {}
        self._rows: List[tuple] = []
        self._build(parent)

    def _build(self, parent: tk.Misc):
        dlg = tk.Toplevel(parent)
        dlg.title("Name the speakers")
        dlg.resizable(False, False)
        dlg.transient(parent)
        dlg.grab_set()

        n = len(self._speakers)
        if self._existing:
            intro = (
                f"{n} speaker label{'s' if n != 1 else ''} still need a name.\n"
                "Choose from the existing names or type a new one:"
            )
        else:
            intro = (
                "Who are the speakers in this recording?\n"
                "Enter a name for each speaker found:"
            )
        ttk.Label(dlg, text=intro, wraplength=360, justify=tk.LEFT,
                  padding=(12, 12, 12, 6)).pack(fill=tk.X)

        self._grid = ttk.Frame(dlg, padding=(12, 0, 12, 6))
        self._grid.pack(fill=tk.X)

        for i, sp in enumerate(self._speakers):
            self._add_row(self._prefilled.get(sp, ''), focus=(i == 0))

        ttk.Button(dlg, text="+ Add speaker",
                   command=lambda: self._add_row('')).pack(
            anchor='w', padx=12, pady=(0, 4))

        ttk.Separator(dlg, orient='horizontal').pack(
            fill=tk.X, padx=12, pady=(4, 0))

        opt = ttk.Frame(dlg, padding=(12, 6, 12, 6))
        opt.pack(fill=tk.X)
        self._autoplay_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt,
                        text="Auto-play audio when I click a paragraph",
                        variable=self._autoplay_var).pack(anchor='w')

        btn_row = ttk.Frame(dlg, padding=(12, 4, 12, 12))
        btn_row.pack(fill=tk.X)
        ttk.Button(btn_row, text="Cancel",
                   command=dlg.destroy).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(btn_row, text="Start ->",
                   command=self._confirm).pack(side=tk.RIGHT)

        dlg.bind('<Return>', lambda e: self._confirm())
        dlg.bind('<Escape>', lambda e: dlg.destroy())

        dlg.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - dlg.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - dlg.winfo_height()) // 3
        dlg.geometry(f"+{max(0, px)}+{max(0, py)}")

        self._dlg = dlg
        parent.wait_window(dlg)

    def _add_row(self, prefill: str = '', focus: bool = False):
        i   = len(self._rows)
        var = tk.StringVar(value=prefill)
        ttk.Label(self._grid, text=f"Speaker {i + 1}:",
                  anchor='e', width=12).grid(
            row=i, column=0, padx=(0, 8), pady=4, sticky='e')
        if self._existing:
            w = ttk.Combobox(self._grid, textvariable=var,
                             values=self._existing, width=20)
        else:
            w = ttk.Entry(self._grid, textvariable=var, width=22)
        w.grid(row=i, column=1, pady=4, sticky='w')
        self._rows.append((var, w))
        if focus:
            w.focus_set()

    def _confirm(self):
        names = [v.get().strip() for v, _ in self._rows if v.get().strip()]
        if not names:
            messagebox.showwarning("No names",
                                   "Please enter at least one speaker name.",
                                   parent=self._dlg)
            return
        name_map: Dict[str, str] = {}
        for i, sp in enumerate(self._speakers):
            name_map[sp] = names[i] if i < len(names) else sp
        self.result = (name_map, names, self._autoplay_var.get())
        self._dlg.destroy()


# ============================================================================
# Phase 2 — Click-driven identification panel
# ============================================================================

class SpeakerIdentifyPanel:
    """
    Non-modal floating panel for click-driven speaker identification.

    The user clicks any paragraph in the transcript; the editor fires
    paragraph_click_callback -> _on_paragraph_clicked, which loads that
    paragraph into the panel, highlights it, and plays the audio.

    After the user clicks a speaker button the panel either moves to the
    next paragraph or next unresolved paragraph (toggle), and focus
    (transcript highlight + audio) follows automatically.
    """

    HIGHLIGHT_TAG = "spkid_current"

    def __init__(
        self,
        parent:      tk.Misc,
        editor,
        name_map:    Dict[str, str],
        all_names:   List[str],
        autoplay:    bool,
        player=None,
        text_widget: tk.Text = None,
        on_complete: Optional[Callable] = None,
    ):
        self._parent      = parent
        self._editor      = editor
        self._entries     = editor._entries
        self._name_map    = name_map
        self._all_names   = all_names
        self._player      = player
        self._tw          = text_widget
        self._on_complete = on_complete

        self._current_idx: Optional[int] = None
        self._last_assigned: Optional[str] = None

        self._editor.paragraph_click_callback = self._on_paragraph_clicked

        self._build_ui(parent, autoplay)
        self._update_counts()

        if self._tw:
            self._tw.tag_configure(self.HIGHLIGHT_TAG, background='#fff9c4')

        # Note: intentionally NOT scrolling to top here so the user
        # stays at their current position in the transcript when the
        # panel opens mid-session.

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, parent: tk.Misc, autoplay: bool):
        dlg = tk.Toplevel(parent)
        dlg.title("Identify speakers")
        dlg.resizable(True, False)
        dlg.transient(parent)
        dlg.protocol("WM_DELETE_WINDOW", self._on_finish)

        # Top: unresolved count + auto-play
        top = ttk.Frame(dlg, padding=(10, 8, 10, 4))
        top.pack(fill=tk.X)
        self._unresolved_var = tk.StringVar()
        ttk.Label(top, textvariable=self._unresolved_var,
                  font=('Arial', 9, 'bold')).pack(side=tk.LEFT)
        self._autoplay_var = tk.BooleanVar(value=autoplay)
        ttk.Checkbutton(top, text="Auto-play",
                        variable=self._autoplay_var).pack(side=tk.RIGHT)

        ttk.Separator(dlg, orient='horizontal').pack(fill=tk.X, padx=10)

        # Paragraph info: timestamp + current label
        info = ttk.Frame(dlg, padding=(10, 4, 10, 0))
        info.pack(fill=tk.X)
        self._ts_var  = tk.StringVar(value="")
        self._lbl_var = tk.StringVar(value="")
        ttk.Label(info, textvariable=self._ts_var,
                  font=('Consolas', 9), foreground='#666666').pack(side=tk.LEFT)
        ttk.Label(info, textvariable=self._lbl_var,
                  font=('Arial', 9, 'italic'),
                  foreground='#555555').pack(side=tk.LEFT, padx=(8, 0))

        # Paragraph text display
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

        # Speaker buttons
        self._who_label = ttk.Label(dlg, text="",
                                    font=('Arial', 9), padding=(10, 2, 10, 2))
        self._who_label.pack(anchor='w')

        btn_row = ttk.Frame(dlg, padding=(10, 0, 10, 8))
        btn_row.pack(fill=tk.X)
        self._name_btns: List[tk.Button] = []
        for name in self._all_names:
            btn = tk.Button(
                btn_row, text=name,
                font=('Arial', 10, 'bold'),
                bg='#ddeeff', activebackground='#bbddff',
                relief=tk.RAISED, padx=10, pady=4,
                state=tk.DISABLED,
                command=lambda n=name: self._assign(n),
            )
            btn.pack(side=tk.LEFT, padx=(0, 6))
            self._name_btns.append(btn)

        self._same_btn = ttk.Button(btn_row, text="Same \u2191",
                                    command=self._assign_same,
                                    state=tk.DISABLED)
        self._same_btn.pack(side=tk.LEFT, padx=(6, 6))

        self._skip_btn = ttk.Button(btn_row, text="Skip",
                                    command=self._skip,
                                    state=tk.DISABLED)
        self._skip_btn.pack(side=tk.LEFT)

        ttk.Separator(dlg, orient='horizontal').pack(
            fill=tk.X, padx=10, pady=(0, 0))

        # Identify all
        id_frame = ttk.Frame(dlg, padding=(10, 6, 10, 4))
        id_frame.pack(fill=tk.X)
        ttk.Button(id_frame, text="Identify all",
                   command=self._identify_all).pack(side=tk.LEFT, anchor='n')
        ttk.Label(id_frame,
                  text="  Assigns all unresolved paragraphs using\n"
                       "  the heuristic labels. Use this if the\n"
                       "  SPEAKER_A / B assignments look mostly\n"
                       "  correct in the transcript.",
                  font=('Arial', 8), foreground='#666666',
                  justify=tk.LEFT).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Separator(dlg, orient='horizontal').pack(
            fill=tk.X, padx=10, pady=(4, 0))

        # Navigation mode
        nav = ttk.Frame(dlg, padding=(10, 4, 10, 4))
        nav.pack(fill=tk.X)
        ttk.Label(nav, text="After assigning, move to:",
                  font=('Arial', 9)).pack(side=tk.LEFT)
        self._nav_var = tk.StringVar(value="next")
        ttk.Radiobutton(nav, text="Next paragraph",
                        variable=self._nav_var,
                        value="next").pack(side=tk.LEFT, padx=(8, 4))
        ttk.Radiobutton(nav, text="Next unresolved",
                        variable=self._nav_var,
                        value="unresolved").pack(side=tk.LEFT)

        ttk.Separator(dlg, orient='horizontal').pack(
            fill=tk.X, padx=10, pady=(4, 0))

        # Status report
        self._status_frame = ttk.Frame(dlg, padding=(10, 4, 10, 4))
        self._status_frame.pack(fill=tk.X)

        # Finish & save
        bot = ttk.Frame(dlg, padding=(10, 2, 10, 10))
        bot.pack(fill=tk.X)
        ttk.Button(bot, text="Finish & save",
                   command=self._on_finish).pack(side=tk.RIGHT)
        self._paused = False
        self._pause_btn = ttk.Button(bot, text="⏸ Pause",
                                     command=self._toggle_pause)
        self._pause_btn.pack(side=tk.RIGHT, padx=(0, 8))
        self._pause_lbl = ttk.Label(bot, text="",
                                    font=('Arial', 8), foreground='#cc6600')
        self._pause_lbl.pack(side=tk.LEFT)

        # Keyboard shortcuts
        for i, name in enumerate(self._all_names):
            dlg.bind(str(i + 1), lambda e, n=name: self._assign(n))
        dlg.bind('<space>',  lambda e: self._assign_same() or 'break')
        dlg.bind('s',        lambda e: self._skip())
        dlg.bind('<Escape>', lambda e: self._on_finish())

        dlg.update_idletasks()
        px = (parent.winfo_rootx()
              + parent.winfo_width()
              - dlg.winfo_width() - 20)
        py = parent.winfo_rooty() + 60
        dlg.geometry(f"430x{dlg.winfo_reqheight()}+{max(0, px)}+{max(0, py)}")

        self._dlg = dlg

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_para_text(self, text: str):
        self._para_text.config(state=tk.NORMAL)
        self._para_text.delete('1.0', tk.END)
        self._para_text.insert(tk.END, text)
        self._para_text.config(state=tk.DISABLED)

    def _set_buttons_enabled(self, enabled: bool):
        state = tk.NORMAL if enabled else tk.DISABLED
        for btn in self._name_btns:
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

    def _scroll_to_top(self):
        if self._tw:
            self._tw.yview_moveto(0)
            self._tw.see('1.0')

    def _highlight_entry(self, entry_idx: int):
        if not self._tw or not self._editor:
            return
        self._tw.tag_remove(self.HIGHLIGHT_TAG, '1.0', tk.END)
        seg_map = getattr(self._editor, '_segment_map', [])
        segs = [n for n, (eidx, _, _) in enumerate(seg_map) if eidx == entry_idx]
        if not segs:
            return
        first = self._tw.tag_ranges(f"seg_{segs[0]}")
        last  = self._tw.tag_ranges(f"seg_{segs[-1]}")
        if not first or not last:
            return
        self._tw.tag_add(self.HIGHLIGHT_TAG, first[0], last[1])
        self._tw.tag_raise(self.HIGHLIGHT_TAG)
        self._tw.see(first[0])

    # ------------------------------------------------------------------
    # Core: load a paragraph into the panel
    # ------------------------------------------------------------------

    def _show_entry(self, entry_idx: int):
        """Load entry into panel, highlight it, play audio."""
        if entry_idx is None or entry_idx >= len(self._entries):
            return
        self._current_idx = entry_idx
        entry = self._entries[entry_idx]

        self._ts_var.set(self._fmt_ts(entry.get('start', 0.0)))
        self._lbl_var.set(f"  Current label: {entry.get('speaker', '?')}")
        self._set_para_text(entry.get('text', ''))
        self._set_buttons_enabled(True)
        self._highlight_entry(entry_idx)

        if self._autoplay_var.get() and self._player:
            try:
                self._player.play(from_position=entry.get('start', 0.0))
            except Exception:
                pass

    def _on_paragraph_clicked(self, entry_idx: int):
        """Called by editor when the user clicks any paragraph."""
        self._show_entry(entry_idx)

    # ------------------------------------------------------------------
    # Navigation after assignment
    # ------------------------------------------------------------------

    def _next_idx(self) -> Optional[int]:
        if self._current_idx is None:
            return None
        n = len(self._entries)
        if self._nav_var.get() == "next":
            nxt = self._current_idx + 1
            return nxt if nxt < n else None
        else:
            for i in range(self._current_idx + 1, n):
                if _is_heuristic(self._entries[i].get('speaker', '').strip()):
                    return i
            return None

    def _advance(self):
        nxt = self._next_idx()
        if nxt is not None:
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
            if self._tw:
                self._tw.tag_remove(self.HIGHLIGHT_TAG, '1.0', tk.END)

    # ------------------------------------------------------------------
    # Assignment actions
    # ------------------------------------------------------------------

    def _assign(self, name: str):
        if self._current_idx is None:
            return
        self._entries[self._current_idx]['speaker']     = name
        self._entries[self._current_idx]['provisional'] = False
        self._last_assigned = name
        self._same_btn.config(state=tk.NORMAL)
        self._update_counts()
        # Re-render the transcript immediately so the updated speaker
        # label is visible on screen without needing to press Save.
        if self._editor is not None:
            try:
                self._editor.render()
            except Exception:
                pass
        # Brief pause so the user can see the updated label before
        # the panel advances to the next paragraph.
        self._dlg.after(500, self._advance)

    def _assign_same(self):
        if self._last_assigned:
            self._assign(self._last_assigned)

    def _skip(self):
        if self._current_idx is None:
            return
        self._advance()

    # ------------------------------------------------------------------
    # Identify all
    # ------------------------------------------------------------------

    def _identify_all(self):
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
        self._scroll_to_top()

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
        if self._tw:
            self._tw.tag_remove(self.HIGHLIGHT_TAG, '1.0', tk.END)

    # ------------------------------------------------------------------
    # Status / counts
    # ------------------------------------------------------------------

    def _update_counts(self):
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
            f"{unresolved} of {total} paragraph{'s' if total != 1 else ''} unresolved"
        )

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
    # Finish
    # ------------------------------------------------------------------

    def _finish(self):
        if self._editor:
            self._editor.paragraph_click_callback = None

        if self._player:
            try:
                self._player.stop()
            except Exception:
                pass

        if self._tw:
            self._tw.tag_remove(self.HIGHLIGHT_TAG, '1.0', tk.END)

        if self._editor:
            try:
                self._editor._save_to_library()
                # Preserve scroll position so closing the panel leaves the
                # viewport at the last paragraph worked on, not at the top.
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

    # ------------------------------------------------------------------
    # Pause / Resume
    # ------------------------------------------------------------------

    def _toggle_pause(self):
        if self._paused:
            self._resume()
        else:
            self._pause()

    def _pause(self):
        """Deregister click callback so the transcript responds to edits."""
        self._paused = True
        self._editor.paragraph_click_callback = None
        self._pause_btn.config(text="▶ Resume")
        self._pause_lbl.config(
            text="Paused — edit the transcript, then click Resume."
        )
        self._set_buttons_enabled(False)
        # Stop audio so it doesn't play while editing
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
        # Re-enable buttons only if a paragraph is loaded
        if self._current_idx is not None:
            self._set_buttons_enabled(True)
        # Also refresh entries reference in case edits changed them
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
    Launch the two-phase speaker identification workflow.
    Called by ThreadViewerWindow._start_speaker_identification().
    """
    if editor is None:
        messagebox.showinfo(
            "Identify speakers",
            "The transcript editor is not available.",
            parent=parent,
        )
        return

    heuristic_speakers = _discover_heuristic_speakers(editor._entries)
    existing_names     = _discover_real_names(editor._entries)

    if not heuristic_speakers and not existing_names:
        messagebox.showinfo(
            "Identify speakers",
            "No speaker labels found in this transcript.",
            parent=parent,
        )
        return

    inferred     = _infer_name_map(editor._entries)
    all_inferred = (heuristic_speakers and
                    all(sp in inferred for sp in heuristic_speakers))

    if all_inferred and existing_names:
        name_map  = inferred
        all_names = existing_names
        autoplay  = True
    else:
        phase1 = SpeakerNameDialog(
            parent, heuristic_speakers, existing_names,
            prefilled=inferred,
        )
        if phase1.result is None:
            return
        name_map, all_names, autoplay = phase1.result

    if not heuristic_speakers:
        messagebox.showinfo(
            "Identify speakers",
            "No unresolved speaker labels remain.\n\n"
            "The identification panel will open so you can review "
            "or correct any assignments.",
            parent=parent,
        )

    SpeakerIdentifyPanel(
        parent=parent,
        editor=editor,
        name_map=name_map,
        all_names=all_names,
        autoplay=autoplay,
        player=player,
        text_widget=text_widget,
        on_complete=on_complete,
    )
