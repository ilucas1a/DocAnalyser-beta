"""
UNIVERSAL_DOCUMENT_SAVER.PY
============================

A SINGLE, GENERIC auto-save function that handles ALL document types:
- YouTube transcripts
- PDF documents
- OCR from images
- Audio transcriptions
- Dictation
- Web scraping
- Facebook posts
- Substack articles
- ... ANY document type!

NO CODE DUPLICATION - one function saves them all!

Usage:
------
from universal_document_saver import UniversalDocumentSaver

# Initialize once
doc_saver = UniversalDocumentSaver()

# Use for ANY document type:
doc_id = doc_saver.save_source_document(
    entries=entries,          # List of entry dicts
    title=title,              # Document title
    doc_type="youtube",       # Type identifier
    source=url,               # Source URL/path
    metadata=metadata         # Optional metadata dict
)
"""

from typing import List, Dict, Optional
import datetime


class UniversalDocumentSaver:
    """
    Universal document saver that handles ALL input modalities.
    One function to save them all!
    """
    
    def __init__(self, enabled: bool = True, auto_set_current: bool = True):
        """
        Initialize the universal saver.
        
        Args:
            enabled: Whether auto-save is enabled
            auto_set_current: Whether to automatically set as current document
        """
        self.enabled = enabled
        self.auto_set_current = auto_set_current
        self.last_saved_doc_id = None
    
    def save_source_document(self,
                            entries: List[Dict],
                            title: str,
                            doc_type: str,
                            source: str,
                            metadata: Optional[Dict] = None) -> Optional[str]:
        """
        Save ANY source document to the Documents Library.
        
        Works for ALL input types:
        - YouTube transcripts
        - PDF documents
        - OCR results
        - Audio transcriptions
        - Dictation
        - Web pages
        - Facebook posts
        - Substack articles
        - ... and more!
        
        Args:
            entries: List of document entries/segments
                     Each entry should be a dict with at least 'text' key
                     Optional keys: 'location', 'start', 'duration', 'timestamp', 'page', etc.
            title: Document title (e.g., "YouTube: Video Title", "PDF: Document.pdf")
            doc_type: Document type identifier
                     Examples: "youtube", "pdf", "ocr", "audio_transcription",
                              "dictation", "web", "facebook", "substack"
            source: Source identifier (URL, file path, etc.)
            metadata: Optional metadata dict
                     Can include: published_date, author, duration, page_count, etc.
        
        Returns:
            Document ID if saved successfully, None otherwise
        """
        if not self.enabled:
            print("⏭️  Auto-save disabled")
            return None
        
        if not entries:
            print("⚠️  No entries to save")
            return None
        
        if not title:
            print("⚠️  No title provided")
            return None
        
        try:
            from document_library import add_document_to_library
            
            # Prepare metadata
            if metadata is None:
                metadata = {}
            
            # Add common metadata fields
            metadata['fetched_at'] = datetime.datetime.now().isoformat()
            metadata['auto_saved'] = True
            metadata['editable'] = False  # Source documents are read-only
            
            # Save to library as SOURCE document
            doc_id = add_document_to_library(
                doc_type=doc_type,
                source=source,
                title=title,
                entries=entries,
                metadata=metadata,
                document_class='source'  # Always 'source' for fetched documents
            )
            
            print(f"✅ Auto-saved source document: {title}")
            print(f"   Type: {doc_type}")
            print(f"   Entries: {len(entries)}")
            print(f"   Document ID: {doc_id}")
            
            self.last_saved_doc_id = doc_id
            return doc_id
            
        except Exception as e:
            print(f"❌ Failed to auto-save source document: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def enable(self):
        """Enable auto-save"""
        self.enabled = True
        print("✅ Source document auto-save ENABLED")
    
    def disable(self):
        """Disable auto-save"""
        self.enabled = False
        print("⏸️  Source document auto-save DISABLED")
    
    def toggle(self) -> bool:
        """Toggle auto-save on/off"""
        self.enabled = not self.enabled
        status = "ENABLED" if self.enabled else "DISABLED"
        print(f"🔄 Source document auto-save {status}")
        return self.enabled
    
    def get_last_saved_id(self) -> Optional[str]:
        """Get the document ID of the last saved document"""
        return self.last_saved_doc_id


"""
===============================================================================
INTEGRATION EXAMPLES - How to Use in Main.py
===============================================================================
"""

# ============================================================================
# STEP 1: Initialize in main.py __init__
# ============================================================================

"""
In your main.py __init__ method:

from universal_document_saver import UniversalDocumentSaver

def __init__(self):
    # ... other init code ...
    
    # Initialize universal saver
    self.doc_saver = UniversalDocumentSaver(enabled=True)
"""


# ============================================================================
# STEP 2: Use After EVERY Document Fetch
# ============================================================================

"""
EXAMPLE 1: YouTube Transcripts
-------------------------------
"""

def handle_youtube_url(self, url):
    """When user loads a YouTube URL"""
    from youtube_utils import fetch_youtube_transcript
    
    # Fetch the transcript
    success, entries, title, doc_type, metadata = fetch_youtube_transcript(url)
    
    if success:
        # AUTO-SAVE using universal saver
        doc_id = self.doc_saver.save_source_document(
            entries=entries,
            title=title,
            doc_type=doc_type,
            source=url,
            metadata=metadata
        )
        
        # Set as current document for AI processing
        self.current_document_id = doc_id
        self.current_document_source = url
        
        # Display in UI
        self.display_entries(entries)


"""
EXAMPLE 2: PDF Documents
------------------------
"""

def handle_pdf_file(self, filepath):
    """When user loads a PDF file"""
    from pdf_handler import extract_text_from_pdf
    
    # Extract text from PDF
    entries, title, metadata = extract_text_from_pdf(filepath)
    
    # AUTO-SAVE using universal saver
    doc_id = self.doc_saver.save_source_document(
        entries=entries,
        title=title,
        doc_type="pdf",
        source=filepath,
        metadata=metadata
    )
    
    # Set as current document
    self.current_document_id = doc_id
    self.current_document_source = filepath


"""
EXAMPLE 3: OCR from Images
---------------------------
"""

def handle_ocr_scan(self, image_paths):
    """When user scans images with OCR"""
    from ocr_handler import perform_ocr
    
    # Perform OCR
    entries, title, metadata = perform_ocr(image_paths)
    
    # AUTO-SAVE using universal saver
    doc_id = self.doc_saver.save_source_document(
        entries=entries,
        title=title,
        doc_type="ocr",
        source=f"{len(image_paths)} images",
        metadata=metadata
    )
    
    # Set as current document
    self.current_document_id = doc_id


"""
EXAMPLE 4: Audio Transcription
-------------------------------
"""

def handle_audio_file(self, audio_path):
    """When user transcribes audio"""
    from audio_handler import transcribe_audio
    
    # Transcribe audio
    entries, title, metadata = transcribe_audio(audio_path, self.api_key)
    
    # AUTO-SAVE using universal saver
    doc_id = self.doc_saver.save_source_document(
        entries=entries,
        title=title,
        doc_type="audio_transcription",
        source=audio_path,
        metadata=metadata
    )
    
    # Set as current document
    self.current_document_id = doc_id


"""
EXAMPLE 5: Dictation
---------------------
"""

def handle_dictation(self, audio_data):
    """When user uses dictation"""
    from dictation_handler import transcribe_dictation
    
    # Transcribe dictation
    entries, title, metadata = transcribe_dictation(audio_data)
    
    # AUTO-SAVE using universal saver
    doc_id = self.doc_saver.save_source_document(
        entries=entries,
        title=title,
        doc_type="dictation",
        source="Live dictation",
        metadata=metadata
    )
    
    # Set as current document
    self.current_document_id = doc_id


"""
EXAMPLE 6: Web Scraping
-----------------------
"""

def handle_web_url(self, url):
    """When user scrapes a web page"""
    from web_scraper import scrape_page
    
    # Scrape the page
    entries, title, metadata = scrape_page(url)
    
    # AUTO-SAVE using universal saver
    doc_id = self.doc_saver.save_source_document(
        entries=entries,
        title=title,
        doc_type="web",
        source=url,
        metadata=metadata
    )
    
    # Set as current document
    self.current_document_id = doc_id


# ============================================================================
# STEP 3: Generic Handler Pattern (RECOMMENDED)
# ============================================================================

"""
BEST PRACTICE: Create ONE generic handler that works for ALL types
"""

def load_document(self, entries, title, doc_type, source, metadata=None):
    """
    UNIVERSAL document loader - works for ALL input types!
    
    Call this after fetching ANY document type.
    """
    # AUTO-SAVE to library
    doc_id = self.doc_saver.save_source_document(
        entries=entries,
        title=title,
        doc_type=doc_type,
        source=source,
        metadata=metadata
    )
    
    # Set as current document
    self.current_document_id = doc_id
    self.current_document_source = source
    
    # Display in UI
    self.display_entries(entries)
    self.update_status(f"Loaded: {title}")
    
    # Refresh library if open
    if hasattr(self, 'refresh_library'):
        self.refresh_library()
    
    return doc_id


"""
Then use it for EVERYTHING:
"""

def handle_youtube(self, url):
    success, entries, title, doc_type, metadata = fetch_youtube_transcript(url)
    if success:
        self.load_document(entries, title, doc_type, url, metadata)

def handle_pdf(self, path):
    entries, title, metadata = extract_pdf(path)
    self.load_document(entries, title, "pdf", path, metadata)

def handle_ocr(self, images):
    entries, title, metadata = perform_ocr(images)
    self.load_document(entries, title, "ocr", "images", metadata)

# ONE function, ALL document types! ✅


"""
===============================================================================
TESTING
===============================================================================
"""

if __name__ == "__main__":
    print("UniversalDocumentSaver Demo")
    print("=" * 80)
    
    saver = UniversalDocumentSaver()
    
    # Test 1: YouTube
    doc_id = saver.save_source_document(
        entries=[
            {'text': 'Hello world', 'start': 0},
            {'text': 'This is a test', 'start': 5}
        ],
        title="YouTube: Test Video",
        doc_type="youtube",
        source="https://youtube.com/watch?v=test123",
        metadata={'published_date': '2024-01-01'}
    )
    print(f"YouTube doc_id: {doc_id}\n")
    
    # Test 2: PDF
    doc_id = saver.save_source_document(
        entries=[
            {'text': 'Page 1 content', 'page': 1},
            {'text': 'Page 2 content', 'page': 2}
        ],
        title="PDF: Test Document.pdf",
        doc_type="pdf",
        source="/path/to/test.pdf",
        metadata={'page_count': 2}
    )
    print(f"PDF doc_id: {doc_id}\n")
    
    # Test 3: OCR
    doc_id = saver.save_source_document(
        entries=[
            {'text': 'OCR text from image 1', 'image': 1},
            {'text': 'OCR text from image 2', 'image': 2}
        ],
        title="OCR: Scanned Document",
        doc_type="ocr",
        source="2 images",
        metadata={'image_count': 2}
    )
    print(f"OCR doc_id: {doc_id}\n")
    
    print("=" * 80)
    print("All document types saved with ONE function! ✅")
