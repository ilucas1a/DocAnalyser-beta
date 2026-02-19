"""
dictation_dialog.py - Speech-to-Text Recording Dialog
Modal dialog for recording and transcribing speech.
Supports local (faster-whisper) and cloud (OpenAI) transcription.
Now supports multiple recording segments that can be combined.
"""

import os
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox


class DictationDialog:
    """
    Modal dialog for recording and transcribing speech.
    Supports local (faster-whisper) and cloud (OpenAI) transcription.
    Supports multiple recording segments that are combined before transcription.
    """
    
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.recorder = None
        self.is_recording = False
        self.audio_segments = []  # List of audio file paths (accumulated segments)
        self.transcription_result = None
        self.duration_timer = None
        self.total_duration = 0.0  # Accumulated duration from previous segments
        
        # Get settings from app config
        self.mode = app.config.get("dictation_mode", "local_first")
        self.whisper_model = app.config.get("whisper_model", "base")
        
        # Get API keys for both cloud providers
        self.openai_key = app.config.get("keys", {}).get("OpenAI (ChatGPT)", "")
        self.assemblyai_key = app.config.get("keys", {}).get("AssemblyAI", "")
        
        # Determine cloud provider from transcription engine setting
        # If user has selected assemblyai as their engine, use it for cloud fallback too
        transcription_engine = app.config.get("transcription_engine", "openai_whisper")
        if transcription_engine == "assemblyai":
            self.cloud_provider = "assemblyai"
        else:
            self.cloud_provider = "openai"
        
        # Get speaker diarization preference
        self.speaker_labels = app.config.get("speaker_diarization", False)
        
        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("🎙️ Dictation")
        self.dialog.geometry("420x400")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Center on parent
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 420) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 400) // 2
        self.dialog.geometry(f"+{x}+{y}")
        
        self._setup_ui()
        
        # Handle window close
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _setup_ui(self):
        """Create the dialog UI."""
        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        ttk.Label(
            main_frame, 
            text="🎙️ Record Speech",
            font=('Arial', 14, 'bold')
        ).pack(pady=(0, 10))
        
        # Recording indicator
        self.record_frame = ttk.Frame(main_frame)
        self.record_frame.pack(pady=15)
        
        self.record_indicator = ttk.Label(
            self.record_frame,
            text="●",
            font=('Arial', 48),
            foreground='gray'
        )
        self.record_indicator.pack()
        
        self.duration_label = ttk.Label(
            self.record_frame,
            text="0:00",
            font=('Arial', 24)
        )
        self.duration_label.pack(pady=5)
        
        # Segment counter label
        self.segment_label = ttk.Label(
            self.record_frame,
            text="",
            font=('Arial', 9),
            foreground='#666666'
        )
        self.segment_label.pack()
        
        self.status_label = ttk.Label(
            self.record_frame,
            text="Click Record to start",
            font=('Arial', 10),
            foreground='gray'
        )
        self.status_label.pack(pady=(5, 0))
        
        # Main buttons frame (Record / Continue / Transcribe)
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=15)
        
        self.record_btn = ttk.Button(
            btn_frame,
            text="🔴 Record",
            command=self._toggle_recording,
            width=12
        )
        self.record_btn.pack(side=tk.LEFT, padx=3)
        
        # Continue button - initially hidden, shown after first segment
        self.continue_btn = ttk.Button(
            btn_frame,
            text="▶️ Continue",
            command=self._continue_recording,
            width=12
        )
        # Don't pack yet - will show after first segment is recorded
        
        self.transcribe_btn = ttk.Button(
            btn_frame,
            text="📝 Transcribe",
            command=self._transcribe,
            width=12,
            state=tk.DISABLED
        )
        self.transcribe_btn.pack(side=tk.LEFT, padx=3)
        
        # Secondary buttons frame (Start Fresh)
        btn_frame2 = ttk.Frame(main_frame)
        btn_frame2.pack(pady=5)
        
        self.clear_btn = ttk.Button(
            btn_frame2,
            text="🗑️ Start Fresh",
            command=self._clear_segments,
            width=12
        )
        # Don't pack yet - will show after first segment
        
        # Mode indicator
        mode_frame = ttk.Frame(main_frame)
        mode_frame.pack(fill=tk.X, pady=10)
        
        mode_text = self._get_mode_description()
        self.mode_label = ttk.Label(
            mode_frame,
            text=mode_text,
            font=('Arial', 9),
            foreground='gray',
            wraplength=380,
            justify=tk.CENTER
        )
        self.mode_label.pack()
        
        # Cancel button
        ttk.Button(
            main_frame,
            text="Cancel",
            command=self._on_close,
            width=10
        ).pack(pady=(10, 0))
    
    def _get_mode_description(self) -> str:
        """Get description text for current mode."""
        if self.mode == "local_first":
            return "🔒 Local transcription (free & private)\nFalls back to cloud if needed"
        elif self.mode == "cloud_direct":
            return "☁️ Cloud transcription (OpenAI)\nFastest & most accurate (~$0.006/min)"
        else:  # local_only
            return "🔒 Local only (fully private)\nAudio never leaves your computer"
    
    def _update_segment_display(self):
        """Update the segment counter and show/hide Continue button."""
        num_segments = len(self.audio_segments)
        
        if num_segments == 0:
            self.segment_label.config(text="")
            self.continue_btn.pack_forget()
            self.clear_btn.pack_forget()
        elif num_segments == 1:
            self.segment_label.config(text="1 segment recorded")
            # Show Continue and Clear buttons
            self.continue_btn.pack(side=tk.LEFT, padx=3, after=self.record_btn)
            self.clear_btn.pack(pady=2)
        else:
            self.segment_label.config(text=f"{num_segments} segments recorded")
    
    def _format_duration(self, seconds: float) -> str:
        """Format seconds as M:SS or H:MM:SS."""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        if mins >= 60:
            hours = mins // 60
            mins = mins % 60
            return f"{hours}:{mins:02d}:{secs:02d}"
        return f"{mins}:{secs:02d}"
    
    def _toggle_recording(self):
        """Start or stop recording."""
        if self.is_recording:
            self._stop_recording()
        else:
            self._start_recording()
    
    def _continue_recording(self):
        """Continue recording (add another segment)."""
        if not self.is_recording:
            self._start_recording()
    
    def _start_recording(self):
        """Start recording from microphone."""
        try:
            from transcription_handler import AudioRecorder
            
            self.recorder = AudioRecorder()
            success, msg = self.recorder.start_recording()
            
            if not success:
                messagebox.showerror("Recording Error", msg)
                return
            
            self.is_recording = True
            self.record_btn.config(text="⏹ Stop")
            self.continue_btn.pack_forget()  # Hide continue while recording
            self.record_indicator.config(foreground='red')
            self.status_label.config(text="Recording...")
            self.transcribe_btn.config(state=tk.DISABLED)
            self.clear_btn.pack_forget()  # Hide clear while recording
            
            # Start duration timer
            self._update_duration()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start recording:\n{e}")
    
    def _stop_recording(self):
        """Stop recording and save audio file to segments list."""
        if not self.recorder:
            return
        
        # Stop duration timer
        if self.duration_timer:
            self.dialog.after_cancel(self.duration_timer)
            self.duration_timer = None
        
        success, msg, audio_path = self.recorder.stop_recording()
        
        self.is_recording = False
        self.record_btn.config(text="🔴 Record")
        self.record_indicator.config(foreground='green')
        
        if success and audio_path:
            # Get duration of this segment
            segment_duration = self.recorder.get_duration()
            self.total_duration += segment_duration
            
            # Add to segments list (don't replace!)
            self.audio_segments.append(audio_path)
            
            # Update UI
            self._update_segment_display()
            self.status_label.config(
                text=f"Ready to transcribe (total: {self._format_duration(self.total_duration)})"
            )
            self.duration_label.config(text=self._format_duration(self.total_duration))
            self.transcribe_btn.config(state=tk.NORMAL)
        else:
            self.status_label.config(text=f"Recording failed: {msg}")
            self.record_indicator.config(foreground='gray')
    
    def _clear_segments(self):
        """Clear all recorded segments and start fresh."""
        # Clean up all segment files
        for segment_path in self.audio_segments:
            try:
                if os.path.exists(segment_path):
                    os.unlink(segment_path)
            except:
                pass
        
        # Reset state
        self.audio_segments = []
        self.total_duration = 0.0
        
        # Update UI
        self._update_segment_display()
        self.duration_label.config(text="0:00")
        self.status_label.config(text="Click Record to start")
        self.record_indicator.config(foreground='gray')
        self.transcribe_btn.config(state=tk.DISABLED)
    
    def _update_duration(self):
        """Update the duration display while recording."""
        if not self.is_recording or not self.recorder:
            return
        
        # Show total duration (previous segments + current)
        current_duration = self.recorder.get_duration()
        total = self.total_duration + current_duration
        self.duration_label.config(text=self._format_duration(total))
        
        # Schedule next update
        self.duration_timer = self.dialog.after(100, self._update_duration)
    
    def _concatenate_audio_segments(self) -> str:
        """
        Concatenate all audio segments into a single file.
        Returns path to the combined audio file.
        """
        if len(self.audio_segments) == 1:
            # Only one segment, no need to concatenate
            return self.audio_segments[0]
        
        try:
            import soundfile as sf
            import numpy as np
            
            # Read all segments
            all_audio = []
            sample_rate = None
            
            for segment_path in self.audio_segments:
                data, sr = sf.read(segment_path)
                if sample_rate is None:
                    sample_rate = sr
                elif sr != sample_rate:
                    # Resample if needed (shouldn't happen with our recorder)
                    pass
                all_audio.append(data)
            
            # Concatenate
            combined = np.concatenate(all_audio)
            
            # Save to new temp file
            combined_path = tempfile.mktemp(suffix=".wav", prefix="dictation_combined_")
            sf.write(combined_path, combined, sample_rate)
            
            return combined_path
            
        except Exception as e:
            # If concatenation fails, just use the last segment
            print(f"Warning: Failed to concatenate audio segments: {e}")
            return self.audio_segments[-1] if self.audio_segments else None
    
    def _transcribe(self):
        """Transcribe the recorded audio (all segments combined)."""
        if not self.audio_segments:
            messagebox.showwarning("No Recording", "Please record audio first.")
            return
        
        # Disable buttons during transcription
        self.record_btn.config(state=tk.DISABLED)
        self.continue_btn.config(state=tk.DISABLED)
        self.transcribe_btn.config(state=tk.DISABLED)
        self.clear_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Preparing audio...")
        self.record_indicator.config(foreground='orange')
        
        # Run transcription in thread
        import threading
        thread = threading.Thread(target=self._transcribe_thread, daemon=True)
        thread.start()
    
    def _transcribe_thread(self):
        """Transcription thread."""
        combined_audio_path = None
        try:
            # First, concatenate segments if multiple
            if len(self.audio_segments) > 1:
                self.dialog.after(0, lambda: self.status_label.config(
                    text=f"Combining {len(self.audio_segments)} segments..."
                ))
                combined_audio_path = self._concatenate_audio_segments()
            else:
                combined_audio_path = self.audio_segments[0]
            
            if not combined_audio_path:
                raise Exception("No audio to transcribe")
            
            from transcription_handler import transcribe_audio
            
            def update_status(msg):
                self.dialog.after(0, lambda: self.status_label.config(text=msg[:50]))
            
            update_status("Transcribing...")
            
            success, text, metadata = transcribe_audio(
                audio_path=combined_audio_path,
                mode=self.mode,
                model_name=self.whisper_model,
                device="auto",
                language=None,  # Auto-detect
                openai_api_key=self.openai_key,
                assemblyai_api_key=self.assemblyai_key,
                cloud_provider=self.cloud_provider,
                speaker_labels=self.speaker_labels,
                progress_callback=update_status
            )
            
            # Clean up combined file if we created one
            if combined_audio_path and combined_audio_path not in self.audio_segments:
                try:
                    os.unlink(combined_audio_path)
                except:
                    pass
            
            # Update UI on main thread
            self.dialog.after(0, lambda: self._handle_transcription_result(success, text, metadata))
            
        except Exception as e:
            # Clean up combined file on error
            if combined_audio_path and combined_audio_path not in self.audio_segments:
                try:
                    os.unlink(combined_audio_path)
                except:
                    pass
            self.dialog.after(0, lambda: self._handle_transcription_error(str(e)))
    
    def _handle_transcription_result(self, success: bool, text: str, metadata: dict):
        """Handle transcription result on main thread."""
        self.record_btn.config(state=tk.NORMAL)
        
        if success and text.strip():
            self.transcription_result = (text, metadata)
            self.status_label.config(text="✅ Transcription complete!")
            self.record_indicator.config(foreground='green')
            
            # Clean up all audio segment files
            self._cleanup_all_audio()
            
            # Close dialog and pass result to app
            self.dialog.destroy()
            self.app._handle_dictation_result(text, metadata)
        else:
            self.status_label.config(text=f"❌ Failed: {text[:40]}..." if text else "❌ No speech detected")
            self.record_indicator.config(foreground='red')
            self.transcribe_btn.config(state=tk.NORMAL)
            self.continue_btn.config(state=tk.NORMAL)
            self.clear_btn.config(state=tk.NORMAL)
    
    def _handle_transcription_error(self, error: str):
        """Handle transcription error."""
        self.record_btn.config(state=tk.NORMAL)
        self.transcribe_btn.config(state=tk.NORMAL)
        self.continue_btn.config(state=tk.NORMAL)
        self.clear_btn.config(state=tk.NORMAL)
        self.status_label.config(text=f"❌ Error: {error[:40]}")
        self.record_indicator.config(foreground='red')
        messagebox.showerror("Transcription Error", error)
    
    def _cleanup_all_audio(self):
        """Clean up all temporary audio segment files."""
        for segment_path in self.audio_segments:
            try:
                if os.path.exists(segment_path):
                    os.unlink(segment_path)
            except:
                pass
        self.audio_segments = []
    
    def _on_close(self):
        """Handle dialog close."""
        # Stop recording if in progress
        if self.is_recording and self.recorder:
            self.recorder.stop_recording()
        
        # Stop timer
        if self.duration_timer:
            self.dialog.after_cancel(self.duration_timer)
        
        # Clean up all audio segments
        self._cleanup_all_audio()
        
        self.dialog.destroy()
