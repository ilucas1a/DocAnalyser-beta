"""
ChunkSettingsWindow - Chunk Size Settings Dialog

Extracted from Main.py for better maintainability.
"""

import tkinter as tk
from tkinter import ttk, messagebox

from config import CHUNK_SIZES
from config_manager import save_config


class ChunkSettingsWindow:
    """
    Chunk Settings Window - Configure document chunk sizes
    
    Allows user to select small/medium/large chunk sizes
    for document processing.
    """
    
    def __init__(self, parent, app):
        """
        Initialize Chunk Settings Window
        
        Args:
            parent: Parent tkinter window (usually app.root)
            app: Reference to main DocAnalyserApp instance
        """
        self.parent = parent
        self.app = app
        
        # Create the window
        self.window = tk.Toplevel(parent)
        self.window.title("Chunk Size Settings")
        self.window.geometry("500x400")
        
        # Track selected value
        current = self.app.config.get("chunk_size", "medium")
        self.selected = tk.StringVar(value=current)
        
        # Build the UI
        self._create_ui()
    
    def _create_ui(self):
        """Create all UI elements"""
        
        # Title
        ttk.Label(
            self.window, 
            text="Choose chunk size for processing:", 
            font=('Arial', 12, 'bold')
        ).pack(pady=10)
        
        # Radio buttons for each chunk size
        for key, info in CHUNK_SIZES.items():
            frame = ttk.LabelFrame(self.window, text=info["label"], padding=10)
            frame.pack(fill=tk.X, padx=20, pady=5)
            
            rb = ttk.Radiobutton(
                frame, 
                text=f"{info['description']}\nQuality: {info['quality']}", 
                variable=self.selected,
                value=key
            )
            rb.pack(anchor=tk.W)
        
        # Save button
        ttk.Button(
            self.window, 
            text="Save & Close", 
            command=self._save_and_close
        ).pack(pady=20)
    
    def _save_and_close(self):
        """Save the selected chunk size and close the window"""
        self.app.config["chunk_size"] = self.selected.get()
        save_config(self.app.config)
        messagebox.showinfo("Success", "Chunk size setting saved")
        self.window.destroy()
