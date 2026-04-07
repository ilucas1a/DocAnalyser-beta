"""
launch_transcript.py
=====================
Opens a DocAnalyser transcript .docx file in Word AND starts the companion
audio player in one command.

Usage:
    python launch_transcript.py "C:/Ian/Tony_Stewart_20262903m4a_source.docx"

Or without arguments — prompts you to select the .docx file:
    python launch_transcript.py

The script:
  1. Reads the audio file path from the Document Information block in the .docx
  2. Starts companion_player.py with that audio path (background process)
  3. Opens the .docx in Word

Author: DocAnalyser Development Team
"""

from __future__ import annotations

import os
import sys
import subprocess
import time


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLAYER_SCRIPT = os.path.join(SCRIPT_DIR, "companion_player.py")
PYTHON_EXE = sys.executable


def _find_audio_path(docx_path: str) -> str | None:
    """
    Try several strategies to find the audio file for this transcript:
      1. 'Audio file:' line in the Document Information block of the .docx
      2. DocAnalyser database — look for an audio_transcription doc whose
         title matches the .docx filename stem
    Returns the audio path if found and the file exists, else None.
    """
    # Strategy 1: read from the docx itself
    try:
        from docx import Document
        doc = Document(docx_path)
        for para in doc.paragraphs:
            text = para.text.strip()
            if text.startswith("Audio file:"):
                audio = text[len("Audio file:"):].strip()
                if audio and os.path.isfile(audio):
                    return audio
    except Exception:
        pass

    # Strategy 2: look up the DocAnalyser database
    try:
        import sys
        sys.path.insert(0, SCRIPT_DIR)
        from document_library import load_document_entries, get_document_by_id
        import sqlite3, os as _os
        appdata = _os.getenv("APPDATA") or _os.path.expanduser("~")
        db_path = _os.path.join(appdata, "DocAnalyser_Beta", "docanalyser.db")
        if _os.path.isfile(db_path):
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            # Find audio_transcription docs and check their metadata
            rows = conn.execute(
                "SELECT id, metadata FROM documents "
                "WHERE is_deleted=0 AND doc_type='audio_transcription' "
                "ORDER BY updated_at DESC LIMIT 50"
            ).fetchall()
            conn.close()
            import json
            for row in rows:
                try:
                    meta = json.loads(row["metadata"]) if row["metadata"] else {}
                    fp = meta.get("audio_file_path")
                    if fp and _os.path.isfile(fp):
                        return fp
                except Exception:
                    continue
    except Exception:
        pass

    return None


def _pick_docx() -> str | None:
    """Show a file picker if no argument given."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        path = filedialog.askopenfilename(
            title="Select transcript Word document",
            filetypes=[("Word documents", "*.docx"), ("All files", "*.*")]
        )
        root.destroy()
        return os.path.normpath(path) if path else None
    except Exception:
        return None


def _pick_audio(docx_path: str) -> str | None:
    """Show a file picker to choose the audio file manually."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        initial = os.path.dirname(docx_path)
        path = filedialog.askopenfilename(
            title="Select audio file for this transcript",
            initialdir=initial,
            filetypes=[
                ("Audio files", "*.mp3 *.m4a *.wav *.ogg *.aac *.flac"),
                ("All files", "*.*")
            ]
        )
        root.destroy()
        return os.path.normpath(path) if path else None
    except Exception:
        return None


def launch(docx_path: str):
    docx_path = os.path.normpath(docx_path)

    if not os.path.isfile(docx_path):
        print(f"ERROR: File not found: {docx_path}")
        sys.exit(1)

    # ── Find audio file ───────────────────────────────────────────────────────
    print(f"Reading transcript: {os.path.basename(docx_path)}")
    audio_path = _find_audio_path(docx_path)

    if audio_path:
        print(f"Audio file found automatically: {audio_path}")
    else:
        # Only ask the user if we genuinely cannot find it
        print("Audio file not found automatically — please select it.")
        audio_path = _pick_audio(docx_path)
        if not audio_path:
            print("No audio file selected — launching Word without audio player.")

    # ── Start companion player ────────────────────────────────────────────────
    if audio_path and os.path.isfile(PLAYER_SCRIPT):
        print(f"Starting companion player…")
        cmd = [PYTHON_EXE, PLAYER_SCRIPT, audio_path]
        kwargs = {}
        if sys.platform == "win32":
            # CREATE_NEW_CONSOLE gives the player its own window
            kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
        subprocess.Popen(cmd, **kwargs)
        # Give the player a moment to start its HTTP server before Word opens
        time.sleep(1.5)
    elif not os.path.isfile(PLAYER_SCRIPT):
        print(f"Warning: companion_player.py not found at {PLAYER_SCRIPT}")

    # ── Open Word document ────────────────────────────────────────────────────
    print(f"Opening Word document…")
    if sys.platform == "win32":
        os.startfile(docx_path)
    elif sys.platform == "darwin":
        subprocess.run(["open", docx_path])
    else:
        subprocess.run(["xdg-open", docx_path])

    print("Done. Word is opening — click any [MM:SS] timestamp to play audio.")


def main():
    if len(sys.argv) > 1:
        docx_path = " ".join(sys.argv[1:]).strip('"')
    else:
        print("Select the transcript Word document…")
        docx_path = _pick_docx()
        if not docx_path:
            print("No file selected. Exiting.")
            sys.exit(0)

    launch(docx_path)


if __name__ == "__main__":
    main()
