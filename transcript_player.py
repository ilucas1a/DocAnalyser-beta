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


def is_player_available(audio_path: str, entries: Optional[List] = None) -> bool:
    """Check whether the transcript player can be used."""
    if not PYGAME_AVAILABLE:
        return False
    if not audio_path or not os.path.exists(audio_path):
        return False
    if not entries or len(entries) == 0:
        return False
    ext = os.path.splitext(audio_path)[1].lower()
    if ext not in ('.mp3', '.wav', '.ogg', '.flac', '.m4a', '.wma'):
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
                 text_widget: tk.Text, config: dict = None, **kwargs):
        super().__init__(parent, **kwargs)

        self.audio_path = audio_path
        self.entries = entries or []
        self.text_widget = text_widget
        self.config = config or {}

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

        self._build_ui()
        self._init_mixer()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        """Build the compact playback control bar."""
        self.configure(padding=(8, 4))

        controls = ttk.Frame(self)
        controls.pack(fill=tk.X)

        # Play / Pause
        self.play_btn = ttk.Button(controls, text="\u25b6 Play", width=8,
                                   command=self.toggle_play)
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

    def _init_mixer(self):
        """Initialise pygame mixer."""
        if self._initialised or not PYGAME_AVAILABLE:
            return
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2,
                              buffer=2048)
            pygame.mixer.music.load(self.audio_path)

            # Try to get actual duration
            try:
                snd = pygame.mixer.Sound(self.audio_path)
                self._duration = snd.get_length()
                del snd
            except Exception:
                pass

            self.slider.configure(to=max(self._duration, 1))
            self._initialised = True
            logger.info(f"Transcript player initialised: "
                        f"{os.path.basename(self.audio_path)} "
                        f"({self._fmt_time(self._duration)})")

        except Exception as e:
            logger.error(f"Failed to initialise audio: {e}")
            self.play_btn.configure(state=tk.DISABLED)

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
                segments.append({
                    'start': entry.get('start', 0),
                    'text': text,
                    'speaker': entry.get('speaker', ''),
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

            if duration <= self.MAX_SEGMENT_SECS:
                segments.append({
                    'start': start,
                    'text': text,
                    'speaker': speaker,
                    'is_first_in_entry': True
                })
            else:
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

    def insert_tagged_entries(self):
        """
        Insert all transcript entries into the text widget with per-segment
        tags so they can be individually highlighted during playback.

        Large entries (e.g. AssemblyAI utterances spanning minutes) are
        split into sentence-level sub-segments for fine-grained clicking.
        """
        # Build fine-grained segments
        self.playback_segments = self._build_playback_segments()

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

        print(f"🎵 insert_tagged_entries: {len(self.entries)} raw entries → "
              f"{len(self.playback_segments)} playback segments", flush=True)

        for i, seg in enumerate(self.playback_segments):
            tag_name = f"{self.TAG_PREFIX}{i}"
            start = seg['start']
            text = seg['text']
            speaker = seg.get('speaker', '')

            show_ts = (
                ts_interval == "every_segment"
                or (start - last_ts_time) >= interval_secs
            )

            line_parts = []
            if show_ts and ts_interval != "never":
                line_parts.append(f"[{self._fmt_time(start)}] ")
                last_ts_time = start
            if speaker:
                line_parts.append(f"[{speaker}]: ")
            line_parts.append(text)
            line_parts.append("\n\n")

            full_line = "".join(line_parts)
            tw.insert(tk.END, full_line, (tag_name, self.TAG_CLICKABLE, "source_text"))

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

    def _apply_highlight(self, seg_idx: int):
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
