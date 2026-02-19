# Force Reprocess Feature - Implementation Guide

This guide shows you how to add a "Force Reprocess" option that lets you choose between using cached OCR results or reprocessing from scratch.

## Overview

Currently, when you load a PDF that's been processed before, the app automatically uses the cached OCR results. This new feature adds a checkbox to let you choose.

## Changes Required

### 1. Modify `ocr_handler.py`

**File:** `ocr_handler.py`  
**Function:** `extract_text_from_pdf_with_ocr` (around line 428)

**FIND THIS:**
```python
def extract_text_from_pdf_with_ocr(filepath: str, language: str = "eng", quality: str = "balanced",
                                   progress_callback=None, resume_from_page: int = 0) -> List[Dict]:
    """Extract text from PDF using OCR with pre-screening for corruption"""

    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    # Check for cached results
    cached = load_cached_ocr(filepath, quality, language)
    if cached and resume_from_page == 0:
        log("✅ Using cached OCR results")
        return cached
```

**REPLACE WITH:**
```python
def extract_text_from_pdf_with_ocr(filepath: str, language: str = "eng", quality: str = "balanced",
                                   progress_callback=None, resume_from_page: int = 0, force_reprocess: bool = False) -> List[Dict]:
    """Extract text from PDF using OCR with pre-screening for corruption
    
    Args:
        filepath: Path to PDF file
        language: OCR language code
        quality: OCR quality preset
        progress_callback: Function to report progress
        resume_from_page: Page to resume from
        force_reprocess: If True, ignore cache and reprocess from scratch
    """

    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    # Check for cached results (unless force_reprocess is True)
    if not force_reprocess:
        cached = load_cached_ocr(filepath, quality, language)
        if cached and resume_from_page == 0:
            log("✅ Using cached OCR results")
            return cached
    else:
        log("🔄 Force reprocess enabled - ignoring cache")
        # Delete existing cache if it exists
        cache_path = get_ocr_cache_path(filepath, quality, language)
        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
                log("🗑️ Deleted old cache file")
            except Exception as e:
                log(f"⚠️ Could not delete cache: {e}")
```

---

### 2. Modify `Main.py` - Add Checkbox to UI

**File:** `Main.py`

**Step A: Add instance variable in `__init__` method (around line 132)**

**FIND THIS SECTION:**
```python
        self.transcription_engine_var = tk.StringVar(value=self.config.get("transcription_engine", "openai_whisper"))
        self.transcription_lang_var = tk.StringVar(value=self.config.get("transcription_language", "en"))
        self.diarization_var = tk.BooleanVar(value=self.config.get("speaker_diarization", False))
        self.setup_ui()
```

**ADD THIS LINE BEFORE `self.setup_ui()`:**
```python
        self.force_reprocess_var = tk.BooleanVar(value=False)  # Checkbox for force reprocess
```

**Step B: Add checkbox to Local Files tab**

**FIND:** The section where the OCR settings frame is created (around line 2300-2400, search for "OCR Settings" and "setup_file_tab")

You'll find code like this:
```python
        # OCR Settings frame
        ocr_frame = ttk.LabelFrame(file_frame, text="📋 OCR Settings", padding=10)
        ocr_frame.pack(fill=tk.X, pady=(0, 5))
```

**ADD THIS CODE after the OCR settings frame (before any buttons):**
```python
        # Force reprocess checkbox
        reprocess_frame = ttk.Frame(file_frame)
        reprocess_frame.pack(fill=tk.X, pady=5)
        
        force_reprocess_cb = ttk.Checkbutton(
            reprocess_frame,
            text="Force Reprocess (ignore cache, reprocess from scratch)",
            variable=self.force_reprocess_var
        )
        force_reprocess_cb.pack(anchor=tk.W, padx=5)
        
        ttk.Label(
            reprocess_frame,
            text="Tip: Check this if you want to reprocess with different OCR settings",
            font=('Arial', 8),
            foreground='gray'
        ).pack(anchor=tk.W, padx=20)
```

**Step C: Pass the force_reprocess parameter when calling OCR**

**FIND:** All places where `extract_text_from_pdf_with_ocr` is called. Search for this function name in Main.py.

You should find it in at least two places:
1. When processing local PDF files
2. When processing web PDFs

**FOR EACH OCCURRENCE, CHANGE FROM:**
```python
entries = extract_text_from_pdf_with_ocr(
    filepath,
    language=self.config.get("ocr_language", "eng"),
    quality=self.config.get("ocr_quality", "balanced"),
    progress_callback=self.set_status
)
```

**TO:**
```python
entries = extract_text_from_pdf_with_ocr(
    filepath,
    language=self.config.get("ocr_language", "eng"),
    quality=self.config.get("ocr_quality", "balanced"),
    progress_callback=self.set_status,
    force_reprocess=self.force_reprocess_var.get()  # NEW: Pass checkbox value
)
```

---

## How It Works

1. **When checkbox is UNCHECKED (default):**
   - App checks for cached OCR results
   - If cache exists, uses it instantly
   - If no cache, processes the PDF and saves results

2. **When checkbox is CHECKED:**
   - App ignores any existing cache
   - Deletes the old cache file
   - Processes the PDF fresh from scratch
   - Saves new results to cache

---

## Benefits

✅ **Fast by default** - Uses cache when available  
✅ **User control** - Can force reprocess when needed  
✅ **Clean cache** - Automatically removes old cache when reprocessing  
✅ **Status updates** - Shows clear messages about what's happening

---

## Use Cases for Force Reprocess

- Changed OCR language settings
- Changed OCR quality (fast → accurate)
- Suspect the cached version had errors
- Source PDF was updated
- Want to test different OCR settings

---

## Testing

1. Load a PDF for the first time → Should process normally
2. Load the same PDF again → Should use cache (fast)
3. Check "Force Reprocess" and load again → Should reprocess from scratch
4. Watch status messages to confirm behavior

---

## Alternative: Quick Access Button

If you want a button instead of/in addition to the checkbox, add this in the same location:

```python
# Quick button to toggle force reprocess
ttk.Button(
    reprocess_frame,
    text="🔄 Reprocess This File",
    command=lambda: [self.force_reprocess_var.set(True), self.load_file()],
    width=20
).pack(side=tk.LEFT, padx=5)
```

This gives users a one-click option to reprocess the current file.
