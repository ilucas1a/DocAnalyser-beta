"""
document_fetcher.py - Document Fetching & Processing
Handles fetching documents from local files and web URLs
"""

import os
import re
import tempfile
from typing import List, Dict, Optional, Tuple

# Import from our modules
from config import *
from utils import format_timestamp
from ocr_handler import is_pdf_scanned

# Document processing library
try:
    from docx import Document

    DOCX_SUPPORT = True
except Exception:
    DOCX_SUPPORT = False

# RTF support
try:
    from striprtf.striprtf import rtf_to_text

    RTF_SUPPORT = True
except Exception:
    RTF_SUPPORT = False

# Legacy .doc file support (Windows only, requires Microsoft Word)
DOC_SUPPORT = False
try:
    import sys
    if sys.platform == 'win32':
        import win32com.client
        DOC_SUPPORT = True
except Exception:
    DOC_SUPPORT = False

# PDF support - multiple libraries for robustness
try:
    import PyPDF2

    PDF_SUPPORT_PYPDF2 = True
except Exception:
    PDF_SUPPORT_PYPDF2 = False

try:
    import fitz  # PyMuPDF

    PDF_SUPPORT_PYMUPDF = True
except Exception:
    PDF_SUPPORT_PYMUPDF = False

PDF_SUPPORT = PDF_SUPPORT_PYPDF2 or PDF_SUPPORT_PYMUPDF

# Web scraping
try:
    import requests
    from bs4 import BeautifulSoup

    BS4_SUPPORT = True
    WEB_SUPPORT = True
except Exception:
    BS4_SUPPORT = False
    WEB_SUPPORT = False

# Spreadsheet support
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False


# -------------------------
# Text Encoding Utilities
# -------------------------

def clean_text_encoding(text: str) -> str:
    """
    Fix common character encoding issues from RTF and other formats.
    Handles Windows-1252 to UTF-8 conversion problems.
    """
    # Common encoding replacements (Windows-1252 misinterpreted as UTF-8)
    # Format: 'garbled_text': 'correct_text'
    replacements = {
        # Em and en dashes
        'â€"': '—',
        'â€"': '–',
        '\u2013': '–',  # en dash
        '\u2014': '—',  # em dash

        # Smart quotes
        'â€˜': ''',
        'â€™': ''',
        'â€œ': '"',
        'â€': '"',
        '\u2018': "'",  # left single quote
        '\u2019': "'",  # right single quote
        '\u201C': '"',  # left double quote
        '\u201D': '"',  # right double quote

        # Other punctuation
        'â€¦': '…',
        'â€¢': '•',
        '\u2026': '...',  # ellipsis
        '\u2022': '*',  # bullet

        # Accented characters
        'Ã©': 'é',
        'Ã¨': 'è',
        'Ã ': 'à',
        'Ã¡': 'á',
        'Ã­': 'í',
        'Ã³': 'ó',
        'Ãº': 'ú',
        'Ã±': 'ñ',
        'Ã¼': 'ü',
        'Ã¶': 'ö',
        'Ã¤': 'ä',
        'Ã§': 'ç',
        'Ã': 'Á',
        'Ã‰': 'É',
        'Ã': 'Í',
        'Ã"': 'Ó',
        'Ãš': 'Ú',

        # Currency and symbols
        'â‚¬': '€',
        'Â£': '£',
        'Â¥': '¥',
        'Â°': '°',
        'Â©': '©',
        'Â®': '®',
        'â„¢': '™',

        # Fractions
        'Â½': '1/2',
        'Â¼': '1/4',
        'Â¾': '3/4',
        'â…"': '1/3',
        'â…"': '2/3',

        # Non-breaking space
        'Â ': ' ',
        '\u00A0': ' ',

        # Common double-encodings (mojibake)
        'Ã‚Â': '',  # Common artifact
        'â€‹': '',  # Zero-width space
    }

    # Apply replacements
    for wrong, right in replacements.items():
        text = text.replace(wrong, right)

    # Remove any remaining control characters except newlines and tabs
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', '', text)

    # Normalize multiple spaces
    text = re.sub(r' {2,}', ' ', text)

    # Fix common spacing issues around punctuation
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)  # Remove space before punctuation
    text = re.sub(r'([.,;:!?])([A-Za-z])', r'\1 \2', text)  # Add space after punctuation

    return text.strip()


# -------------------------
# Google Sheets Support
# -------------------------

def is_google_sheets_url(url: str) -> bool:
    """
    Check if URL is a Google Sheets URL.
    
    Args:
        url: URL string to check
        
    Returns:
        True if URL is a Google Sheets URL, False otherwise
    """
    return "docs.google.com/spreadsheets" in url.lower()


def extract_google_sheets_id(url: str) -> Optional[str]:
    """
    Extract the Google Sheets ID from a URL.
    
    Args:
        url: Google Sheets URL
        
    Returns:
        Sheet ID if found, None otherwise
        
    Examples:
        https://docs.google.com/spreadsheets/d/1ABC123.../edit
        https://docs.google.com/spreadsheets/d/1ABC123.../edit#gid=0
        https://docs.google.com/spreadsheets/d/1ABC123.../edit?usp=sharing
    """
    import re
    
    # Pattern to extract sheet ID from various Google Sheets URL formats
    pattern = r'/spreadsheets/d/([a-zA-Z0-9-_]+)'
    match = re.search(pattern, url)
    
    if match:
        return match.group(1)
    return None


def download_google_sheet(url: str, sheet_id: str) -> Tuple[bool, str, str]:
    """
    Download a Google Sheet as an Excel file.
    
    Args:
        url: Original Google Sheets URL
        sheet_id: Extracted sheet ID
        
    Returns:
        Tuple of (success: bool, file_path_or_error: str, title: str)
    """
    try:
        # Convert Google Sheets URL to export URL
        export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
        
        # Download the file
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        
        response = requests.get(export_url, timeout=30, headers=headers)
        response.raise_for_status()
        
        # Create a temporary file
        temp_file = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        temp_file.write(response.content)
        temp_file.close()
        
        # Try to get a better title from the original URL or use sheet ID
        title = f"Google Sheet {sheet_id[:8]}"
        
        return True, temp_file.name, title
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            return False, "Google Sheet access denied. Make sure the sheet is shared with 'Anyone with the link can view'.", url
        elif e.response.status_code == 404:
            return False, "Google Sheet not found. Check that the URL is correct and the sheet exists.", url
        else:
            return False, f"HTTP error downloading Google Sheet: {str(e)}", url
    except Exception as e:
        return False, f"Error downloading Google Sheet: {str(e)}", url


def fetch_google_sheet(url: str) -> Tuple[bool, any, str, str]:
    """
    Fetch and process a Google Sheets document.
    
    Args:
        url: Google Sheets URL
        
    Returns:
        (success: bool, result: list/str, title: str, doc_type: str)
    """
    if not PANDAS_AVAILABLE:
        return False, "pandas library not available. Install with: pip install pandas openpyxl", url, "google_sheets"
    
    if not OPENPYXL_AVAILABLE:
        return False, "openpyxl library not available. Install with: pip install openpyxl", url, "google_sheets"
    
    # Extract sheet ID
    sheet_id = extract_google_sheets_id(url)
    if not sheet_id:
        return False, "Could not extract Google Sheets ID from URL", url, "google_sheets"
    
    # Download the sheet
    success, result, title = download_google_sheet(url, sheet_id)
    if not success:
        return False, result, title, "google_sheets"
    
    temp_file_path = result
    
    try:
        # Read the spreadsheet using pandas
        df = pd.read_excel(temp_file_path, sheet_name=0)  # Read first sheet
        
        if df.empty:
            return False, "Google Sheet appears to be empty", title, "google_sheets"
        
        # Convert to text format for AI analysis
        # Create a structured text representation
        text_parts = []
        
        # Add header
        text_parts.append(f"GOOGLE SHEET DATA: {title}")
        text_parts.append(f"Dimensions: {len(df)} rows × {len(df.columns)} columns")
        text_parts.append(f"Columns: {', '.join(df.columns)}")
        text_parts.append("\n" + "="*80 + "\n")
        
        # Add the data in CSV format (easier for AI to parse)
        csv_text = df.to_csv(index=False)
        text_parts.append(csv_text)
        
        # Add summary statistics for numeric columns
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        if numeric_cols:
            text_parts.append("\n" + "="*80)
            text_parts.append("NUMERIC COLUMN SUMMARIES:")
            text_parts.append("="*80 + "\n")
            for col in numeric_cols:
                stats = df[col].describe()
                text_parts.append(f"\n{col}:")
                text_parts.append(f"  Count: {stats['count']:.0f}")
                text_parts.append(f"  Mean: {stats['mean']:.2f}")
                text_parts.append(f"  Std: {stats['std']:.2f}")
                text_parts.append(f"  Min: {stats['min']:.2f}")
                text_parts.append(f"  25%: {stats['25%']:.2f}")
                text_parts.append(f"  50% (Median): {stats['50%']:.2f}")
                text_parts.append(f"  75%: {stats['75%']:.2f}")
                text_parts.append(f"  Max: {stats['max']:.2f}")
        
        full_text = "\n".join(text_parts)
        
        # Return as entries format (no timestamps for spreadsheets)
        entries = [{'text': full_text}]
        
        return True, entries, title, "google_sheets"
        
    except Exception as e:
        return False, f"Error processing Google Sheet: {str(e)}", title, "google_sheets"
    finally:
        # Clean up temporary file
        try:
            os.remove(temp_file_path)
        except:
            pass


# -------------------------
# Entry Formatting
# -------------------------

"""
FIXED entries_to_text function for document_fetcher.py

Replace lines 160-178 in document_fetcher.py with this corrected version.

The bug was: if start > 1000: lines.append(f"[Page {start}] {text}")
This assumed values > 1000 were page numbers, but they're seconds for video transcripts!

The fix: Check if entry has a 'location' field to determine if it's a page or timestamp.
"""


def legacy_entries_to_text(entries: List[Dict], include_timestamps: bool = True) -> str:
    """Convert entries to formatted text with optional timestamps"""
    lines = []
    for entry in entries:
        text = entry.get('text', '').strip()
        if not text:
            continue

        if include_timestamps and 'start' in entry:
            start = entry['start']
            if isinstance(start, (int, float)):
                # Check if entry has a pre-formatted location field (for PDFs)
                if 'location' in entry and entry['location'].startswith('Page'):
                    # This is a PDF page number - use the location field as-is
                    lines.append(f"[{entry['location']}] {text}")
                else:
                    # This is a timestamp (video/audio) - format it properly
                    lines.append(f"[{format_timestamp(start)}] {text}")
            else:
                lines.append(text)
        else:
            lines.append(text)

    return '\n\n'.join(lines)

# -------------------------
# Local File Fetching
# -------------------------

def fetch_local_file(filepath: str) -> Tuple[bool, any, str, str]:
    """
    Fetch content from a local file.

    Supports: .txt, .rtf, .doc, .docx, .pdf, audio files

    Returns: (success: bool, result: list/str, title: str, doc_type: str)
    """
    try:
        ext = os.path.splitext(filepath)[1].lower()
        title = os.path.basename(filepath)

        if ext == '.txt':
            # Try multiple encodings
            text = None
            encodings_to_try = ['utf-8', 'cp1252', 'latin-1', 'iso-8859-1']

            for encoding in encodings_to_try:
                try:
                    with open(filepath, 'r', encoding=encoding, errors='ignore') as f:
                        text = f.read().strip()

                    if text:
                        # Clean up any encoding issues
                        text = clean_text_encoding(text)
                        break
                except Exception:
                    continue

            if not text:
                return False, "Could not read text file with any supported encoding", title, "file"

            # Auto-detect TurboScribe transcript format:
            #   [00:00:05] Speaker 1: Hello everyone...
            #   [00:01:23] Speaker 2: Thanks for having me...
            import re as _re
            ts_pattern = _re.compile(
                r'\[(\d{1,2}:\d{2}:\d{2}|\d{1,2}:\d{2})\]\s*[^:]+:\s*.+'
            )
            # Check first 20 non-blank lines — if most match, it's a transcript
            non_blank = [ln for ln in text.split('\n') if ln.strip()][:20]
            ts_matches = sum(1 for ln in non_blank if ts_pattern.match(ln.strip()))
            
            if len(non_blank) >= 3 and ts_matches / len(non_blank) > 0.5:
                # It's a TurboScribe (or similar) speaker transcript
                try:
                    from turboscribe_helper import parse_turboscribe_txt
                    entries = parse_turboscribe_txt(filepath)
                    if entries and len(entries) >= 2:
                        # Use audio title without extension for a cleaner library name
                        clean_title = os.path.splitext(title)[0]
                        return True, entries, f"🎤 {clean_title}", "turboscribe_import"
                except Exception as e:
                    logging.warning(f"TurboScribe auto-parse failed, loading as plain text: {e}")
            
            entries = [{'text': text}]  # ✅ No 'start' field for text files
            return True, entries, title, "file"

        elif ext in ['.html', '.htm']:
            # HTML files - extract text from HTML
            if not BS4_SUPPORT:
                return False, "BeautifulSoup not installed. Install with: pip install beautifulsoup4", title, "file"
            
            try:
                # Try multiple encodings
                html_content = None
                encodings_to_try = ['utf-8', 'cp1252', 'latin-1', 'iso-8859-1']
                
                for encoding in encodings_to_try:
                    try:
                        with open(filepath, 'r', encoding=encoding, errors='ignore') as f:
                            html_content = f.read()
                        if html_content:
                            break
                    except Exception:
                        continue
                
                if not html_content:
                    return False, "Could not read HTML file with any supported encoding", title, "file"
                
                # Parse HTML with BeautifulSoup
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                
                # Get text
                text = soup.get_text()
                
                # Clean up whitespace
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text = '\n'.join(chunk for chunk in chunks if chunk)
                
                # Clean up any encoding issues
                text = clean_text_encoding(text)
                text = text.strip()
                
                if not text or len(text) < 10:
                    return False, "HTML file appears empty after parsing", title, "file"
                
                entries = [{'text': text}]
                return True, entries, title, "file"
                
            except Exception as e:
                return False, f"Error parsing HTML file: {str(e)}", title, "file"
        
        elif ext == '.rtf':
            if not RTF_SUPPORT:
                return False, "striprtf not installed. Install with: pip install striprtf", title, "file"

            try:
                # Try multiple encodings for RTF files
                text = None
                encodings_to_try = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']

                for encoding in encodings_to_try:
                    try:
                        with open(filepath, 'r', encoding=encoding, errors='ignore') as f:
                            rtf_content = f.read()

                        # Use striprtf to extract text
                        text = rtf_to_text(rtf_content)

                        # Clean up encoding issues
                        text = clean_text_encoding(text)
                        text = text.strip()

                        if text and len(text) > 10:
                            break
                    except Exception:
                        continue

                if not text or len(text) < 10:
                    return False, "RTF file appears empty after parsing.", title, "file"

                entries = [{'text': text}]  # ✅ No 'start' field for RTF files
                return True, entries, title, "file"

            except Exception as e:
                return False, f"Error parsing RTF file: {str(e)}", title, "file"

        elif ext == '.docx':
            if not DOCX_SUPPORT:
                return False, "python-docx not installed. Install with: pip install python-docx", title, "file"

            doc = Document(filepath)
            text = '\n\n'.join([p.text for p in doc.paragraphs if p.text.strip()])

            # Clean up any encoding issues
            text = clean_text_encoding(text)

            entries = [{'text': text}]  # ✅ No 'start' field for DOCX files
            return True, entries, title, "file"

        elif ext == '.doc':
            # Legacy .doc format - requires pywin32 and Microsoft Word on Windows
            if not DOC_SUPPORT:
                return False, (
                    "Legacy .doc files require Microsoft Word to be installed.\n\n"
                    "Alternatives:\n"
                    "• Save the file as .docx in Microsoft Word\n"
                    "• Use LibreOffice to convert to .docx\n"
                    "• Use an online converter"
                ), title, "file"

            try:
                import pythoncom
                pythoncom.CoInitialize()  # Initialize COM for this thread
                
                word = win32com.client.Dispatch("Word.Application")
                word.Visible = False
                
                # Open the document
                doc = word.Documents.Open(os.path.abspath(filepath))
                
                # Extract text from all paragraphs
                text = doc.Content.Text
                
                # Close document without saving
                doc.Close(False)
                word.Quit()
                
                # Clean up COM
                pythoncom.CoUninitialize()
                
                # Clean up any encoding issues
                text = clean_text_encoding(text)
                text = text.strip()
                
                if not text:
                    return False, "Could not extract text from .doc file", title, "file"
                
                entries = [{'text': text}]  # ✅ No 'start' field for DOC files
                return True, entries, title, "file"
                
            except Exception as e:
                return False, f"Error reading .doc file: {str(e)}\n\nTry saving the file as .docx instead.", title, "file"

        elif ext == '.pdf':
            if not PDF_SUPPORT:
                return False, "No PDF libraries installed. Install with: pip install PyPDF2 PyMuPDF", title, "file"

            # Check if scanned first
            if is_pdf_scanned(filepath):
                return False, "SCANNED_PDF", title, "file"

            entries = []
            extraction_method = "none"

            # Try PyMuPDF first (most robust)
            if PDF_SUPPORT_PYMUPDF:
                try:
                    import fitz
                    doc = fitz.open(filepath)

                    for page_num in range(len(doc)):
                        try:
                            page = doc[page_num]
                            text = page.get_text()

                            if text and text.strip():
                                entries.append(
                                    {'start': page_num + 1, 'text': text.strip(), 'location': f'Page {page_num + 1}'})
                        except Exception as e:
                            print(f"Warning: Could not extract text from page {page_num + 1}: {e}")
                            continue

                    doc.close()

                    # If we got good results, return them
                    if entries and sum(len(e['text']) for e in entries) > 100:
                        extraction_method = "PyMuPDF"
                        return True, entries, title, "file"

                except Exception as e:
                    print(f"PyMuPDF extraction failed: {e}, trying PyPDF2...")

            # Fallback to PyPDF2 if PyMuPDF failed or not available
            if PDF_SUPPORT_PYPDF2 and not entries:
                try:
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")

                        with open(filepath, 'rb') as f:
                            reader = PyPDF2.PdfReader(f)

                            for page_num, page in enumerate(reader.pages, start=1):
                                try:
                                    text = page.extract_text()
                                    if text and text.strip():
                                        entries.append(
                                            {'start': page_num, 'text': text.strip(), 'location': f'Page {page_num}'})
                                except Exception as e:
                                    print(f"Warning: Could not extract text from page {page_num}: {e}")
                                    continue

                    if entries and sum(len(e['text']) for e in entries) > 100:
                        extraction_method = "PyPDF2"

                except Exception as e:
                    print(f"PyPDF2 extraction failed: {e}")

            # Check quality of extraction
            if entries:
                total_chars = sum(len(e['text']) for e in entries)

                # Check for garbled text (common in old PDFs with encoding issues)
                sample_text = ' '.join([e['text'] for e in entries[:3]])  # First 3 entries
                garbled_chars = sum(1 for c in sample_text if ord(c) > 127 and not c.isalpha())
                garbled_ratio = garbled_chars / len(sample_text) if sample_text else 0

                # If mostly garbled or very little text, suggest OCR
                if garbled_ratio > 0.3 or total_chars < 100:
                    return False, "SCANNED_PDF", title, "file"

                print(f"Successfully extracted {total_chars} characters using {extraction_method}")
                return True, entries, title, "file"

            # No text extracted at all - definitely needs OCR
            return False, "SCANNED_PDF", title, "file"

        elif ext in ['.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif']:
            # Image files - return code for OCR processing
            return False, "IMAGE_FILE", title, "image"
        
        elif ext in ['.xlsx', '.xls', '.csv']:
            # Spreadsheet files
            if not PANDAS_AVAILABLE:
                return False, "pandas library not available. Install with: pip install pandas openpyxl", title, "file"
            
            if ext == '.xlsx' and not OPENPYXL_AVAILABLE:
                return False, "openpyxl library not available for .xlsx files. Install with: pip install openpyxl", title, "file"
            
            try:
                # Read the spreadsheet
                if ext == '.csv':
                    df = pd.read_csv(filepath)
                else:
                    df = pd.read_excel(filepath, sheet_name=0)  # Read first sheet
                
                if df.empty:
                    return False, "Spreadsheet appears to be empty", title, "file"
                
                # Convert to text format for AI analysis
                text_parts = []
                
                # Add header
                text_parts.append(f"SPREADSHEET DATA: {title}")
                text_parts.append(f"Dimensions: {len(df)} rows × {len(df.columns)} columns")
                text_parts.append(f"Columns: {', '.join(df.columns)}")
                text_parts.append("\n" + "="*80 + "\n")
                
                # Add the data in CSV format
                csv_text = df.to_csv(index=False)
                text_parts.append(csv_text)
                
                # Add summary statistics for numeric columns
                numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
                if numeric_cols:
                    text_parts.append("\n" + "="*80)
                    text_parts.append("NUMERIC COLUMN SUMMARIES:")
                    text_parts.append("="*80 + "\n")
                    for col in numeric_cols:
                        stats = df[col].describe()
                        text_parts.append(f"\n{col}:")
                        text_parts.append(f"  Count: {stats['count']:.0f}")
                        text_parts.append(f"  Mean: {stats['mean']:.2f}")
                        text_parts.append(f"  Std: {stats['std']:.2f}")
                        text_parts.append(f"  Min: {stats['min']:.2f}")
                        text_parts.append(f"  25%: {stats['25%']:.2f}")
                        text_parts.append(f"  50% (Median): {stats['50%']:.2f}")
                        text_parts.append(f"  75%: {stats['75%']:.2f}")
                        text_parts.append(f"  Max: {stats['max']:.2f}")
                
                full_text = "\n".join(text_parts)
                entries = [{'text': full_text}]
                
                return True, entries, title, "spreadsheet"
                
            except Exception as e:
                return False, f"Error reading spreadsheet: {str(e)}", title, "file"
        
        elif ext in SUPPORTED_AUDIO_FORMATS:
            return False, "AUDIO_FILE", title, "audio"
        else:
            return False, f"Unsupported file type: {ext}", title, "file"
    except Exception as e:
        return False, f"Error reading file: {str(e)}", title, "file"


# -------------------------
# Web URL Fetching
# -------------------------

def fetch_web_url(url: str) -> Tuple[bool, any, str, str, dict]:
    """
    Fetch content from a web URL.
    Handles Google Sheets, HTML pages, and direct PDF links.

    Returns: (success: bool, result: list/str, title: str, doc_type: str, metadata: dict)
    """
    if not WEB_SUPPORT:
        return False, "requests and beautifulsoup4 not installed. Install with: pip install requests beautifulsoup4", url, "web", {}
    
    # Check if this is a Google Sheets URL
    if is_google_sheets_url(url):
        success, result, title, doc_type = fetch_google_sheet(url)
        return success, result, title, doc_type, {}

    # Use browser-like headers to avoid 403 Forbidden errors
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }

    try:
        # First, make a HEAD request to check content type
        head_response = requests.head(url, timeout=10, allow_redirects=True, headers=headers)
        content_type = head_response.headers.get('Content-Type', '').lower()

        # Check if it's a PDF by content-type or URL extension
        is_pdf = 'application/pdf' in content_type or url.lower().endswith('.pdf')

        if is_pdf:
            # Handle PDF URLs by downloading to temp file
            try:
                response = requests.get(url, timeout=30, headers=headers)
                response.raise_for_status()

                # Create a temporary file to save the PDF
                with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf:
                    temp_pdf.write(response.content)
                    temp_pdf_path = temp_pdf.name

                # Use existing PDF processing
                try:
                    # Try to extract text normally first
                    success, result, title, doc_type = fetch_local_file(temp_pdf_path)

                    if success:
                        # Extract filename from URL for title
                        url_title = url.split('/')[-1].replace('.pdf', '').replace('_', ' ')
                        return True, result, url_title, "web_pdf", {}
                    elif result == "SCANNED_PDF":
                        # Return special code for scanned PDF
                        url_title = url.split('/')[-1].replace('.pdf', '').replace('_', ' ')
                        return False, "SCANNED_PDF", url_title, "web_pdf", {}
                    else:
                        return False, f"Could not extract text from PDF: {result}", url, "web_pdf", {}
                finally:
                    # Clean up temp file
                    try:
                        os.remove(temp_pdf_path)
                    except:
                        pass

            except Exception as e:
                return False, f"Failed to download/process PDF: {str(e)}", url, "web_pdf", {}

        # Not a PDF - proceed with HTML scraping
        response = requests.get(url, timeout=10, headers=headers)
        response.raise_for_status()

        if BS4_SUPPORT:
            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.title.string.strip() if soup.title else url
            paragraphs = [p.get_text().strip() for p in soup.find_all('p') if p.get_text().strip()]

            if not paragraphs:
                return False, "No meaningful content found", url, "web", {}

            # Extract publication date from meta tags
            published_date = extract_publication_date(soup, response.text)
            
            metadata = {}
            if published_date:
                metadata['published_date'] = published_date

            entries = [{'text': p} for p in paragraphs]
            return True, entries, title, "web", metadata
        else:
            return False, "BeautifulSoup not installed. Install with: pip install beautifulsoup4", url, "web", {}

    except Exception as e:
        return False, f"Failed to fetch URL: {str(e)}", url, "web", {}


def extract_publication_date(soup, html_text: str) -> str:
    """
    Extract publication date from HTML meta tags and JSON-LD.
    
    Args:
        soup: BeautifulSoup object
        html_text: Raw HTML text (for JSON-LD parsing)
        
    Returns:
        ISO date string (YYYY-MM-DD) or empty string if not found
    """
    import re
    from datetime import datetime
    
    date_str = None
    
    # Try various meta tags
    meta_selectors = [
        ('property', 'article:published_time'),
        ('property', 'og:article:published_time'),
        ('name', 'datePublished'),
        ('name', 'date'),
        ('name', 'DC.date'),
        ('name', 'DC.Date'),
        ('name', 'pubdate'),
        ('name', 'publication_date'),
        ('itemprop', 'datePublished'),
        ('property', 'og:updated_time'),  # Fallback to updated time
    ]
    
    for attr, value in meta_selectors:
        meta = soup.find('meta', attrs={attr: value})
        if meta and meta.get('content'):
            date_str = meta['content']
            break
    
    # Try time element with datetime attribute
    if not date_str:
        time_elem = soup.find('time', attrs={'datetime': True})
        if time_elem:
            date_str = time_elem['datetime']
    
    # Try JSON-LD schema
    if not date_str:
        try:
            import json
            for script in soup.find_all('script', type='application/ld+json'):
                if script.string:
                    try:
                        ld_data = json.loads(script.string)
                        # Handle both single objects and arrays
                        if isinstance(ld_data, list):
                            for item in ld_data:
                                if isinstance(item, dict) and 'datePublished' in item:
                                    date_str = item['datePublished']
                                    break
                        elif isinstance(ld_data, dict):
                            if 'datePublished' in ld_data:
                                date_str = ld_data['datePublished']
                            elif '@graph' in ld_data:
                                for item in ld_data['@graph']:
                                    if isinstance(item, dict) and 'datePublished' in item:
                                        date_str = item['datePublished']
                                        break
                    except json.JSONDecodeError:
                        continue
                if date_str:
                    break
        except Exception:
            pass
    
    # Parse and normalize the date
    if date_str:
        try:
            # Common formats
            formats = [
                '%Y-%m-%dT%H:%M:%S%z',      # ISO with timezone
                '%Y-%m-%dT%H:%M:%SZ',        # ISO with Z
                '%Y-%m-%dT%H:%M:%S',         # ISO without timezone
                '%Y-%m-%d',                   # Simple date
                '%B %d, %Y',                  # January 15, 2025
                '%b %d, %Y',                  # Jan 15, 2025
                '%d %B %Y',                   # 15 January 2025
                '%d %b %Y',                   # 15 Jan 2025
                '%m/%d/%Y',                   # 01/15/2025
                '%d/%m/%Y',                   # 15/01/2025
            ]
            
            # Clean the date string
            clean_date = date_str.strip()
            
            for fmt in formats:
                try:
                    dt = datetime.strptime(clean_date[:len(clean_date)], fmt)
                    return dt.strftime('%Y-%m-%d')
                except ValueError:
                    continue
            
            # Try dateutil as fallback
            try:
                from dateutil import parser
                dt = parser.parse(clean_date)
                return dt.strftime('%Y-%m-%d')
            except:
                pass
                
        except Exception:
            pass
    
    return ""

def fetch_web_video(url: str, api_key: str, engine: str, options: dict,
                    bypass_cache: bool, progress_callback) -> Tuple[bool, any, str, str]:
    """
    Download and transcribe video from any supported website using yt-dlp.

    Supports 1000+ sites including iai.tv, TED, Vimeo, Twitter, and more.

    Args:
        url: Web URL containing video
        api_key: API key for transcription service
        engine: Transcription engine to use
        options: Transcription options (language, diarization, etc.)
        bypass_cache: Whether to bypass audio cache
        progress_callback: Function to update progress status

    Returns: (success, result/error, title, source_type)
    """
    try:
        import yt_dlp
        import tempfile
        import os

        progress_callback(f"🔍 Detecting video at {url[:50]}...")

        # Configure yt-dlp options
        ydl_opts = {
            'format': 'bestaudio/best',  # Get best audio quality
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }

        # First, extract video info without downloading
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)

                if not info:
                    return False, "Could not extract video information from URL", url, "web_video"

                # Get video title
                title = info.get('title', 'Unknown Video')
                duration = info.get('duration', 0)

                # Check if video is available
                if info.get('is_live'):
                    return False, "Live streams are not supported", title, "web_video"

                # Format duration safely (handle both int and float)
                if duration:
                    minutes = int(duration // 60)
                    seconds = int(duration % 60)
                    progress_callback(f"📹 Found video: {title} ({minutes}:{seconds:02d})")
                else:
                    progress_callback(f"📹 Found video: {title}")

            except Exception as e:
                # Not a video URL or unsupported site
                error_msg = str(e)
                if "Unsupported URL" in error_msg:
                    return False, "NOT_A_VIDEO", url, "web"
                return False, f"Could not access video: {error_msg}", url, "web_video"

        # Now download and transcribe
        progress_callback(f"⬇️ Downloading audio from video...")

        # Create temporary directory for download
        temp_dir = tempfile.mkdtemp()

        try:
            # Configure download options
            download_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }

            # Download audio
            with yt_dlp.YoutubeDL(download_opts) as ydl:
                ydl.download([url])

            # Find the downloaded audio file
            audio_files = [f for f in os.listdir(temp_dir) if f.endswith('.mp3')]

            if not audio_files:
                return False, "Failed to download audio from video", title, "web_video"

            audio_path = os.path.join(temp_dir, audio_files[0])

            # Transcribe the audio
            progress_callback(f"🎤 Transcribing audio...")

            from audio_handler import transcribe_audio_file

            success, entries, transcription_title = transcribe_audio_file(
                filepath=audio_path,
                engine=engine,
                api_key=api_key,
                options=options,
                bypass_cache=bypass_cache,
                progress_callback=progress_callback
            )

            if success:
                return True, entries, title, "web_video"
            else:
                return False, f"Transcription failed: {entries}", title, "web_video"

        finally:
            # Clean up temporary files
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except:
                pass

    except ImportError:
        return False, "yt-dlp not installed. Install with: pip install yt-dlp", url, "web_video"
    except Exception as e:
        return False, f"Error processing web video: {str(e)}", url, "web_video"
