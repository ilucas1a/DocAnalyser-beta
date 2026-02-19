# Step-by-Step Guide for Adding Force Reprocess Feature
## For VBA Users New to Python

This guide will help you add a checkbox to your app that lets you choose whether to use cached OCR results or reprocess from scratch.

---

## What You're Adding (In VBA Terms)

Think of this like adding an Excel userform checkbox that controls whether your macro uses saved data or recalculates everything fresh.

**Cached Mode (checkbox unchecked):**
- Like using Application.CalculationMode = xlCalculationAutomatic
- Fast because it uses previously saved results

**Force Reprocess (checkbox checked):**
- Like forcing Application.Calculate
- Slower but ensures fresh results with current settings

---

## Files You'll Edit

1. **ocr_handler.py** - The "backend" code (like a Module in VBA)
2. **Main.py** - The "frontend" UI code (like a UserForm in VBA)

---

## STEP 1: Edit ocr_handler.py (The Easy Part!)

### What You're Doing
Adding a parameter to a function - like adding an Optional parameter to a VBA function.

### Instructions

1. **Open** `ocr_handler.py` in PyCharm (or your text editor)

2. **Use Edit → Find** (Ctrl+F) to search for:
   ```
   def extract_text_from_pdf_with_ocr
   ```

3. **You'll see this code around line 428:**
   ```python
   def extract_text_from_pdf_with_ocr(filepath: str, language: str = "eng", 
                                      quality: str = "balanced",
                                      progress_callback=None, 
                                      resume_from_page: int = 0) -> List[Dict]:
   ```

4. **Change the first line TO:**
   ```python
   def extract_text_from_pdf_with_ocr(filepath: str, language: str = "eng", 
                                      quality: str = "balanced",
                                      progress_callback=None, 
                                      resume_from_page: int = 0, 
                                      force_reprocess: bool = False) -> List[Dict]:
   ```
   
   💡 **Think of it like:** `Function ProcessPDF(FilePath$, Language$, Optional ForceReprocess As Boolean = False)`

5. **A few lines down, find this:**
   ```python
   # Check for cached results
   cached = load_cached_ocr(filepath, quality, language)
   if cached and resume_from_page == 0:
       log("✅ Using cached OCR results")
       return cached
   ```

6. **Replace it with:**
   ```python
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

   💡 **Think of it like:** 
   ```vba
   If Not ForceReprocess Then
       ' Use cache
   Else
       ' Delete cache and recalculate
   End If
   ```

7. **Save** the file (Ctrl+S)

✅ **Done with ocr_handler.py!**

---

## STEP 2: Edit Main.py (The UI Part)

### Part A: Add the Variable (Like Declaring a Checkbox Control)

1. **Open** `Main.py` in PyCharm

2. **Use Edit → Find** (Ctrl+F) to search for:
   ```
   self.diarization_var = tk.BooleanVar
   ```

3. **You'll see something like:**
   ```python
   self.transcription_engine_var = tk.StringVar(value=self.config.get("transcription_engine", "openai_whisper"))
   self.transcription_lang_var = tk.StringVar(value=self.config.get("transcription_language", "en"))
   self.diarization_var = tk.BooleanVar(value=self.config.get("speaker_diarization", False))
   self.setup_ui()
   ```

4. **Add this line BEFORE `self.setup_ui()`:**
   ```python
   self.force_reprocess_var = tk.BooleanVar(value=False)
   ```

   💡 **Think of it like:** `Dim chkForceReprocess As MSForms.CheckBox` in VBA userform code

---

### Part B: Add the Checkbox to the Form

1. **Still in Main.py**, search for:
   ```
   OCR Settings
   ```

2. **You'll find a section that creates the OCR settings frame - it looks like:**
   ```python
   # OCR Settings frame
   ocr_frame = ttk.LabelFrame(file_frame, text="📋 OCR Settings", padding=10)
   ocr_frame.pack(fill=tk.X, pady=(0, 5))
   
   [... some more code for language and quality dropdowns ...]
   ```

3. **After the OCR settings frame code (but BEFORE any Load File button), add:**
   ```python
   # Force Reprocess checkbox
   reprocess_frame = ttk.Frame(file_frame)
   reprocess_frame.pack(fill=tk.X, pady=5)
   
   force_reprocess_cb = ttk.Checkbutton(
       reprocess_frame,
       text="☐ Force Reprocess (ignore cache, reprocess from scratch)",
       variable=self.force_reprocess_var
   )
   force_reprocess_cb.pack(anchor=tk.W, padx=5)
   
   ttk.Label(
       reprocess_frame,
       text="Tip: Check this to reprocess with different OCR settings",
       font=('Arial', 8),
       foreground='gray'
   ).pack(anchor=tk.W, padx=20)
   ```

   💡 **Think of it like:** Dragging a CheckBox control onto your VBA UserForm

---

### Part C: Connect the Checkbox to the Function

This is like having your VBA button's Click event call a function with the checkbox value.

1. **Still in Main.py**, search for all places where this function is called:**
   ```
   extract_text_from_pdf_with_ocr
   ```

2. **You'll find calls that look like:**
   ```python
   entries = extract_text_from_pdf_with_ocr(
       filepath,
       language=self.config.get("ocr_language", "eng"),
       quality=self.config.get("ocr_quality", "balanced"),
       progress_callback=self.set_status
   )
   ```

3. **Change each one TO:**
   ```python
   entries = extract_text_from_pdf_with_ocr(
       filepath,
       language=self.config.get("ocr_language", "eng"),
       quality=self.config.get("ocr_quality", "balanced"),
       progress_callback=self.set_status,
       force_reprocess=self.force_reprocess_var.get()
   )
   ```
   
   💡 **Notice:** Just adding one line at the end: `force_reprocess=self.force_reprocess_var.get()`

4. **Repeat** for ALL occurrences (typically 2-3 places)

5. **Save** the file (Ctrl+S)

✅ **Done with Main.py!**

---

## STEP 3: Test It!

1. **Run** your app
2. **Load a PDF** - should process normally (might take time for first load)
3. **Load the same PDF again** - should load instantly (using cache)
4. **Check the "Force Reprocess" checkbox**
5. **Load the same PDF again** - should reprocess from scratch
6. **Watch the status messages** - you should see "Force reprocess enabled"

---

## Troubleshooting

### Error: "unexpected keyword argument 'force_reprocess'"
**Problem:** You didn't add the parameter to the function definition in ocr_handler.py  
**Fix:** Go back to STEP 1 and make sure you added `, force_reprocess: bool = False` to the function signature

### Error: "'DocAnalyserApp' object has no attribute 'force_reprocess_var'"
**Problem:** You didn't add the variable in __init__  
**Fix:** Go back to Part A of STEP 2 and add `self.force_reprocess_var = tk.BooleanVar(value=False)`

### Checkbox doesn't appear
**Problem:** You might have added the checkbox code in the wrong place  
**Fix:** Make sure you added it in the Local Files tab setup, after the OCR settings but before the Load button

---

## What Each Part Does (VBA Comparison)

| Component | Python Code | VBA Equivalent |
|-----------|-------------|----------------|
| Variable declaration | `self.force_reprocess_var = tk.BooleanVar()` | `Dim chkForce As Boolean` |
| Checkbox control | `ttk.Checkbutton(variable=...)` | `CheckBox1` on UserForm |
| Getting value | `.get()` | `CheckBox1.Value` |
| Setting value | `.set(True)` | `CheckBox1.Value = True` |
| Function parameter | `force_reprocess: bool = False` | `Optional ForceIt As Boolean = False` |
| If statement | `if not force_reprocess:` | `If Not ForceIt Then` |

---

## Need Help?

If you get stuck:
1. Check that you saved both files after editing
2. Make sure Python syntax is exact (indentation matters!)
3. Look at the error message - Python errors are usually clear about what's wrong
4. Compare your code to the examples line by line

Remember: In Python, indentation IS the code structure (like VBA's If/End If, but spaces instead of keywords).
