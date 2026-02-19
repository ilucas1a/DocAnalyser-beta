
from __future__ import annotations
"""
ocr_handler.py - OCR Processing
Handles image and scanned PDF text extraction with corruption protection
"""
# KNOWN LIMITATION:
# PDFs with "Object X Y ref" corruption cause infinite loops at the C library level
# that cannot be caught programmatically on Windows. Users must:
# 1. Close application if OCR freezes for >1 minute
# 2. Repair PDF at https://www.ilovepdf.com/repair-pdf
# 3. Try again with repaired PDF
import os
import sys
import json
import webbrowser
import subprocess
import tempfile
from typing import List, Dict, Optional

# Import from our modules
from config import *
from utils import calculate_file_hash, format_size

# Vision AI for OCR escalation
try:
    from ai_handler import (
        call_vision_ai, 
        check_provider_supports_vision,
        check_provider_supports_pdf,
        process_pdf_with_cloud_ai,
        extract_text_from_pdf_cloud_ai,
        ocr_with_google_cloud_vision  # Dedicated OCR service
    )
    VISION_AI_AVAILABLE = True
except ImportError:
    VISION_AI_AVAILABLE = False

# Import OCR libraries
try:
    import pytesseract
    from pdf2image import convert_from_path
    from PIL import Image, ImageEnhance, ImageFilter

    OCR_SUPPORT = True
except Exception as e:
    OCR_SUPPORT = False
    OCR_IMPORT_ERROR = str(e)

try:
    import PyPDF2

    PDF_SUPPORT_PYPDF2 = True
except Exception:
    PDF_SUPPORT_PYPDF2 = False

PDF_SUPPORT = PDF_SUPPORT_PYPDF2


# -------------------------
# OCR Post-Processing (Fix Encoding Artifacts)
# -------------------------

def fix_ocr_encoding_artifacts(text: str) -> str:
    """
    Fix common encoding artifacts from Tesseract OCR.
    
    Tesseract often produces UTF-8 mojibake when processing documents
    with curly quotes, em-dashes, and other special characters.
    This function cleans up these predictable errors.
    
    Args:
        text: Raw OCR text with potential encoding artifacts
        
    Returns:
        Cleaned text with proper Unicode characters
    """
    if not text:
        return text
    
    # Common UTF-8 mojibake patterns and their corrections
    replacements = [
        # Curly double quotes
        ('â€œ', '"'),      # Left double quote
        ('â€', '"'),   # Right double quote
        ('â€', '"'),       # Partial right quote
        
        # Curly single quotes / apostrophes
        ('â€™', "'"),      # Right single quote / apostrophe
        ('â€˜', "'"),      # Left single quote
        
        # Dashes
        ('â€"', '—'),      # Em dash
        ('â€"', '–'),      # En dash
        
        # Other common artifacts
        ('Â«', '«'),       # Left guillemet
        ('Â»', '»'),       # Right guillemet
        ('â€¦', '…'),      # Ellipsis
        ('â€¢', '•'),      # Bullet point
        ('â„¢', '™'),      # Trademark
        ('Â©', '©'),       # Copyright
        ('Â®', '®'),       # Registered trademark
        ('â‚¬', '€'),      # Euro sign
        ('Â£', '£'),       # Pound sign
        ('Â°', '°'),       # Degree symbol
        ('Â½', '½'),       # One half
        ('Â¼', '¼'),       # One quarter
        ('Â¾', '¾'),       # Three quarters
    ]
    
    # Apply all replacements
    for old, new in replacements:
        text = text.replace(old, new)
    
    # Clean up stray Â characters before letters (non-breaking space artifacts)
    import re
    text = re.sub(r'Â([A-Za-z])', r'\1', text)
    
    # Remove standalone Â characters
    text = text.replace(' Â ', ' ')
    text = text.replace('Â ', ' ')
    text = text.replace(' Â', ' ')
    
    # Clean up multiple spaces
    text = re.sub(r'  +', ' ', text)
    
    # Clean up lines that are mostly garbage (common at headers/footers)
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if len(stripped) > 0:
            alnum_count = sum(1 for c in stripped if c.isalnum() or c.isspace())
            total_count = len(stripped)
            # If less than 30% alphanumeric and line is short, likely garbage
            if total_count < 50 and total_count > 0 and alnum_count / total_count < 0.3:
                continue  # Skip garbage line
        cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines).strip()

# -------------------------
# OCR Cache Functions
# -------------------------

def ensure_ocr_cache():
    """Ensure OCR cache directory exists"""
    os.makedirs(OCR_CACHE_DIR, exist_ok=True)


def get_ocr_cache_path(filepath: str, quality: str, language: str) -> str:
    """Get cache file path for OCR results"""
    file_hash = calculate_file_hash(filepath)
    cache_key = f"{file_hash}_{quality}_{language}.json"
    return os.path.join(OCR_CACHE_DIR, cache_key)


def load_cached_ocr(filepath: str, quality: str, language: str) -> Optional[List[Dict]]:
    """Load cached OCR results if available"""
    ensure_ocr_cache()
    cache_path = get_ocr_cache_path(filepath, quality, language)

    if not os.path.exists(cache_path):
        return None

    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def save_ocr_cache(filepath: str, quality: str, language: str, entries: List[Dict]):
    """Save OCR results to cache"""
    ensure_ocr_cache()
    cache_path = get_ocr_cache_path(filepath, quality, language)

    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: Could not save OCR cache: {e}")


# -------------------------
# Tesseract Functions
# -------------------------

def get_tessdata_dir() -> Optional[str]:
    """Find tessdata directory for Tesseract, including bundled version"""
    # Check for bundled tessdata first (when running as frozen exe)
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        bundled_paths = [
            os.path.join(exe_dir, '_internal', 'tools', 'tesseract', 'tessdata'),
            os.path.join(exe_dir, 'tools', 'tesseract', 'tessdata'),
        ]
        for path in bundled_paths:
            eng_file = os.path.join(path, 'eng.traineddata')
            if os.path.exists(eng_file):
                return path
    
    # Check standard installation paths
    if sys.platform.startswith("win"):
        standard_paths = [
            r"C:\Program Files\Tesseract-OCR\tessdata",
            r"C:\Program Files (x86)\Tesseract-OCR\tessdata",
            r"C:\Tesseract-OCR\tessdata",
        ]
        for path in standard_paths:
            eng_file = os.path.join(path, 'eng.traineddata')
            if os.path.exists(eng_file):
                return path
    
    return None


def find_tesseract_windows() -> Optional[str]:
    """Find Tesseract installation on Windows, including bundled version"""
    if not sys.platform.startswith("win"):
        return None

    # Check for bundled Tesseract first (when running as frozen exe)
    if getattr(sys, 'frozen', False):
        # Running as packaged executable
        exe_dir = os.path.dirname(sys.executable)
        bundled_paths = [
            os.path.join(exe_dir, '_internal', 'tools', 'tesseract', 'tesseract.exe'),
            os.path.join(exe_dir, 'tools', 'tesseract', 'tesseract.exe'),
        ]
        for path in bundled_paths:
            if os.path.exists(path):
                return path

    common_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"C:\Tesseract-OCR\tesseract.exe",
        os.path.join(os.environ.get('LOCALAPPDATA', ''), r"Programs\Tesseract-OCR\tesseract.exe"),
    ]

    for path in common_paths:
        if os.path.exists(path):
            return path

    return None


def configure_tesseract_path(custom_path: str = ""):
    """Configure Tesseract executable path"""
    if not OCR_SUPPORT:
        return False

    if custom_path and os.path.exists(custom_path):
        pytesseract.pytesseract.tesseract_cmd = custom_path
        return True

    if sys.platform.startswith("win"):
        found_path = find_tesseract_windows()
        if found_path:
            pytesseract.pytesseract.tesseract_cmd = found_path
            return True

    return False


def check_ocr_availability() -> tuple:
    """Check if OCR is available and properly configured"""
    if not OCR_SUPPORT:
        return False, f"OCR libraries not installed. Error: {OCR_IMPORT_ERROR}\n\nInstall with: pip install pytesseract pdf2image Pillow", ""

    # Import load_config from main (this function should be in config or utils eventually)
    try:
        from utils import load_json
        config = load_json(CONFIG_PATH, DEFAULT_CONFIG)
    except:
        config = DEFAULT_CONFIG

    custom_path = config.get("tesseract_path", "")
    configure_tesseract_path(custom_path)

    try:
        version = pytesseract.get_tesseract_version()
        current_path = pytesseract.pytesseract.tesseract_cmd

        poppler_available, _ = check_poppler_availability()
        if not poppler_available:
            return False, "POPPLER_NOT_FOUND", current_path

        return True, "", current_path
    except Exception as e:
        if sys.platform.startswith("win"):
            found_path = find_tesseract_windows()
            if found_path:
                pytesseract.pytesseract.tesseract_cmd = found_path
                try:
                    pytesseract.get_tesseract_version()
                    poppler_available, _ = check_poppler_availability()
                    if not poppler_available:
                        return False, "POPPLER_NOT_FOUND", found_path
                    return True, "", found_path
                except:
                    pass

        return False, "TESSERACT_NOT_FOUND", ""


def get_tesseract_install_info() -> tuple:
    """Get installation instructions for Tesseract"""
    if sys.platform.startswith("win"):
        url = "https://github.com/UB-Mannheim/tesseract/wiki"
        instructions = """Tesseract OCR is required for scanning documents.

WINDOWS INSTALLATION (Quick Method):
1. Click 'Download Tesseract' below
2. Download the latest installer (e.g., tesseract-ocr-w64-setup-5.x.x.exe)
3. Run the installer
4. Important: During installation, note the installation path
5. Restart this application

Default installation path: C:\\Program Files\\Tesseract-OCR\\tesseract.exe

If Tesseract is not auto-detected, you can manually configure the path in OCR Settings."""
        return url, instructions
    elif sys.platform == "darwin":
        url = "https://formulae.brew.sh/formula/tesseract"
        instructions = """Tesseract OCR is required for scanning documents.

MAC INSTALLATION:
Using Homebrew (Recommended):
  1. Open Terminal
  2. Run: brew install tesseract
  3. Restart this application

Tesseract will be automatically added to your PATH."""
        return url, instructions
    else:
        url = "https://tesseract-ocr.github.io/tessdoc/Installation.html"
        instructions = """Tesseract OCR is required for scanning documents.

LINUX INSTALLATION:
Ubuntu/Debian:
  sudo apt-get install tesseract-ocr

Fedora:
  sudo dnf install tesseract

Arch:
  sudo pacman -S tesseract

Then restart this application."""
        return url, instructions


# -------------------------
# Poppler Functions
# -------------------------

def find_poppler_path() -> Optional[str]:
    """Find Poppler installation path, including bundled version"""
    if not sys.platform.startswith("win"):
        return None  # On Linux/Mac, poppler is typically in PATH

    # Check for bundled Poppler first (when running as frozen exe)
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        bundled_paths = [
            os.path.join(exe_dir, '_internal', 'tools', 'poppler', 'Library', 'bin'),
            os.path.join(exe_dir, '_internal', 'tools', 'poppler', 'bin'),
            os.path.join(exe_dir, 'tools', 'poppler', 'Library', 'bin'),
            os.path.join(exe_dir, 'tools', 'poppler', 'bin'),
        ]
        for path in bundled_paths:
            pdftoppm = os.path.join(path, 'pdftoppm.exe')
            if os.path.exists(pdftoppm):
                return path

    # Check common installation paths
    common_paths = [
        r"C:\poppler\Library\bin",
        r"C:\poppler\bin",
        r"C:\Program Files\poppler\Library\bin",
        r"C:\Program Files\poppler\bin",
    ]
    for path in common_paths:
        pdftoppm = os.path.join(path, 'pdftoppm.exe')
        if os.path.exists(pdftoppm):
            return path

    return None


def check_poppler_availability() -> tuple:
    """Check if Poppler is available"""
    if not OCR_SUPPORT:
        return False, "OCR libraries not installed"

    # Try to find and configure Poppler path
    poppler_path = find_poppler_path()
    if poppler_path:
        # Add to PATH so pdf2image can find it
        os.environ['PATH'] = poppler_path + os.pathsep + os.environ.get('PATH', '')

    try:
        from pdf2image import pdfinfo_from_path
        return True, ""
    except Exception:
        return False, "POPPLER_NOT_FOUND"


def get_poppler_install_info() -> tuple:
    """Get installation instructions for Poppler"""
    if sys.platform.startswith("win"):
        url = "https://github.com/oschwartz10612/poppler-windows/releases/"
        instructions = """Poppler is required to convert PDF pages to images for OCR.

WINDOWS INSTALLATION (Quick Method):
1. Click 'Download Poppler' below
2. Download the latest Release-XX.XX.X-0.zip file
3. Extract the ZIP file to C:\\poppler
4. Add to system PATH:
   - Open System Properties → Environment Variables
   - Under System Variables, find 'Path'
   - Click Edit → New
   - Add: C:\\poppler\\Library\\bin
   - Click OK on all dialogs
5. Restart this application

Alternative: The setup wizard can help configure a custom path."""
        return url, instructions
    elif sys.platform == "darwin":
        url = "https://formulae.brew.sh/formula/poppler"
        instructions = """Poppler is required to convert PDF pages to images for OCR.

MAC INSTALLATION:
Using Homebrew (Recommended):
  1. Open Terminal
  2. Run: brew install poppler
  3. Restart this application

Poppler will be automatically added to your PATH."""
        return url, instructions
    else:
        url = "https://poppler.freedesktop.org/"
        instructions = """Poppler is required to convert PDF pages to images for OCR.

LINUX INSTALLATION:
Ubuntu/Debian:
  sudo apt-get install poppler-utils

Fedora:
  sudo dnf install poppler-utils

Arch:
  sudo pacman -S poppler

Then restart this application."""
        return url, instructions


# -------------------------
# PDF Corruption Detection
# -------------------------

def test_pdf_with_subprocess(filepath: str, timeout: int = 5) -> tuple:
    """
    Test PDF by trying to convert just the FIRST page with a subprocess timeout.
    This catches infinite loops because subprocess CAN be killed (unlike threads).
    
    Timeout reduced to 5 seconds - converting one page at 72 DPI should be very fast.

    Returns: (is_safe, error_message)
    """
    # When running as frozen executable, we can't use sys.executable to run Python scripts
    # because sys.executable is DocAnalyser.exe, not python.exe
    # In this case, skip the subprocess test and proceed with caution
    if getattr(sys, 'frozen', False):
        # Running as packaged executable - skip subprocess test
        # The main OCR process will handle errors if they occur
        return True, ""
    
    try:
        # Create a simple test script that tries to convert first page only
        test_script = f'''
import sys
try:
    from pdf2image import convert_from_path
    images = convert_from_path(r"{filepath}", dpi=72, first_page=1, last_page=1)
    print("SUCCESS")
except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(1)
'''

        # Write test script to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(test_script)
            test_file = f.name

        try:
            # Run the test script with timeout
            result = subprocess.run(
                [sys.executable, test_file],
                capture_output=True,
                timeout=timeout,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            if 'SUCCESS' in result.stdout:
                return True, ""
            else:
                return False, f"PDF test conversion failed: {result.stdout[:200]} {result.stderr[:200]}"

        except subprocess.TimeoutExpired:
            return False, f"PDF test timed out after {timeout} seconds - infinite loop detected!"

        finally:
            # Clean up temp file
            try:
                os.unlink(test_file)
            except:
                pass

    except Exception as e:
        # If we can't test, log warning but allow it to proceed
        print(f"Warning: Could not pre-screen PDF: {e}")
        return True, ""


def pre_screen_pdf_for_ocr(filepath: str, log_func) -> bool:
    """
    Pre-screen PDF for corruption issues before attempting full OCR.
    Returns True if safe to proceed, False if corrupted.
    Automatically offers repair if corruption detected.
    """
    log_func("🔍 Pre-screening PDF for corruption...")
    log_func("🧪 Testing first page conversion (5 second timeout)...")

    is_safe, error = test_pdf_with_subprocess(filepath, timeout=5)

    if not is_safe:
        log_func(f"❌ PDF pre-screen FAILED: {error}")
        log_func("")
        log_func("This PDF will cause an infinite loop and cannot be processed.")
        offer_pdf_repair(filepath, log_func)
        return False

    log_func("✅ PDF passed pre-screen - safe for OCR")
    return True


def offer_pdf_repair(filepath: str, log_func):
    """Offer to open PDF repair website"""
    error_msg = f"""
╔══════════════════════════════════════════════════════════════════╗
║              CORRUPTED PDF DETECTED                              ║
╚══════════════════════════════════════════════════════════════════╝

File: {os.path.basename(filepath)}

This PDF is corrupted and will cause an infinite processing loop.
This is common with very old scanned documents.

📋 QUICK FIX STEPS:

1. Opening PDF repair website in your browser...
2. Upload your PDF file: {os.path.basename(filepath)}
3. Download the repaired version
4. Try OCR again with the repaired file

🔧 Repair website: https://www.ilovepdf.com/repair-pdf

Alternative repair sites:
• https://smallpdf.com/repair-pdf  
• https://www.pdf2go.com/repair-pdf

The repair process usually takes less than 1 minute!
"""

    log_func(error_msg)

    # Try to open repair website
    try:
        webbrowser.open("https://www.ilovepdf.com/repair-pdf")
        log_func("🌐 Opened PDF repair website in your browser")
    except Exception:
        log_func("⚠️ Could not open browser automatically")


def try_cloud_ai_pdf_fallback(
    filepath: str,
    provider: str,
    model: str,
    api_key: str,
    log_func,
    document_title: str = None,
    all_api_keys: dict = None
) -> tuple:
    """
    Try to process a corrupted PDF using Cloud AI direct processing.
    
    This bypasses Poppler entirely by sending the raw PDF to Claude or Gemini.
    Will automatically try alternative providers if the selected one doesn't support PDF.
    
    Args:
        filepath: Path to the PDF file
        provider: Currently selected AI provider name
        model: Model name for selected provider
        api_key: API key for selected provider
        log_func: Logging function
        document_title: Optional document title
        all_api_keys: Dict of all configured API keys (provider -> key)
                      If provided, enables fallback to other PDF-capable providers
        
    Returns:
        Tuple of (success, result_or_error)
        If success: result is list of entry dicts
        If failure: result is error message string
    """
    if not VISION_AI_AVAILABLE:
        return False, "Cloud AI module not available"
    
    # Build list of providers to try, in order of preference
    providers_to_try = []
    
    # PDF-capable providers and their default models
    pdf_providers = {
        "Google (Gemini)": "gemini-1.5-flash",
        "Anthropic (Claude)": "claude-3-5-sonnet-20241022",
    }
    
    # First, try the selected provider if it supports PDF
    if provider in pdf_providers and api_key:
        providers_to_try.append((provider, model, api_key))
    
    # Then add other PDF-capable providers if we have their API keys
    if all_api_keys:
        for pdf_provider, default_model in pdf_providers.items():
            if pdf_provider != provider:  # Don't add if already in list
                key = all_api_keys.get(pdf_provider, "")
                if key and key != "not-required":
                    providers_to_try.append((pdf_provider, default_model, key))
    
    # If no PDF-capable providers available
    if not providers_to_try:
        log_func(f"\n⚠️ No PDF-capable AI providers configured.")
        log_func("   Direct PDF processing requires Gemini or Claude API access.")
        _show_gemini_suggestion(log_func)
        return False, "No PDF-capable providers available"
    
    # Try each provider in order
    last_error = None
    for try_provider, try_model, try_key in providers_to_try:
        log_func(f"\n💡 Attempting direct PDF upload to {try_provider}...")
        log_func("   This bypasses local PDF conversion entirely.")
        
        try:
            success, result = process_pdf_with_cloud_ai(
                pdf_path=filepath,
                provider=try_provider,
                model=try_model,
                api_key=try_key,
                document_title=document_title,
                progress_callback=log_func
            )
            
            if success:
                # Convert text result to entries format
                entries = []
                paragraphs = [p.strip() for p in result.split('\n\n') if p.strip()]
                
                for para in paragraphs:
                    entries.append({
                        'start': 1,
                        'text': para,
                        'location': f'Cloud AI ({try_provider})'
                    })
                
                log_func(f"✅ Success with {try_provider}! Extracted {len(entries)} text segments.")
                return True, entries
            else:
                log_func(f"❌ {try_provider} failed: {result[:100]}...")
                last_error = result
                
        except Exception as e:
            log_func(f"❌ {try_provider} error: {str(e)[:100]}")
            last_error = str(e)
    
    # All providers failed - show helpful suggestion
    log_func(f"\n❌ All Cloud AI providers failed.")
    
    # If Gemini wasn't tried (no API key), suggest it
    gemini_key = all_api_keys.get("Google (Gemini)", "") if all_api_keys else ""
    if not gemini_key or gemini_key == "not-required":
        _show_gemini_suggestion(log_func)
    
    return False, last_error or "All PDF-capable providers failed"


def _show_gemini_suggestion(log_func):
    """
    Show helpful message about using Gemini for corrupted PDFs.
    """
    log_func("")
    log_func("═" * 55)
    log_func("💡 TIP: Google Gemini is excellent for corrupted PDFs")
    log_func("═" * 55)
    log_func("")
    log_func("Gemini can often read PDFs that crash other tools.")
    log_func("The API has a generous free tier (enough for most documents).")
    log_func("")
    log_func("🔗 Get a free Gemini API key:")
    log_func("   https://aistudio.google.com/app/apikey")
    log_func("")
    log_func("Once you have a key, add it in Settings → API Keys.")
    log_func("")


def extract_text_from_pdf_smart(
    filepath: str,
    language: str = "eng",
    quality: str = "balanced",
    provider: str = None,
    model: str = None,
    api_key: str = None,
    all_api_keys: dict = None,
    progress_callback=None,
    force_cloud: bool = False
) -> tuple:
    """
    Smart PDF text extraction with automatic fallback chain:
    
    1. Try local Poppler + Tesseract (fastest, free)
    2. If fails → Try Cloud AI direct PDF upload (Plan B)
    3. If Plan B fails → Offer iLovePDF repair (Plan C)
    
    Args:
        filepath: Path to PDF file
        language: OCR language code
        quality: OCR quality preset
        provider: AI provider for Cloud fallback
        model: AI model for Cloud fallback
        api_key: API key for Cloud fallback
        all_api_keys: Dict of all configured API keys (enables trying multiple providers)
        progress_callback: Progress logging function
        force_cloud: Skip local OCR, go straight to Cloud AI
        
    Returns:
        Tuple of (success, entries_or_error, method_used)
        method_used: 'local', 'cloud_direct', or 'failed'
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg)
    
    document_title = os.path.basename(filepath)
    
    # Option to skip directly to Cloud AI (useful for known-problematic PDFs)
    if force_cloud:
        log("🌐 Force Cloud mode - skipping local OCR")
        if provider and model and api_key:
            success, result = try_cloud_ai_pdf_fallback(
                filepath, provider, model, api_key, log, document_title,
                all_api_keys=all_api_keys
            )
            if success:
                return True, result, 'cloud_direct'
            else:
                log(f"\n❌ Cloud AI failed: {result}")
                offer_pdf_repair(filepath, log)
                return False, result, 'failed'
        else:
            log("⚠️ Cloud AI not configured - need provider, model, and API key")
            return False, "Cloud AI not configured", 'failed'
    
    # STEP 1: Try local Poppler + Tesseract
    log("📄 Attempting local PDF processing...")
    
    try:
        # Pre-screen for corruption
        if not pre_screen_pdf_for_ocr(filepath, log):
            raise RuntimeError("PDF failed pre-screening")
        
        # Try local OCR
        entries = extract_text_from_pdf_with_ocr(
            filepath=filepath,
            language=language,
            quality=quality,
            progress_callback=progress_callback
        )
        
        if entries:
            log(f"✅ Local OCR successful! Extracted {len(entries)} segments.")
            return True, entries, 'local'
        else:
            raise RuntimeError("No text extracted")
            
    except Exception as local_error:
        log(f"\n⚠️ Local processing failed: {str(local_error)[:100]}")
        
        # STEP 2: Try Cloud AI direct PDF (Plan B)
        if provider and model and api_key and VISION_AI_AVAILABLE:
            log("\n" + "="*50)
            log("💡 PLAN B: Trying Cloud AI direct PDF processing...")
            log("="*50)
            
            success, result = try_cloud_ai_pdf_fallback(
                filepath, provider, model, api_key, log, document_title,
                all_api_keys=all_api_keys
            )
            
            if success:
                return True, result, 'cloud_direct'
            else:
                log(f"\n❌ Plan B also failed.")
        else:
            if not (provider and model and api_key):
                log("\n⚠️ Cloud AI fallback not available (no API configured)")
            elif not VISION_AI_AVAILABLE:
                log("\n⚠️ Cloud AI module not available")
        
        # STEP 3: Offer iLovePDF repair (Plan C)
        log("\n" + "="*50)
        log("🛠️ PLAN C: Manual PDF repair required")
        log("="*50)
        offer_pdf_repair(filepath, log)
        
        return False, str(local_error), 'failed'


# -------------------------
# Confidence Scoring & Cloud AI OCR
# -------------------------

def get_tesseract_confidence(image, language: str = "eng", config: str = "") -> tuple:
    """
    Get OCR result with confidence score from Tesseract
    
    Args:
        image: PIL Image object
        language: Tesseract language code
        config: Tesseract config string
        
    Returns:
        Tuple of (text, average_confidence)
    """
    if not OCR_SUPPORT:
        return "", 0
    
    try:
        # Get detailed data including confidence scores
        data = pytesseract.image_to_data(image, lang=language, config=config, output_type=pytesseract.Output.DICT)
        
        # Extract text and confidences
        confidences = []
        texts = []
        
        for i, conf in enumerate(data['conf']):
            # Tesseract returns -1 for non-text elements
            if conf != -1 and data['text'][i].strip():
                confidences.append(float(conf))
                texts.append(data['text'][i])
        
        # Calculate average confidence
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        
        # Also get the full text for comparison
        full_text = pytesseract.image_to_string(image, lang=language, config=config).strip()
        
        # Apply encoding artifact fixes
        full_text = fix_ocr_encoding_artifacts(full_text)
        
        return full_text, avg_confidence
        
    except Exception as e:
        print(f"Warning: Could not get confidence scores: {e}")
        # Fall back to regular OCR without confidence
        try:
            text = pytesseract.image_to_string(image, lang=language, config=config).strip()
            return text, 50  # Return middle confidence as unknown
        except:
            return "", 0


def ocr_with_cloud_ai(image_path: str, provider: str, model: str, api_key: str,
                       document_title: str = None, progress_callback=None,
                       text_type: str = "printed", custom_prompt: str = None) -> tuple:
    """
    Perform OCR using Cloud AI vision capabilities
    
    Args:
        image_path: Path to image file
        provider: AI provider name
        model: Model name
        api_key: API key
        document_title: Optional title for logging
        progress_callback: Optional callback for progress updates
        text_type: "printed" or "handwriting" - affects prompt selection
        custom_prompt: Optional custom prompt (overrides text_type prompt)
        
    Returns:
        Tuple of (success, text_or_error)
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)
    
    if not VISION_AI_AVAILABLE:
        return False, "Vision AI module not available"
    
    # Check if provider supports vision
    if not check_provider_supports_vision(provider, model):
        return False, (
            f"Your current AI provider ({provider}) with model '{model}' "
            f"doesn't support image analysis.\n\n"
            f"To use Cloud AI for OCR, please switch to one of these providers:\n"
            f"• OpenAI (ChatGPT) - GPT-4o, GPT-4o-mini, GPT-4-turbo\n"
            f"• Anthropic (Claude) - Any Claude model (3+)\n"
            f"• Google (Gemini) - Any Gemini model\n"
            f"• xAI (Grok) - Grok Vision models"
        )
    
    log(f"🤖 Sending image to {provider} for transcription...")
    
    success, result = call_vision_ai(
        provider=provider,
        model=model,
        image_path=image_path,
        api_key=api_key,
        prompt=custom_prompt,  # Pass custom prompt if provided
        document_title=document_title,
        progress_callback=progress_callback,
        text_type=text_type
    )
    
    if success:
        log(f"✅ Cloud AI transcription complete")
    else:
        log(f"❌ Cloud AI error: {result}")
    
    return success, result


def extract_text_from_image_with_options(
    image_path: str,
    ocr_mode: str,
    language: str = "eng",
    quality: str = "balanced",
    provider: str = None,
    model: str = None,
    api_key: str = None,
    document_title: str = None,
    progress_callback=None,
    escalation_callback=None
) -> tuple:
    """
    Extract text from a single image with OCR mode options
    
    Args:
        image_path: Path to image file
        ocr_mode: "local_first" or "cloud_direct"
        language: OCR language
        quality: OCR quality preset
        provider: AI provider (for cloud mode)
        model: AI model (for cloud mode)
        api_key: API key (for cloud mode)
        document_title: Document title for logging
        progress_callback: Callback for progress messages
        escalation_callback: Callback to ask user about escalation (returns True/False)
        
    Returns:
        Tuple of (success, text, method_used)
        method_used is "tesseract" or "cloud_ai"
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)
    
    # Cloud direct mode - skip Tesseract entirely
    if ocr_mode == "cloud_direct":
        if not provider or not api_key:
            return False, "Cloud AI requires a configured AI provider with API key", None
        
        success, result = ocr_with_cloud_ai(
            image_path, provider, model, api_key, document_title, progress_callback
        )
        return success, result, "cloud_ai" if success else None
    
    # Local first mode - try Tesseract, offer escalation if poor
    if not OCR_SUPPORT:
        return False, "Tesseract OCR not available", None
    
    try:
        from PIL import Image
        image = Image.open(image_path)
        
        # Preprocess
        processed_image = preprocess_image_for_ocr(image, quality)
        
        # Get OCR preset config
        preset = OCR_PRESETS.get(quality, OCR_PRESETS["balanced"])
        custom_config = f'--psm {preset["psm"]} --oem 3'
        
        # Get result with confidence
        log("📄 Running local OCR (Tesseract)...")
        text, confidence = get_tesseract_confidence(processed_image, language, custom_config)
        
        log(f"📊 OCR confidence: {confidence:.1f}%")
        
        # Check if confidence is acceptable (threshold: 60%)
        if confidence >= 60:
            log(f"✅ Good confidence - using local result")
            return True, text, "tesseract"
        
        # Low confidence - offer escalation if callback provided and cloud is available
        if confidence < 60 and escalation_callback and provider and api_key:
            log(f"⚠️ Low confidence ({confidence:.1f}%) - local OCR may be unreliable")
            
            # Check if provider supports vision before asking
            if VISION_AI_AVAILABLE and check_provider_supports_vision(provider, model):
                # Ask user if they want to try Cloud AI
                should_escalate = escalation_callback(
                    confidence,
                    provider,
                    model
                )
                
                if should_escalate:
                    success, cloud_result = ocr_with_cloud_ai(
                        image_path, provider, model, api_key, document_title, progress_callback
                    )
                    if success:
                        return True, cloud_result, "cloud_ai"
                    else:
                        log(f"⚠️ Cloud AI failed, using local result: {cloud_result}")
                        return True, text, "tesseract"
            else:
                log(f"ℹ️ Current provider doesn't support vision - using local result")
        
        # Return local result (either no escalation callback, or user declined)
        return True, text, "tesseract"
        
    except Exception as e:
        return False, f"OCR error: {str(e)}", None


# -------------------------
# OCR Processing Functions
# -------------------------

def preprocess_image_for_ocr(image: Image.Image, quality_preset: str) -> Image.Image:
    """Preprocess image for better OCR results"""
    preset = OCR_PRESETS.get(quality_preset, OCR_PRESETS["balanced"])

    # Convert to grayscale
    if image.mode != 'L':
        image = image.convert('L')

    # Enhance image if needed
    if preset["enhance"]:
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(1.3)

    # Denoise if needed
    if preset["denoise"]:
        image = image.filter(ImageFilter.MedianFilter(size=3))

    return image


def extract_text_from_pdf_with_ocr(filepath: str, language: str = "eng",
                                   quality: str = "balanced",
                                   progress_callback=None,
                                   resume_from_page: int = 0,
                                   force_reprocess: bool = False) -> List[Dict]:
    """Extract text from PDF using OCR with pre-screening for corruption"""

    def log(msg):  # ⭐ FIXED: Removed extra space before 'def'
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

    log(f"Starting OCR with {OCR_PRESETS[quality]['label']} quality, language: {OCR_LANGUAGES.get(language, language)}")

    # PRE-SCREEN: Test PDF BEFORE attempting full conversion
    # This prevents infinite loops by catching corrupt PDFs early
    if not pre_screen_pdf_for_ocr(filepath, log):
        raise RuntimeError(
            "PDF failed pre-screening check and will cause infinite loop. Please repair the PDF and try again.")

    preset = OCR_PRESETS[quality]
    
    # Build Tesseract config - include tessdata-dir for bundled version
    tessdata_dir = get_tessdata_dir()
    if tessdata_dir:
        # For Tesseract 5.x, TESSDATA_PREFIX should point directly to the tessdata folder
        # (the folder containing eng.traineddata, not its parent)
        os.environ['TESSDATA_PREFIX'] = tessdata_dir
        log(f"Set TESSDATA_PREFIX to: {tessdata_dir}")
    
    custom_config = f'--psm {preset["psm"]} --oem 3'

    # Convert PDF to images (should be safe now after pre-screening)
    log("Converting PDF pages to images...")

    # Raise Pillow's decompression bomb limit for large scanned pages
    # This is safe because the user deliberately loaded this file
    old_max_pixels = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = 500_000_000  # ~500MP (raised from 178MP default)

    try:
        images = convert_from_path(filepath, dpi=300)
        log(f"✅ Successfully converted {len(images)} pages to images")

    except Exception as e:
        # If decompression bomb error, retry at lower DPI
        if 'decompression bomb' in str(e).lower() or 'exceeds limit' in str(e).lower():
            log(f"⚠️ Page images too large at 300 DPI, retrying at 150 DPI...")
            try:
                images = convert_from_path(filepath, dpi=150)
                log(f"✅ Successfully converted {len(images)} pages at reduced DPI")
            except Exception as retry_err:
                Image.MAX_IMAGE_PIXELS = old_max_pixels
                log(f"❌ Conversion failed even at reduced DPI: {str(retry_err)}")
                offer_pdf_repair(filepath, log)
                raise RuntimeError(f"PDF pages too large for OCR: {str(retry_err)}")
        else:
            Image.MAX_IMAGE_PIXELS = old_max_pixels
            log(f"❌ Conversion failed: {str(e)}")
            offer_pdf_repair(filepath, log)
            raise RuntimeError(f"PDF conversion failed: {str(e)}\n\nPlease repair the PDF and try again.")

    Image.MAX_IMAGE_PIXELS = old_max_pixels  # Restore limit after conversion

    total_pages = len(images)
    log(f"Processing {total_pages} pages with OCR...")

    entries = []
    start_page = resume_from_page

    for page_num, image in enumerate(images[start_page:], start=start_page):
        try:
            log(f"📄 Processing page {page_num + 1}/{total_pages}...")

            # Preprocess and extract text
            processed_image = preprocess_image_for_ocr(image, quality)
            text = pytesseract.image_to_string(processed_image, lang=language, config=custom_config)
            text = text.strip()
            
            # Apply encoding artifact fixes
            text = fix_ocr_encoding_artifacts(text)

            if text:
                # Split into paragraphs
                paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
                for para in paragraphs:
                    entries.append({
                        'start': page_num + 1,
                        'text': para,
                        'location': f'Page {page_num + 1}'
                    })

            # Save progress periodically
            if (page_num + 1) % 10 == 0:
                save_ocr_cache(filepath, quality, language, entries)
                log(f"💾 Progress saved at page {page_num + 1}")

        except Exception as e:
            log(f"⚠️ Error on page {page_num + 1}: {e}")
            continue

    if not entries:
        raise RuntimeError("No text could be extracted from PDF using OCR")

    # Save final results
    save_ocr_cache(filepath, quality, language, entries)
    log(f"✅ OCR complete! Extracted {len(entries)} text segments from {total_pages} pages")

    return entries


def is_pdf_scanned(filepath: str) -> bool:
    """
    Check if PDF is scanned with improved detection including IMAGE ANALYSIS.

    ⭐ ULTIMATE VERSION - Detects scanned PDFs even with perfect OCR text layers ⭐

    Many modern scanners embed high-quality OCR text layers that pass all text quality
    checks. This version adds IMAGE DETECTION to catch these cases - if a PDF has
    large images covering the pages, it's scanned even if text extraction is perfect.

    Returns:
        True if OCR is needed (scanned document)
        False if PDF has good native text

    Enhanced features:
    - ⭐ NEW: Image detection and size analysis
    - ⭐ NEW: Full-page image detection (catches scanner-embedded OCR layers)
    - Threshold: 500 characters per page
    - Spacing analysis for OCR artifacts
    - Word count validation
    - Character diversity check
    - Single character ratio check
    """
    if not PDF_SUPPORT:
        return False

    try:
        with open(filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            pages_to_check = min(3, len(reader.pages))
            total_text = ""
            page_texts = []
            pages_with_large_images = 0

            for i in range(pages_to_check):
                page = reader.pages[i]
                text = page.extract_text()
                page_texts.append(text)
                total_text += text

                # ═══════════════════════════════════════════════════════
                # ⭐ NEW CHECK: Detect Large Images (Scanned Pages)
                # ═══════════════════════════════════════════════════════
                # This catches scanned PDFs with embedded OCR text layers
                try:
                    if '/XObject' in page['/Resources']:
                        xObject = page['/Resources']['/XObject'].get_object()

                        for obj in xObject:
                            if xObject[obj]['/Subtype'] == '/Image':
                                # Get image dimensions
                                try:
                                    width = int(xObject[obj]['/Width'])
                                    height = int(xObject[obj]['/Height'])

                                    # Detect full-page or large images
                                    # Typical scanned page is 400-600px at standard resolution
                                    # Any image larger than 300x300 is likely a scanned page
                                    if width > 300 and height > 300:
                                        pages_with_large_images += 1
                                        break  # Found large image, no need to check more
                                except:
                                    pass
                except:
                    pass  # Some PDFs have unusual structures

            # ═══════════════════════════════════════════════════════════
            # ⭐ IMAGE-BASED DECISION (with text quality gate)
            # ═══════════════════════════════════════════════════════════
            # Large images PLUS poor text = scanned document
            # Large images PLUS good text = illustrated document (NOT scanned)
            # This prevents PDFs with embedded photos/artwork from being
            # misclassified as scanned when they have perfectly good text.
            avg_chars_per_page = len(total_text) / pages_to_check
            has_good_text = avg_chars_per_page >= 500

            if not has_good_text:
                # Text is sparse — large images confirm it's scanned
                if pages_with_large_images == pages_to_check:
                    return True
                if pages_with_large_images >= 2:
                    return True

            # ═══════════════════════════════════════════════════════════
            # CHECK 1: Character Count Threshold (already computed above)
            # ═══════════════════════════════════════════════════════════
            if not has_good_text:
                return True

            # ═══════════════════════════════════════════════════════════
            # CHECK 2: Text Spacing Quality
            # ═══════════════════════════════════════════════════════════
            for text in page_texts:
                if len(text) > 50:
                    space_ratio = text.count(' ') / len(text) if len(text) > 0 else 0

                    if space_ratio < 0.05:
                        return True

                    if space_ratio > 0.40:
                        return True

            # ═══════════════════════════════════════════════════════════
            # CHECK 3: Word Count Validation
            # ═══════════════════════════════════════════════════════════
            words = total_text.split()
            if len(words) < 150:
                return True

            # ═══════════════════════════════════════════════════════════
            # CHECK 4: Character Diversity
            # ═══════════════════════════════════════════════════════════
            alpha_chars = sum(1 for c in total_text if c.isalpha())
            if len(total_text) > 0:
                alpha_ratio = alpha_chars / len(total_text)
                if alpha_ratio < 0.40:
                    return True

            # ═══════════════════════════════════════════════════════════
            # CHECK 5: OCR Error Patterns
            # ═══════════════════════════════════════════════════════════
            single_chars = sum(1 for w in words if len(w) == 1)
            if len(words) > 0:
                single_char_ratio = single_chars / len(words)
                if single_char_ratio > 0.20:
                    return True

            # ═══════════════════════════════════════════════════════════
            # PASSED ALL CHECKS
            # ═══════════════════════════════════════════════════════════
            return False

    except Exception as e:
        print(f"Warning: Could not analyze PDF structure: {e}")
        return True


# -------------------------
# Cache Management
# -------------------------

def get_cache_info() -> Dict:
    """Get information about cache directories"""
    ocr_size = 0
    ocr_count = 0
    audio_size = 0
    audio_count = 0
    outputs_size = 0
    outputs_count = 0

    # OCR cache
    try:
        if os.path.exists(OCR_CACHE_DIR):
            for file in os.listdir(OCR_CACHE_DIR):
                filepath = os.path.join(OCR_CACHE_DIR, file)
                if os.path.isfile(filepath):
                    ocr_size += os.path.getsize(filepath)
                    ocr_count += 1
    except Exception:
        pass

    # Audio cache
    try:
        if os.path.exists(AUDIO_CACHE_DIR):
            for file in os.listdir(AUDIO_CACHE_DIR):
                filepath = os.path.join(AUDIO_CACHE_DIR, file)
                if os.path.isfile(filepath):
                    audio_size += os.path.getsize(filepath)
                    audio_count += 1
    except Exception:
        pass

    # Outputs cache
    try:
        if os.path.exists(DATA_DIR):
            for file in os.listdir(DATA_DIR):
                if file.startswith('output_') and file.endswith('.txt'):
                    filepath = os.path.join(DATA_DIR, file)
                    if os.path.isfile(filepath):
                        outputs_size += os.path.getsize(filepath)
                        outputs_count += 1
    except Exception:
        pass

    return {
        'ocr_size': ocr_size,
        'ocr_count': ocr_count,
        'audio_size': audio_size,
        'audio_count': audio_count,
        'outputs_size': outputs_size,
        'outputs_count': outputs_count,
        'total_size': ocr_size + audio_size + outputs_size,
        'total_count': ocr_count + audio_count + outputs_count
    }


def clear_cache(cache_type: str) -> tuple:
    """Clear cache files. Returns (success, message)"""
    cleared_count = 0
    cleared_size = 0

    try:
        # Clear OCR cache
        if cache_type in ['all', 'ocr'] and os.path.exists(OCR_CACHE_DIR):
            for file in os.listdir(OCR_CACHE_DIR):
                filepath = os.path.join(OCR_CACHE_DIR, file)
                if os.path.isfile(filepath):
                    size = os.path.getsize(filepath)
                    os.remove(filepath)
                    cleared_count += 1
                    cleared_size += size

        # Clear audio cache
        if cache_type in ['all', 'audio'] and os.path.exists(AUDIO_CACHE_DIR):
            for file in os.listdir(AUDIO_CACHE_DIR):
                filepath = os.path.join(AUDIO_CACHE_DIR, file)
                if os.path.isfile(filepath):
                    size = os.path.getsize(filepath)
                    os.remove(filepath)
                    cleared_count += 1
                    cleared_size += size

        # Clear processed outputs AND update document_library.json
        if cache_type in ['all', 'outputs']:
            # Delete output files
            for file in os.listdir(DATA_DIR):
                if file.startswith('output_') and file.endswith('.txt'):
                    filepath = os.path.join(DATA_DIR, file)
                    if os.path.isfile(filepath):
                        size = os.path.getsize(filepath)
                        os.remove(filepath)
                        cleared_count += 1
                        cleared_size += size

            # Clear output references from document_library.json
            library_path = os.path.join(DATA_DIR, 'document_library.json')
            if os.path.exists(library_path):
                try:
                    with open(library_path, 'r', encoding='utf-8') as f:
                        library = json.load(f)

                    # Clear processed_outputs array for all documents
                    for doc in library:
                        if 'processed_outputs' in doc:
                            doc['processed_outputs'] = []

                    # Save updated library
                    with open(library_path, 'w', encoding='utf-8') as f:
                        json.dump(library, f, indent=2, ensure_ascii=False)
                except Exception as e:
                    print(f"Warning: Could not update document_library.json: {e}")

        size_mb = cleared_size / (1024 * 1024)
        return True, f"Cleared {cleared_count} files ({size_mb:.2f} MB)"

    except Exception as e:
        return False, f"Error clearing cache: {str(e)}"


# -------------------------
# Multi-Image OCR Processing
# -------------------------

def process_multiple_images_ocr(
    image_files: List[str],
    ocr_mode: str = "local_first",
    language: str = "eng",
    quality: str = "balanced",
    confidence_threshold: int = 60,
    provider: str = None,
    model: str = None,
    api_key: str = None,
    progress_callback=None,
    cancel_check=None,
    text_type: str = "printed",
    context_hint: str = ""
) -> tuple:
    """
    Process multiple image files as pages of a single document.
    
    Args:
        image_files: List of image file paths in page order
        ocr_mode: "local_first" or "cloud_direct"
        language: OCR language code (e.g., "eng")
        quality: OCR quality preset
        confidence_threshold: Minimum confidence for local OCR before cloud fallback
        provider: AI provider for cloud OCR
        model: AI model for cloud OCR
        api_key: API key for cloud OCR
        progress_callback: Function(page_num, total_pages, message) for progress updates
        cancel_check: Function() that returns True if processing should be cancelled
        text_type: "printed" or "handwriting" - affects prompt selection
        context_hint: User-provided context for handwriting (e.g., "Letter from 1975, names: John, Mary")
        
    Returns:
        Tuple of (success, entries_or_error)
        If success: entries is list of dicts with 'start', 'text', 'location' keys
        If failure: entries_or_error is error message string
    """
    if not image_files:
        return False, "No image files provided"
    
    entries = []
    total_pages = len(image_files)
    errors = []  # Collect errors from failed pages
    
    for page_num, image_path in enumerate(image_files, start=1):
        # Check for cancellation
        if cancel_check and cancel_check():
            return False, "Processing cancelled"
        
        # Progress update
        if progress_callback:
            filename = os.path.basename(image_path)
            progress_callback(page_num, total_pages, f"Processing {filename}")
        
        # Process this image
        success, text, method, confidence = process_single_image_ocr(
            image_path=image_path,
            ocr_mode=ocr_mode,
            language=language,
            quality=quality,
            confidence_threshold=confidence_threshold,
            provider=provider,
            model=model,
            api_key=api_key,
            text_type=text_type,
            context_hint=context_hint
        )
        
        if success and text and text.strip():
            # Split into paragraphs
            paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
            
            if paragraphs:
                for para in paragraphs:
                    entries.append({
                        'start': page_num,
                        'text': para,
                        'location': f'Page {page_num}',
                        'confidence': confidence  # Include confidence score
                    })
            else:
                # No paragraph breaks, add as single entry
                entries.append({
                    'start': page_num,
                    'text': text.strip(),
                    'location': f'Page {page_num}',
                    'confidence': confidence  # Include confidence score
                })
        else:
            # Capture the error for this page
            error_msg = text if not success else "Empty result"
            errors.append(f"Page {page_num}: {error_msg}")
    
    if entries:
        return True, entries
    else:
        # No text extracted - return the actual errors
        if errors:
            # Show first few errors to help diagnose
            error_summary = "\n".join(errors[:3])
            if len(errors) > 3:
                error_summary += f"\n... and {len(errors) - 3} more page(s) failed"
            return False, f"No text could be extracted from any page.\n\nErrors:\n{error_summary}"
        else:
            return False, "No text could be extracted from any page"


def process_single_image_ocr(
    image_path: str,
    ocr_mode: str = "local_first",
    language: str = "eng",
    quality: str = "balanced",
    confidence_threshold: int = 60,
    provider: str = None,
    model: str = None,
    api_key: str = None,
    text_type: str = "printed",
    context_hint: str = ""
) -> tuple:
    """
    Process a single image with OCR.
    
    Args:
        image_path: Path to image file
        ocr_mode: "local_first" or "cloud_direct"
        language: OCR language code
        quality: OCR quality preset
        confidence_threshold: Minimum confidence before cloud fallback
        provider: AI provider for cloud OCR
        model: AI model for cloud OCR  
        api_key: API key for cloud OCR
        text_type: "printed" or "handwriting" - affects prompt selection
        context_hint: User-provided context for handwriting
        
    Returns:
        Tuple of (success, text, method_used, confidence)
        method_used is "tesseract" or "cloud_ai" or None
        confidence is float (0-100) or None
    """
    try:
        # Cloud direct mode - skip local OCR entirely
        if ocr_mode == "cloud_direct":
            if not api_key or api_key == "not-required":
                return False, f"No API key configured for {provider}", None, None
            
            # Import the function that builds the custom prompt with context
            from ai_handler import build_ocr_prompt_with_context
            custom_prompt = build_ocr_prompt_with_context(text_type, context_hint)
            
            success, result = ocr_with_cloud_ai(
                image_path=image_path,
                provider=provider,
                model=model,
                api_key=api_key,
                document_title=os.path.basename(image_path),
                progress_callback=None,
                text_type=text_type,
                custom_prompt=custom_prompt
            )
            
            if success:
                return True, result, "cloud_ai", 100.0
            else:
                return False, result, None, None
        
        # Local first mode - try Tesseract
        if not OCR_SUPPORT:
            return False, "Tesseract OCR not available", None, None
        
        from PIL import Image
        image = Image.open(image_path)
        
        # Get OCR preset config
        preset = OCR_PRESETS.get(quality, OCR_PRESETS["balanced"])
        custom_config = f'--psm {preset["psm"]} --oem 3'
        
        # Preprocess image
        processed_image = preprocess_image_for_ocr(image, quality)
        
        # Get OCR with confidence score
        text, confidence = get_tesseract_confidence(processed_image, language, custom_config)
        
        # Apply encoding artifact fixes
        text = fix_ocr_encoding_artifacts(text) if text else text
        
        # Return Tesseract result directly (no Cloud AI fallback for printed text)
        # User chose "printed" mode = Tesseract only, predictable/safe errors
        return True, text, "tesseract", confidence
        
    except Exception as e:
        return False, str(e), None, None


# -------------------------
# Smart OCR Router (Printed vs Handwriting)
# -------------------------

# Text type options for UI
OCR_TEXT_TYPES = {
    "printed": {
        "label": "Printed Text (Local OCR - use for clean, modern print)",
        "description": "Uses local Tesseract OCR (free, accurate for clear print)",
        "method": "tesseract"
    },
    "handwriting": {
        "label": "Handwriting or low-quality print (Online AI - uses your selected provider)",
        "description": "Uses AI vision (GPT-4o recommended) to interpret handwriting",
        "method": "vision_ai"
    }
}


def ocr_image_smart(
    image_path: str,
    text_type: str = "printed",
    language: str = "eng",
    quality: str = "balanced",
    # For printed text (Cloud Vision)
    cloud_vision_api_key: str = None,
    # For handwriting (Vision AI)
    vision_provider: str = None,
    vision_model: str = None,
    vision_api_key: str = None,
    # General
    document_title: str = None,
    progress_callback=None
) -> tuple:
    """
    Smart OCR router - chooses the best OCR method based on text type.
    
    Args:
        image_path: Path to image file
        text_type: "printed" or "handwriting"
        language: OCR language code (for fallback)
        quality: OCR quality preset (for fallback)
        cloud_vision_api_key: Google Cloud Vision API key (for printed text)
        vision_provider: AI provider name (for handwriting)
        vision_model: AI model name (for handwriting)
        vision_api_key: AI provider API key (for handwriting)
        document_title: Optional document title for logging
        progress_callback: Callback for progress messages
        
    Returns:
        Tuple of (success, text, method_used)
        method_used: "cloud_vision", "vision_ai", "tesseract", or None
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg)
    
    # ═══════════════════════════════════════════════════════════════
    # PRINTED TEXT → Tesseract (local, free, accurate for clear print)
    # ═══════════════════════════════════════════════════════════════
    if text_type == "printed":
        log("📖 Text type: Printed → Using local Tesseract OCR")
        return _fallback_to_tesseract(image_path, language, quality, log)
    
    # ═══════════════════════════════════════════════════════════════
    # HANDWRITING → Vision AI (interpretive)
    # ═══════════════════════════════════════════════════════════════
    elif text_type == "handwriting":
        # Check if Vision AI is configured
        if vision_provider and vision_api_key and vision_api_key.strip():
            if VISION_AI_AVAILABLE and check_provider_supports_vision(vision_provider, vision_model):
                log("✍️ Text type: Handwriting → Using AI Vision")
                
                success, result = ocr_with_cloud_ai(
                    image_path=image_path,
                    provider=vision_provider,
                    model=vision_model,
                    api_key=vision_api_key,
                    document_title=document_title,
                    progress_callback=progress_callback,
                    text_type="handwriting"
                )
                
                if success:
                    return True, result, "vision_ai"
                else:
                    log(f"⚠️ Vision AI failed: {result}")
                    log("Falling back to local Tesseract...")
            else:
                log(f"⚠️ {vision_provider} doesn't support vision or is unavailable")
                log("Falling back to local Tesseract...")
        else:
            log("⚠️ Vision AI not configured")
            log("💡 For handwriting, configure an AI provider (GPT-4o, Claude, Gemini) in Settings")
            log("Falling back to local Tesseract...")
        
        # Fallback to Tesseract
        return _fallback_to_tesseract(image_path, language, quality, log)
    
    else:
        log(f"⚠️ Unknown text type: {text_type}")
        return _fallback_to_tesseract(image_path, language, quality, log)


def _fallback_to_tesseract(image_path: str, language: str, quality: str, log_func) -> tuple:
    """
    Fallback to local Tesseract OCR.
    """
    if not OCR_SUPPORT:
        return False, "Tesseract OCR not available and no cloud service configured", None
    
    try:
        from PIL import Image
        log_func("📄 Running local OCR (Tesseract)...")
        
        image = Image.open(image_path)
        processed_image = preprocess_image_for_ocr(image, quality)
        
        preset = OCR_PRESETS.get(quality, OCR_PRESETS["balanced"])
        custom_config = f'--psm {preset["psm"]} --oem 3'
        
        text = pytesseract.image_to_string(processed_image, lang=language, config=custom_config)
        text = text.strip()
        
        if text:
            # Apply encoding artifact fixes
            text = fix_ocr_encoding_artifacts(text)
            log_func(f"✅ Tesseract extracted {len(text)} characters")
            return True, text, "tesseract"
        else:
            return False, "No text extracted by Tesseract", None
            
    except Exception as e:
        return False, f"Tesseract error: {str(e)}", None


def check_cloud_vision_configured(config: dict) -> tuple:
    """
    Check if Google Cloud Vision is configured.
    
    Returns:
        Tuple of (is_configured, message)
    """
    api_key = config.get("keys", {}).get("Google Cloud Vision", "")
    
    if api_key and api_key.strip():
        return True, "Google Cloud Vision is configured"
    else:
        return False, (
            "Google Cloud Vision API key not configured.\n\n"
            "To use accurate OCR for printed text:\n"
            "1. Go to https://console.cloud.google.com/\n"
            "2. Enable the Cloud Vision API\n"
            "3. Create an API key\n"
            "4. Add it in Settings → API Keys → Google Cloud Vision"
        )