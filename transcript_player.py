"""
transcript_player.py - Audio-synchronised transcript player for DocAnalyser.

Provides a playback control bar that plays the original audio file while
highlighting the corresponding segment in the thread viewer's text widget.
The user can click any segment to jump to that point in the audio.

Dependencies:
    - pygame (for MP3/WAV/OGG playback)
    - tkinter (already available)

Usage:
    Automatically activated in the Thread Viewer when:
    1. The document type is "audio_transcription"
    2. The original audio file still exists on disk
    3. pygame is installed

Author: DocAnalyser Development Team
"""

from __future__ import annotations

import os
import time
import logging
import tkinter as tk
from tkinter import ttk
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Lazy import - don't break the app if pygame isn't installed
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    logger.info("pygame not installed - transcript player unavailable. "
                "Install with: pip install pygame")


def _get_ffmpeg_cmd() -> str:
    """
    Return the path to the ffmpeg executable.
    Checks the bundled tools (via dependency_checker.find_ffmpeg) first,
    then falls back to 'ffmpeg' on PATH so both the installed app and
    the dev environment work correctly.
    """
    try:
        from dependency_checker import find_ffmpeg
        ok, path, _ = find_ffmpeg()
        if ok and path:
            candidate = os.path.join(path, 'ffmpeg.exe')
            if os.path.isfile(candidate):
                return candidate
            candidate = os.path.join(path, 'ffmpeg')
            if os.path.isfile(candidate):
                return candidate
    except Exception:
        pass
    return 'ffmpeg'  # fall back to PATH


def _get_ffprobe_cmd() -> str:
    """Return the path to the ffprobe executable (same directory as ffmpeg)."""
    try:
        from dependency_checker import find_ffmpeg
        ok, path, _ = find_ffmpeg()
        if ok and path:
            candidate = os.path.join(path, 'ffprobe.exe')
            if os.path.isfile(candidate):
                return candidate
            candidate = os.path.join(path, 'ffprobe')
            if os.path.isfile(candidate):
                return candidate
    except Exception:
        pass
    return 'ffprobe'  # fall back to PATH


def preconvert_for_player(audio_path: str) -> None:
    """
    Pre-convert an audio file to a small MP3 in a background thread so
    that pygame.mixer can load it almost instantly when the Thread Viewer
    opens.

    The output is stored next to the source file with a '_playback.mp3'
    suffix, e.g.:
        C:/Ian/interviews/Paul.m4a  →  C:/Ian/interviews/Paul_playback.mp3

    If the file already exists it is not re-created.  Safe to call
    multiple times.  Errors are logged but never raised — if conversion
    fails, pygame will fall back to loading the original file directly.

    Call this immediately after a successful transcription so the
    converted file is ready by the time the user opens the Thread Viewer.
    """
    if not audio_path or not os.path.isfile(audio_path):
        return

    playback_path = os.path.splitext(audio_path)[0] + '_playback.mp3'
    if os.path.isfile(playback_path):
        return  # Already done

    def _convert():
        print(f"🎵 FFMPEG START: converting {os.path.basename(audio_path)} → {os.path.basename(playback_path)}", flush=True)
        tmp_path = playback_path + '.tmp'
        try:
            import subprocess
            result = subprocess.run(
                [_get_ffmpeg_cmd(), '-y', '-i', audio_path,
                 '-vn',                    # strip video if present
                 '-acodec', 'libmp3lame',
                 '-q:a', '4',             # decent quality, small file
                 '-ar', '44100',          # standard sample rate for pygame
                 '-f', 'mp3',             # explicit format so .tmp ext is ok
                 tmp_path],               # write to .tmp first
                capture_output=True, timeout=300
            )
            if result.returncode == 0 and os.path.isfile(tmp_path):
                # Atomic rename: only visible to the rest of the app
                # once fully written
                os.replace(tmp_path, playback_path)
                logger.info(
                    f"Pre-converted for player: "
                    f"{os.path.basename(audio_path)} → "
                    f"{os.path.basename(playback_path)}"
                )
                print(f"🎵 FFMPEG DONE: {os.path.basename(playback_path)}", flush=True)
            else:
                logger.warning(
                    f"Pre-conversion failed (rc={result.returncode}): "
                    f"{result.stderr.decode(errors='replace')[:200]}"
                )
                # Clean up failed temp file
                if os.path.isfile(tmp_path):
                    os.remove(tmp_path)
        except FileNotFoundError:
            logger.debug("ffmpeg not found — skipping pre-conversion")
        except Exception as e:
            logger.warning(f"Pre-conversion error: {e}")
            if os.path.isfile(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    import threading
    threading.Thread(target=_convert, daemon=True).start()


def is_player_available(audio_path: str, entries: Optional[List] = None) -> bool:
    """Check whether the transcript player can be used."""
    if not PYGAME_AVAILABLE:
        return False
    if not audio_path or not os.path.exists(audio_path):
        return False
    if not entries or len(entries) == 0:
        return False
    ext = os.path.splitext(audio_path)[1].lower()
    if ext not in ('.mp3', '.wav', '.ogg', '.flac', '.m4a', '.wma',
                   '.mp4', '.mkv', '.webm', '.aac', '.mov', '.avi'):
        return False
    return True


class TranscriptPlayer(ttk.Frame):
    """
    A compact playback bar with audio-text synchronisation.

    Sits inside the thread viewer.  When playing, it highlights the
    current segment in the text widget and auto-scrolls to follow.

    Args:
        parent:      Parent Tk widget (the thread viewer window)
        audio_path:  Path to the original audio file
        entries:     List of entry dicts with at least 'start' (float, seconds)
                     and 'text' (str) keys.  May also have 'speaker'.
        text_widget: The ScrolledText widget that displays the transcript
        config:      App config dict (for timestamp_interval, etc.)
    """

    # Tag names
    TAG_HIGHLIGHT = "player_highlight"
    TAG_PREFIX = "seg_"
    TAG_CLICKABLE = "seg_click"

    # Timing
    UPDATE_INTERVAL_MS = 200

    def __init__(self, parent, audio_path: str, entries: List[Dict],
                 text_widget: tk.Text, config: dict = None,
                 status_callback=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.audio_path = audio_path
        self.entries = entries or []
        self.text_widget = text_widget
        self.config = config or {}
        # Optional callback(str) to update the main app status bar
        self._status_cb = status_callback

        # Playback state
        self._playing = False
        self._paused = False
        self._position = 0.0
        self._play_start_real = 0.0
        self._duration = 0.0
        self._current_seg_idx = -1
        self._update_job = None
        self._initialised = False
        self._slider_dragging = False

        # Estimate duration from entries
        if self.entries:
            last = self.entries[-1]
            self._duration = last.get('start', 0) + 15.0

        self._init_pending = True   # True while background init is running
        self._build_ui()
        # Initialise mixer in a background thread so the UI never freezes
        # while pygame loads and ffprobe queries the file duration.
        import threading
        threading.Thread(target=self._init_mixer, daemon=True).start()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        """Build the compact playback control bar."""
        self.configure(padding=(8, 4))

        controls = ttk.Frame(self)
        controls.pack(fill=tk.X)

        # Play / Pause — starts disabled until _init_mixer completes
        self.play_btn = ttk.Button(controls, text="Wait…", width=8,
                                   command=self.toggle_play,
                                   state=tk.DISABLED)
        self.play_btn.pack(side=tk.LEFT, padx=(0, 6))

        # Skip back / forward
        ttk.Button(controls, text="\u23ea 10s", width=6,
                   command=lambda: self.skip(-10)).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(controls, text="10s \u23e9", width=6,
                   command=lambda: self.skip(10)).pack(side=tk.LEFT, padx=(0, 8))

        # Time display
        self.time_label = ttk.Label(controls, text="00:00 / 00:00",
                                    font=('Consolas', 9))
        self.time_label.pack(side=tk.LEFT, padx=(0, 8))

        # Position slider
        self.slider_var = tk.DoubleVar(value=0)
        self.slider = ttk.Scale(controls, from_=0, to=max(self._duration, 1),
                                orient=tk.HORIZONTAL, variable=self.slider_var,
                                command=self._on_slider_move)
        self.slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.slider.bind("<ButtonPress-1>", self._on_slider_press)
        self.slider.bind("<ButtonRelease-1>", self._on_slider_release)

        # Stop
        ttk.Button(controls, text="\u23f9 Stop", width=7,
                   command=self.stop).pack(side=tk.LEFT)

    # ------------------------------------------------------------------
    # Pygame Mixer
    # ------------------------------------------------------------------

    # Video container extensions that need audio extraction before pygame can play them
    _VIDEO_EXTS = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.flv', '.wmv'}

    def _extract_audio_for_playback(self, source_path: str) -> str:
        """
        Return the best path for pygame to load.

        Priority order:
        1. A pre-converted '_playback.mp3' created by preconvert_for_player()
           — exists for any format after a fresh transcription.  Loads in
           under a second regardless of original file size.
        2. A legacy '_audio.mp3' created by earlier on-demand extraction
           (kept for backwards compatibility with files converted before
           the pre-conversion feature was added).
        3. For video containers (.mp4, .mkv etc.), extract on the fly now
           using ffmpeg (first-open only; result cached as '_audio.mp3').
        4. Original file unchanged (pygame tries directly; may be slow
           for large .m4a/.wav files if no pre-converted file exists).
        """
        base = os.path.splitext(source_path)[0]

        # Check for pre-converted playback MP3 first (fastest)
        playback_path = base + '_playback.mp3'
        if os.path.isfile(playback_path):
            logger.info(f"Using pre-converted playback file: "
                        f"{os.path.basename(playback_path)}")
            return playback_path

        # Legacy on-demand extraction cache
        legacy_path = base + '_audio.mp3'
        if os.path.isfile(legacy_path):
            logger.info(f"Using cached audio extraction: "
                        f"{os.path.basename(legacy_path)}")
            return legacy_path

        ext = os.path.splitext(source_path)[1].lower()
        if ext not in self._VIDEO_EXTS:
            return source_path  # Native audio — load directly

        tmp_path = os.path.splitext(source_path)[0] + '_audio.mp3'
        if os.path.isfile(tmp_path):
            logger.info(f"Using cached audio extraction: {tmp_path}")
            return tmp_path

        # Try to extract with ffmpeg
        try:
            import subprocess
            result = subprocess.run(
                [_get_ffmpeg_cmd(), '-y', '-i', source_path,
                 '-vn',            # no video
                 '-acodec', 'libmp3lame',
                 '-q:a', '2',      # good quality VBR
                 tmp_path],
                capture_output=True, timeout=120
            )
            if result.returncode == 0 and os.path.isfile(tmp_path):
                logger.info(f"Audio extracted to {tmp_path}")
                return tmp_path
            else:
                logger.warning(
                    f"ffmpeg extraction failed (rc={result.returncode}): "
                    f"{result.stderr.decode(errors='replace')[:200]}"
                )
        except FileNotFoundError:
            logger.warning("ffmpeg not found — cannot extract audio from video file")
        except Exception as e:
            logger.warning(f"Audio extraction error: {e}")

        return source_path  # Fallback: try loading original (will likely fail)

    def _set_status(self, msg: str) -> None:
        """Post msg to the main app status bar if a callback was supplied."""
        if self._status_cb:
            try:
                self._status_cb(msg)
            except Exception:
                pass

    def _poll_conversion(self, attempt: int = 0) -> None:
        """
        Called every 2 seconds after a failed init to check whether the
        background ffmpeg conversion has finished.  Once _playback.mp3
        exists, reset _initialised and retry _init_mixer on the
        background thread.
        """
        playback_path = os.path.splitext(self.audio_path)[0] + '_playback.mp3'
        if os.path.isfile(playback_path):
            # Conversion done — reset state and try again
            self._initialised = False
            self._init_pending = True
            self.play_btn.configure(text="Wait\u2026")
            self._set_status(
                f"✅ Audio prepared — loading player..."
            )
            import threading
            threading.Thread(target=self._init_mixer, daemon=True).start()
        elif attempt < 60:  # Give up after 2 minutes
            self.after(2000, lambda: self._poll_conversion(attempt + 1))
        else:
            # Conversion never finished
            self.play_btn.configure(
                text="\u25b6 Play", state=tk.DISABLED)
            logger.warning(
                "Audio conversion did not complete within 2 minutes.")

    def _get_duration_ffprobe(self, audio_path: str) -> float:
        """
        Use ffprobe to read the audio duration from file metadata.
        Returns duration in seconds, or 0.0 if ffprobe is unavailable
        or the query fails.  This is near-instant regardless of file size.
        """
        try:
            import subprocess, json
            result = subprocess.run(
                [_get_ffprobe_cmd(), '-v', 'quiet',
                 '-print_format', 'json',
                 '-show_format',
                 audio_path],
                capture_output=True, timeout=10
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                dur = float(data.get('format', {}).get('duration', 0))
                if dur > 0:
                    return dur
        except Exception:
            pass
        return 0.0

    # Formats pygame can always handle natively without conversion
    _PYGAME_SAFE_EXTS = {'.mp3', '.wav', '.ogg'}

    def _init_mixer(self):
        """Initialise pygame mixer."""
        if self._initialised or not PYGAME_AVAILABLE:
            return

        # ── Proactive pre-conversion check ───────────────────────────────
        # If the source format is not guaranteed safe for pygame AND no
        # pre-converted _playback.mp3 exists yet, skip the doomed load and
        # go straight to background conversion + polling.  This avoids the
        # ModPlug_Load / codec error for .m4a, .aac, .wma, .mp4 etc.
        ext = os.path.splitext(self.audio_path)[1].lower()
        playback_path = os.path.splitext(self.audio_path)[0] + '_playback.mp3'
        if ext not in self._PYGAME_SAFE_EXTS and not os.path.isfile(playback_path):
            print(f"🎵 PRE-CONVERT: {ext} not pygame-safe, no playback.mp3 found — starting ffmpeg conversion", flush=True)
            logger.info(
                f"{ext} is not natively supported by pygame — "
                "starting background conversion before loading."
            )
            self._init_pending = False
            try:
                preconvert_for_player(self.audio_path)
                fname = os.path.basename(self.audio_path)
                self.after(0, lambda: self.play_btn.configure(
                    text="Wait\u2026", state=tk.DISABLED))
                self.after(0, lambda: self._set_status(
                    f"🔄 Preparing audio player — converting {fname} to MP3 "
                    f"for playback (this takes 1-2 minutes for large files)..."
                ))
                self.after(0, self._poll_conversion)
            except Exception as e:
                print(f"🎵 PRE-CONVERT ERROR: {e}", flush=True)
                logger.error(f"Could not start pre-conversion: {e}")
                self.after(0, lambda: self.play_btn.configure(state=tk.DISABLED))
            return
        print(f"🎵 INIT-MIXER: {ext} is pygame-safe or playback.mp3 exists — proceeding with direct load", flush=True)
        # ── End proactive check ───────────────────────────────────────────

        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2,
                              buffer=2048)

            # Extract audio from video containers before loading into pygame
            playback_path = self._extract_audio_for_playback(self.audio_path)
            pygame.mixer.music.load(playback_path)

            # Get duration via ffprobe (instant metadata read, no file loading)
            # Falls back to the entry-based estimate already set in __init__.
            duration = self._get_duration_ffprobe(playback_path)
            if duration and duration > 0:
                self._duration = duration

            self._initialised = True
            self._init_pending = False
            logger.info(f"Transcript player initialised: "
                        f"{os.path.basename(self.audio_path)} "
                        f"({self._fmt_time(self._duration)})")

            # Update slider and confirm Play button on the main thread
            self.after(0, lambda: self.slider.configure(
                to=max(self._duration, 1)))
            self.after(0, lambda: self.play_btn.configure(
                text='\u25b6 Play', state=tk.NORMAL))
            self.after(0, lambda: self._set_status(
                f'✅ Audio player ready — click Play or any segment to begin'))

        except Exception as e:
            logger.error(f"Failed to initialise audio: {e}")
            self._init_pending = False

            # If loading failed and no pre-converted file exists yet,
            # kick off background conversion and retry once it finishes.
            playback_path = os.path.splitext(self.audio_path)[0] + '_playback.mp3'
            if not os.path.isfile(playback_path):
                try:
                    preconvert_for_player(self.audio_path)
                    # Show "Converting..." and poll until the file appears
                    self.after(0, lambda: self.play_btn.configure(
                        text="Converting\u2026", state=tk.DISABLED))
                    self.after(0, self._poll_conversion)
                except Exception:
                    self.after(0, lambda: self.play_btn.configure(state=tk.DISABLED))
            else:
                self.after(0, lambda: self.play_btn.configure(state=tk.DISABLED))

    # ------------------------------------------------------------------
    # Playback Controls
    # ------------------------------------------------------------------

    def toggle_play(self):
        if self._playing:
            self.pause()
        elif self._paused:
            self.resume()
        else:
            self.play()

    def resume(self):
        """Resume from paused state (avoids re-seeking)."""
        if not self._paused:
            return
        pygame.mixer.music.unpause()
        self._play_start_real = time.time()
        self._playing = True
        self._paused = False
        self.play_btn.configure(text="\u23f8 Pause")
        self._schedule_update()

    def play(self, from_position: float = None):
        if not self._initialised:
            if getattr(self, '_init_pending', False):
                # Background init still running — retry in 500ms
                self.play_btn.configure(text="Loading\u2026", state=tk.DISABLED)
                delay = from_position  # capture for lambda
                self.after(500, lambda: self._retry_play(delay))
                return
            # Not pending and not initialised — try once synchronously
            # (covers the edge case where threading never started)
            self._init_mixer()
            if not self._initialised:
                return

        if from_position is not None:
            self._position = max(0.0, min(from_position, self._duration))

        print(f"🎵 PLAY from position={self._position:.1f}s", flush=True)

        # Strategy: try play(start=) first, fall back to play() + set_pos()
        seek_ok = False
        if self._position > 0.5:
            try:
                pygame.mixer.music.play(start=self._position)
                seek_ok = True
                print(f"🎵   play(start={self._position:.1f}) succeeded", flush=True)
            except Exception as e1:
                print(f"🎵   play(start=) failed: {e1}", flush=True)
                try:
                    pygame.mixer.music.play()
                    pygame.mixer.music.set_pos(self._position)
                    seek_ok = True
                    print(f"🎵   play() + set_pos({self._position:.1f}) succeeded", flush=True)
                except Exception as e2:
                    print(f"🎵   set_pos() also failed: {e2}", flush=True)

        if not seek_ok:
            pygame.mixer.music.play()
            if self._position > 0.5:
                print(f"🎵   WARNING: could not seek, playing from start", flush=True)
                self._position = 0.0

        self._play_start_real = time.time()
        self._playing = True
        self._paused = False
        self.play_btn.configure(text="\u23f8 Pause")
        self._schedule_update()

    def _retry_play(self, from_position):
        """Called after a short delay when init was still pending.
        If now initialised, play; if still pending, reschedule."""
        if getattr(self, '_init_pending', False):
            # Still loading — wait another 500ms
            self.after(500, lambda: self._retry_play(from_position))
            return
        # Update button text regardless of success/failure
        if self._initialised:
            self.play_btn.configure(text="\u25b6 Play", state=tk.NORMAL)
            self.play(from_position=from_position)
        else:
            self.play_btn.configure(text="\u25b6 Play", state=tk.DISABLED)

    def pause(self):
        if not self._playing:
            return
        self._position = self._get_current_position()
        pygame.mixer.music.pause()
        self._playing = False
        self._paused = True
        self.play_btn.configure(text="\u25b6 Play")
        self._cancel_update()

    def stop(self):
        if self._initialised:
            pygame.mixer.music.stop()
        self._playing = False
        self._paused = False
        self._position = 0.0
        self.play_btn.configure(text="\u25b6 Play")
        self._cancel_update()
        self._update_time_display(0.0)
        self.slider_var.set(0)
        self._clear_highlight()

    def skip(self, delta_seconds: float):
        new_pos = self._get_current_position() + delta_seconds
        new_pos = max(0.0, min(new_pos, self._duration))
        if self._playing:
            self.play(from_position=new_pos)
        else:
            self._position = new_pos
            self._update_time_display(new_pos)
            self.slider_var.set(new_pos)
            self._highlight_for_position(new_pos)

    def seek_to(self, seconds: float):
        seconds = max(0.0, min(seconds, self._duration))
        if self._playing:
            self.play(from_position=seconds)
        else:
            self._position = seconds
            self._update_time_display(seconds)
            self.slider_var.set(seconds)
            self._highlight_for_position(seconds)

    # ------------------------------------------------------------------
    # Position Tracking
    # ------------------------------------------------------------------

    def _get_current_position(self) -> float:
        if self._playing:
            elapsed = time.time() - self._play_start_real
            return min(self._position + elapsed, self._duration)
        return self._position

    # ------------------------------------------------------------------
    # Update Loop
    # ------------------------------------------------------------------

    def _schedule_update(self):
        self._cancel_update()
        self._update_job = self.after(self.UPDATE_INTERVAL_MS, self._update_tick)

    def _cancel_update(self):
        if self._update_job is not None:
            self.after_cancel(self._update_job)
            self._update_job = None

    def _update_tick(self):
        if not self._playing:
            return

        pos = self._get_current_position()

        # End of audio?
        if pos >= self._duration - 0.5:
            # Also check if pygame has actually stopped
            if not pygame.mixer.music.get_busy():
                self.stop()
                return

        if not self._slider_dragging:
            self.slider_var.set(pos)

        self._update_time_display(pos)
        self._highlight_for_position(pos)
        self._schedule_update()

    # ------------------------------------------------------------------
    # Slider Interaction
    # ------------------------------------------------------------------

    def _on_slider_press(self, event):
        self._slider_dragging = True

    def _on_slider_release(self, event):
        self._slider_dragging = False
        self.seek_to(self.slider_var.get())

    def _on_slider_move(self, value):
        if self._slider_dragging:
            self._update_time_display(float(value))

    # ------------------------------------------------------------------
    # Time Display
    # ------------------------------------------------------------------

    def _update_time_display(self, position: float):
        self.time_label.configure(
            text=f"{self._fmt_time(position)} / {self._fmt_time(self._duration)}"
        )

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        s = max(0, int(seconds))
        if s >= 3600:
            return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"
        return f"{s // 60:02d}:{s % 60:02d}"

    # ------------------------------------------------------------------
    # Segment Highlighting
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Entry Splitting (for coarse entries like AssemblyAI utterances)
    # ------------------------------------------------------------------

    MAX_SEGMENT_SECS = 20  # Split entries longer than this

    def _build_playback_segments(self):
        """
        Build a list of playback segments from the entries.

        If entries are already fine-grained (median duration ≤ MAX_SEGMENT_SECS),
        use them directly — no splitting needed.  This is the normal case for
        sentence-level data from AssemblyAI's get_sentences() or faster-whisper.

        If entries are coarse (e.g. old cached AssemblyAI utterances spanning
        minutes), split them into sentence-level sub-segments with interpolated
        timestamps.
        """
        import re

        # ── Estimate typical entry duration to decide strategy ──────────
        durations = []
        for i, entry in enumerate(self.entries):
            start = entry.get('start', 0)
            if i + 1 < len(self.entries):
                d = self.entries[i + 1].get('start', start) - start
                durations.append(max(d, 0))
        if durations:
            durations.sort()
            median_dur = durations[len(durations) // 2]
        else:
            median_dur = 0

        already_fine = median_dur <= self.MAX_SEGMENT_SECS

        print(f"🎵 _build_playback_segments: {len(self.entries)} entries, "
              f"median duration={median_dur:.1f}s, "
              f"strategy={'pass-through' if already_fine else 'split-coarse'}",
              flush=True)

        # ── Pass-through: entries are already sentence-level ────────────
        if already_fine:
            segments = []
            for entry in self.entries:
                text = entry.get('text', '').strip()
                if not text:
                    continue
                speaker = entry.get('speaker', '')
                stored_sentences = entry.get('sentences')
                if stored_sentences and len(stored_sentences) > 1:
                    # Use real per-sentence timestamps stored by transcript_cleaner
                    for j, sent in enumerate(stored_sentences):
                        sent_text = sent.get('text', '').strip()
                        if not sent_text:
                            continue
                        segments.append({
                            'start': sent.get('start', entry.get('start', 0)),
                            'text': sent_text,
                            'speaker': speaker if j == 0 else '',
                            'is_first_in_entry': (j == 0),
                        })
                else:
                    segments.append({
                        'start': entry.get('start', 0),
                        'text': text,
                        'speaker': speaker,
                        'is_first_in_entry': True
                    })
            return segments

        # ── Split coarse entries (old cached utterances) ────────────────
        segments = []
        for i, entry in enumerate(self.entries):
            start = entry.get('start', 0)
            text = entry.get('text', '').strip()
            speaker = entry.get('speaker', '')
            if not text:
                continue

            if i + 1 < len(self.entries):
                next_start = self.entries[i + 1].get('start', start)
                duration = max(next_start - start, 0)
            else:
                duration = 15.0

            # Use real per-sentence timestamps if stored by transcript_cleaner
            stored_sentences = entry.get('sentences')
            if stored_sentences and len(stored_sentences) > 1:
                for j, sent in enumerate(stored_sentences):
                    sent_text = sent.get('text', '').strip()
                    if not sent_text:
                        continue
                    segments.append({
                        'start': sent.get('start', start),
                        'text': sent_text,
                        'speaker': speaker if j == 0 else '',
                        'is_first_in_entry': (j == 0),
                    })
            elif duration <= self.MAX_SEGMENT_SECS:
                segments.append({
                    'start': start,
                    'text': text,
                    'speaker': speaker,
                    'is_first_in_entry': True
                })
            else:
                # Fallback: split by sentence and interpolate timestamps
                sentences = re.split(r'(?<=[.!?])\s+', text)
                if len(sentences) <= 1:
                    segments.append({
                        'start': start,
                        'text': text,
                        'speaker': speaker,
                        'is_first_in_entry': True
                    })
                else:
                    total_chars = sum(len(s) for s in sentences)
                    running_time = start
                    for j, sentence in enumerate(sentences):
                        sentence = sentence.strip()
                        if not sentence:
                            continue
                        segments.append({
                            'start': running_time,
                            'text': sentence,
                            'speaker': speaker if j == 0 else '',
                            'is_first_in_entry': (j == 0)
                        })
                        frac = len(sentence) / total_chars if total_chars > 0 else 0
                        running_time += duration * frac

        return segments

    # ------------------------------------------------------------------
    # Segment Highlighting & Insertion
    # ------------------------------------------------------------------

    def insert_tagged_entries(self, speaker_filter=None):
        """
        Insert transcript entries into the text widget with per-segment tags
        so they can be individually highlighted and clicked during playback.

        Args:
            speaker_filter: If set, only entries whose 'speaker' field matches
                            this value are inserted.  None = show all speakers.

        Large entries (e.g. AssemblyAI utterances spanning minutes) are
        split into sentence-level sub-segments for fine-grained clicking.
        """
        # Build fine-grained segments from raw entries
        all_segments = self._build_playback_segments()

        # Apply speaker filter — keep original timestamps so seek still works
        if speaker_filter:
            segments = [
                s for s in all_segments
                if s.get('speaker', '').strip() == speaker_filter
            ]
        else:
            segments = all_segments

        # Store as self.playback_segments so the click handler and highlight
        # loop both operate on exactly this (possibly filtered) list.
        self.playback_segments = segments

        tw = self.text_widget
        ts_interval = self.config.get("timestamp_interval", "every_segment")

        interval_secs = {
            "every_segment": 0,
            "1min": 60,
            "5min": 300,
            "10min": 600,
            "never": float('inf')
        }.get(ts_interval, 0)

        last_ts_time = -interval_secs

        print(f"🎵 insert_tagged_entries: {len(all_segments)} total segments → "
              f"{len(segments)} shown (filter={speaker_filter!r})", flush=True)

        for i, seg in enumerate(segments):
            tag_name = f"{self.TAG_PREFIX}{i}"
            start = seg['start']
            text = seg['text']
            speaker = seg.get('speaker', '')
            is_first = seg.get('is_first_in_entry', True)

            # Is the next segment a continuation of this paragraph (not a
            # new entry)? Used to decide space vs paragraph break after text.
            next_seg = segments[i + 1] if i + 1 < len(segments) else None
            next_is_continuation = (
                next_seg is not None
                and not next_seg.get('is_first_in_entry', True)
            )

            # ── Paragraph header (timestamp + speaker label) ──────────────
            # Shown only on the first sentence of each entry, as plain
            # (non-clickable) text so clicking it doesn't seek.
            if is_first:
                show_ts = (
                    ts_interval == "every_segment"
                    or (start - last_ts_time) >= interval_secs
                )
                header_parts = []
                if show_ts and ts_interval != "never":
                    header_parts.append(f"[{self._fmt_time(start)}] ")
                    last_ts_time = start
                if speaker and speaker_filter is None:
                    header_parts.append(f"[{speaker}]: ")
                if header_parts:
                    tw.insert(tk.END, "".join(header_parts), "source_text")

            # ── Sentence text — individually tagged for click-to-seek ──────
            # Sentences within a paragraph flow as prose; only the paragraph
            # boundaries get a blank line.
            tw.insert(tk.END, text, (tag_name, self.TAG_CLICKABLE, "source_text"))

            if next_is_continuation:
                tw.insert(tk.END, " ", "source_text")   # space within paragraph
            else:
                tw.insert(tk.END, "\n\n", "source_text")  # paragraph break

        # Click to seek
        tw.tag_bind(self.TAG_CLICKABLE, "<Button-1>", self._on_segment_click)

        # Highlight style
        tw.tag_configure(self.TAG_HIGHLIGHT,
                         background="#FFF3CD", relief="flat")

        # Hand cursor on hover
        tw.tag_bind(self.TAG_CLICKABLE, "<Enter>",
                    lambda e: tw.configure(cursor="hand2"))
        tw.tag_bind(self.TAG_CLICKABLE, "<Leave>",
                    lambda e: tw.configure(cursor=""))

    def _on_segment_click(self, event):
        """Seek audio to the clicked segment's start time."""
        # Suppress seeking while the user is editing the transcript
        if getattr(self, 'edit_mode', False):
            return
        tw = self.text_widget
        index = tw.index(f"@{event.x},{event.y}")
        tags = tw.tag_names(index)
        print(f"🎵 CLICK at {index}, tags={tags}", flush=True)

        segs = getattr(self, 'playback_segments', self.entries)
        for tag in tags:
            if tag.startswith(self.TAG_PREFIX) and tag[len(self.TAG_PREFIX):].isdigit():
                try:
                    seg_idx = int(tag[len(self.TAG_PREFIX):])
                    start = segs[seg_idx].get('start', 0)
                    print(f"🎵 SEEK to segment {seg_idx}, start={start:.1f}s", flush=True)
                    if self._initialised:
                        pygame.mixer.music.stop()
                    self._playing = False
                    self._paused = False
                    self.play(from_position=start)
                except (ValueError, IndexError) as e:
                    print(f"🎵 CLICK error: {e}", flush=True)
                return
        print("🎵 CLICK: no segment tag found", flush=True)

    def _highlight_for_position(self, position: float):
        seg_idx = self._find_segment_for_position(position)
        if seg_idx == self._current_seg_idx:
            return
        self._current_seg_idx = seg_idx
        self._apply_highlight(seg_idx)

    def _find_segment_for_position(self, position: float) -> int:
        """Binary search for the segment containing the given position."""
        segs = getattr(self, 'playback_segments', self.entries)
        if not segs:
            return -1
        lo, hi = 0, len(segs) - 1
        result = -1
        while lo <= hi:
            mid = (lo + hi) // 2
            if segs[mid].get('start', 0) <= position:
                result = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return result

    def _apply_highlight(self, seg_idx: int, auto_scroll: bool = True):
        tw = self.text_widget
        tw.tag_remove(self.TAG_HIGHLIGHT, "1.0", tk.END)

        if seg_idx < 0:
            return

        tag_name = f"{self.TAG_PREFIX}{seg_idx}"
        ranges = tw.tag_ranges(tag_name)
        if not ranges:
            return

        tw.tag_add(self.TAG_HIGHLIGHT, ranges[0], ranges[1])
        tw.tag_raise(self.TAG_HIGHLIGHT)
        # Only auto-scroll if not suppressed (e.g. immediately after a save)
        # and audio is actually playing.
        suppressed = time.time() < getattr(self, '_scroll_suppressed_until', 0)
        if auto_scroll and self._playing and not suppressed:
            tw.see(ranges[0])

    def _clear_highlight(self):
        self.text_widget.tag_remove(self.TAG_HIGHLIGHT, "1.0", tk.END)
        self._current_seg_idx = -1

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self):
        """Stop playback and release resources. Call on window close."""
        self._cancel_update()
        try:
            if self._initialised:
                pygame.mixer.music.stop()
                pygame.mixer.quit()
                self._initialised = False
        except Exception:
            pass

    def destroy(self):
        self.cleanup()
        super().destroy()
