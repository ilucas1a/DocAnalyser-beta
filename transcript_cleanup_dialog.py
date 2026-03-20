"""
transcript_cleanup_dialog.py
============================
Transcript cleanup dialog for DocAnalyser.

Shown automatically after faster-whisper transcription completes.
Offers the user:

  Section A — Cleanup (always available, always recommended)
    [x] Remove breath fragments (uh, um, mm-hmm...)
    [x] Join fragments into sentences and paragraphs
    [x] Keep listener back-channels as [annotations]

  Section B — Speaker identification (choose one)
    ( ) Skip — I'll assign speakers manually later
    ( ) Suggest speakers automatically
        Note shown: based on question patterns; may need correction
    ( ) Detect speakers by voice  [requires one-time setup / ready]
        Note shown: more accurate; takes approx. same time as recording

  Section C — Speaker names (shown when B is not 'skip')
    Speaker A:  [____________]   e.g. Margaret
    Speaker B:  [____________]   e.g. Interviewer

The dialog runs the cleanup pipeline in a background thread with a
progress bar, then calls result_callback with the cleaned entries.

Usage (called from document_fetching.py after transcription):
    from transcript_cleanup_dialog import show_transcript_cleanup_dialog

    show_transcript_cleanup_dialog(
        parent        = self.root,
        entries       = raw_entries,          # from faster-whisper
        audio_path    = audio_file_path,      # for seek links + pyannote
        config        = self.config,          # DocAnalyser config dict
        result_callback = self._on_cleanup_done,
    )

    def _on_cleanup_done(self, result):
        # result is None if user clicked Skip / closed dialog
        # otherwise: {'entries': [...], 'audio_path': str, 'speaker_ids': [...]}
        ...
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import logging
from typing import List, Dict, Optional, Callable

logger = logging.getLogger(__name__)

# ── Appearance (matches DocAnalyser's grey palette) ──────────────────────────
BG          = "#f0f0f0"
BG_SECTION  = "#ffffff"
BG_NOTE     = "#fff8e1"
BG_WARN     = "#fff3e0"
FG          = "#1a1a1a"
FG_MUTED    = "#666666"
FG_NOTE     = "#5d4037"
FG_SUCCESS  = "#2e7d32"
FG_ERROR    = "#c62828"
FG_LINK     = "#0066cc"
FONT_TITLE  = ("Arial", 12, "bold")
FONT_BODY   = ("Arial", 10)
FONT_SMALL  = ("Arial", 9)
FONT_BOLD   = ("Arial", 10, "bold")
DIALOG_W    = 540
DIALOG_H    = 560


# ============================================================================
# DIALOG CLASS
# ============================================================================

class TranscriptCleanupDialog:
    """
    Modal dialog for transcript cleanup options.

    Blocks until the user dismisses it.  The result is available via
    self.result after the window closes:
        None  — user skipped / closed without running cleanup
        dict  — cleanup ran; keys: entries, audio_path, speaker_ids, warnings
    """

    def __init__(
        self,
        parent:          tk.Tk,
        entries:         List[Dict],
        audio_path:      Optional[str],
        config:          Dict,
        result_callback: Optional[Callable] = None,
    ):
        """
        Args:
            parent:           DocAnalyser root window.
            entries:          Raw faster-whisper entries.
            audio_path:       Path to the original audio file.
            config:           DocAnalyser config dict (for HF token, settings).
            result_callback:  Optional function(result_dict_or_None) called
                              after cleanup completes or dialog is dismissed.
        """
        self.parent          = parent
        self.entries         = entries
        self.audio_path      = audio_path
        self.config          = config
        self.result_callback = result_callback
        self.result          = None

        # Options state
        self._do_cleanup      = tk.BooleanVar(value=True)
        self._do_backchannels = tk.BooleanVar(value=True)
        self._speaker_mode    = tk.StringVar(value="heuristic")
        #  "skip" | "heuristic" | "voice"
        self._name_a          = tk.StringVar(value="")
        self._name_b          = tk.StringVar(value="")

        # Detect HF token and diarization availability
        self._hf_token    = config.get("keys", {}).get("HuggingFace", "")
        self._diar_ready  = self._check_diar_ready()
        self._diar_status = self._get_diar_status()

        self._build_window()

    # ── Availability helpers ─────────────────────────────────────────────────

    def _check_diar_ready(self) -> bool:
        try:
            import diarization_handler
            return diarization_handler.is_available(self._hf_token)
        except ImportError:
            return False

    def _get_diar_status(self) -> str:
        try:
            import diarization_handler
            return diarization_handler.get_status(self._hf_token)["message"]
        except ImportError:
            return "diarization_handler.py not found."

    # ── Window construction ───────────────────────────────────────────────────

    def _build_window(self):
        self.win = tk.Toplevel(self.parent)
        self.win.title("Transcript Cleanup")
        self.win.configure(bg=BG)
        self.win.resizable(False, False)
        self.win.transient(self.parent)
        self.win.grab_set()

        # ── Scrollable content area ───────────────────────────────────────────
        # Use a canvas so that if the dialog is taller than the screen on
        # small displays, the content can still be scrolled.
        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL,
                                   command=canvas.yview)
        # Only show scrollbar if needed (packed later conditionally)

        self._content = tk.Frame(canvas, bg=BG)
        canvas_window = canvas.create_window(
            (0, 0), window=self._content, anchor="nw"
        )

        def _on_frame_configure(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Show scrollbar only if content taller than canvas
            if self._content.winfo_reqheight() > canvas.winfo_height():
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                canvas.configure(yscrollcommand=scrollbar.set)
            else:
                scrollbar.pack_forget()

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        self._content.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        # ── Build sections ────────────────────────────────────────────────────
        self._build_header()
        self._build_section_a()
        self._build_section_b()
        self._build_section_c()
        self._build_progress_area()

        # ── Bottom button bar ─────────────────────────────────────────────────
        btn_bar = tk.Frame(self.win, bg="#e0e0e0", height=52)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)
        btn_bar.pack_propagate(False)

        self._skip_btn = tk.Button(
            btn_bar, text="Skip cleanup",
            font=FONT_BODY, width=14,
            relief=tk.FLAT, bg="#e0e0e0", fg=FG_MUTED,
            activebackground="#cccccc",
            command=self._on_skip,
        )
        self._skip_btn.pack(side=tk.LEFT, padx=12, pady=10)

        self._run_btn = tk.Button(
            btn_bar, text="Clean up transcript",
            font=("Arial", 10, "bold"), width=20,
            relief=tk.FLAT, bg="#1565c0", fg="white",
            activebackground="#0d47a1", activeforeground="white",
            command=self._on_run,
        )
        self._run_btn.pack(side=tk.RIGHT, padx=12, pady=10)

        # Centre on parent
        self.win.update_idletasks()
        px = self.parent.winfo_x() + (self.parent.winfo_width()  - DIALOG_W) // 2
        py = self.parent.winfo_y() + (self.parent.winfo_height() - DIALOG_H) // 2
        self.win.geometry(f"{DIALOG_W}x{DIALOG_H}+{px}+{py}")

        self.win.protocol("WM_DELETE_WINDOW", self._on_skip)

    # ── Section builders ──────────────────────────────────────────────────────

    def _build_header(self):
        hdr = tk.Frame(self._content, bg="#37474f")
        hdr.pack(fill=tk.X)
        tk.Label(
            hdr,
            text="Transcript cleanup options",
            font=FONT_TITLE, bg="#37474f", fg="white",
            padx=16, pady=11,
        ).pack(side=tk.LEFT)

        # Segment count
        n = len(self.entries)
        tk.Label(
            hdr,
            text=f"{n:,} segments",
            font=FONT_SMALL, bg="#37474f", fg="#b0bec5",
            padx=12, pady=11,
        ).pack(side=tk.RIGHT)

    def _section_frame(self, title: str) -> tk.Frame:
        """Create a labelled section box."""
        outer = tk.Frame(self._content, bg=BG)
        outer.pack(fill=tk.X, padx=14, pady=(10, 0))

        tk.Label(
            outer, text=title,
            font=FONT_BOLD, bg=BG, fg=FG,
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 4))

        inner = tk.Frame(outer, bg=BG_SECTION,
                         highlightbackground="#cccccc",
                         highlightthickness=1)
        inner.pack(fill=tk.X)
        return inner

    def _note(self, parent: tk.Frame, text: str,
              bg: str = BG_NOTE, fg: str = FG_NOTE):
        """A small coloured note box."""
        f = tk.Frame(parent, bg=bg,
                     highlightbackground="#ffe082",
                     highlightthickness=1)
        f.pack(fill=tk.X, padx=10, pady=(2, 8))
        tk.Label(
            f, text=text, bg=bg, fg=fg,
            font=FONT_SMALL, justify=tk.LEFT,
            wraplength=DIALOG_W - 60, anchor="w",
            padx=8, pady=5,
        ).pack(fill=tk.X)

    def _build_section_a(self):
        frame = self._section_frame("Cleanup")
        pad = dict(padx=12, pady=3)

        tk.Label(
            frame,
            text=(
                "Faster-whisper produces many short fragments per sentence. "
                "These options join them into readable paragraphs."
            ),
            font=FONT_SMALL, bg=BG_SECTION, fg=FG_MUTED,
            wraplength=DIALOG_W - 50, justify=tk.LEFT, anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(8, 4))

        tk.Checkbutton(
            frame,
            text="Remove breath fragments  (uh, um, mm, hmm…)",
            variable=self._do_cleanup,
            font=FONT_BODY, bg=BG_SECTION, fg=FG,
            activebackground=BG_SECTION,
            anchor="w",
        ).pack(fill=tk.X, **pad)

        # Backchannel option — indented, only enabled when cleanup is on
        self._bc_check = tk.Checkbutton(
            frame,
            text="Keep listener back-channels as  [annotations]  "
                 "(e.g.  [Mm-hmm],  [Right])",
            variable=self._do_backchannels,
            font=FONT_SMALL, bg=BG_SECTION, fg=FG_MUTED,
            activebackground=BG_SECTION,
            anchor="w",
        )
        self._bc_check.pack(fill=tk.X, padx=26, pady=(0, 4))
        self._do_cleanup.trace_add("write", self._on_cleanup_toggle)

        tk.Label(
            frame, text="",
            bg=BG_SECTION, height=1,
        ).pack()  # bottom padding

    def _on_cleanup_toggle(self, *_):
        state = tk.NORMAL if self._do_cleanup.get() else tk.DISABLED
        self._bc_check.config(state=state)

    def _build_section_b(self):
        frame = self._section_frame("Speaker identification")

        pad = dict(padx=12, pady=2)

        tk.Label(
            frame,
            text="How should speakers be identified in the cleaned transcript?",
            font=FONT_SMALL, bg=BG_SECTION, fg=FG_MUTED,
            wraplength=DIALOG_W - 50, justify=tk.LEFT, anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(8, 6))

        # Option: Skip
        tk.Radiobutton(
            frame,
            text="Skip — I will assign speakers manually later",
            variable=self._speaker_mode, value="skip",
            font=FONT_BODY, bg=BG_SECTION, fg=FG,
            activebackground=BG_SECTION, anchor="w",
            command=self._on_speaker_mode_changed,
        ).pack(fill=tk.X, **pad)

        # Option: Heuristic
        tk.Radiobutton(
            frame,
            text="Suggest speakers automatically",
            variable=self._speaker_mode, value="heuristic",
            font=FONT_BODY, bg=BG_SECTION, fg=FG,
            activebackground=BG_SECTION, anchor="w",
            command=self._on_speaker_mode_changed,
        ).pack(fill=tk.X, **pad)

        self._note(
            frame,
            "Labels are based on question patterns and response length.\n"
            "Suitable as a starting point — may need correction,\n"
            "especially for informal or conversational interviews.",
            bg="#fff8e1", fg="#5d4037",
        )

        # Option: Voice (pyannote)
        voice_frame = tk.Frame(frame, bg=BG_SECTION)
        voice_frame.pack(fill=tk.X, **pad)

        self._voice_radio = tk.Radiobutton(
            voice_frame,
            text="Detect speakers by voice  (more accurate)",
            variable=self._speaker_mode, value="voice",
            font=FONT_BODY, bg=BG_SECTION, fg=FG,
            activebackground=BG_SECTION, anchor="w",
            command=self._on_speaker_mode_changed,
            state=tk.NORMAL if self._diar_ready else tk.DISABLED,
        )
        self._voice_radio.pack(side=tk.LEFT)

        if not self._diar_ready:
            setup_link = tk.Label(
                voice_frame,
                text="  Set up",
                font=("Arial", 9, "underline"), bg=BG_SECTION,
                fg=FG_LINK, cursor="hand2",
            )
            setup_link.pack(side=tk.LEFT)
            setup_link.bind("<Button-1>", self._on_open_setup_wizard)

        # Status note for voice option
        if self._diar_ready:
            voice_note = (
                "Uses your computer's audio analysis — no data sent anywhere.\n"
                "Takes approximately as long as the recording itself on this computer."
            )
            note_bg, note_fg = "#e8f5e9", "#2e7d32"
        else:
            voice_note = (
                f"Not yet set up.  {self._diar_status}\n"
                "Click 'Set up' above to complete the one-time setup."
            )
            note_bg, note_fg = "#fafafa", "#888888"

        self._note(frame, voice_note, bg=note_bg, fg=note_fg)

        tk.Label(frame, text="", bg=BG_SECTION, height=1).pack()

    def _build_section_c(self):
        """Speaker name entry — shown/hidden based on speaker mode."""
        self._section_c_frame = self._section_frame("Speaker names")

        tk.Label(
            self._section_c_frame,
            text=(
                "Enter real names to replace the automatic labels.\n"
                "Leave blank to keep 'Speaker A' / 'Speaker B'."
            ),
            font=FONT_SMALL, bg=BG_SECTION, fg=FG_MUTED,
            wraplength=DIALOG_W - 50, justify=tk.LEFT, anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(8, 6))

        grid = tk.Frame(self._section_c_frame, bg=BG_SECTION)
        grid.pack(fill=tk.X, padx=12, pady=(0, 10))

        # Speaker A
        tk.Label(
            grid, text="Speaker A:",
            font=FONT_BODY, bg=BG_SECTION, fg=FG, width=12, anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=4)

        self._entry_a = tk.Entry(
            grid, textvariable=self._name_a,
            font=FONT_BODY, width=24,
            relief=tk.SOLID, bd=1,
        )
        self._entry_a.grid(row=0, column=1, sticky="w", padx=(6, 0), pady=4)

        tk.Label(
            grid, text="e.g. Margaret",
            font=FONT_SMALL, bg=BG_SECTION, fg=FG_MUTED,
        ).grid(row=0, column=2, sticky="w", padx=(8, 0))

        # Speaker B
        tk.Label(
            grid, text="Speaker B:",
            font=FONT_BODY, bg=BG_SECTION, fg=FG, width=12, anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=4)

        self._entry_b = tk.Entry(
            grid, textvariable=self._name_b,
            font=FONT_BODY, width=24,
            relief=tk.SOLID, bd=1,
        )
        self._entry_b.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=4)

        tk.Label(
            grid, text="e.g. Interviewer",
            font=FONT_SMALL, bg=BG_SECTION, fg=FG_MUTED,
        ).grid(row=1, column=2, sticky="w", padx=(8, 0))

        self._update_section_c_visibility()

    def _on_speaker_mode_changed(self, *_):
        self._update_section_c_visibility()

    def _update_section_c_visibility(self):
        """Show or hide Section C based on speaker mode."""
        mode = self._speaker_mode.get()
        if mode == "skip":
            self._section_c_frame.pack_forget()
        else:
            # Re-pack if not currently visible
            self._section_c_frame.pack(
                fill=tk.X, padx=14, pady=(10, 0),
                after=self._section_c_frame.master.winfo_children()[-2]
                if hasattr(self, '_progress_outer') else None,
            )

    def _build_progress_area(self):
        """Progress bar and status — hidden until cleanup runs."""
        self._progress_outer = tk.Frame(self._content, bg=BG)
        self._progress_outer.pack(fill=tk.X, padx=14, pady=(10, 4))

        self._progress_label = tk.Label(
            self._progress_outer, text="",
            font=FONT_SMALL, bg=BG, fg=FG_MUTED,
            anchor="w", wraplength=DIALOG_W - 40,
        )
        self._progress_label.pack(fill=tk.X)

        self._progress_bar = ttk.Progressbar(
            self._progress_outer,
            mode="indeterminate", length=DIALOG_W - 40,
        )
        # Not packed until cleanup starts

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_skip(self):
        """User chose Skip or closed the dialog."""
        self.result = None
        if self.result_callback:
            self.result_callback(None)
        self.win.destroy()

    def _on_run(self):
        """User clicked 'Clean up transcript'."""
        self._run_btn.config(state=tk.DISABLED, text="Running…")
        self._skip_btn.config(state=tk.DISABLED)

        # Show progress bar
        self._progress_bar.pack(fill=tk.X, pady=(4, 2))
        self._progress_bar.start(10)

        # Collect options
        do_cleanup      = self._do_cleanup.get()
        do_backchannels = self._do_backchannels.get()
        speaker_mode    = self._speaker_mode.get()
        name_a          = self._name_a.get().strip()
        name_b          = self._name_b.get().strip()

        name_map = {}
        if speaker_mode != "skip":
            if name_a:
                name_map["SPEAKER_A"] = name_a
                name_map["SPEAKER_00"] = name_a   # in case pyannote used
            if name_b:
                name_map["SPEAKER_B"] = name_b
                name_map["SPEAKER_01"] = name_b

        use_diarization = (speaker_mode == "voice")
        hf_token        = self._hf_token if use_diarization else None

        entries    = self.entries
        audio_path = self.audio_path

        def _run():
            try:
                import transcript_cleaner as tc

                if do_cleanup:
                    result = tc.clean_transcript(
                        entries          = entries,
                        audio_path       = audio_path,
                        hf_token         = hf_token,
                        name_map         = name_map if name_map else None,
                        use_diarization  = use_diarization,
                        keep_backchannels = do_backchannels,
                        progress_callback = self._progress,
                    )
                    cleaned_entries = tc.paragraphs_to_entries(
                        result["paragraphs"]
                    )
                    out = {
                        "entries":      cleaned_entries,
                        "audio_path":   result.get("audio_path", audio_path),
                        "speaker_ids":  result.get("speaker_ids", []),
                        "warnings":     result.get("warnings", []),
                        "diarization_used": result.get("diarization_used", False),
                    }
                else:
                    # User unchecked cleanup — just return entries unchanged
                    # but still apply name map if provided
                    out = {
                        "entries":      entries,
                        "audio_path":   audio_path,
                        "speaker_ids":  [],
                        "warnings":     [],
                        "diarization_used": False,
                    }

                self.win.after(0, self._on_done, out)

            except Exception as e:
                import traceback
                logger.error(f"Transcript cleanup error: {e}")
                logger.error(traceback.format_exc())
                self.win.after(0, self._on_error, str(e))

        threading.Thread(target=_run, daemon=True).start()

    def _progress(self, msg: str):
        """Called from background thread — schedule UI update."""
        def _update():
            self._progress_label.config(text=msg, fg=FG_MUTED)
        self.win.after(0, _update)

    def _on_done(self, result: Dict):
        """Called on main thread when cleanup completes successfully."""
        self._progress_bar.stop()
        self._progress_bar.config(mode="determinate")
        self._progress_bar["value"] = 100

        n = len(result.get("entries", []))
        self._progress_label.config(
            text=f"Done — {n} paragraphs ready.",
            fg=FG_SUCCESS,
        )

        # Show any warnings
        warnings = result.get("warnings", [])
        if warnings:
            for w in warnings:
                logger.warning(f"Transcript cleanup warning: {w}")
            messagebox.showwarning(
                "Cleanup note",
                "\n".join(warnings),
                parent=self.win,
            )

        self.result = result
        if self.result_callback:
            self.result_callback(result)

        # Brief pause so the user sees "Done" before the dialog closes
        self.win.after(900, self.win.destroy)

    def _on_error(self, error_msg: str):
        """Called on main thread when cleanup fails."""
        self._progress_bar.stop()
        self._progress_label.config(
            text=f"Cleanup failed: {error_msg}", fg=FG_ERROR
        )
        self._run_btn.config(
            state=tk.NORMAL, text="Try again",
            bg="#c62828", fg="white",
        )
        self._skip_btn.config(state=tk.NORMAL)
        messagebox.showerror(
            "Cleanup error",
            f"The transcript cleanup encountered an error:\n\n{error_msg}\n\n"
            "The transcript has been loaded without cleanup.",
            parent=self.win,
        )

    def _on_open_setup_wizard(self, _event=None):
        """Open the HuggingFace setup wizard from the setup link."""
        self.win.grab_release()
        try:
            from hf_setup_wizard import run_hf_setup_wizard

            def _save_token(token: str):
                if "keys" not in self.config:
                    self.config["keys"] = {}
                self.config["keys"]["HuggingFace"] = token

            token = run_hf_setup_wizard(self.parent, _save_token)
            if token:
                self._hf_token   = token
                self._diar_ready = self._check_diar_ready()
                # Refresh the dialog so the voice option becomes enabled
                self._refresh_voice_option()
        finally:
            self.win.grab_set()

    def _refresh_voice_option(self):
        """Re-enable the voice radio button if setup just completed."""
        if self._diar_ready:
            self._voice_radio.config(state=tk.NORMAL)
            self._speaker_mode.set("voice")
            self._on_speaker_mode_changed()


# ============================================================================
# CONVENIENCE FUNCTION  (called from document_fetching.py)
# ============================================================================

def show_transcript_cleanup_dialog(
        parent:          tk.Tk,
        entries:         List[Dict],
        audio_path:      Optional[str],
        config:          Dict,
        result_callback: Optional[Callable] = None,
) -> None:
    """
    Show the transcript cleanup dialog.

    This function returns immediately; the result is delivered
    asynchronously via result_callback when the user finishes.

    Args:
        parent:           DocAnalyser root Tk window.
        entries:          Raw faster-whisper entries list.
        audio_path:       Path to the original audio file (for seek links
                          and optional pyannote diarization).
        config:           DocAnalyser config dict.  Must contain
                          config["keys"]["HuggingFace"] if voice
                          diarization has been set up.
        result_callback:  function(result) called when done.
                          result is None if skipped, otherwise a dict:
                          {
                            "entries":     List[Dict],  cleaned entries
                            "audio_path":  str,
                            "speaker_ids": List[str],
                            "warnings":    List[str],
                            "diarization_used": bool,
                          }
    """
    dialog = TranscriptCleanupDialog(
        parent          = parent,
        entries         = entries,
        audio_path      = audio_path,
        config          = config,
        result_callback = result_callback,
    )
    parent.wait_window(dialog.win)


# ============================================================================
# STANDALONE PREVIEW
# ============================================================================

if __name__ == "__main__":
    import os, sys

    root = tk.Tk()
    root.title("DocAnalyser — Cleanup Dialog Preview")
    root.geometry("900x600")
    root.configure(bg="#f0f0f0")

    tk.Label(
        root, text="DocAnalyser (preview)",
        font=("Arial", 14), bg="#f0f0f0",
    ).pack(pady=20)

    result_label = tk.Label(root, text="", font=("Arial", 10), bg="#f0f0f0",
                             wraplength=800, justify=tk.LEFT)
    result_label.pack(pady=8, padx=20)

    # Load dummy entries if available
    dummy_entries = []
    dummy_path = os.path.join(os.path.dirname(__file__), "dummy_transcript.txt")
    if os.path.exists(dummy_path):
        try:
            sys.path.insert(0, os.path.dirname(__file__))
            import transcript_cleaner as tc
            dummy_entries = tc._parse_dummy_transcript(dummy_path)
            print(f"Loaded {len(dummy_entries)} dummy entries.")
        except Exception as e:
            print(f"Could not load dummy entries: {e}")

    if not dummy_entries:
        # Minimal synthetic entries for UI preview
        dummy_entries = [
            {"start": 0.5,  "end": 2.8,  "text": "Good morning and welcome.",
             "timestamp": "[00:00:00]"},
            {"start": 2.9,  "end": 3.2,  "text": "uh",
             "timestamp": "[00:00:02]"},
            {"start": 3.3,  "end": 6.1,
             "text": "Thank you so much for having me.",
             "timestamp": "[00:00:03]"},
        ]

    fake_config = {
        "keys": {"HuggingFace": ""},
        "timestamp_interval": "every_segment",
    }

    def _on_result(result):
        if result is None:
            result_label.config(text="User skipped cleanup.", fg="#c62828")
        else:
            n     = len(result.get("entries", []))
            spks  = result.get("speaker_ids", [])
            diar  = result.get("diarization_used", False)
            warns = result.get("warnings", [])
            result_label.config(
                text=(
                    f"Cleanup complete.  {n} paragraphs.\n"
                    f"Speakers: {spks}\n"
                    f"Diarization used: {diar}\n"
                    f"Warnings: {warns}"
                ),
                fg="#2e7d32",
            )

    def _open():
        show_transcript_cleanup_dialog(
            parent          = root,
            entries         = dummy_entries,
            audio_path      = None,
            config          = fake_config,
            result_callback = _on_result,
        )

    tk.Button(
        root, text="Open Cleanup Dialog",
        command=_open,
        font=("Arial", 11), padx=16, pady=8,
    ).pack(pady=10)

    root.mainloop()
