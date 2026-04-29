"""
transcript_cleanup_dialog.py
==============================
Post-transcription options dialog shown after a faster-whisper transcription
completes.  Offers cleanup and speaker identification options, runs the
processing pipeline in a background thread, then delivers cleaned entries via
callback.

Modality: Non-modal (intentional) — runs independently so DocAnalyser remains
usable during long pyannote runs.

Routing
-------
After cleanup (or skip), the dialog shows two routing buttons:
  • "Thread Viewer"  — result passed with routing="thread_viewer"
  • "Microsoft Word" — result passed with routing="word"

Result dict schema (always a dict, never None):
{
    "entries":             List[Dict],   # cleaned entries (absent if skipped)
    "audio_path":          str or None,
    "speaker_ids":         List[str],
    "diarization_used":    bool,
    "warnings":            List[str],
    "corrections_applied": int,          # v1.7-alpha: total hits from
                                          # Phase 3 corrections list (0 if
                                          # none selected or skipped).
    "routing":             str,          # "thread_viewer" or "word"
    "skipped":             bool,         # True when user skipped cleanup
}
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Dict, Optional, Callable


# ── Feature flag ──────────────────────────────────────────────────────────────
# Voice-based speaker detection requires pyannote.audio + GPU.
# Disabled for general release.  Set to True to re-enable.
PYANNOTE_ENABLED = False


# =============================================================================
# Public entry point
# =============================================================================

def show_transcript_cleanup_dialog(
    parent,
    entries:         List[Dict],
    audio_path:      Optional[str],
    config:          dict,
    result_callback: Callable,
) -> "TranscriptCleanupDialog":
    """
    Open the cleanup dialog (non-modal) and return the instance.

    result_callback(result_dict) is called when the user finishes — either
    after cleanup completes or after clicking Skip — followed by a routing
    choice.  result_dict always contains a "routing" key and a "skipped" key.
    """
    dlg = TranscriptCleanupDialog(
        parent, entries, audio_path, config, result_callback
    )
    return dlg


# =============================================================================
# Dialog class
# =============================================================================

class TranscriptCleanupDialog:
    """
    Post-transcription cleanup + speaker identification dialog.

    Layout
    ------
    Title / segment count
    Section A — Cleanup options      (always shown)
    Section B — Speaker ID mode      (choose one radio button)
    Section C — Speaker names        (shown when B != skip)
    Progress area                    (shown while cleanup is running)
    Button row                       (Run / Skip -> then replaced by routing btns)
    """

    def __init__(
        self,
        parent,
        entries:         List[Dict],
        audio_path:      Optional[str],
        config:          dict,
        result_callback: Callable,
    ):
        self._parent          = parent
        self._entries         = entries
        self._audio_path      = audio_path
        self._config          = config
        self._result_callback = result_callback

        self._running        = False
        self._start_time     = 0.0
        self._timer_job: Optional[str] = None
        self._cleanup_result: Optional[dict] = None

        self._build_window()

    # =========================================================================
    # Window construction
    # =========================================================================

    def _build_window(self):
        self.win = tk.Toplevel(self._parent)
        self.win.title("Transcript Clean-up")
        self.win.resizable(True, True)        # v1.7-alpha: was False, False
        self.win.minsize(440, 480)
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

        # Position abutting the LEFT border of the main UI window
        # (consistent with other Settings dialogs in DocAnalyser).
        # Default height is the dialog's natural content size; the
        # dialog is resizable so the user can stretch it taller if
        # desired. Walks up to the root Tk window in case our parent
        # is itself a Toplevel.
        self.win.update_idletasks()
        w = 470
        h = 460        # natural content size; avoids whitespace below buttons
        try:
            anchor = self._parent
            while anchor.master is not None:
                anchor = anchor.master
            a_x = anchor.winfo_x()
            a_y = anchor.winfo_y()
            # Right edge of dialog meets left edge of main UI.
            px = a_x - w
            py = a_y
            if px < 0:
                # Off-screen left — fall back to centred-on-anchor.
                px = a_x + (anchor.winfo_width() - w) // 2
            self.win.geometry(f"{w}x{h}+{max(0, px)}+{max(0, py)}")
        except Exception:
            self.win.geometry(f"{w}x{h}")

        outer = tk.Frame(self.win, padx=14, pady=10)
        outer.pack(fill=tk.BOTH, expand=True)

        # ── Title ─────────────────────────────────────────────────────────────
        tk.Label(
            outer,
            text="Transcription complete",
            font=("Segoe UI", 12, "bold"),
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 2))

        n = len(self._entries)
        tk.Label(
            outer,
            text=f"{n} segment{'s' if n != 1 else ''} transcribed.  "
                 "Choose options below.",
            font=("Segoe UI", 9),
            fg="#555555",
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 8))

        self._build_section_a(outer)
        self._build_section_b(outer)
        self._build_section_c(outer)
        self._build_progress(outer)
        self._build_buttons(outer)

    # -------------------------------------------------------------------------
    # Section A — Cleanup options
    # -------------------------------------------------------------------------

    def _build_section_a(self, parent):
        frame = tk.LabelFrame(parent, text=" A — Cleanup ", padx=8, pady=6)
        frame.pack(fill=tk.X, pady=(0, 6))

        self._remove_fillers_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            frame,
            text="Remove breath fragments  (uh, um, mm, hmm\u2026)",
            variable=self._remove_fillers_var,
            command=self._on_filler_toggle,
        ).pack(anchor="w")

        self._keep_backchannels_var = tk.BooleanVar(value=True)
        self._bc_cb = tk.Checkbutton(
            frame,
            text="  Keep listener back-channels as [annotations]",
            variable=self._keep_backchannels_var,
        )
        self._bc_cb.pack(anchor="w", padx=(16, 0))

        # ---- Corrections list row (v1.7-alpha) -----------------------------
        # Adds a dropdown of available Corrections Lists (find-and-replace
        # rules applied during Phase 3 of clean_transcript).  The default
        # selection is the bundled "General" list; "(none\u2014skip)" disables
        # the phase entirely.  The Edit lists\u2026 button opens the
        # management dialog when it is available (Day 5+); until then it
        # shows a 'coming soon' notice.
        corr_row = tk.Frame(frame)
        corr_row.pack(fill=tk.X, anchor="w", pady=(8, 0))

        tk.Label(
            corr_row, text="Corrections list:", anchor="w"
        ).pack(side=tk.LEFT)

        self._corrections_list_var = tk.StringVar()
        self._corrections_combo = ttk.Combobox(
            corr_row,
            textvariable=self._corrections_list_var,
            state="readonly",
            width=22,
        )
        self._corrections_combo.pack(side=tk.LEFT, padx=(6, 6))

        self._edit_lists_btn = tk.Button(
            corr_row,
            text="Edit lists\u2026",
            command=self._on_edit_lists,
        )
        self._edit_lists_btn.pack(side=tk.LEFT)

        self._populate_corrections_combo()

    # ----------------------------------------------------------------
    # Corrections list helpers (v1.7-alpha)
    # ----------------------------------------------------------------

    def _populate_corrections_combo(self):
        """
        Load available Corrections Lists into the dropdown.

        Defensive: if corrections_db_adapter is missing, the database is
        not migrated, or the call raises for any other reason, the only
        option presented is "(none \u2014 skip)" \u2014 the cleanup dialog
        still works, just without corrections.

        Default selection logic:
          * If a list named "General" exists, select it (the bundled list
            with starter rules for common transcription errors).
          * Otherwise select "(none \u2014 skip)" so behaviour matches the
            pre-v1.7 pipeline.
        Called both at construction time and after the management dialog
        closes (Day 5+) so newly-created lists appear immediately.
        """
        # First option always available, regardless of database state
        self._available_lists = [("(none \u2014 skip)", None)]

        try:
            from corrections_db_adapter import list_get_all
            for lst in list_get_all():
                self._available_lists.append((lst["name"], lst["id"]))
        except Exception as exc:
            import logging
            logging.warning(
                "Could not load Corrections Lists for cleanup dialog: %s", exc
            )

        labels = [label for label, _ in self._available_lists]
        self._corrections_combo["values"] = labels

        # Default to "General" if present, otherwise the (none) option
        default_idx = 0
        for i, (label, _) in enumerate(self._available_lists):
            if label == "General":
                default_idx = i
                break
        self._corrections_combo.current(default_idx)

    def _resolve_corrections_list_id(self) -> Optional[int]:
        """
        Return the corrections_list_id that should be passed to
        clean_transcript() based on the current dropdown selection.
        Returns None when "(none \u2014 skip)" is selected or when the
        selection cannot be matched (defensive).
        """
        label = self._corrections_list_var.get()
        for lst_label, lst_id in self._available_lists:
            if lst_label == label:
                return lst_id
        return None

    def _on_edit_lists(self):
        """
        Open the Corrections Lists management dialog (Day 5+).

        The dialog refreshes the dropdown on close so any new/renamed/
        deleted lists appear immediately.  Until the management module
        ships, the button shows a 'coming soon' notice.
        """
        try:
            from corrections_management_dialog import (
                show_corrections_management_dialog,
            )
        except ImportError:
            messagebox.showinfo(
                "Coming soon",
                "Corrections list management is being added in the next "
                "release.\n\n"
                "For now, the bundled \"General\" list is available with "
                "starter rules for common transcription errors. Select it "
                "from the dropdown to apply those rules during cleanup, or "
                "choose \"(none\u2014skip)\" to skip the corrections phase.",
                parent=self.win,
            )
            return

        try:
            show_corrections_management_dialog(
                self.win,
                on_close=self._populate_corrections_combo,
            )
        except Exception as exc:
            import logging, traceback
            logging.error(
                "Failed to open corrections management dialog:\n"
                + traceback.format_exc()
            )
            messagebox.showerror(
                "Could not open management dialog",
                f"The corrections list management dialog could not be "
                f"opened:\n\n{exc}",
                parent=self.win,
            )

    def _on_filler_toggle(self):
        """Disable back-channel option when filler removal is off."""
        if self._remove_fillers_var.get():
            self._bc_cb.config(state=tk.NORMAL)
        else:
            self._keep_backchannels_var.set(False)
            self._bc_cb.config(state=tk.DISABLED)

    # -------------------------------------------------------------------------
    # Section B — Speaker identification mode
    # -------------------------------------------------------------------------

    def _build_section_b(self, parent):
        frame = tk.LabelFrame(
            parent, text=" B — Speaker identification ", padx=8, pady=6
        )
        frame.pack(fill=tk.X, pady=(0, 6))

        self._speaker_mode = tk.StringVar(value="skip")
        self._speaker_mode.trace_add("write", lambda *_: self._on_mode_change())

        tk.Radiobutton(
            frame,
            text="Skip \u2014 assign manually later",
            variable=self._speaker_mode,
            value="skip",
        ).pack(anchor="w")

        tk.Radiobutton(
            frame,
            text="Suggest speakers automatically  (heuristic, provisional)",
            variable=self._speaker_mode,
            value="heuristic",
        ).pack(anchor="w")

        # Voice detection row
        voice_row = tk.Frame(frame)
        voice_row.pack(fill=tk.X, anchor="w")

        if PYANNOTE_ENABLED:
            diar_ready = self._check_diar_ready()
            state = tk.NORMAL if diar_ready else tk.DISABLED
            self._voice_rb = tk.Radiobutton(
                voice_row,
                text="Detect speakers by voice",
                variable=self._speaker_mode,
                value="voice",
                state=state,
            )
            self._voice_rb.pack(side=tk.LEFT)

            if not diar_ready:
                lbl = tk.Label(
                    voice_row,
                    text=" [Set up]",
                    fg="blue",
                    cursor="hand2",
                    font=("Segoe UI", 9, "underline"),
                )
                lbl.pack(side=tk.LEFT)
                lbl.bind("<Button-1>", lambda _e: self._on_open_setup_wizard())
            else:
                tk.Label(
                    voice_row,
                    text=" \u2714 ready",
                    fg="#228822",
                    font=("Segoe UI", 9),
                ).pack(side=tk.LEFT)
        else:
            # PYANNOTE_ENABLED = False — disabled with a note, no "Set up" link
            self._voice_rb = tk.Radiobutton(
                voice_row,
                text="Detect speakers by voice",
                variable=self._speaker_mode,
                value="voice",
                state=tk.DISABLED,
            )
            self._voice_rb.pack(side=tk.LEFT)
            tk.Label(
                voice_row,
                text="  (not available \u2014 see Help for setup)",
                fg="#888888",
                font=("Segoe UI", 8),
            ).pack(side=tk.LEFT)

    # -------------------------------------------------------------------------
    # Section C — Speaker names
    # -------------------------------------------------------------------------

    def _build_section_c(self, parent):
        self._section_c = tk.LabelFrame(
            parent, text=" C \u2014 Speaker names ", padx=8, pady=6
        )
        # Not packed initially — toggled by _on_mode_change()

        self._speaker_a_var = tk.StringVar()
        self._speaker_b_var = tk.StringVar()

        row_a = tk.Frame(self._section_c)
        row_a.pack(fill=tk.X, pady=2)
        tk.Label(row_a, text="Speaker 1:", width=10, anchor="w").pack(side=tk.LEFT)
        tk.Entry(
            row_a, textvariable=self._speaker_a_var, width=24
        ).pack(side=tk.LEFT, padx=4)

        row_b = tk.Frame(self._section_c)
        row_b.pack(fill=tk.X, pady=2)
        tk.Label(row_b, text="Speaker 2:", width=10, anchor="w").pack(side=tk.LEFT)
        tk.Entry(
            row_b, textvariable=self._speaker_b_var, width=24
        ).pack(side=tk.LEFT, padx=4)

        tk.Label(
            self._section_c,
            text="Names are optional \u2014 you can assign speakers after cleanup.",
            font=("Segoe UI", 8),
            fg="#666666",
            anchor="w",
        ).pack(fill=tk.X, pady=(4, 0))

    def _on_mode_change(self):
        """Show or hide Section C depending on chosen speaker mode."""
        if self._speaker_mode.get() == "skip":
            self._section_c.pack_forget()
        else:
            self._section_c.pack(fill=tk.X, pady=(0, 6))

    # -------------------------------------------------------------------------
    # Progress area
    # -------------------------------------------------------------------------

    def _build_progress(self, parent):
        self._progress_frame = tk.Frame(parent)
        # Not packed initially — shown when cleanup starts

        self._progress_bar = ttk.Progressbar(
            self._progress_frame,
            mode="indeterminate",
            length=430,
        )
        self._progress_bar.pack(fill=tk.X, pady=(0, 2))

        self._elapsed_var = tk.StringVar(value="")
        tk.Label(
            self._progress_frame,
            textvariable=self._elapsed_var,
            font=("Segoe UI", 8),
            fg="#555555",
            anchor="w",
        ).pack(fill=tk.X)

    def _show_progress(self):
        self._progress_frame.pack(fill=tk.X, pady=(4, 0))
        self._progress_bar.start(12)
        self._start_time = time.time()
        self._tick_timer()

    def _hide_progress(self):
        self._progress_bar.stop()
        if self._timer_job:
            try:
                self.win.after_cancel(self._timer_job)
            except Exception:
                pass
            self._timer_job = None
        self._progress_frame.pack_forget()

    def _tick_timer(self):
        elapsed = time.time() - self._start_time
        self._elapsed_var.set(f"Elapsed: {elapsed:.1f}s")
        self._timer_job = self.win.after(500, self._tick_timer)

    # -------------------------------------------------------------------------
    # Button row
    # -------------------------------------------------------------------------

    def _build_buttons(self, parent):
        self._btn_frame = tk.Frame(parent)
        self._btn_frame.pack(fill=tk.X, pady=(12, 0))

        self._run_btn = tk.Button(
            self._btn_frame,
            text="Run Cleanup",
            command=self._on_run,
            width=14,
        )
        self._run_btn.pack(side=tk.LEFT, padx=(0, 6))

        self._skip_btn = tk.Button(
            self._btn_frame,
            text="Skip cleanup",
            command=self._on_skip,
            width=14,
        )
        self._skip_btn.pack(side=tk.LEFT)

    # =========================================================================
    # Actions
    # =========================================================================

    def _on_run(self):
        """Validate options and launch the cleanup background thread."""
        if self._running:
            return

        mode        = self._speaker_mode.get()
        remove_fill = self._remove_fillers_var.get()
        keep_bc     = self._keep_backchannels_var.get() and remove_fill

        # Build name_map from Section C entries
        name_map: Dict[str, str] = {}
        if mode != "skip":
            a = self._speaker_a_var.get().strip()
            b = self._speaker_b_var.get().strip()
            if a:
                name_map["SPEAKER_A"] = a
            if b:
                name_map["SPEAKER_B"] = b

        use_diar = (
            mode == "voice"
            and PYANNOTE_ENABLED
            and self._check_diar_ready()
        )

        # Resolve Corrections List selection (v1.7-alpha).
        # Captured here on the main thread so the value is read while
        # Tkinter variables are still safe to access from this scope.
        corrections_list_id = self._resolve_corrections_list_id()

        # Disable buttons during processing
        self._run_btn.config(state=tk.DISABLED)
        self._skip_btn.config(state=tk.DISABLED)
        self._running = True
        self._show_progress()

        # ── Worker thread ──────────────────────────────────────────────────
        def _worker():
            try:
                from transcript_cleaner import (
                    clean_transcript,
                    paragraphs_to_entries,
                )
                hf_token = (
                    self._config.get("huggingface_token") if use_diar else None
                )
                raw = clean_transcript(
                    entries=self._entries,
                    audio_path=self._audio_path,
                    hf_token=hf_token,
                    name_map=name_map,
                    use_diarization=use_diar,
                    keep_backchannels=keep_bc,
                    corrections_list_id=corrections_list_id,
                )
                cleaned = paragraphs_to_entries(raw.get("paragraphs", []))
                result_dict = {
                    "entries":             cleaned,
                    "audio_path":          self._audio_path,
                    "speaker_ids":         raw.get("speaker_ids", []),
                    "diarization_used":    raw.get("diarization_used", False),
                    "warnings":            raw.get("warnings", []),
                    "corrections_applied": raw.get("corrections_applied", 0),
                    "skipped":             False,
                }
                self.win.after(0, lambda: self._on_complete(result_dict))

            except Exception as exc:
                import traceback as _tb
                err = _tb.format_exc()
                self.win.after(0, lambda: self._on_run_error(str(exc), err))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_run_error(self, short_msg: str, full_trace: str):
        """Called on main thread when the worker raises an exception."""
        self._running = False
        self._hide_progress()
        self._run_btn.config(state=tk.NORMAL)
        self._skip_btn.config(state=tk.NORMAL)

        import logging
        logging.error(f"Transcript cleanup error:\n{full_trace}")

        messagebox.showerror(
            "Cleanup error",
            f"Cleanup failed:\n\n{short_msg}\n\n"
            "The raw transcript has been kept.  You can skip cleanup and\n"
            "continue with the unprocessed transcript.",
            parent=self.win,
        )

    def _on_complete(self, result_dict: dict):
        """
        Called on main thread after the worker finishes successfully.
        Shows a brief 'Done' confirmation, then reveals routing buttons
        after 600 ms so the user can see something happened.
        """
        self._running = False
        self._hide_progress()
        self._cleanup_result = result_dict

        # Visual confirmation that processing finished
        self._run_btn.config(state=tk.DISABLED, text="Done \u2714")
        self._skip_btn.config(state=tk.DISABLED)

        self.win.after(600, lambda: self._show_routing_choice(result_dict))

    def _on_skip(self):
        """
        User clicked Skip cleanup.
        Show routing buttons immediately — cleanup result will be skipped=True.
        """
        # Prevent double-click
        self._run_btn.config(state=tk.DISABLED)
        self._skip_btn.config(state=tk.DISABLED)

        skip_result: dict = {"skipped": True}
        self._show_routing_choice(skip_result)

    def _show_routing_choice(self, result: dict):
        """
        Replace the Run/Skip button row with routing buttons:
          "Thread Viewer"  and  "Microsoft Word"

        The chosen button fires _result_callback with result + routing field
        injected, then destroys the dialog.
        """
        # Clear existing button-row widgets
        for widget in self._btn_frame.winfo_children():
            widget.destroy()

        tk.Label(
            self._btn_frame,
            text="Open in:",
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 8))

        def _route(routing: str):
            result["routing"] = routing
            # Destroy window first so focus returns to DocAnalyser cleanly,
            # then fire callback.
            self.win.after(80, self.win.destroy)
            try:
                self._result_callback(result)
            except Exception:
                import logging, traceback
                logging.error(
                    "result_callback raised in cleanup routing:\n"
                    + traceback.format_exc()
                )

        tk.Button(
            self._btn_frame,
            text="Thread Viewer",
            command=lambda: _route("thread_viewer"),
            width=14,
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            self._btn_frame,
            text="Microsoft Word",
            command=lambda: _route("word"),
            width=14,
        ).pack(side=tk.LEFT)

    def _on_close(self):
        """
        Window closed via the x button.
        Treat as skip + thread_viewer routing so the raw transcript
        remains loaded and usable.
        Blocked while cleanup is actively running (avoids partial state).
        """
        if self._running:
            return   # Don't allow close during active processing

        try:
            self._result_callback({
                "skipped": True,
                "routing": "thread_viewer",
            })
        except Exception:
            pass
        self.win.destroy()

    # =========================================================================
    # Pyannote / diarization helpers
    # =========================================================================

    def _check_diar_ready(self) -> bool:
        """
        Returns True only when PYANNOTE_ENABLED is True and all prerequisites
        are met (pyannote installed, torch available, HF token set, model
        cached).  Short-circuits to False when PYANNOTE_ENABLED = False.
        """
        if not PYANNOTE_ENABLED:
            return False
        try:
            from diarization_handler import is_available
            hf_token = self._config.get("huggingface_token", "")
            return is_available(hf_token)
        except ImportError:
            return False

    def _get_diar_status(self) -> str:
        """
        Human-readable status string for voice detection readiness.
        Short-circuits when PYANNOTE_ENABLED = False.
        """
        if not PYANNOTE_ENABLED:
            return "disabled"
        try:
            from diarization_handler import get_status
            hf_token = self._config.get("huggingface_token", "")
            info = get_status(hf_token)
            return info.get("message", "unknown")
        except ImportError:
            return "diarization_handler not found"

    def _on_open_setup_wizard(self):
        """
        Launch HuggingFace setup wizard.
        Only reachable from UI when PYANNOTE_ENABLED = True.
        """
        try:
            from hf_setup_wizard import run_hf_setup_wizard
            token = run_hf_setup_wizard(
                self.win,
                config_save_callback=lambda t: self._config.__setitem__(
                    "huggingface_token", t
                ),
            )
            if token:
                self._refresh_voice_option()
        except ImportError:
            messagebox.showerror(
                "Setup unavailable",
                "HuggingFace setup wizard could not be found.",
                parent=self.win,
            )

    def _refresh_voice_option(self):
        """
        Re-enable the voice radio button after successful HF setup.
        No-op when PYANNOTE_ENABLED = False.
        """
        if not PYANNOTE_ENABLED:
            return
        if self._check_diar_ready():
            try:
                self._voice_rb.config(state=tk.NORMAL)
            except Exception:
                pass
