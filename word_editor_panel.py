"""
word_editor_panel.py
=====================
Unified Word-based transcript editing panel for DocAnalyser.

One always-on-top window that combines:

  AUDIO PLAYER (top section)
    * Loads the source audio file (ffmpeg -> MP3 cache, played via pygame)
    * Play / Pause, +/-10s, +/-30s skip, draggable scrub slider
    * "Jump to" field: type  4:23  or  1:04:23  then Enter / Go
    * Double-click any paragraph row -> seeks audio AND moves the Word
      cursor to that paragraph so the user can edit immediately

  SPEAKER ASSIGNMENT (bottom section)
    * Paragraph list mirrors the transcript; panel follows Word cursor
      via COM polling every 500 ms
    * Enter real names for SPEAKER_X labels, then bulk-apply to the doc
    * Per-paragraph "Assign to" buttons update Word inline using the
      [MM:SS] timestamp as an anchor (no cursor-position dependency)
    * Prev / Next unresolved navigation
    * Refresh button re-scans the live Word document so split paragraphs
      appear in the panel immediately (no save/reload needed)
    * "Save edits to DocAnalyser" reads the edited .docx back and syncs
      the library so Thread Viewer and AI prompts see the latest version

SENTENCE-LEVEL TIMESTAMPS & PARAGRAPH SPLITTING
    When the transcript is exported each sentence is prefixed with a tiny
    (7pt, light-grey) {MM:SS} marker inside the paragraph body.  These
    markers are visually unobtrusive but carry full timing information.

    If the user splits a paragraph in Word by pressing Enter, the second
    half of the paragraph will already start with the correct sentence
    timestamp in the form {MM:SS}.  Click "Refresh" in the Speaker Panel
    to pick up the split immediately.  "Save edits to DocAnalyser" also
    handles these split paragraphs and creates new entries with the correct
    timestamps, inheriting the speaker from the preceding paragraph.

COM requirement: pywin32 (already a project dependency).
pygame requirement: optional.  If not installed, audio section is disabled.

Author: DocAnalyser Development Team
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from typing import List, Dict, Optional, Callable

logger = logging.getLogger(__name__)

# -- COM (pywin32) -------------------------------------------------------------
try:
    import win32com.client as _com
    COM_AVAILABLE = True
except ImportError:
    _com          = None        # type: ignore[assignment]
    COM_AVAILABLE = False

# -- Audio engine (pygame) -----------------------------------------------------
try:
    import pygame
    pygame.mixer.init()
    PYGAME_OK = True
except Exception:
    pygame    = None            # type: ignore[assignment]
    PYGAME_OK = False

# -- Colour palette ------------------------------------------------------------
BG           = "#2b2b2b"
BG_ALT       = "#303030"
BG_LIST      = "#1e1e1e"
BG_CURRENT   = "#4a4a1a"
FG           = "#e8e8e8"
FG_DIM       = "#888888"
FG_RESOLVED  = "#66cc66"
FG_UNRES     = "#cccccc"
ACCENT       = "#4a9eff"
BTN_BG       = "#3c3c3c"
BTN_ACTIVE   = "#505050"
SAVE_BG      = "#2d5a27"
SAVE_ACTIVE  = "#3a7533"

FONT_BODY    = ("Segoe UI", 9)
FONT_SMALL   = ("Segoe UI", 8)
FONT_BOLD    = ("Segoe UI", 9, "bold")
FONT_MONO    = ("Consolas", 9)
FONT_TIME_LG = ("Consolas", 16, "bold")
FONT_JUMP    = ("Consolas", 10)


# -- Shared helpers ------------------------------------------------------------

def _fmt_time(seconds: float) -> str:
    s = max(0, int(round(seconds)))
    if s >= 3600:
        return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"
    return f"{s // 60:02d}:{s % 60:02d}"


def _parse_ts(ts: str) -> float:
    try:
        parts = [int(p) for p in ts.split(":")]
        if len(parts) == 2:
            return float(parts[0] * 60 + parts[1])
        if len(parts) == 3:
            return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    except (ValueError, AttributeError):
        pass
    return 0.0


def _parse_jump(text: str) -> Optional[float]:
    text = text.strip()
    if not text:
        return None
    if ":" in text:
        return _parse_ts(text)
    try:
        return float(text)
    except ValueError:
        return None


def _run_ffmpeg(cmd: list):
    kwargs: dict = {"check": True, "capture_output": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.run(cmd, **kwargs)


# -- Regex patterns ------------------------------------------------------------

_HEURISTIC_RE = re.compile(r'^SPEAKER_[A-Z0-9]+$')

_PARA_RE = re.compile(
    r'^\[(\d+:\d{2}(?::\d{2})?)\]\s+\[([^\]]*)\]:\s*(.*)',
    re.DOTALL,
)

_SENT_TS_RE = re.compile(r'\{(\d+:\d{2}(?::\d{2})?)\}')

_SPLIT_RE = re.compile(r'^\{(\d+:\d{2}(?::\d{2})?)\}\s*(.*)', re.DOTALL)

# Regex used by Hide/Show TS to find all timestamp markers in paragraph text
_TS_MARKER_RE = re.compile(r'[\[{]\d+:\d{2}(?::\d{2})?[\]}]')

# Detects an embedded paragraph header ([MM:SS] [Speaker]: ) inside a body text,
# i.e. one that was the start of a paragraph that has since been merged upward.
_EMBEDDED_HDR_RE = re.compile(
    r'\[(\d+:\d{2}(?::\d{2})?)\][\s\u00a0]+\[([^\]]+)\]:[\s\u00a0]*'
)


def _is_heuristic(speaker: str) -> bool:
    return bool(_HEURISTIC_RE.match(str(speaker or "")))


def _is_resolved(entry: Dict) -> bool:
    spk = entry.get("speaker", "")
    return bool(spk) and not _is_heuristic(spk) and not entry.get("provisional")


# =============================================================================
# Main panel class
# =============================================================================

class WordEditorPanel:
    """Unified speaker-assignment + audio-player panel for Word-based editing."""

    _POLL_MS = 500

    def __init__(
        self,
        parent:           tk.Widget,
        doc_id:           str,
        entries:          List[Dict],
        audio_path:       Optional[str],
        docx_path:        str,
        config:           dict,
        on_save_callback: Optional[Callable] = None,
    ):
        self._parent         = parent
        self._doc_id         = doc_id
        self._entries        = [dict(e) for e in entries]
        self._audio_path     = audio_path
        self._docx_path      = docx_path
        self._config         = config
        self._on_save_cb     = on_save_callback

        self._current_idx    : Optional[int] = None
        self._poll_job       : Optional[str] = None
        self._last_para_text : str           = ""
        self._name_vars      : Dict[str, tk.StringVar] = {}
        self._word_positioned: bool          = False
        self._highlighted_ts : Optional[str] = None

        self._mp3_path        : Optional[str] = None
        self._duration        : float         = 0.0
        self._playing         : bool          = False
        self._position        : float         = 0.0
        self._play_start_wall : float         = 0.0
        self._play_start_pos  : float         = 0.0
        self._slider_dragging : bool          = False
        self._audio_loading   : bool          = False

        self._build_window()
        self._populate_list()
        self._poll_audio()

        if COM_AVAILABLE:
            self._start_poll()

        if audio_path and os.path.isfile(audio_path):
            self.win.after(200, lambda: self._load_audio(audio_path))

        # Pre-fill speaker names from saved metadata
        self.win.after(100, self._load_speaker_names)

    # =========================================================================
    # Window construction
    # =========================================================================

    def _build_window(self):
        self.win = tk.Toplevel(self._parent)
        self.win.title("DocAnalyser \u2014 Speaker Panel")
        self.win.configure(bg=BG)
        self.win.resizable(True, True)

        # ── Screen dimensions ──────────────────────────────────────────────
        # Use the parent window (already realized) to get reliable screen dims.
        # This avoids DPI-scaling issues that can affect a brand-new Toplevel.
        self._parent.update_idletasks()
        sw = self._parent.winfo_screenwidth()
        sh = self._parent.winfo_screenheight()
        pw = 430
        ph = min(860, sh - 40)
        px = sw - pw - 4
        py = 2
        panel_geom = f"{pw}x{ph}+{px}+{py}"

        # Apply geometry immediately, then again after 200 ms.
        # The second call overrides any OS "smart placement" that might have
        # moved the window after the first call.
        self.win.geometry(panel_geom)
        self.win.minsize(380, 600)
        self.win.attributes("-topmost", True)
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        self.win.after(200, lambda: self.win.geometry(panel_geom))

        # ── Reposition Word to the left half ──────────────────────────────
        word_w = sw - pw - 12
        _word_attempts = [0]
        def _position_word():
            _word_attempts[0] += 1
            try:
                import win32gui, win32con
                hwnd = win32gui.FindWindow("OpusApp", None)  # Word's window class
                if hwnd:
                    rect = win32gui.GetWindowRect(hwnd)
                    cur_x = rect[0]
                    cur_w = rect[2] - rect[0]
                    if cur_x != 0 or abs(cur_w - word_w) > 20:
                        win32gui.ShowWindow(hwnd, 9)   # SW_RESTORE (un-maximise)
                        win32gui.SetWindowPos(
                            hwnd, None,
                            0, 0, word_w, sh,
                            win32con.SWP_NOZORDER | win32con.SWP_SHOWWINDOW,
                        )
                    self._word_positioned = True
            except Exception as e:
                logger.debug(f"win32gui word position: {e}")
            if _word_attempts[0] < 24:
                self.win.after(500, _position_word)
        self._position_word_fn = _position_word
        if COM_AVAILABLE:
            self.win.after(500, _position_word)

        # -- Header ------------------------------------------------------------
        hdr = tk.Frame(self.win, bg=BG)
        hdr.pack(fill=tk.X, padx=10, pady=(8, 0))

        tk.Label(
            hdr, text="Speaker Panel",
            bg=BG, fg=FG, font=("Segoe UI", 11, "bold"),
        ).pack(side=tk.LEFT)

        self._badge_var = tk.StringVar(
            value="\u25cf Word linked" if COM_AVAILABLE else "\u25cb Word not linked"
        )
        tk.Label(
            hdr, textvariable=self._badge_var,
            bg=BG,
            fg="#66cc66" if COM_AVAILABLE else FG_DIM,
            font=FONT_SMALL,
        ).pack(side=tk.RIGHT)

        tk.Label(
            self.win, text=os.path.basename(self._docx_path),
            bg=BG, fg=FG_DIM, font=FONT_SMALL, anchor="w", wraplength=380,
        ).pack(fill=tk.X, padx=10, pady=(2, 0))

        self._summary_var = tk.StringVar()
        tk.Label(
            self.win, textvariable=self._summary_var,
            bg=BG, fg=FG_DIM, font=FONT_SMALL, anchor="w",
        ).pack(fill=tk.X, padx=10)
        self._refresh_summary()

        self._build_audio_section()
        self._build_names_section()

        self._btn_outer = tk.Frame(self.win, bg=BG)
        self._btn_outer.pack(fill=tk.X, padx=10, pady=(4, 2))
        self._build_assign_buttons()

        # -- Paragraph list ----------------------------------------------------
        list_frame = tk.Frame(self.win, bg=BG)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(2, 0))

        tk.Label(
            list_frame,
            text="Paragraphs  (double-click to play & navigate)",
            bg=BG, fg=FG_DIM, font=FONT_SMALL, anchor="w",
        ).pack(fill=tk.X)

        lb_frame = tk.Frame(list_frame, bg=BG)
        lb_frame.pack(fill=tk.BOTH, expand=True, pady=(2, 0))

        sb = ttk.Scrollbar(lb_frame, orient=tk.VERTICAL)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        self._listbox = tk.Listbox(
            lb_frame, yscrollcommand=sb.set,
            bg=BG_LIST, fg=FG_UNRES,
            selectbackground=BG_CURRENT, selectforeground="#ffffff",
            activestyle="none", font=FONT_MONO, bd=0,
            highlightthickness=0, relief=tk.FLAT,
        )
        self._listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.config(command=self._listbox.yview)
        self._listbox.bind("<<ListboxSelect>>", self._on_list_click)
        self._listbox.bind("<Double-Button-1>",  self._on_list_double_click)

        # -- Navigation --------------------------------------------------------
        nav = tk.Frame(self.win, bg=BG)
        nav.pack(fill=tk.X, padx=10, pady=(4, 0))
        self._nav_btn(nav, "\u25c4 Prev unresolved", self._nav_prev)
        self._nav_btn(nav, "Next unresolved \u25ba", self._nav_next)
        self._nav_btn(nav, "\u21bb Refresh \u00b6",  self._refresh_from_word)

        # -- Save --------------------------------------------------------------
        tk.Frame(self.win, bg="#444444", height=1).pack(
            fill=tk.X, padx=10, pady=(8, 4)
        )
        tk.Button(
            self.win,
            text="\U0001f4be  Save edits to DocAnalyser",
            command=self._save_to_docanalyzer,
            bg=SAVE_BG, fg="#ffffff",
            activebackground=SAVE_ACTIVE, activeforeground="#ffffff",
            relief=tk.FLAT, font=FONT_BODY, cursor="hand2",
            highlightthickness=0, bd=0, padx=10, pady=5,
        ).pack(fill=tk.X, padx=10)

        tk.Label(
            self.win,
            text="\u26a0  Keep the [MM:SS] timestamps when editing \u2014 they sync back to DocAnalyser.",
            bg=BG, fg="#aa8800", font=FONT_SMALL,
            wraplength=375, justify=tk.LEFT, anchor="w",
        ).pack(fill=tk.X, padx=10, pady=(4, 2))

        self._status_var = tk.StringVar(value="Waiting for Word cursor\u2026")
        tk.Label(
            self.win, textvariable=self._status_var,
            bg="#1a1a1a", fg=FG_DIM, font=FONT_SMALL,
            anchor="w", padx=8, pady=3,
        ).pack(side=tk.BOTTOM, fill=tk.X)

    def _nav_btn(self, parent, text, cmd):
        tk.Button(
            parent, text=text, command=cmd,
            bg=BTN_BG, fg=FG, activebackground=BTN_ACTIVE,
            activeforeground=FG, relief=tk.FLAT, font=FONT_SMALL,
            cursor="hand2", highlightthickness=0, bd=0, padx=8, pady=2,
        ).pack(side=tk.LEFT, padx=(0, 4), pady=4)

    # =========================================================================
    # Audio section
    # =========================================================================

    def _build_audio_section(self):
        frame = tk.LabelFrame(
            self.win, text=" Audio ",
            bg=BG, fg=FG_DIM, font=FONT_SMALL, bd=1, relief=tk.GROOVE,
        )
        frame.pack(fill=tk.X, padx=10, pady=(4, 4))

        top_row = tk.Frame(frame, bg=BG)
        top_row.pack(fill=tk.X, padx=6, pady=(4, 0))

        self._audio_file_var = tk.StringVar(
            value=os.path.basename(self._audio_path)
            if self._audio_path else "No audio file"
        )
        tk.Label(
            top_row, textvariable=self._audio_file_var,
            bg=BG, fg=FG_DIM, font=FONT_SMALL, anchor="w", wraplength=240,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(
            top_row, text="\U0001f4c2",
            command=self._browse_audio,
            bg=BTN_BG, fg=FG, activebackground=BTN_ACTIVE,
            activeforeground=FG, relief=tk.FLAT, font=FONT_SMALL,
            cursor="hand2", highlightthickness=0, bd=0, padx=4, pady=1,
        ).pack(side=tk.RIGHT)

        self._ts_hidden = False
        self._ts_btn = tk.Button(
            top_row, text="Hide ts",
            command=self._toggle_timestamps_hidden,
            bg=BTN_BG, fg=FG_DIM, activebackground=BTN_ACTIVE,
            activeforeground=FG, relief=tk.FLAT, font=FONT_SMALL,
            cursor="hand2", highlightthickness=0, bd=0, padx=5, pady=1,
        )
        self._ts_btn.pack(side=tk.RIGHT, padx=(0, 4))

        time_row = tk.Frame(frame, bg=BG)
        time_row.pack(fill=tk.X, padx=6, pady=(2, 0))

        self._pos_var = tk.StringVar(value="00:00")
        tk.Label(
            time_row, textvariable=self._pos_var,
            bg=BG, fg="#ffffff", font=FONT_TIME_LG,
        ).pack(side=tk.LEFT)

        self._dur_var = tk.StringVar(value=" / 00:00")
        tk.Label(
            time_row, textvariable=self._dur_var,
            bg=BG, fg=FG_DIM, font=("Consolas", 10),
        ).pack(side=tk.LEFT, pady=(4, 0))

        self._slider_var = tk.DoubleVar(value=0.0)
        self._slider = ttk.Scale(
            frame, from_=0.0, to=1000.0,
            orient=tk.HORIZONTAL, variable=self._slider_var,
            command=self._on_slider_move,
        )
        self._slider.pack(fill=tk.X, padx=6, pady=(2, 2))
        self._slider.bind("<ButtonPress-1>",   self._on_slider_press)
        self._slider.bind("<ButtonRelease-1>", self._on_slider_release)

        btn_row = tk.Frame(frame, bg=BG)
        btn_row.pack(pady=(0, 4))

        def _abtn(parent, text, cmd, width=6):
            return tk.Button(
                parent, text=text, command=cmd,
                bg=BTN_BG, fg=FG, activebackground=BTN_ACTIVE,
                activeforeground=FG, relief=tk.FLAT,
                font=FONT_SMALL, width=width, cursor="hand2",
                highlightthickness=0, bd=0, padx=3, pady=2,
            )

        _abtn(btn_row, "\u23ee \u221230s", self._seek_back30, 7).pack(side=tk.LEFT, padx=2)
        _abtn(btn_row, "\u221210s",        self._seek_back10, 5).pack(side=tk.LEFT, padx=2)
        self._play_btn = _abtn(btn_row, "\u25b6  Play", self._toggle_play, 8)
        self._play_btn.pack(side=tk.LEFT, padx=2)
        _abtn(btn_row, "+10s",             self._seek_fwd10,  5).pack(side=tk.LEFT, padx=2)
        _abtn(btn_row, "+30s \u23ed",      self._seek_fwd30,  7).pack(side=tk.LEFT, padx=2)

        jump_row = tk.Frame(frame, bg=BG)
        jump_row.pack(fill=tk.X, padx=6, pady=(0, 6))

        tk.Label(jump_row, text="Jump to:", bg=BG, fg=FG, font=FONT_SMALL).pack(side=tk.LEFT)

        self._jump_var = tk.StringVar()
        jump_entry = tk.Entry(
            jump_row, textvariable=self._jump_var,
            width=8, font=FONT_JUMP,
            bg="#3c3c3c", fg="#ffffff", insertbackground="#ffffff",
            relief=tk.FLAT, bd=2,
        )
        jump_entry.pack(side=tk.LEFT, padx=(4, 3))
        jump_entry.bind("<Return>",   self._on_jump)
        jump_entry.bind("<KP_Enter>", self._on_jump)

        tk.Button(
            jump_row, text="Go", command=self._on_jump,
            bg=ACCENT, fg="#ffffff",
            activebackground="#5aadff", activeforeground="#ffffff",
            relief=tk.FLAT, font=FONT_SMALL, width=4, cursor="hand2",
            highlightthickness=0, bd=0, padx=4, pady=2,
        ).pack(side=tk.LEFT)

        tk.Label(
            jump_row, text="  e.g. 4:23 or 1:04:23",
            bg=BG, fg=FG_DIM, font=("Segoe UI", 8),
        ).pack(side=tk.LEFT, padx=(6, 0))

        self._audio_status_var = tk.StringVar(
            value="Loading audio\u2026" if self._audio_path
            else "Load an audio file to enable playback."
        )
        tk.Label(
            frame, textvariable=self._audio_status_var,
            bg=BG, fg=FG_DIM, font=FONT_SMALL, anchor="w",
        ).pack(fill=tk.X, padx=6, pady=(0, 4))

    # =========================================================================
    # Timestamp hide/show
    # =========================================================================

    def _toggle_timestamps_hidden(self):
        if not COM_AVAILABLE:
            self._status_var.set("Word not linked \u2014 cannot toggle timestamps.")
            return
        if getattr(self, "_ts_toggling", False):
            return
        self._ts_toggling = True
        self._ts_btn.config(state=tk.DISABLED)

        hide   = not getattr(self, "_timestamps_hidden", False)
        action = "Hiding" if hide else "Showing"
        self._status_var.set(f"{action} timestamps\u2026")
        self.win.update_idletasks()

        def _do_toggle():
            count = 0
            try:
                word    = _com.GetActiveObject("Word.Application")
                doc     = word.ActiveDocument
                n_paras = doc.Paragraphs.Count
                for i, para in enumerate(doc.Paragraphs, 1):
                    text = para.Range.Text
                    base = para.Range.Start
                    for m in _TS_MARKER_RE.finditer(text):
                        doc.Range(
                            base + m.start(),
                            base + m.end(),
                        ).Font.Hidden = hide
                        count += 1
                    if i % 20 == 0:
                        pct = int(i / n_paras * 100)
                        self.win.after(
                            0,
                            lambda p=pct, c=count: self._status_var.set(
                                f"{action} timestamps\u2026 {p}%  ({c} markers)"
                            ),
                        )
            except Exception as e:
                logger.warning(f"COM toggle_timestamps_hidden: {e}")
                self.win.after(0, lambda: self._status_var.set(f"Error: {e}"))
                self.win.after(0, lambda: setattr(self, "_ts_toggling", False))
                self.win.after(0, lambda: self._ts_btn.config(state=tk.NORMAL))
                return

            def _done():
                self._timestamps_hidden = hide
                self._ts_btn.config(
                    text="Show ts" if hide else "Hide ts",
                    state=tk.NORMAL,
                )
                state_word = "hidden from print" if hide else "visible"
                self._status_var.set(f"Timestamps {state_word}. ({count} markers)  Print now for a clean transcript." if hide else f"Timestamps {state_word}. ({count} markers)")
                self._ts_toggling = False

            self.win.after(0, _done)

        threading.Thread(target=_do_toggle, daemon=True).start()

    # =========================================================================
    # Speaker name fields
    # =========================================================================

    def _load_speaker_names(self):
        """Pre-fill name fields from metadata saved in a previous session."""
        try:
            from document_library import get_document_by_id
            doc = get_document_by_id(self._doc_id)
            if not doc:
                return
            saved = (doc.get("metadata") or {}).get("word_speaker_names", {})
            for label, var in self._name_vars.items():
                if label in saved and not var.get():
                    var.set(saved[label])
            if saved:
                self._build_assign_buttons()
        except Exception as e:
            logger.debug(f"_load_speaker_names: {e}")

    def _save_speaker_names(self):
        """Persist name-field values to document metadata for next session."""
        names = {label: var.get().strip()
                 for label, var in self._name_vars.items()
                 if var.get().strip()}
        if not names:
            return
        try:
            from document_library import get_document_by_id, update_document_metadata
            doc = get_document_by_id(self._doc_id)
            if not doc:
                return
            meta = dict(doc.get("metadata") or {})
            existing = meta.get("word_speaker_names", {})
            existing.update(names)
            meta["word_speaker_names"] = existing
            update_document_metadata(self._doc_id, meta)
        except Exception as e:
            logger.debug(f"_save_speaker_names: {e}")

    def _build_names_section(self):
        heuristics = sorted(
            {e.get("speaker", "") for e in self._entries
             if _is_heuristic(e.get("speaker", ""))}
        )
        self._names_frame = tk.LabelFrame(
            self.win, text=" Speaker names ",
            bg=BG, fg=FG_DIM, font=FONT_SMALL, bd=1, relief=tk.GROOVE,
        )
        self._names_frame.pack(fill=tk.X, padx=10, pady=(0, 4))

        self._names_rows_frame = tk.Frame(self._names_frame, bg=BG)
        self._names_rows_frame.pack(fill=tk.X)

        if not heuristics:
            tk.Label(
                self._names_rows_frame,
                text="No unresolved SPEAKER_X labels found.",
                bg=BG, fg=FG_DIM, font=FONT_SMALL,
            ).pack(padx=8, pady=4)
        else:
            for label in heuristics:
                self._add_name_row(label)

        btn_row = tk.Frame(self._names_frame, bg=BG)
        btn_row.pack(fill=tk.X, padx=8, pady=(4, 6))
        tk.Button(
            btn_row, text="Apply names to whole document",
            command=self._apply_all_names,
            bg=ACCENT, fg="#ffffff",
            activebackground="#5aadff", activeforeground="#ffffff",
            relief=tk.FLAT, font=FONT_SMALL, cursor="hand2",
            highlightthickness=0, bd=0, padx=8, pady=3,
        ).pack(side=tk.LEFT)
        tk.Button(
            btn_row, text="+ Add speaker",
            command=self._add_extra_speaker,
            bg=BG, fg=FG_DIM,
            activebackground=BTN_ACTIVE, activeforeground=FG,
            relief=tk.FLAT, font=FONT_SMALL, cursor="hand2",
            highlightthickness=0, bd=0, padx=6, pady=3,
        ).pack(side=tk.LEFT, padx=(6, 0))

    def _add_name_row(self, label: str, focus: bool = False):
        """Add a single SPEAKER_X: [name entry] row to the names section."""
        row = tk.Frame(self._names_rows_frame, bg=BG)
        row.pack(fill=tk.X, padx=8, pady=2)
        tk.Label(
            row, text=f"{label}:",
            bg=BG, fg=FG, font=FONT_MONO, width=12, anchor="w",
        ).pack(side=tk.LEFT)
        var = tk.StringVar()
        self._name_vars[label] = var
        ent = tk.Entry(
            row, textvariable=var, width=18,
            bg="#3c3c3c", fg=FG, insertbackground=FG,
            relief=tk.FLAT, font=FONT_BODY,
        )
        ent.pack(side=tk.LEFT, padx=(4, 0))
        ent.bind("<KeyRelease>",
                 lambda _e: self.win.after(0, self._build_assign_buttons))
        ent.bind("<Return>", lambda _e: self._apply_all_names())
        if focus:
            ent.focus_set()
        return var

    def _add_extra_speaker(self):
        """Add a new speaker row for a manually-identified extra participant."""
        existing = set(self._name_vars.keys())
        for i in range(26):
            label = f"SPEAKER_{chr(65 + i)}"
            if label not in existing:
                break
        else:
            self._status_var.set("Maximum number of speaker labels reached.")
            return

        for w in self._names_rows_frame.winfo_children():
            if isinstance(w, tk.Label) and "No unresolved" in (w.cget("text") or ""):
                w.destroy()
                break

        self._add_name_row(label, focus=True)
        self._build_assign_buttons()
        self._status_var.set(
            f"Added {label} \u2014 enter a name then click Assign or Apply."
        )

    # =========================================================================
    # Assignment buttons
    # =========================================================================

    def _build_assign_buttons(self):
        for w in self._btn_outer.winfo_children():
            w.destroy()

        known: set = set()
        for e in self._entries:
            s = e.get("speaker", "")
            if s and not _is_heuristic(s):
                known.add(s)
        for var in self._name_vars.values():
            v = var.get().strip()
            if v:
                known.add(v)

        tk.Label(
            self._btn_outer, text="Assign to:",
            bg=BG, fg=FG_DIM, font=FONT_SMALL,
        ).pack(side=tk.LEFT, padx=(0, 4))

        if not known:
            tk.Label(
                self._btn_outer, text="enter names above first",
                bg=BG, fg=FG_DIM, font=FONT_SMALL,
            ).pack(side=tk.LEFT)
            return

        for name in sorted(known):
            tk.Button(
                self._btn_outer, text=name,
                command=lambda n=name: self._assign(n),
                bg=BTN_BG, fg=FG,
                activebackground=ACCENT, activeforeground="#ffffff",
                relief=tk.FLAT, font=FONT_SMALL, cursor="hand2",
                highlightthickness=0, bd=0, padx=7, pady=2,
            ).pack(side=tk.LEFT, padx=(0, 3))

        tk.Button(
            self._btn_outer, text="Other\u2026",
            command=self._assign_other,
            bg=BTN_BG, fg=FG_DIM,
            activebackground=BTN_ACTIVE, activeforeground=FG,
            relief=tk.FLAT, font=FONT_SMALL, cursor="hand2",
            highlightthickness=0, bd=0, padx=5, pady=2,
        ).pack(side=tk.LEFT)

    # =========================================================================
    # Paragraph list
    # =========================================================================

    def _populate_list(self):
        self._listbox.delete(0, tk.END)
        for i, entry in enumerate(self._entries):
            self._listbox.insert(tk.END, self._row_text(entry))
            if _is_resolved(entry):
                self._listbox.itemconfig(i, fg=FG_RESOLVED)

    def _row_text(self, entry: Dict) -> str:
        ts      = _fmt_time(entry.get("start", 0))
        spk     = entry.get("speaker") or "\u2014"
        txt     = (entry.get("text") or "").strip().replace("\n", " ")
        preview = txt[:38] + ("\u2026" if len(txt) > 38 else "")
        return f"  {ts}  [{spk}]  {preview}"

    def _highlight(self, idx: int):
        if idx == self._current_idx:
            return
        if self._current_idx is not None:
            old = self._current_idx
            self._listbox.itemconfig(
                old,
                bg=BG_ALT if old % 2 else BG_LIST,
                fg=FG_RESOLVED if _is_resolved(self._entries[old]) else FG_UNRES,
            )
        self._current_idx = idx
        self._listbox.itemconfig(idx, bg=BG_CURRENT, fg="#ffffff")
        self._listbox.see(idx)
        entry = self._entries[idx]
        ts    = _fmt_time(entry.get("start", 0))
        spk   = entry.get("speaker") or "no speaker"
        self._status_var.set(
            f"Para {idx + 1} of {len(self._entries)}  [{ts}]  {spk}"
        )

    def _refresh_row(self, idx: int):
        entry = self._entries[idx]
        self._listbox.delete(idx)
        self._listbox.insert(idx, self._row_text(entry))
        if idx == self._current_idx:
            self._listbox.itemconfig(idx, bg=BG_CURRENT, fg="#ffffff")
        else:
            self._listbox.itemconfig(
                idx,
                bg=BG_ALT if idx % 2 else BG_LIST,
                fg=FG_RESOLVED if _is_resolved(entry) else FG_UNRES,
            )
        self._refresh_summary()

    def _refresh_summary(self):
        n     = len(self._entries)
        n_res = sum(1 for e in self._entries if _is_resolved(e))
        self._summary_var.set(
            f"{n} paragraphs \u00b7 {n_res} resolved \u00b7 {n - n_res} unresolved"
        )

    def _on_list_click(self, _event=None):
        sel = self._listbox.curselection()
        if sel:
            self._highlight(sel[0])

    def _on_list_double_click(self, _event=None):
        sel = self._listbox.curselection()
        if not sel:
            return
        idx   = sel[0]
        entry = self._entries[idx]
        start = float(entry.get("start", 0))
        self._highlight(idx)
        self._seek(start)
        self._scroll_word_to_timestamp(f"[{_fmt_time(start)}]")

    def _scroll_word_to_timestamp(self, ts_anchor: str):
        if not COM_AVAILABLE:
            return
        try:
            word = _com.GetActiveObject("Word.Application")
            doc  = word.ActiveDocument

            if self._highlighted_ts and self._highlighted_ts != ts_anchor:
                for para in doc.Paragraphs:
                    if para.Range.Text.strip().startswith(self._highlighted_ts):
                        para.Range.HighlightColorIndex = 0
                        break

            for para in doc.Paragraphs:
                if para.Range.Text.strip().startswith(ts_anchor):
                    rng = para.Range
                    rng.Select()
                    rng.HighlightColorIndex = 7   # wdYellow
                    self._highlighted_ts = ts_anchor
                    break
        except Exception as e:
            logger.debug(f"COM scroll_word_to_timestamp: {e}")

    # =========================================================================
    # COM polling
    # =========================================================================

    def _start_poll(self):
        self._poll_word_cursor()

    def _stop_poll(self):
        if self._poll_job:
            try:
                self.win.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None

    def _clear_word_highlight(self, word=None):
        if not self._highlighted_ts:
            return
        try:
            if word is None:
                word = _com.GetActiveObject("Word.Application")
            doc = word.ActiveDocument
            ts = self._highlighted_ts
            for para in doc.Paragraphs:
                if para.Range.Text.strip().startswith(ts):
                    para.Range.HighlightColorIndex = 0
                    break
        except Exception:
            pass
        self._highlighted_ts = None

    def _poll_word_cursor(self):
        try:
            word = _com.GetActiveObject("Word.Application")
            if not self._word_positioned:
                fn = getattr(self, "_position_word_fn", None)
                if fn:
                    fn()
            para_text = word.Selection.Paragraphs(1).Range.Text.strip()
            if para_text != self._last_para_text:
                self._last_para_text = para_text
                idx = self._match_entry_for_para(para_text)
                if idx is not None:
                    self._highlight(idx)
                    new_ts = f"[{_fmt_time(self._entries[idx].get('start', 0))}]"
                    if self._highlighted_ts and self._highlighted_ts != new_ts:
                        self._clear_word_highlight(word)
                elif _SPLIT_RE.match(para_text) or _EMBEDDED_HDR_RE.search(para_text):
                    if self._highlighted_ts:
                        self._clear_word_highlight(word)
                    self._refresh_from_word()
            self._badge_var.set("\u25cf Word linked")
        except Exception:
            self._badge_var.set("\u25cb Word not linked")
        self._poll_job = self.win.after(self._POLL_MS, self._poll_word_cursor)

    def _match_entry_for_para(self, para_text: str) -> Optional[int]:
        m = re.match(r'^\[(\d+:\d{2}(?::\d{2})?)\]', para_text)
        if not m:
            return None
        seconds   = _parse_ts(m.group(1))
        best_idx  = None
        best_diff = 2.5
        for i, entry in enumerate(self._entries):
            diff = abs(entry.get("start", 0.0) - seconds)
            if diff < best_diff:
                best_diff = diff
                best_idx  = i
        return best_idx

    # =========================================================================
    # Speaker assignment
    # =========================================================================

    def _assign(self, name: str):
        if self._current_idx is None:
            self._status_var.set("No paragraph selected \u2014 click a row first.")
            return
        idx   = self._current_idx
        entry = self._entries[idx]
        old   = entry.get("speaker") or ""
        entry["speaker"]     = name
        entry["provisional"] = False
        self._word_update_para_speaker(idx, old, name)
        self._refresh_row(idx)
        self._status_var.set(f"\u2714  Assigned '{name}' to para {idx + 1}.")
        self._build_assign_buttons()
        self._save_speaker_names()

    def _assign_other(self):
        name = simpledialog.askstring("Speaker name", "Enter name:", parent=self.win)
        if name and name.strip():
            self._assign(name.strip())

    def _apply_all_names(self):
        subs = {
            label: var.get().strip()
            for label, var in self._name_vars.items()
            if var.get().strip()
        }
        if not subs:
            self._status_var.set("Enter names in the fields above first.")
            return

        for entry in self._entries:
            spk = entry.get("speaker", "")
            if spk in subs:
                entry["speaker"]     = subs[spk]
                entry["provisional"] = False

        try:
            word = _com.GetActiveObject("Word.Application")
            for old_lbl, new_name in subs.items():
                rng = word.ActiveDocument.Range()
                rng.Find.Execute(
                    old_lbl, True, False, False, False, False,
                    True, 1, False, new_name, 2,
                )
        except Exception as e:
            logger.warning(f"COM apply_all_names: {e}")

        self._populate_list()
        if self._current_idx is not None:
            self._highlight(self._current_idx)
        self._refresh_summary()
        self._build_assign_buttons()
        self._save_speaker_names()
        n = len(subs)
        self._status_var.set(
            f"Applied {n} name substitution{'s' if n != 1 else ''} to the document."
        )

    def _word_update_para_speaker(self, entry_idx: int, old_speaker: str, new_speaker: str):
        if not COM_AVAILABLE:
            return
        entry     = self._entries[entry_idx]
        ts        = _fmt_time(entry.get("start", 0))
        ts_anchor = f"[{ts}]"
        old_label = f"[{old_speaker}]" if old_speaker else ""
        new_label = f"[{new_speaker}]"
        if not old_label:
            return
        try:
            word = _com.GetActiveObject("Word.Application")
            doc  = word.ActiveDocument
            for para in doc.Paragraphs:
                if para.Range.Text.strip().startswith(ts_anchor):
                    para.Range.Find.Execute(
                        old_label, True, False, False, False, False,
                        True, 0, False, new_label, 2,
                    )
                    break
        except Exception as e:
            logger.warning(f"COM _word_update_para_speaker: {e}")

    # =========================================================================
    # Navigation
    # =========================================================================

    def _nav_prev(self):
        start = (self._current_idx or 0) - 1
        for i in range(start, -1, -1):
            if not _is_resolved(self._entries[i]):
                self._highlight(i)
                self._listbox.selection_clear(0, tk.END)
                self._listbox.selection_set(i)
                return
        self._status_var.set("No earlier unresolved paragraphs.")

    def _nav_next(self):
        start = (self._current_idx if self._current_idx is not None else -1) + 1
        for i in range(start, len(self._entries)):
            if not _is_resolved(self._entries[i]):
                self._highlight(i)
                self._listbox.selection_clear(0, tk.END)
                self._listbox.selection_set(i)
                return
        self._status_var.set("All remaining paragraphs are resolved. \U0001f389")

    def _demote_merged_headers_in_word(self, doc, para) -> bool:
        raw        = para.Range.Text
        matches    = list(_EMBEDDED_HDR_RE.finditer(raw))
        n_matched  = len(matches)

        if n_matched < 2:
            return False

        GREY_999   = 153 + 153 * 256 + 153 * 65536
        para_start = para.Range.Start
        made_change = False

        for m in reversed(matches[1:]):
            sent_ts   = m.group(1)
            ts_new    = "{" + sent_ts + "}"
            abs_start = para_start + m.start()
            abs_end   = para_start + m.end()

            try:
                actual = doc.Range(abs_start, abs_end).Text
            except Exception as e:
                logger.warning(f"COM demote read '{sent_ts}': {e}")
                continue

            logger.debug(
                f"demote: para_start={para_start} m.start={m.start()} "
                f"m.end={m.end()} actual={repr(actual)} expected={repr(m.group(0))}"
            )

            try:
                doc.Range(abs_start, abs_end).Text = ts_new
                fmt = doc.Range(abs_start, abs_start + len(ts_new))
                fmt.Font.Size  = 7
                fmt.Font.Color = GREY_999
                fmt.Font.Bold  = False
                made_change = True
            except Exception as e:
                logger.warning(f"COM demote replace '{sent_ts}': {e}")

        return made_change

    def _refresh_from_word(self):
        if not COM_AVAILABLE:
            self._status_var.set("Word not linked \u2014 cannot refresh.")
            return
        try:
            word = _com.GetActiveObject("Word.Application")
            doc  = word.ActiveDocument
        except Exception as e:
            self._status_var.set(f"Could not connect to Word: {e}")
            return

        ts_to_entry  = {_fmt_time(e.get("start", 0)): dict(e) for e in self._entries}
        new_entries  : List[Dict] = []
        last_speaker = "SPEAKER_A"

        try:
            for para in doc.Paragraphs:
                text = para.Range.Text.strip()
                if not text:
                    continue
                m = _PARA_RE.match(text)
                if m:
                    ts_str, speaker, content = m.groups()
                    last_speaker = speaker
                    if _EMBEDDED_HDR_RE.search(content):
                        self._demote_merged_headers_in_word(doc, para)
                        text    = para.Range.Text.strip()
                        m2      = _PARA_RE.match(text)
                        if m2:
                            ts_str, speaker, content = m2.groups()
                            last_speaker = speaker
                    clean = _SENT_TS_RE.sub("", content).strip()
                    entry = ts_to_entry.get(ts_str)
                    if entry is None:
                        seconds = _parse_ts(ts_str)
                        best, bd = None, 2.5
                        for e in self._entries:
                            d = abs(e.get("start", 0.0) - seconds)
                            if d < bd:
                                bd, best = d, dict(e)
                        entry = best or {"start": seconds, "end": seconds + 30.0}
                    entry = dict(entry)
                    entry["speaker"] = speaker
                    entry["text"]    = clean
                    entry.pop("provisional", None)
                    new_entries.append(entry)
                    continue
                sm = _SPLIT_RE.match(text)
                if sm:
                    sent_ts, remainder = sm.groups()
                    clean = _SENT_TS_RE.sub("", remainder).strip()
                    if not clean:
                        continue
                    seconds = _parse_ts(sent_ts)
                    new_entries.append({
                        "start":       seconds,
                        "end":         seconds + 30.0,
                        "speaker":     last_speaker,
                        "provisional": True,
                        "text":        clean,
                        "sentences":   [],
                    })
        except Exception as e:
            self._status_var.set(f"Error reading Word document: {e}")
            return

        if not new_entries:
            self._status_var.set("No transcript paragraphs found in Word document.")
            return

        new_entries.sort(key=lambda e: e.get("start", 0.0))

        n_split = sum(1 for e in new_entries if e.get("provisional"))
        if n_split:
            for entry in new_entries:
                if entry.get("provisional"):
                    self._promote_split_para_in_word(
                        doc,
                        _fmt_time(entry["start"]),
                        entry.get("speaker", "SPEAKER_A"),
                    )

        self._entries = new_entries
        self._populate_list()
        self._refresh_summary()
        self._build_assign_buttons()
        msg = f"Refreshed: {len(new_entries)} paragraphs"
        if n_split:
            msg += f" ({n_split} split paragraph{'s' if n_split != 1 else ''} added — speaker inherited, please confirm)"
        self._status_var.set(msg)

    def _promote_split_para_in_word(self, doc, sent_ts: str, speaker: str):
        anchor   = "{" + sent_ts + "}"
        ts_part  = f"[{sent_ts}]"
        gap_part = "\u00a0\u00a0"
        spk_part = f"[{speaker}]:\u00a0"
        new_prefix = ts_part + gap_part + spk_part

        GREY_999   = 153 + 153 * 256 + 153 * 65536
        AUTO_COLOR = -16777216

        for para in doc.Paragraphs:
            raw   = para.Range.Text
            ptext = raw.strip()
            if not ptext.startswith(anchor):
                continue
            try:
                anchor_offset = raw.find(anchor)
                if anchor_offset < 0:
                    break
                abs_start = para.Range.Start + anchor_offset

                doc.Range(abs_start, abs_start + len(anchor)).Text = new_prefix

                pos = abs_start

                rng_ts = doc.Range(pos, pos + len(ts_part))
                rng_ts.Font.Size  = 8
                rng_ts.Font.Color = GREY_999
                rng_ts.Font.Bold  = False
                pos += len(ts_part)

                rng_gap = doc.Range(pos, pos + len(gap_part))
                rng_gap.Font.Size  = 11
                rng_gap.Font.Color = AUTO_COLOR
                rng_gap.Font.Bold  = False
                pos += len(gap_part)

                rng_spk = doc.Range(pos, pos + len(spk_part))
                rng_spk.Font.Size  = 11
                rng_spk.Font.Color = AUTO_COLOR
                rng_spk.Font.Bold  = True

            except Exception as e:
                logger.warning(f"COM promote_split_para '{sent_ts}': {e}")
            break

    # =========================================================================
    # Save back to DocAnalyser
    # =========================================================================

    def _save_to_docanalyzer(self):
        if not os.path.isfile(self._docx_path):
            messagebox.showerror(
                "File not found",
                f"Cannot find:\n{self._docx_path}\n\n"
                "Make sure Word has saved it (Ctrl+S) before clicking Save.",
                parent=self.win,
            )
            return
        self._status_var.set("Reading Word document\u2026")
        self.win.update_idletasks()
        try:
            updated = self._parse_docx()
        except Exception as e:
            messagebox.showerror("Read error", f"Could not read the Word document:\n{e}",
                                 parent=self.win)
            self._status_var.set("Save failed.")
            return
        if not updated:
            messagebox.showwarning(
                "Nothing found",
                "No transcript paragraphs were found.\n\n"
                "The [MM:SS] or {MM:SS} timestamps at the start of each paragraph "
                "must be intact for DocAnalyser to sync the edits back.",
                parent=self.win,
            )
            self._status_var.set("Save cancelled \u2014 no entries found.")
            return
        try:
            from document_library import update_transcript_entries
            update_transcript_entries(self._doc_id, updated)
        except Exception as e:
            messagebox.showerror("Save error", f"Could not save to library:\n{e}",
                                 parent=self.win)
            self._status_var.set("Save failed.")
            return

        self._update_word_edit_date()

        self._entries = updated
        self._populate_list()
        if self._current_idx is not None:
            self._highlight(min(self._current_idx, len(self._entries) - 1))
        self._refresh_summary()
        if self._on_save_cb:
            try:
                self._on_save_cb(updated)
            except Exception:
                pass
        self._status_var.set(f"Saved {len(updated)} paragraphs to DocAnalyser. \u2714")

    def _update_word_edit_date(self):
        if not COM_AVAILABLE:
            return
        import datetime as _dt
        now_str  = _dt.datetime.now().strftime("%d-%b-%Y  %H:%M")
        username = os.getenv("USERNAME") or os.getenv("USER") or "Unknown"
        try:
            word = _com.GetActiveObject("Word.Application")
            doc  = word.ActiveDocument
            for label, new_val in [("Date last edited: ", now_str),
                                   ("By: ", username)]:
                rng = doc.Range()
                rng.Find.ClearFormatting()
                found = rng.Find.Execute(
                    label, True, False, False, False, False,
                    True, 1, False, "", 0,
                )
                if found:
                    value_start = rng.End
                    value_rng = doc.Range(value_start, value_start)
                    value_rng.MoveEndUntil("\n", 1)
                    value_rng.Text = new_val
        except Exception as e:
            logger.debug(f"_update_word_edit_date: {e}")

    def _parse_docx(self) -> List[Dict]:
        from docx import Document
        doc         = Document(self._docx_path)
        ts_to_entry = {_fmt_time(e.get("start", 0)): dict(e) for e in self._entries}
        result: List[Dict] = []
        last_speaker = "SPEAKER_A"

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            m = _PARA_RE.match(text)
            if m:
                ts_str, speaker, content = m.groups()
                last_speaker = speaker
                clean_content = _SENT_TS_RE.sub("", content).strip()
                entry = ts_to_entry.get(ts_str)
                if entry is None:
                    seconds   = _parse_ts(ts_str)
                    best, bd  = None, 2.5
                    for e in self._entries:
                        d = abs(e.get("start", 0.0) - seconds)
                        if d < bd:
                            bd, best = d, dict(e)
                    entry = best
                if entry is None:
                    continue
                entry             = dict(entry)
                entry["speaker"]  = speaker
                entry["text"]     = clean_content
                entry.pop("provisional", None)
                result.append(entry)
                continue
            sm = _SPLIT_RE.match(text)
            if sm:
                sent_ts_str, remainder = sm.groups()
                sent_seconds = _parse_ts(sent_ts_str)
                clean_text = _SENT_TS_RE.sub("", remainder).strip()
                if not clean_text:
                    continue
                result.append({
                    "start":       sent_seconds,
                    "end":         sent_seconds + 30.0,
                    "speaker":     last_speaker,
                    "provisional": True,
                    "text":        clean_text,
                    "sentences":   [],
                })

        result.sort(key=lambda e: e.get("start", 0.0))
        return result

    # =========================================================================
    # Audio player
    # =========================================================================

    def _browse_audio(self):
        self.win.attributes("-topmost", False)
        try:
            path = filedialog.askopenfilename(
                title="Open audio file",
                filetypes=[
                    ("Audio files", "*.mp3 *.m4a *.wav *.ogg *.aac *.flac *.wma"),
                    ("All files", "*.*"),
                ],
                parent=self.win,
            )
        finally:
            self.win.attributes("-topmost", True)
        if path:
            self._load_audio(os.path.normpath(path))

    def _load_audio(self, path: str):
        if not PYGAME_OK:
            self._audio_status_var.set("pygame not installed \u2014 pip install pygame")
            return
        if self._audio_loading:
            return
        self._audio_loading = True
        self._audio_status_var.set(f"Loading {os.path.basename(path)}\u2026")
        self.win.update_idletasks()

        def _do_load():
            try:
                cache_dir = os.path.join(
                    os.getenv("APPDATA") or os.path.expanduser("~"),
                    "DocAnalyser_Beta", "audio_cache",
                )
                os.makedirs(cache_dir, exist_ok=True)
                key      = hashlib.md5(path.encode()).hexdigest()[:12]
                mp3_path = os.path.join(cache_dir, f"panel_{key}.mp3")
            except Exception:
                import tempfile
                mp3_path = tempfile.mktemp(suffix=".mp3")

            if not os.path.exists(mp3_path):
                try:
                    _run_ffmpeg(["ffmpeg", "-y", "-i", path, "-q:a", "2", mp3_path])
                except Exception:
                    mp3_path = path

            try:
                pygame.mixer.music.load(mp3_path)
            except Exception as e:
                self.win.after(0, lambda: self._audio_status_var.set(f"Cannot load: {e}"))
                self.win.after(0, lambda: setattr(self, "_audio_loading", False))
                return

            duration = 0.0
            try:
                snd      = pygame.mixer.Sound(mp3_path)
                duration = snd.get_length()
                del snd
            except Exception:
                pass

            def _apply():
                if self._playing:
                    pygame.mixer.music.stop()
                    self._playing = False
                self._audio_path      = path
                self._duration        = duration
                self._position        = 0.0
                self._play_start_pos  = 0.0
                self._play_start_wall = 0.0
                self._audio_loading   = False
                self._audio_file_var.set(os.path.basename(path))
                self._dur_var.set(f" / {_fmt_time(duration)}")
                self._pos_var.set("00:00")
                self._slider_var.set(0.0)
                self._update_play_btn()
                self._audio_status_var.set(
                    "Ready. Double-click a paragraph row to seek and play."
                )

            self.win.after(0, _apply)

        threading.Thread(target=_do_load, daemon=True).start()

    def _toggle_play(self):
        if not PYGAME_OK or not self._audio_path:
            if not self._audio_path:
                self._browse_audio()
            return
        if self._playing:
            pygame.mixer.music.pause()
            elapsed        = time.time() - self._play_start_wall
            self._position = min(self._play_start_pos + elapsed, self._duration)
            self._playing  = False
            self._audio_status_var.set(f"Paused at {_fmt_time(self._position)}")
        else:
            pygame.mixer.music.unpause()
            self._play_start_pos  = self._position
            self._play_start_wall = time.time()
            self._playing         = True
            self._audio_status_var.set(f"Playing from {_fmt_time(self._position)}")
        self._update_play_btn()

    def _seek(self, seconds: float):
        if not PYGAME_OK or not self._audio_path:
            return
        seconds = max(0.0, min(seconds, self._duration or seconds))
        pygame.mixer.music.stop()
        pygame.mixer.music.play(start=seconds)
        self._position        = seconds
        self._play_start_pos  = seconds
        self._play_start_wall = time.time()
        self._playing         = True
        self._update_play_btn()
        self._audio_status_var.set(f"Playing from {_fmt_time(seconds)}")

    def _seek_back10(self):  self._seek(max(0.0, self._position - 10.0))
    def _seek_fwd10(self):   self._seek(self._position + 10.0)
    def _seek_back30(self):  self._seek(max(0.0, self._position - 30.0))
    def _seek_fwd30(self):   self._seek(self._position + 30.0)

    def _on_jump(self, _event=None):
        text = self._jump_var.get().strip()
        if not text:
            return
        t = _parse_jump(text)
        if t is None:
            self._audio_status_var.set(f"Cannot parse '{text}' \u2014 use MM:SS e.g. 4:23")
            return
        self._jump_var.set("")
        self._seek(t)

    def _on_slider_press(self, _event):
        self._slider_dragging = True
        if self._playing and PYGAME_OK:
            pygame.mixer.music.pause()

    def _on_slider_release(self, _event):
        self._slider_dragging = False
        if self._duration > 0:
            self._seek((self._slider_var.get() / 1000.0) * self._duration)

    def _on_slider_move(self, value):
        if self._slider_dragging and self._duration > 0:
            self._position = (float(value) / 1000.0) * self._duration
            self._pos_var.set(_fmt_time(self._position))

    def _update_play_btn(self):
        self._play_btn.config(
            text="\u23f8  Pause" if self._playing else "\u25b6  Play"
        )

    def _poll_audio(self):
        if not self._slider_dragging and self._playing and PYGAME_OK:
            elapsed        = time.time() - self._play_start_wall
            self._position = self._play_start_pos + elapsed
            if self._duration > 0 and self._position >= self._duration:
                self._position = self._duration
                self._playing  = False
                self._update_play_btn()
                self._audio_status_var.set("Finished.")
            elif not pygame.mixer.music.get_busy() and self._playing:
                self._playing = False
                self._update_play_btn()

        if not self._slider_dragging:
            self._pos_var.set(_fmt_time(self._position))
            if self._duration > 0:
                self._slider_var.set(
                    min(1000.0, (self._position / self._duration) * 1000.0)
                )

        try:
            self.win.after(200, self._poll_audio)
        except Exception:
            pass

    # =========================================================================
    # Cleanup
    # =========================================================================

    def _on_close(self):
        self._save_speaker_names()
        self._stop_poll()
        if PYGAME_OK and self._playing:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        self.win.destroy()


# -- Public entry point --------------------------------------------------------

def show_word_editor_panel(
    parent:           tk.Widget,
    doc_id:           str,
    entries:          List[Dict],
    audio_path:       Optional[str],
    docx_path:        str,
    config:           dict,
    on_save_callback: Optional[Callable] = None,
) -> WordEditorPanel:
    """Open the unified Word Editor Panel (non-modal, always-on-top)."""
    return WordEditorPanel(
        parent, doc_id, entries, audio_path, docx_path,
        config, on_save_callback,
    )
