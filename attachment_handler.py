"""
attachment_handler.py

Handles file attachments for DocAnalyser prompts.
Allows users to attach additional documents that will be included
in the context when sending prompts to the AI.

The AttachmentManager class manages temporary attachments that are 
included in AI prompts. These are NOT saved to the Documents Library.

Usage:
    from attachment_handler import AttachmentManager, check_local_ai_context_warning
"""

import os
from typing import List, Dict, Optional


# Local AI provider names that have limited context windows
LOCAL_AI_PROVIDERS = [
    "LM Studio (Local)",
    "Ollama",
    "Local",
]

# Typical context limits for local models (in tokens)
LOCAL_AI_CONTEXT_LIMITS = {
    "small": 4096,      # Older/smaller models
    "medium": 8192,     # Common default
    "large": 32768,     # Newer models like Llama 3
    "typical": 8192,    # Used for warnings
}


def check_local_ai_context_warning(provider: str, total_words: int, attachment_count: int) -> Optional[str]:
    """
    Check if the user should be warned about local AI context limitations.
    
    Args:
        provider: Current AI provider name
        total_words: Total words in attachments (or document + attachments)
        attachment_count: Number of attachments
        
    Returns:
        Warning message string if warning needed, None otherwise
    """
    # Check if it's a local AI provider
    is_local = any(local in provider for local in LOCAL_AI_PROVIDERS)
    if not is_local:
        return None
    
    # Only warn if there are attachments or significant content
    if attachment_count == 0:
        return None
    
    # Estimate tokens (rough: 1 word ≈ 1.3 tokens)
    estimated_tokens = int(total_words * 1.3)
    typical_limit = LOCAL_AI_CONTEXT_LIMITS["typical"]
    
    # Warn if approaching or exceeding typical local model limits
    if estimated_tokens > typical_limit * 0.7:  # 70% of typical limit
        warning = (
            f"⚠️ Local AI Context Warning\n\n"
            f"You have {attachment_count} attachment{'s' if attachment_count != 1 else ''} "
            f"totalling approximately {total_words:,} words (~{estimated_tokens:,} tokens).\n\n"
            f"Local AI models (via LM Studio, Ollama, etc.) typically have limited "
            f"context windows of 4K-32K tokens. Your content may:\n\n"
            f"  • Be truncated (AI only sees part of the content)\n"
            f"  • Cause errors or slow performance\n"
            f"  • Produce lower quality responses\n\n"
            f"For multi-document analysis, consider using a cloud provider:\n"
            f"  • Claude (200K tokens)\n"
            f"  • GPT-4 (128K tokens)\n"
            f"  • Gemini (1M+ tokens)\n\n"
            f"Continue anyway?"
        )
        return warning
    
    return None


class AttachmentManager:
    """
    Manages file attachments for AI prompts.
    
    Handles:
    - Adding/removing attachments
    - Extracting text from various file formats
    - Building attachment text for prompts
    - Token estimation
    
    Attachments are temporary and are NOT saved to the Documents Library.
    They are included in the AI prompt context for multi-document analysis.
    """
    
    # Supported file extensions
    SUPPORTED_EXTENSIONS = {
        '.txt': 'Text file',
        '.pdf': 'PDF document',
        '.docx': 'Word document',
        '.doc': 'Word document (legacy)',
        '.rtf': 'Rich text file',
        '.md': 'Markdown file',
        '.csv': 'CSV file',
        '.json': 'JSON file',
    }
    
    def __init__(self):
        self.attachments: List[Dict] = []
        # Each attachment: {
        #     'path': str,
        #     'filename': str,
        #     'text': str,
        #     'word_count': int,
        #     'token_estimate': int,
        #     'error': str or None,
        #     'from_library': bool (optional),
        #     'from_sources_dialog': bool (optional),
        #     'doc_id': str (optional, for library docs)
        # }
    
    def get_supported_filetypes(self) -> List[tuple]:
        """Get file types for file dialog"""
        types = [("All supported", " ".join(f"*{ext}" for ext in self.SUPPORTED_EXTENSIONS.keys()))]
        for ext, desc in self.SUPPORTED_EXTENSIONS.items():
            types.append((desc, f"*{ext}"))
        types.append(("All files", "*.*"))
        return types
    
    def add_from_library(self, doc_id: str, doc_title: str, doc_text: str) -> Dict:
        """
        Add a document from the DocAnalyser library as an attachment.
        
        Args:
            doc_id: Document ID from library
            doc_title: Document title
            doc_text: Already-extracted document text
            
        Returns:
            Attachment dict
        """
        # Check if already attached
        for att in self.attachments:
            if att.get('doc_id') == doc_id:
                return {'error': f"Document already attached: {doc_title}"}
        
        if not doc_text or not doc_text.strip():
            return {'error': f"No text content in document: {doc_title}"}
        
        word_count = len(doc_text.split())
        token_estimate = int(word_count * 1.3)
        
        attachment = {
            'doc_id': doc_id,
            'path': f"library://{doc_id}",
            'filename': doc_title,
            'text': doc_text,
            'word_count': word_count,
            'token_estimate': token_estimate,
            'error': None,
            'from_library': True
        }
        
        self.attachments.append(attachment)
        return attachment
    
    def add_from_text(self, title: str, text: str, source: str) -> Dict:
        """
        Add content directly as an attachment (text already extracted).
        
        Used by the unified sources dialog when adding to prompt context.
        
        Args:
            title: Display title for the attachment
            text: Already-extracted text content
            source: Source URL or file path
            
        Returns:
            Attachment dict with 'error' key if failed
        """
        # Check if already attached (by source)
        for att in self.attachments:
            if att.get('path') == source or att.get('source') == source:
                return {'error': f"Source already attached: {title}"}
        
        if not text or not text.strip():
            return {'error': f"No text content: {title}"}
        
        word_count = len(text.split())
        token_estimate = int(word_count * 1.3)
        
        attachment = {
            'path': source,
            'source': source,
            'filename': title,
            'text': text,
            'word_count': word_count,
            'token_estimate': token_estimate,
            'error': None,
            'from_sources_dialog': True
        }
        
        self.attachments.append(attachment)
        return attachment
    
    def add_attachment(self, filepath: str, progress_callback=None) -> Dict:
        """
        Add a file attachment.
        
        Args:
            filepath: Path to the file
            progress_callback: Optional function to report progress
            
        Returns:
            Attachment dict with extracted text or error
        """
        if not os.path.exists(filepath):
            return {'error': f"File not found: {filepath}"}
        
        filename = os.path.basename(filepath)
        ext = os.path.splitext(filepath)[1].lower()
        
        # Check if already attached
        for att in self.attachments:
            if att['path'] == filepath:
                return {'error': f"File already attached: {filename}"}
        
        if progress_callback:
            progress_callback(f"Extracting text from {filename}...")
        
        # Extract text based on file type
        try:
            text = self._extract_text(filepath, ext)
            
            if not text or not text.strip():
                return {'error': f"No text content found in {filename}"}
            
            word_count = len(text.split())
            token_estimate = int(word_count * 1.3)
            
            attachment = {
                'path': filepath,
                'filename': filename,
                'text': text,
                'word_count': word_count,
                'token_estimate': token_estimate,
                'error': None
            }
            
            self.attachments.append(attachment)
            return attachment
            
        except Exception as e:
            return {'error': f"Error reading {filename}: {str(e)}"}
    
    def _extract_text(self, filepath: str, ext: str) -> str:
        """Extract text from a file based on its extension"""
        
        if ext == '.txt' or ext == '.md':
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        
        elif ext == '.pdf':
            return self._extract_pdf(filepath)
        
        elif ext == '.docx':
            return self._extract_docx(filepath)
        
        elif ext == '.doc':
            return self._extract_doc(filepath)
        
        elif ext == '.rtf':
            return self._extract_rtf(filepath)
        
        elif ext == '.csv':
            return self._extract_csv(filepath)
        
        elif ext == '.json':
            return self._extract_json(filepath)
        
        else:
            # Try reading as plain text
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
    
    def _extract_pdf(self, filepath: str) -> str:
        """Extract text from PDF"""
        try:
            import PyPDF2
            text_parts = []
            with open(filepath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            return '\n\n'.join(text_parts)
        except ImportError:
            raise ImportError("PyPDF2 not installed. Install with: pip install PyPDF2")
    
    def _extract_docx(self, filepath: str) -> str:
        """Extract text from DOCX"""
        try:
            from docx import Document
            doc = Document(filepath)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return '\n\n'.join(paragraphs)
        except ImportError:
            raise ImportError("python-docx not installed. Install with: pip install python-docx")
    
    def _extract_doc(self, filepath: str) -> str:
        """Extract text from legacy DOC files"""
        try:
            import textract
            text = textract.process(filepath).decode('utf-8')
            return text
        except ImportError:
            try:
                return self._extract_docx(filepath)
            except:
                raise ImportError("Cannot read .doc files. Install textract or convert to .docx")
    
    def _extract_rtf(self, filepath: str) -> str:
        """Extract text from RTF"""
        try:
            from striprtf.striprtf import rtf_to_text
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                rtf_content = f.read()
            return rtf_to_text(rtf_content)
        except ImportError:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            import re
            text = re.sub(r'\\[a-z]+\d*\s?', '', content)
            text = re.sub(r'[{}]', '', text)
            return text
    
    def _extract_csv(self, filepath: str) -> str:
        """Extract text from CSV"""
        import csv
        rows = []
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.reader(f)
            for row in reader:
                rows.append(' | '.join(row))
        return '\n'.join(rows)
    
    def _extract_json(self, filepath: str) -> str:
        """Extract text from JSON"""
        import json
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return json.dumps(data, indent=2)
    
    def remove_attachment(self, index: int) -> bool:
        """Remove attachment by index"""
        if 0 <= index < len(self.attachments):
            self.attachments.pop(index)
            return True
        return False
    
    def remove_attachment_by_path(self, filepath: str) -> bool:
        """Remove attachment by file path"""
        for i, att in enumerate(self.attachments):
            if att['path'] == filepath:
                self.attachments.pop(i)
                return True
        return False
    
    def clear_all(self):
        """Remove all attachments"""
        self.attachments.clear()
    
    def get_attachment_count(self) -> int:
        """Get number of attachments"""
        return len(self.attachments)
    
    def get_total_tokens(self) -> int:
        """Get estimated total tokens for all attachments"""
        return sum(att['token_estimate'] for att in self.attachments)
    
    def get_total_words(self) -> int:
        """Get total word count for all attachments"""
        return sum(att['word_count'] for att in self.attachments)
    
    def build_attachment_text(self) -> str:
        """
        Build formatted text containing all attachments.
        
        Returns:
            Formatted string with all attachment contents
        """
        if not self.attachments:
            return ""
        
        parts = []
        parts.append("=" * 60)
        parts.append("ATTACHED DOCUMENTS")
        parts.append("=" * 60)
        
        for i, att in enumerate(self.attachments, 1):
            parts.append(f"\n--- ATTACHMENT {i}: {att['filename']} ---")
            parts.append(f"(~{att['word_count']} words)")
            parts.append("")
            parts.append(att['text'])
            parts.append("")
        
        parts.append("=" * 60)
        parts.append("END OF ATTACHMENTS")
        parts.append("=" * 60)
        
        return '\n'.join(parts)
    
    def get_summary(self) -> str:
        """Get a summary of current attachments"""
        if not self.attachments:
            return "No attachments"
        
        count = len(self.attachments)
        words = self.get_total_words()
        tokens = self.get_total_tokens()
        
        return f"{count} file{'s' if count != 1 else ''} attached (~{words:,} words, ~{tokens:,} tokens)"
