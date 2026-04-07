"""
companion_player.py
====================
DocAnalyser Companion Audio Player.

A lightweight audio player designed to sit alongside Microsoft Word while
the user edits a transcript.  The user reads timestamps in the Word document
(e.g. [04:23]) and types them into the Jump field to seek instantly.

No URL scheme, no named pipe, no HTTP server.  Fully standalone.

Usage:
    python companion_player.py "C:/path/to/audio.m4a"
    python companion_player.py          # opens a file picker

Dependencies:
    pip install pygame

Author: DocAnalyser Development Team
"""

from __future__ import annotations

import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional

# ── Audio engine ──────────────────────────────────────────────────────────────
try:
    import pygame
    pygame.mixer.init()
    PYGAME_OK = True
except ImportError:
    PYGAME_OK = False

# ── Appearance ────────────────────────────────────────────────────────────────
BG         = "#2b2b2b"   # dark background — visible alongside white Word doc
FG         = "#e8e8e8"
FG_DIM     = "#888888"
FG_TIME    = "#ffffff"
ACCENT     = "#4a9eff"
BTN_BG     = "#3c3c3c"
BTN_ACTIVE = "#505050"
FONT_BODY  = ("Segoe UI", 9)
FONT_TIME  = ("Consolas", 20, "bold")
FONT_JUMP  = ("Consolas", 11)
FONT_BTN   = ("Segoe UI", 9)
WIN_W      = 420
WIN_H      = 220


def _fmt_time(seconds: float) -> str:
    """Format seconds as MM:SS or H:MM:SS."""
    s = max(0, int(round(seconds)))
    if s >= 3600:
        return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"
    return f"{s // 60:02d}:{s % 60:02d}"


def _parse_time(text: str) -> Optional[float]:
    """
    Parse a time string entered by the user into seconds.

    Accepts:
        4:23     →  263.0   (MM:SS)
        1:04:23  →  3863.0  (H:MM:SS)
        263      →  263.0   (raw seconds)
        4.23     →  4.23    (decimal seconds — not MM:SS!)
    Returns None if the string cannot be parsed.
    """
    text = text.strip()
    if not text:
        return None
    # H:MM:SS or MM:SS
    if ":" in text:
        parts = text.split(":")
        try:
            parts = [int(p) for p in parts]
        except ValueError:
            return None
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        return None
    # Numeric (seconds)
    try:
        return float(text)
    except ValueError:
        return None


class CompanionPlayer:
    """Compact audio player with jump-to-time capability."""

    def __init__(self, root: tk.Tk, initial_audio: Optional[str] = None):
        self.root             = root
        self._audio_path      = None
        self._mp3_path        = None     # ffmpeg-converted temp file
        self._duration        = 0.0
        self._playing         = False
        self._position        = 0.0      # current playback position in seconds
        self._play_start_wall = 0.0      # wall-clock time when play started
        self._play_start_pos  = 0.0      # position (secs) when play started
        self._slider_dragging = False    # True while user drags the slider
        self._loading         = False    # True while ffmpeg conversion runs

        self._build_ui()
        self._poll_position()            # start the 200 ms update loop

        if initial_audio and os.path.isfile(initial_audio):
            self.root.after(150, lambda: self._load_audio(initial_audio))

    # =========================================================================
    # UI construction
    # =========================================================================

    def _build_ui(self):
        self.root.title("DocAnalyser Player")
        self.root.resizable(False, False)
        self.root.geometry(f"{WIN_W}x{WIN_H}")
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)   # float above Word
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        pad = dict(padx=10, pady=4)

        # ── File name label ───────────────────────────────────────────────────
        self._file_var = tk.StringVar(value="No file loaded")
        tk.Label(
            self.root, textvariable=self._file_var,
            bg=BG, fg=FG_DIM, font=FONT_BODY,
            anchor="w", wraplength=WIN_W - 20,
        ).pack(fill=tk.X, padx=10, pady=(8, 0))

        # ── Large position / duration display ─────────────────────────────────
        time_frame = tk.Frame(self.root, bg=BG)
        time_frame.pack(fill=tk.X, padx=10, pady=(2, 0))

        self._pos_var = tk.StringVar(value="00:00")
        tk.Label(
            time_frame, textvariable=self._pos_var,
            bg=BG, fg=FG_TIME, font=FONT_TIME,
        ).pack(side=tk.LEFT)

        self._dur_var = tk.StringVar(value=" / 00:00")
        tk.Label(
            time_frame, textvariable=self._dur_var,
            bg=BG, fg=FG_DIM, font=("Consolas", 12),
            anchor="sw",
        ).pack(side=tk.LEFT, pady=(6, 0))

        # ── Slider (draggable scrub bar) ──────────────────────────────────────
        self._slider_var = tk.DoubleVar(value=0.0)
        self._slider = ttk.Scale(
            self.root,
            from_=0.0, to=1000.0,
            orient=tk.HORIZONTAL,
            variable=self._slider_var,
            command=self._on_slider_move,
        )
        self._slider.pack(fill=tk.X, padx=10, pady=(0, 4))
        self._slider.bind("<ButtonPress-1>",   self._on_slider_press)
        self._slider.bind("<ButtonRelease-1>", self._on_slider_release)

        # ── Playback buttons ──────────────────────────────────────────────────
        btn_frame = tk.Frame(self.root, bg=BG)
        btn_frame.pack(pady=(0, 4))

        def _btn(parent, text, cmd, width=7):
            b = tk.Button(
                parent, text=text, command=cmd,
                bg=BTN_BG, fg=FG, activebackground=BTN_ACTIVE,
                activeforeground=FG, relief=tk.FLAT,
                font=FONT_BTN, width=width, cursor="hand2",
                highlightthickness=0, bd=0, padx=4, pady=3,
            )
            b.pack(side=tk.LEFT, padx=3)
            return b

        _btn(btn_frame, "⏮ −30s",  self._seek_back30, width=7)
        _btn(btn_frame, "−10s",    self._seek_back10,  width=5)
        self._play_btn = _btn(btn_frame, "▶  Play", self._toggle_play, width=8)
        _btn(btn_frame, "+10s",    self._seek_fwd10,   width=5)
        _btn(btn_frame, "+30s ⏭",  self._seek_fwd30,   width=7)

        # ── Jump-to-time row ──────────────────────────────────────────────────
        jump_frame = tk.Frame(self.root, bg=BG)
        jump_frame.pack(fill=tk.X, padx=10, pady=(2, 6))

        tk.Label(
            jump_frame, text="Jump to:", bg=BG, fg=FG,
            font=FONT_BODY,
        ).pack(side=tk.LEFT)

        self._jump_var = tk.StringVar()
        self._jump_entry = tk.Entry(
            jump_frame,
            textvariable=self._jump_var,
            width=8, font=FONT_JUMP,
            bg="#3c3c3c", fg=FG_TIME,
            insertbackground=FG_TIME,
            relief=tk.FLAT, bd=3,
        )
        self._jump_entry.pack(side=tk.LEFT, padx=(6, 4))
        self._jump_entry.bind("<Return>",  self._on_jump)
        self._jump_entry.bind("<KP_Enter>",self._on_jump)

        self._jump_btn = tk.Button(
            jump_frame, text="Go",
            command=self._on_jump,
            bg=ACCENT, fg="#ffffff", activebackground="#5aadff",
            activeforeground="#ffffff", relief=tk.FLAT,
            font=FONT_BTN, width=4, cursor="hand2",
            highlightthickness=0, bd=0, padx=4, pady=2,
        )
        self._jump_btn.pack(side=tk.LEFT)

        tk.Label(
            jump_frame, text=" e.g.  4:23  or  1:04:23",
            bg=BG, fg=FG_DIM, font=("Segoe UI", 8),
        ).pack(side=tk.LEFT, padx=(8, 0))

        # Open file button — right-aligned in same row
        tk.Button(
            jump_frame, text="📂 Open file",
            command=self._browse,
            bg=BTN_BG, fg=FG, activebackground=BTN_ACTIVE,
            activeforeground=FG, relief=tk.FLAT,
            font=FONT_BTN, cursor="hand2",
            highlightthickness=0, bd=0, padx=6, pady=2,
        ).pack(side=tk.RIGHT)

        # ── Status bar ────────────────────────────────────────────────────────
        self._status_var = tk.StringVar(value="Open an audio file to begin.")
        tk.Label(
            self.root, textvariable=self._status_var,
            bg=BG, fg=FG_DIM, font=("Segoe UI", 8),
            anchor="w",
        ).pack(fill=tk.X, padx=10, pady=(0, 6))

    # =========================================================================
    # File loading
    # =========================================================================

    def _browse(self):
        """Open a file picker to choose an audio file."""
        self.root.attributes("-topmost", False)
        try:
            path = filedialog.askopenfilename(
                title="Open audio file",
                filetypes=[
                    ("Audio files", "*.mp3 *.m4a *.wav *.ogg *.aac *.flac *.wma"),
                    ("All files", "*.*"),
                ],
            )
        finally:
            self.root.attributes("-topmost", True)
        if path:
            self._load_audio(os.path.normpath(path))

    def _load_audio(self, path: str):
        """Load an audio file, converting via ffmpeg if necessary."""
        if not PYGAME_OK:
            messagebox.showerror(
                "pygame not installed",
                "The audio player requires pygame.\n\n"
                "Install it with:\n    pip install pygame",
            )
            return

        if self._loading:
            return   # already loading — ignore re-entrant calls

        self._loading = True
        self._set_status(f"Loading {os.path.basename(path)}…")
        self.root.update_idletasks()

        def _do_load():
            # Derive a stable cache path so we only convert once per file.
            try:
                import hashlib
                cache_dir = os.path.join(
                    os.getenv("APPDATA") or os.path.expanduser("~"),
                    "DocAnalyser_Beta", "audio_cache",
                )
                os.makedirs(cache_dir, exist_ok=True)
                key      = hashlib.md5(path.encode()).hexdigest()[:12]
                mp3_path = os.path.join(cache_dir, f"player_{key}.mp3")
            except Exception:
                import tempfile
                mp3_path = tempfile.mktemp(suffix=".mp3")

            # Only convert if the cache file doesn't already exist.
            if not os.path.exists(mp3_path):
                try:
                    _run_ffmpeg([
                        "ffmpeg", "-y", "-i", path,
                        "-q:a", "2", mp3_path,
                    ])
                except Exception:
                    mp3_path = path    # fall back to original if ffmpeg unavailable

            load_path = mp3_path
            try:
                pygame.mixer.music.load(load_path)
            except Exception as e:
                msg = str(e)
                self.root.after(0, lambda: self._set_status(f"Cannot load: {msg}"))
                self.root.after(0, lambda: setattr(self, "_loading", False))
                return

            # Measure duration.
            duration = 0.0
            try:
                snd      = pygame.mixer.Sound(load_path)
                duration = snd.get_length()
                del snd
            except Exception:
                pass

            def _apply():
                if self._playing:
                    pygame.mixer.music.stop()
                    self._playing = False

                self._audio_path      = path
                self._mp3_path        = mp3_path if mp3_path != path else None
                self._duration        = duration
                self._position        = 0.0
                self._play_start_pos  = 0.0
                self._play_start_wall = 0.0
                self._loading         = False

                self._file_var.set(os.path.basename(path))
                self._dur_var.set(f" / {_fmt_time(duration)}")
                self._pos_var.set("00:00")
                self._slider_var.set(0.0)
                self._update_play_btn()
                self._set_status("Ready.  Type a timestamp in 'Jump to' or press Play.")

            self.root.after(0, _apply)

        threading.Thread(target=_do_load, daemon=True).start()

    # =========================================================================
    # Playback controls
    # =========================================================================

    def _toggle_play(self):
        if not PYGAME_OK:
            return
        if not self._audio_path:
            self._browse()
            return

        if self._playing:
            pygame.mixer.music.pause()
            # Capture position precisely at the moment of pause.
            elapsed        = time.time() - self._play_start_wall
            self._position = min(self._play_start_pos + elapsed, self._duration)
            self._playing  = False
            self._set_status(f"Paused at {_fmt_time(self._position)}")
        else:
            pygame.mixer.music.unpause()
            self._play_start_pos  = self._position
            self._play_start_wall = time.time()
            self._playing         = True
            self._set_status(f"Playing from {_fmt_time(self._position)}")

        self._update_play_btn()

    def _seek(self, seconds: float):
        """Seek to an absolute position and start playing."""
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
        self._set_status(f"Playing from {_fmt_time(seconds)}")

    def _seek_back10(self):  self._seek(max(0.0, self._position - 10.0))
    def _seek_fwd10(self):   self._seek(self._position + 10.0)
    def _seek_back30(self):  self._seek(max(0.0, self._position - 30.0))
    def _seek_fwd30(self):   self._seek(self._position + 30.0)

    def _on_jump(self, event=None):
        """Called when the user presses Enter in the Jump field or clicks Go."""
        text = self._jump_var.get().strip()
        if not text:
            self._jump_entry.focus_set()
            return
        t = _parse_time(text)
        if t is None:
            self._set_status(f"Cannot parse time '{text}' — use MM:SS e.g. 4:23")
            self._jump_entry.select_range(0, tk.END)
            self._jump_entry.focus_set()
            return
        self._jump_var.set("")          # clear the field ready for next jump
        self._seek(t)
        self._jump_entry.focus_set()    # return focus so next type is instant

    # =========================================================================
    # Slider (scrub bar) — drag to seek
    # =========================================================================

    def _on_slider_press(self, event):
        self._slider_dragging = True
        if self._playing:
            pygame.mixer.music.pause()

    def _on_slider_release(self, event):
        self._slider_dragging = False
        if self._duration > 0:
            fraction = self._slider_var.get() / 1000.0
            t        = fraction * self._duration
            self._seek(t)

    def _on_slider_move(self, value):
        """Called continuously while the slider is dragged."""
        if self._slider_dragging and self._duration > 0:
            fraction      = float(value) / 1000.0
            self._position = fraction * self._duration
            self._pos_var.set(_fmt_time(self._position))

    # =========================================================================
    # Position polling loop  (runs every 200 ms on the Tkinter main thread)
    # =========================================================================

    def _poll_position(self):
        if not self._slider_dragging and self._playing and PYGAME_OK:
            elapsed        = time.time() - self._play_start_wall
            self._position = self._play_start_pos + elapsed

            # Detect natural end-of-track.
            if self._duration > 0 and self._position >= self._duration:
                self._position = self._duration
                self._playing  = False
                self._update_play_btn()
                self._set_status("Finished.")
            elif not pygame.mixer.music.get_busy() and self._playing:
                # pygame stopped unexpectedly (e.g. end of file)
                self._playing = False
                self._update_play_btn()

        if not self._slider_dragging:
            self._pos_var.set(_fmt_time(self._position))
            if self._duration > 0:
                pct = min(1000.0, (self._position / self._duration) * 1000.0)
                self._slider_var.set(pct)

        self.root.after(200, self._poll_position)

    # =========================================================================
    # Helpers
    # =========================================================================

    def _update_play_btn(self):
        self._play_btn.config(
            text="⏸  Pause" if self._playing else "▶  Play"
        )

    def _set_status(self, msg: str):
        self._status_var.set(msg)

    def _on_close(self):
        if PYGAME_OK:
            try:
                pygame.mixer.music.stop()
                pygame.mixer.quit()
            except Exception:
                pass
        self.root.destroy()


# ── ffmpeg helper ──────────────────────────────────────────────────────────────

def _run_ffmpeg(cmd: list):
    """Run ffmpeg suppressing its console window on Windows."""
    import subprocess
    kwargs: dict = {"check": True, "capture_output": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.run(cmd, **kwargs)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    if not PYGAME_OK:
        # Show an error in a minimal Tk window rather than crashing silently.
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "pygame not installed",
            "The DocAnalyser companion player requires pygame.\n\n"
            "Install it with:\n    pip install pygame\n\n"
            "Then restart the player.",
        )
        root.destroy()
        sys.exit(1)

    audio_file = None
    if len(sys.argv) > 1:
        candidate = " ".join(sys.argv[1:]).strip('"').strip("'")
        if os.path.isfile(candidate):
            audio_file = candidate

    root = tk.Tk()
    CompanionPlayer(root, initial_audio=audio_file)
    root.mainloop()


if __name__ == "__main__":
    main()
