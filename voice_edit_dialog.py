"""
voice_edit_dialog.py - Voice-Assisted Text Editing
Allows users to edit OCR transcription results using voice commands.

Commands are keyword-triggered for speed and reliability:
- "New paragraph" → Insert paragraph break
- "New line" → Insert line break
- "Replace X with Y" → Find and replace text
- "Delete X" → Remove specific text
- "Insert X after Y" → Add text after a marker
- "Scratch that" / "Undo" → Undo last action
- "Done" / "Finish" → Complete editing

All other speech is inserted as text at cursor position.
"""

import os
import re
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable, List, Tuple
import threading
import queue


class CommandReferencePopup:
    """
    Small, movable, always-on-top popup showing available voice commands.
    Can be dragged around the screen and minimized.
    """
    
    COMMANDS = [
        ("New paragraph", "Insert ¶ break"),
        ("New line", "Insert line break"),
        ("Replace [X] with [Y]", "Find & replace"),
        ("Delete [word]", "Remove text"),
        ("Insert [X] after [Y]", "Add text"),
        ("Scratch that / Undo", "Undo last"),
        ("Select all", "Select all text"),
        ("Clear all", "Delete everything"),
        ("Done / Finish", "Save & close"),
    ]
    
    def __init__(self, parent):
        self.parent = parent
        self.minimized = False
        
        # Create top-level window
        self.window = tk.Toplevel(parent)
        self.window.title("Voice Commands")
        self.window.attributes('-topmost', True)
        self.window.resizable(False, False)
        self.window.overrideredirect(False)  # Keep title bar for dragging
        
        # Make it a tool window (smaller title bar on Windows)
        try:
            self.window.attributes('-toolwindow', True)
        except:
            pass
        
        # Position near top-right of parent
        self.window.update_idletasks()
        parent.update_idletasks()
        x = parent.winfo_x() + parent.winfo_width() + 10
        y = parent.winfo_y()
        # Keep on screen
        screen_width = self.window.winfo_screenwidth()
        if x + 200 > screen_width:
            x = parent.winfo_x() - 210
        self.window.geometry(f"+{x}+{y}")
        
        self._build_ui()
        
        # Handle close
        self.window.protocol("WM_DELETE_WINDOW", self.toggle_minimize)
    
    def _build_ui(self):
        """Build the command reference UI."""
        self.main_frame = ttk.Frame(self.window, padding=5)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header_frame = ttk.Frame(self.main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(
            header_frame,
            text="🎤 Voice Commands",
            font=('Arial', 9, 'bold')
        ).pack(side=tk.LEFT)
        
        # Minimize button
        self.min_btn = ttk.Button(
            header_frame,
            text="−",
            width=2,
            command=self.toggle_minimize
        )
        self.min_btn.pack(side=tk.RIGHT)
        
        # Commands list
        self.commands_frame = ttk.Frame(self.main_frame)
        self.commands_frame.pack(fill=tk.BOTH, expand=True)
        
        for cmd, desc in self.COMMANDS:
            row = ttk.Frame(self.commands_frame)
            row.pack(fill=tk.X, pady=1)
            
            ttk.Label(
                row,
                text=cmd,
                font=('Consolas', 8),
                foreground='#0066cc',
                width=22,
                anchor='w'
            ).pack(side=tk.LEFT)
            
            ttk.Label(
                row,
                text=desc,
                font=('Arial', 8),
                foreground='#666666'
            ).pack(side=tk.LEFT, padx=(5, 0))
        
        # Tip at bottom
        ttk.Label(
            self.main_frame,
            text="💡 Other speech → inserted as text",
            font=('Arial', 8, 'italic'),
            foreground='#888888'
        ).pack(pady=(5, 0))
    
    def toggle_minimize(self):
        """Toggle between minimized and full view."""
        if self.minimized:
            self.commands_frame.pack(fill=tk.BOTH, expand=True)
            self.min_btn.config(text="−")
            self.minimized = False
        else:
            self.commands_frame.pack_forget()
            self.min_btn.config(text="+")
            self.minimized = True
    
    def destroy(self):
        """Close the popup."""
        try:
            self.window.destroy()
        except:
            pass


class VoiceEditDialog:
    """
    Dialog for voice-assisted editing of text (typically OCR results).
    
    Features:
    - Text editor with the draft content
    - Voice recording with command recognition
    - Undo/redo support
    - Command reference popup
    """
    
    def __init__(self, parent, app, initial_text: str = "", title: str = "Voice Edit"):
        self.parent = parent
        self.app = app
        self.initial_text = initial_text
        self.result_text = None
        self.cancelled = False
        
        # Recording state
        self.is_recording = False
        self.audio_queue = queue.Queue()
        self.recording_thread = None
        
        # Undo stack
        self.undo_stack: List[str] = []
        self.redo_stack: List[str] = []
        self.max_undo = 50
        
        # Create dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"🎤 {title}")
        self.dialog.geometry("700x400")  # Start shorter
        self.dialog.resizable(True, True)
        self.dialog.minsize(400, 200)  # Allow very short for stacking with PDF
        # Note: Not using transient() so dialog is independent of main window
        # This allows user to minimize main app while editing
        # Also not using grab_set() so it's non-modal
        
        # Center on parent
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 700) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 550) // 2
        self.dialog.geometry(f"+{x}+{y}")
        
        self._setup_ui()
        
        # Create command reference popup
        self.command_popup = CommandReferencePopup(self.dialog)
        
        # Handle close
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Initialize text
        if initial_text:
            self.text_editor.insert('1.0', initial_text)
            self._save_undo_state()
    
    def _setup_ui(self):
        """Create the dialog UI - compact layout for side-by-side comparison."""
        main_frame = ttk.Frame(self.dialog, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header row: Title + Recording button + Status + Indicator
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(
            header_frame,
            text="Edit with Voice",
            font=('Arial', 12, 'bold')
        ).pack(side=tk.LEFT)
        
        # Recording button right next to title
        self.record_btn = ttk.Button(
            header_frame,
            text="🎤 Start Recording",
            command=self._toggle_recording,
            width=16
        )
        self.record_btn.pack(side=tk.LEFT, padx=(15, 5))
        
        # Recording indicator (animated when recording)
        self.recording_indicator = ttk.Label(
            header_frame,
            text="",
            font=('Arial', 12),
            foreground='red'
        )
        self.recording_indicator.pack(side=tk.LEFT, padx=(0, 5))
        
        # Status label
        self.status_label = ttk.Label(
            header_frame,
            text="",
            font=('Arial', 9),
            foreground='gray'
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Commands button on right
        ttk.Button(
            header_frame,
            text="📋 Commands",
            command=self._show_command_popup,
            width=11
        ).pack(side=tk.RIGHT)
        
        # Last recognized text (compact, below header)
        self.last_speech_label = ttk.Label(
            main_frame,
            text="",
            font=('Arial', 8, 'italic'),
            foreground='#666666',
            wraplength=680
        )
        self.last_speech_label.pack(fill=tk.X, pady=(0, 5))
        
        # Text editor - takes most of the space
        text_container = ttk.Frame(main_frame)
        text_container.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        self.text_editor = tk.Text(
            text_container,
            wrap=tk.WORD,
            font=('Georgia', 11),
            undo=True,
            padx=10,
            pady=10,
            bg='#FFFEF5'
        )
        self.text_editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(text_container, orient=tk.VERTICAL, command=self.text_editor.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text_editor.config(yscrollcommand=scrollbar.set)
        
        # Bind keyboard shortcuts
        self.text_editor.bind('<Control-z>', lambda e: self._undo())
        self.text_editor.bind('<Control-y>', lambda e: self._redo())
        self.text_editor.bind('<Control-Z>', lambda e: self._redo())  # Shift+Ctrl+Z
        
        # Bottom buttons - compact row
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)
        
        # Left side - edit buttons
        ttk.Button(
            btn_frame,
            text="↶ Undo",
            command=self._undo,
            width=7
        ).pack(side=tk.LEFT, padx=(0, 3))
        
        ttk.Button(
            btn_frame,
            text="↷ Redo",
            command=self._redo,
            width=7
        ).pack(side=tk.LEFT, padx=(0, 3))
        
        # Right side - main actions
        ttk.Button(
            btn_frame,
            text="✓ Done",
            command=self._on_done,
            width=10
        ).pack(side=tk.RIGHT, padx=(3, 0))
        
        ttk.Button(
            btn_frame,
            text="Cancel",
            command=self._on_cancel,
            width=8
        ).pack(side=tk.RIGHT, padx=(3, 0))
    
    def _save_undo_state(self):
        """Save current text state for undo."""
        current_text = self.text_editor.get('1.0', 'end-1c')
        
        # Don't save if same as last state
        if self.undo_stack and self.undo_stack[-1] == current_text:
            return
        
        self.undo_stack.append(current_text)
        
        # Limit stack size
        if len(self.undo_stack) > self.max_undo:
            self.undo_stack.pop(0)
        
        # Clear redo stack on new action
        self.redo_stack.clear()
    
    def _undo(self, event=None):
        """Undo last change."""
        if len(self.undo_stack) > 1:
            # Save current state to redo
            current = self.text_editor.get('1.0', 'end-1c')
            self.redo_stack.append(current)
            
            # Pop current state
            self.undo_stack.pop()
            
            # Restore previous state
            previous = self.undo_stack[-1]
            self.text_editor.delete('1.0', tk.END)
            self.text_editor.insert('1.0', previous)
            
            self.status_label.config(text="↶ Undone", foreground='orange')
        return 'break'  # Prevent default
    
    def _redo(self, event=None):
        """Redo last undone change."""
        if self.redo_stack:
            state = self.redo_stack.pop()
            self.undo_stack.append(state)
            
            self.text_editor.delete('1.0', tk.END)
            self.text_editor.insert('1.0', state)
            
            self.status_label.config(text="↷ Redone", foreground='orange')
        return 'break'
    
    def _toggle_recording(self):
        """Toggle voice recording on/off."""
        if self.is_recording:
            self._stop_recording()
        else:
            self._start_recording()
    
    def _start_recording(self):
        """Start voice recording."""
        try:
            import speech_recognition as sr
        except ImportError:
            messagebox.showerror(
                "Missing Library",
                "Speech recognition requires the SpeechRecognition library.\n\n"
                "Install with: pip install SpeechRecognition",
                parent=self.dialog
            )
            return
        
        self.is_recording = True
        self.record_btn.config(text="⏹ Stop Recording")
        self.status_label.config(text="🎤 Listening...", foreground='red')
        self._animate_recording()
        
        # Start recording thread
        self.recording_thread = threading.Thread(target=self._recording_loop, daemon=True)
        self.recording_thread.start()
    
    def _stop_recording(self):
        """Stop voice recording."""
        self.is_recording = False
        self.record_btn.config(text="🎤 Start Recording")
        self.status_label.config(text="Recording stopped", foreground='gray')
        self.recording_indicator.config(text="")
    
    def _animate_recording(self):
        """Animate the recording indicator."""
        if not self.is_recording:
            return
        
        # Pulse the indicator
        current = self.recording_indicator.cget('text')
        if current == "🔴":
            self.recording_indicator.config(text="⭕")
        else:
            self.recording_indicator.config(text="🔴")
        
        self.dialog.after(500, self._animate_recording)
    
    def _recording_loop(self):
        """Background thread for continuous voice recognition."""
        try:
            import speech_recognition as sr
            
            recognizer = sr.Recognizer()
            recognizer.dynamic_energy_threshold = True
            recognizer.pause_threshold = 0.8
            
            with sr.Microphone() as source:
                # Adjust for ambient noise
                self.dialog.after(0, lambda: self.status_label.config(
                    text="🔧 Adjusting for ambient noise...", foreground='orange'))
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                self.dialog.after(0, lambda: self.status_label.config(
                    text="🎤 Listening... Speak now!", foreground='green'))
                
                while self.is_recording:
                    try:
                        audio = recognizer.listen(source, timeout=5, phrase_time_limit=15)
                        
                        # Recognize speech
                        try:
                            text = recognizer.recognize_google(audio)
                            if text:
                                # Process on main thread
                                self.dialog.after(0, lambda t=text: self._process_speech(t))
                        except sr.UnknownValueError:
                            pass  # Speech not understood
                        except sr.RequestError as e:
                            self.dialog.after(0, lambda: self.status_label.config(
                                text=f"⚠️ Recognition error: {str(e)[:50]}", foreground='red'))
                    
                    except sr.WaitTimeoutError:
                        pass  # No speech detected, continue listening
                    except Exception as e:
                        if self.is_recording:
                            self.dialog.after(0, lambda: self.status_label.config(
                                text=f"⚠️ Error: {str(e)[:50]}", foreground='red'))
                        
        except Exception as e:
            self.dialog.after(0, lambda: messagebox.showerror(
                "Recording Error", f"Could not access microphone:\n{str(e)}", parent=self.dialog))
            self.dialog.after(0, self._stop_recording)
    
    def _process_speech(self, text: str):
        """Process recognized speech - either as command or text insertion."""
        self.last_speech_label.config(text=f'Heard: "{text}"')
        
        # Normalize text for command matching
        text_lower = text.lower().strip()
        
        # Save state before any changes
        self._save_undo_state()
        
        # Try to match commands
        if self._try_command(text_lower, text):
            return
        
        # Not a command - insert as text at cursor
        self._insert_text(text)
    
    def _try_command(self, text_lower: str, original_text: str) -> bool:
        """
        Try to match and execute a voice command.
        Returns True if a command was matched, False otherwise.
        """
        
        # === PARAGRAPH / LINE BREAKS ===
        if text_lower in ('new paragraph', 'new para', 'paragraph break', 'paragraph'):
            self._insert_at_cursor('\n\n')
            self.status_label.config(text="¶ Inserted paragraph break", foreground='green')
            return True
        
        if text_lower in ('new line', 'line break', 'next line'):
            self._insert_at_cursor('\n')
            self.status_label.config(text="↵ Inserted line break", foreground='green')
            return True
        
        # === UNDO / REDO ===
        if text_lower in ('scratch that', 'undo', 'undo that', 'take that back'):
            self._undo()
            return True
        
        if text_lower in ('redo', 'redo that', 'put it back'):
            self._redo()
            return True
        
        # === SELECT / CLEAR ===
        if text_lower in ('select all', 'select everything'):
            self.text_editor.tag_add('sel', '1.0', 'end-1c')
            self.status_label.config(text="Selected all text", foreground='green')
            return True
        
        if text_lower in ('clear all', 'delete all', 'delete everything', 'clear everything'):
            self.text_editor.delete('1.0', tk.END)
            self.status_label.config(text="🗑️ Cleared all text", foreground='orange')
            return True
        
        # === DONE / FINISH ===
        if text_lower in ('done', 'finish', 'finished', 'complete', 'save', 'save and close'):
            self._on_done()
            return True
        
        # === REPLACE X WITH Y ===
        # Patterns: "replace X with Y", "change X to Y"
        replace_patterns = [
            r'replace\s+(.+?)\s+with\s+(.+)',
            r'change\s+(.+?)\s+to\s+(.+)',
            r'swap\s+(.+?)\s+with\s+(.+)',
            r'substitute\s+(.+?)\s+with\s+(.+)',
        ]
        
        for pattern in replace_patterns:
            match = re.match(pattern, text_lower)
            if match:
                find_text = match.group(1).strip()
                replace_text = match.group(2).strip()
                
                if self._replace_text(find_text, replace_text):
                    self.status_label.config(
                        text=f'✓ Replaced "{find_text}" with "{replace_text}"',
                        foreground='green'
                    )
                else:
                    self.status_label.config(
                        text=f'⚠️ Could not find "{find_text}"',
                        foreground='orange'
                    )
                return True
        
        # === DELETE X ===
        delete_patterns = [
            r'delete\s+(?:the\s+)?(?:word\s+)?(.+)',
            r'remove\s+(?:the\s+)?(?:word\s+)?(.+)',
            r'erase\s+(?:the\s+)?(?:word\s+)?(.+)',
        ]
        
        for pattern in delete_patterns:
            match = re.match(pattern, text_lower)
            if match:
                delete_text = match.group(1).strip()
                
                # Don't delete common filler words that might be accidental
                if delete_text in ('the', 'a', 'an', 'that', 'this'):
                    continue
                
                if self._delete_text(delete_text):
                    self.status_label.config(
                        text=f'🗑️ Deleted "{delete_text}"',
                        foreground='green'
                    )
                else:
                    self.status_label.config(
                        text=f'⚠️ Could not find "{delete_text}"',
                        foreground='orange'
                    )
                return True
        
        # === INSERT X AFTER Y ===
        insert_patterns = [
            r'insert\s+(.+?)\s+after\s+(.+)',
            r'add\s+(.+?)\s+after\s+(.+)',
            r'put\s+(.+?)\s+after\s+(.+)',
        ]
        
        for pattern in insert_patterns:
            match = re.match(pattern, text_lower)
            if match:
                insert_text = match.group(1).strip()
                after_text = match.group(2).strip()
                
                if self._insert_after(after_text, insert_text):
                    self.status_label.config(
                        text=f'✓ Inserted "{insert_text}" after "{after_text}"',
                        foreground='green'
                    )
                else:
                    self.status_label.config(
                        text=f'⚠️ Could not find "{after_text}"',
                        foreground='orange'
                    )
                return True
        
        # === INSERT X BEFORE Y ===
        insert_before_patterns = [
            r'insert\s+(.+?)\s+before\s+(.+)',
            r'add\s+(.+?)\s+before\s+(.+)',
            r'put\s+(.+?)\s+before\s+(.+)',
        ]
        
        for pattern in insert_before_patterns:
            match = re.match(pattern, text_lower)
            if match:
                insert_text = match.group(1).strip()
                before_text = match.group(2).strip()
                
                if self._insert_before(before_text, insert_text):
                    self.status_label.config(
                        text=f'✓ Inserted "{insert_text}" before "{before_text}"',
                        foreground='green'
                    )
                else:
                    self.status_label.config(
                        text=f'⚠️ Could not find "{before_text}"',
                        foreground='orange'
                    )
                return True
        
        # No command matched
        return False
    
    def _insert_at_cursor(self, text: str):
        """Insert text at current cursor position."""
        self.text_editor.insert(tk.INSERT, text)
    
    def _insert_text(self, text: str):
        """Insert dictated text at cursor with proper spacing."""
        # Get character before cursor
        try:
            char_before = self.text_editor.get('insert-1c', 'insert')
        except:
            char_before = ''
        
        # Add space if needed
        if char_before and char_before not in ' \n\t':
            text = ' ' + text
        
        self.text_editor.insert(tk.INSERT, text)
        self.status_label.config(text=f'✓ Inserted text', foreground='green')
    
    def _replace_text(self, find: str, replace: str) -> bool:
        """Replace first occurrence of text. Returns True if found."""
        content = self.text_editor.get('1.0', 'end-1c')
        
        # Case-insensitive search
        lower_content = content.lower()
        find_lower = find.lower()
        
        pos = lower_content.find(find_lower)
        if pos == -1:
            return False
        
        # Find the actual text (preserve case) and replace
        actual_find = content[pos:pos + len(find)]
        new_content = content[:pos] + replace + content[pos + len(find):]
        
        self.text_editor.delete('1.0', tk.END)
        self.text_editor.insert('1.0', new_content)
        
        # Move cursor to replacement
        self.text_editor.mark_set('insert', f'1.0+{pos + len(replace)}c')
        self.text_editor.see('insert')
        
        return True
    
    def _delete_text(self, text: str) -> bool:
        """Delete first occurrence of text. Returns True if found."""
        return self._replace_text(text, '')
    
    def _insert_after(self, marker: str, text: str) -> bool:
        """Insert text after a marker. Returns True if marker found."""
        content = self.text_editor.get('1.0', 'end-1c')
        
        # Case-insensitive search
        lower_content = content.lower()
        marker_lower = marker.lower()
        
        pos = lower_content.find(marker_lower)
        if pos == -1:
            return False
        
        # Insert after marker
        insert_pos = pos + len(marker)
        new_content = content[:insert_pos] + ' ' + text + content[insert_pos:]
        
        self.text_editor.delete('1.0', tk.END)
        self.text_editor.insert('1.0', new_content)
        
        return True
    
    def _insert_before(self, marker: str, text: str) -> bool:
        """Insert text before a marker. Returns True if marker found."""
        content = self.text_editor.get('1.0', 'end-1c')
        
        # Case-insensitive search
        lower_content = content.lower()
        marker_lower = marker.lower()
        
        pos = lower_content.find(marker_lower)
        if pos == -1:
            return False
        
        # Insert before marker
        new_content = content[:pos] + text + ' ' + content[pos:]
        
        self.text_editor.delete('1.0', tk.END)
        self.text_editor.insert('1.0', new_content)
        
        return True
    
    def _show_command_popup(self):
        """Show or restore the command reference popup."""
        if self.command_popup:
            try:
                self.command_popup.window.deiconify()
                self.command_popup.window.lift()
            except:
                # Recreate if destroyed
                self.command_popup = CommandReferencePopup(self.dialog)
        else:
            self.command_popup = CommandReferencePopup(self.dialog)
    
    def _on_done(self):
        """Save and close."""
        self._stop_recording()
        self.result_text = self.text_editor.get('1.0', 'end-1c')
        self.cancelled = False
        
        if self.command_popup:
            self.command_popup.destroy()
        
        self.dialog.destroy()
    
    def _on_cancel(self):
        """Cancel without saving."""
        self._stop_recording()
        self.result_text = None
        self.cancelled = True
        
        if self.command_popup:
            self.command_popup.destroy()
        
        self.dialog.destroy()
    
    def _on_close(self):
        """Handle window close."""
        if self.is_recording:
            self._stop_recording()
        
        # Ask to save if text was modified
        current = self.text_editor.get('1.0', 'end-1c')
        if current != self.initial_text:
            result = messagebox.askyesnocancel(
                "Save Changes?",
                "Do you want to save your changes?",
                parent=self.dialog
            )
            if result is None:  # Cancel
                return
            elif result:  # Yes
                self._on_done()
                return
        
        self._on_cancel()
    
    def get_result(self) -> Optional[str]:
        """Wait for dialog to close and return result."""
        self.dialog.wait_window()
        return self.result_text


def open_voice_edit_dialog(parent, app, text: str, title: str = "Voice Edit") -> Optional[str]:
    """
    Open the voice edit dialog and return edited text.
    
    Args:
        parent: Parent window
        app: Main application instance
        text: Initial text to edit
        title: Dialog title
        
    Returns:
        Edited text if saved, None if cancelled
    """
    dialog = VoiceEditDialog(parent, app, text, title)
    return dialog.get_result()
