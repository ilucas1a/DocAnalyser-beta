"""
document_export.py - Consolidated Document Export Module
Handles all document exports (txt, docx, rtf, pdf) in a single location.

This module consolidates export functionality that was previously duplicated
across Main.py and thread_viewer.py.
"""

import os
import re
import datetime
from typing import Dict, List, Optional, Tuple, Any


def get_export_date() -> str:
    """Get current date/time formatted for export metadata (DD-Mon-YYYY HH:MM:SS)"""
    now = datetime.datetime.now()
    return now.strftime('%d-%b-%Y %H:%M:%S')


def sanitize_filename(text: str, max_length: int = 100) -> str:
    """Convert text to a safe filename"""
    clean_name = re.sub(r'[<>:"/\\|?*]', '-', text)
    clean_name = ''.join(char for char in clean_name if ord(char) >= 32)
    clean_name = re.sub(r'[-\s]+', ' ', clean_name).strip()
    if len(clean_name) > max_length:
        clean_name = clean_name[:max_length].rsplit(' ', 1)[0]
    return clean_name if clean_name else 'document'


def get_file_extension_and_types(format: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Get file extension and filetypes for save dialog"""
    format_map = {
        'txt': ('.txt', [("Text files", "*.txt"), ("All files", "*.*")]),
        'docx': ('.docx', [("Word Document", "*.docx"), ("All files", "*.*")]),
        'rtf': ('.rtf', [("RTF files", "*.rtf"), ("All files", "*.*")]),
        'pdf': ('.pdf', [("PDF files", "*.pdf"), ("All files", "*.*")]),
    }
    return format_map.get(format, ('.txt', [("All files", "*.*")]))


# =============================================================================
# DOCUMENT EXPORT - For source documents and AI products
# =============================================================================

def export_document(
    filepath: str,
    content: str,
    format: str,
    metadata: Dict[str, Any],
    show_messages: bool = True
) -> Tuple[bool, str]:
    """
    Universal document export function.
    
    Args:
        filepath: Full path to save the file
        content: The document content text
        format: Export format ('txt', 'docx', 'rtf', 'pdf')
        metadata: Dict with keys:
            - title: Document title
            - source: Source URL/path
            - published_date: Original publication date (optional)
            - imported_date: When document was imported
            - doc_class: 'source' or 'product'
            - provider: AI provider (optional)
            - model: AI model (optional)
        show_messages: Whether to show success/error message boxes
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    format = format.lower()
    export_date = get_export_date()
    
    # Extract metadata with defaults
    title = metadata.get('title', 'Untitled Document')
    source = metadata.get('source', 'Unknown')
    published_date = metadata.get('published_date')
    imported_date = metadata.get('imported_date', 'Unknown')
    doc_class = metadata.get('doc_class', 'source')
    provider = metadata.get('provider')
    model = metadata.get('model')
    
    try:
        if format == 'txt':
            return _export_as_txt(filepath, content, title, source, published_date, 
                                  imported_date, export_date, doc_class, provider, model, show_messages)
        elif format == 'docx':
            return _export_as_docx(filepath, content, title, source, published_date,
                                   imported_date, export_date, doc_class, provider, model, show_messages)
        elif format == 'rtf':
            return _export_as_rtf(filepath, content, title, source, published_date,
                                  imported_date, export_date, doc_class, provider, model, show_messages)
        elif format == 'pdf':
            return _export_as_pdf(filepath, content, title, source, published_date,
                                  imported_date, export_date, doc_class, provider, model, show_messages)
        else:
            return False, f"Unsupported format: {format}"
    except Exception as e:
        error_msg = f"Export failed: {str(e)}"
        if show_messages:
            from tkinter import messagebox
            messagebox.showerror("Export Error", error_msg)
        return False, error_msg


def _export_as_txt(filepath, content, title, source, published_date, 
                   imported_date, export_date, doc_class, provider, model, show_messages) -> Tuple[bool, str]:
    """Export document as plain text"""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write(f"{title}\n")
        f.write("=" * 80 + "\n\n")
        f.write("DOCUMENT INFORMATION:\n")
        f.write(f"  Title: {title}\n")
        f.write(f"  Source: {source}\n")
        if published_date:
            f.write(f"  Published: {published_date}\n")
        f.write(f"  Imported: {imported_date}\n")
        f.write(f"  Exported: {export_date}\n")
        f.write(f"  Type: {doc_class}\n")
        if provider and model:
            f.write(f"  Processed By: {provider} / {model}\n")
        f.write("\n" + "=" * 80 + "\n\n")
        f.write(content)
    
    if show_messages:
        from tkinter import messagebox
        messagebox.showinfo("Saved", f"✅ Text saved to:\n{filepath}")
    return True, filepath


def _export_as_docx(filepath, content, title, source, published_date,
                    imported_date, export_date, doc_class, provider, model, show_messages) -> Tuple[bool, str]:
    """Export document as Word docx"""
    try:
        from docx import Document
        from docx.shared import Pt
        from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
    except ImportError:
        if show_messages:
            from tkinter import messagebox
            messagebox.showerror("Error", "python-docx library not installed.\n\nInstall with: pip install python-docx")
        return False, "python-docx not installed"
    
    doc = Document()
    
    # Add title heading
    title_para = doc.add_heading(title[:100], 0)
    title_para.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    
    # Add metadata section
    doc.add_heading('Document Information', level=2)
    meta_para = doc.add_paragraph()
    meta_para.add_run("Title: ").bold = True
    meta_para.add_run(f"{title}\n")
    meta_para.add_run("Source: ").bold = True
    meta_para.add_run(f"{source}\n")
    if published_date:
        meta_para.add_run("Published: ").bold = True
        meta_para.add_run(f"{published_date}\n")
    meta_para.add_run("Imported: ").bold = True
    meta_para.add_run(f"{imported_date}\n")
    meta_para.add_run("Exported: ").bold = True
    meta_para.add_run(f"{export_date}\n")
    meta_para.add_run("Type: ").bold = True
    meta_para.add_run(f"{doc_class}\n")
    if provider and model:
        meta_para.add_run("Processed By: ").bold = True
        meta_para.add_run(f"{provider} / {model}\n")
    
    doc.add_paragraph()  # Spacing
    
    # Add content heading
    doc.add_heading('Content', level=2)
    
    # Add content with markdown formatting support
    _add_markdown_content_to_docx(doc, content)
    
    doc.save(filepath)
    
    if show_messages:
        from tkinter import messagebox
        messagebox.showinfo("Saved", f"✅ Document saved to:\n{filepath}")
    return True, filepath


def _export_as_rtf(filepath, content, title, source, published_date,
                   imported_date, export_date, doc_class, provider, model, show_messages) -> Tuple[bool, str]:
    """Export document as RTF"""
    try:
        rtf_content = []
        rtf_content.append(r'{\rtf1\ansi\deff0')
        rtf_content.append(r'{\fonttbl{\f0 Times New Roman;}}')
        rtf_content.append(r'\f0\fs24')
        
        # Title (large, bold)
        safe_title = title.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
        rtf_content.append(r'{\b\fs32 ' + safe_title + r'}\par')
        rtf_content.append(r'\par')
        
        # Metadata section
        rtf_content.append(r'{\b\fs28 Document Information}\par')
        rtf_content.append(r'{\b Title: }' + safe_title + r'\par')
        safe_source = source.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
        rtf_content.append(r'{\b Source: }' + safe_source + r'\par')
        if published_date:
            rtf_content.append(r'{\b Published: }' + published_date + r'\par')
        rtf_content.append(r'{\b Imported: }' + imported_date + r'\par')
        rtf_content.append(r'{\b Exported: }' + export_date + r'\par')
        rtf_content.append(r'{\b Type: }' + doc_class + r'\par')
        if provider and model:
            rtf_content.append(r'{\b Processed By: }' + f"{provider} / {model}" + r'\par')
        rtf_content.append(r'\par')
        
        # Content section
        rtf_content.append(r'{\b\fs28 Content}\par')
        for line in content.split('\n'):
            if line.strip():
                safe_line = line.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
                rtf_content.append(safe_line + r'\par')
        
        rtf_content.append(r'}')
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(rtf_content))
        
        if show_messages:
            from tkinter import messagebox
            messagebox.showinfo("Saved", f"✅ Document saved as RTF:\n{filepath}")
        return True, filepath
        
    except Exception as e:
        # Fallback to TXT
        txt_path = filepath.replace('.rtf', '.txt')
        if show_messages:
            from tkinter import messagebox
            messagebox.showerror("RTF Error", f"Failed to create RTF:\n{str(e)}\n\nSaving as TXT instead...")
        return _export_as_txt(txt_path, content, title, source, published_date,
                              imported_date, export_date, doc_class, provider, model, show_messages)


def _export_as_pdf(filepath, content, title, source, published_date,
                   imported_date, export_date, doc_class, provider, model, show_messages) -> Tuple[bool, str]:
    """Export document as PDF"""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.units import inch
        from reportlab.lib.enums import TA_CENTER
    except ImportError:
        # Fallback to TXT
        txt_path = filepath.replace('.pdf', '.txt')
        if show_messages:
            from tkinter import messagebox
            messagebox.showerror("Error", 
                "reportlab library not installed.\n\n"
                "Install with: pip install reportlab\n\n"
                "Falling back to TXT format...")
        return _export_as_txt(txt_path, content, title, source, published_date,
                              imported_date, export_date, doc_class, provider, model, show_messages)
    
    pdf_doc = SimpleDocTemplate(filepath, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor='#2E4053',
        spaceAfter=20,
        alignment=TA_CENTER
    )
    story.append(Paragraph(title[:100], title_style))
    story.append(Spacer(1, 0.2 * inch))
    
    # Metadata section
    meta_style = ParagraphStyle(
        'Meta',
        parent=styles['Normal'],
        fontSize=10,
        textColor='#555555'
    )
    story.append(Paragraph("<b>Document Information</b>", styles['Heading2']))
    story.append(Paragraph(f"<b>Title:</b> {_escape_pdf_text(title)}", meta_style))
    story.append(Paragraph(f"<b>Source:</b> {_escape_pdf_text(source)}", meta_style))
    if published_date:
        story.append(Paragraph(f"<b>Published:</b> {published_date}", meta_style))
    story.append(Paragraph(f"<b>Imported:</b> {imported_date}", meta_style))
    story.append(Paragraph(f"<b>Exported:</b> {export_date}", meta_style))
    story.append(Paragraph(f"<b>Type:</b> {doc_class}", meta_style))
    if provider and model:
        story.append(Paragraph(f"<b>Processed By:</b> {provider} / {model}", meta_style))
    story.append(Spacer(1, 0.3 * inch))
    
    # Content section
    story.append(Paragraph("<b>Content</b>", styles['Heading2']))
    
    # Process content with markdown formatting and paragraph preservation
    _split_into_pdf_paragraphs(content, story, styles['Normal'])
    
    pdf_doc.build(story)
    
    if show_messages:
        from tkinter import messagebox
        messagebox.showinfo("Saved", f"✅ Document saved as PDF:\n{filepath}")
    return True, filepath


def _escape_pdf_text(text: str) -> str:
    """Escape special characters for PDF/reportlab"""
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    return text


def _markdown_to_pdf_html(text: str) -> str:
    """
    Convert markdown formatting to reportlab-compatible HTML.
    Converts **bold** to <b>bold</b> and *italic* to <i>italic</i>.
    Also escapes special characters.
    """
    import re
    
    # First escape special characters (but not * which we need for markdown)
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    
    # Convert **bold** to <b>bold</b> (do this before italic)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
    
    # Convert *italic* to <i>italic</i>
    text = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', text)
    
    # Convert # headers to bold (simplified for PDF)
    lines = text.split('\n')
    converted_lines = []
    for line in lines:
        if line.strip().startswith('#'):
            # Remove # and make bold
            header_text = line.lstrip('#').strip()
            converted_lines.append(f'<b>{header_text}</b>')
        else:
            converted_lines.append(line)
    
    return '\n'.join(converted_lines)


def _split_into_pdf_paragraphs(content: str, story: list, style):
    """
    Split content into paragraphs and add to PDF story.
    Handles markdown formatting and preserves paragraph breaks.
    """
    from reportlab.platypus import Paragraph, Spacer
    
    # Convert markdown to HTML
    formatted_content = _markdown_to_pdf_html(content)
    
    # Split on double newlines (paragraph breaks) or single newlines for distinct lines
    paragraphs = formatted_content.split('\n\n')
    
    for para in paragraphs:
        if para.strip():
            # Replace single newlines with <br/> for line breaks within paragraph
            para_html = para.strip().replace('\n', '<br/>')
            try:
                story.append(Paragraph(para_html, style))
                story.append(Spacer(1, 6))
            except Exception:
                # If paragraph fails to render, try plain text
                plain = para.replace('<b>', '').replace('</b>', '')
                plain = plain.replace('<i>', '').replace('</i>', '')
                plain = plain.replace('<br/>', ' ')
                try:
                    story.append(Paragraph(plain[:1000], style))
                    story.append(Spacer(1, 6))
                except:
                    pass  # Skip problematic paragraphs


# =============================================================================
# CONVERSATION THREAD EXPORT - For conversation threads
# =============================================================================

def export_conversation_thread(
    filepath: str,
    format: str,
    thread_messages: List[Dict],
    thread_metadata: Dict[str, Any],
    show_messages: bool = True
) -> Tuple[bool, str]:
    """
    Export a conversation thread to file.
    
    Args:
        filepath: Full path to save the file
        format: Export format ('txt', 'docx', 'rtf', 'pdf')
        thread_messages: List of message dicts with 'role' and 'content' keys
        thread_metadata: Dict with keys:
            - doc_title: Source document title
            - source_info: Source URL/path
            - published_date: Original publication date (optional)
            - fetched_date: When document was imported
            - provider: AI provider
            - model: AI model
            - message_count: Number of exchanges
        show_messages: Whether to show success/error message boxes
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    format = format.lower()
    current_time = datetime.datetime.now()
    
    try:
        if format == 'txt':
            return _export_thread_as_txt(filepath, thread_messages, thread_metadata, current_time, show_messages)
        elif format == 'docx':
            return _export_thread_as_docx(filepath, thread_messages, thread_metadata, current_time, show_messages)
        elif format == 'rtf':
            return _export_thread_as_rtf(filepath, thread_messages, thread_metadata, current_time, show_messages)
        elif format == 'pdf':
            return _export_thread_as_pdf(filepath, thread_messages, thread_metadata, current_time, show_messages)
        else:
            return False, f"Unsupported format: {format}"
    except Exception as e:
        error_msg = f"Export failed: {str(e)}"
        if show_messages:
            from tkinter import messagebox
            messagebox.showerror("Export Error", error_msg)
        return False, error_msg


def _export_thread_as_txt(filepath, messages, metadata, current_time, show_messages) -> Tuple[bool, str]:
    """Export conversation thread as plain text"""
    doc_title = metadata.get('doc_title', 'Unknown Document')
    source_info = metadata.get('source_info', 'N/A')
    published_date = metadata.get('published_date')
    fetched_date = metadata.get('fetched_date', 'N/A')
    provider = metadata.get('provider', 'N/A')
    model = metadata.get('model', 'N/A')
    message_count = metadata.get('message_count', len(messages) // 2)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("CONVERSATION THREAD\n")
        f.write("=" * 80 + "\n\n")
        
        f.write("SOURCE DOCUMENT INFORMATION:\n")
        f.write(f"  Title: {doc_title}\n")
        f.write(f"  Source: {source_info}\n")
        if published_date and published_date != 'N/A':
            f.write(f"  Published: {published_date}\n")
        f.write(f"  Imported: {fetched_date}\n")
        f.write("\n")
        
        f.write("CONVERSATION DETAILS:\n")
        f.write(f"  Date: {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"  Messages: {message_count}\n")
        f.write(f"  Processed By: {provider} / {model}\n")
        f.write("\n" + "=" * 80 + "\n\n")
        
        for idx, msg in enumerate(messages):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            
            approx_time = current_time - datetime.timedelta(
                minutes=(len(messages) - idx) * 2
            )
            timestamp_str = approx_time.strftime("%H:%M:%S")
            
            if role == "user":
                f.write(f"🧑 YOU [{timestamp_str}]\n")
            else:
                f.write(f"🤖 AI [{timestamp_str}]\n")
            f.write("-" * 40 + "\n")
            f.write(content + "\n\n")
    
    if show_messages:
        from tkinter import messagebox
        messagebox.showinfo("Saved", f"✅ Thread saved to:\n{filepath}")
    return True, filepath


def _export_thread_as_docx(filepath, messages, metadata, current_time, show_messages) -> Tuple[bool, str]:
    """Export conversation thread as Word docx with markdown formatting"""
    try:
        from docx import Document
        from docx.shared import Pt, RGBColor
        from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
    except ImportError:
        if show_messages:
            from tkinter import messagebox
            messagebox.showerror("Error", 
                "python-docx library not installed.\n\n"
                "Install with: pip install python-docx")
        return False, "python-docx not installed"
    
    doc_title = metadata.get('doc_title', 'Unknown Document')
    source_info = metadata.get('source_info', 'N/A')
    published_date = metadata.get('published_date')
    fetched_date = metadata.get('fetched_date', 'N/A')
    provider = metadata.get('provider', 'N/A')
    model = metadata.get('model', 'N/A')
    message_count = metadata.get('message_count', len(messages) // 2)
    
    doc = Document()
    
    # Add title
    title = doc.add_heading('Conversation Thread', 0)
    title.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    
    # Add metadata - SOURCE DOCUMENT INFO
    doc.add_heading('Source Document Information', level=2)
    source_para = doc.add_paragraph()
    source_para.add_run("Title: ").bold = True
    source_para.add_run(f"{doc_title}\n")
    source_para.add_run("Source: ").bold = True
    source_para.add_run(f"{source_info}\n")
    if published_date and published_date != 'N/A':
        source_para.add_run("Published: ").bold = True
        source_para.add_run(f"{published_date}\n")
    source_para.add_run("Imported: ").bold = True
    source_para.add_run(f"{fetched_date}\n")
    
    doc.add_paragraph()  # Spacing
    
    # Add metadata - CONVERSATION DETAILS
    doc.add_heading('Conversation Details', level=2)
    meta_para = doc.add_paragraph()
    meta_para.add_run("Date: ").bold = True
    meta_para.add_run(f"{current_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    meta_para.add_run("Messages: ").bold = True
    meta_para.add_run(f"{message_count}\n")
    meta_para.add_run("Processed By: ").bold = True
    meta_para.add_run(f"{provider} / {model}\n")
    
    doc.add_paragraph()  # Spacing
    
    # Add conversation
    for idx, msg in enumerate(messages):
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        
        approx_time = current_time - datetime.timedelta(
            minutes=(len(messages) - idx) * 2
        )
        timestamp_str = approx_time.strftime("%H:%M:%S")
        
        # Add role header
        header_para = doc.add_paragraph()
        if role == "user":
            run = header_para.add_run(f"🧑 YOU [{timestamp_str}]")
            run.font.color.rgb = RGBColor(46, 64, 83)  # Dark blue
        else:
            run = header_para.add_run(f"🤖 AI [{timestamp_str}]")
            run.font.color.rgb = RGBColor(22, 83, 126)  # Blue
        run.bold = True
        run.font.size = Pt(11)
        
        # Add content with markdown formatting
        _add_markdown_content_to_docx(doc, content)
        
        # Add spacing between exchanges
        if idx < len(messages) - 1:
            doc.add_paragraph()
    
    doc.save(filepath)
    
    if show_messages:
        from tkinter import messagebox
        messagebox.showinfo("Saved", f"✅ Thread saved as Word document:\n{filepath}")
    return True, filepath


def _export_thread_as_rtf(filepath, messages, metadata, current_time, show_messages) -> Tuple[bool, str]:
    """Export conversation thread as RTF"""
    doc_title = metadata.get('doc_title', 'Unknown Document')
    source_info = metadata.get('source_info', 'N/A')
    published_date = metadata.get('published_date')
    fetched_date = metadata.get('fetched_date', 'N/A')
    provider = metadata.get('provider', 'N/A')
    model = metadata.get('model', 'N/A')
    message_count = metadata.get('message_count', len(messages) // 2)
    
    try:
        rtf_content = []
        rtf_content.append(r'{\rtf1\ansi\deff0')
        rtf_content.append(r'{\fonttbl{\f0 Times New Roman;}}')
        rtf_content.append(r'\f0\fs24')
        
        # Title
        rtf_content.append(r'{\b\fs32 Conversation Thread}\par')
        rtf_content.append(r'\par')
        
        # Source Document Info
        rtf_content.append(r'{\b\fs28 Source Document Information}\par')
        safe_title = doc_title.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
        rtf_content.append(r'{\b Title: }' + safe_title + r'\par')
        safe_source = source_info.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
        rtf_content.append(r'{\b Source: }' + safe_source + r'\par')
        if published_date and published_date != 'N/A':
            rtf_content.append(r'{\b Published: }' + published_date + r'\par')
        rtf_content.append(r'{\b Imported: }' + fetched_date + r'\par')
        rtf_content.append(r'\par')
        
        # Conversation Details
        rtf_content.append(r'{\b\fs28 Conversation Details}\par')
        rtf_content.append(r'{\b Date: }' + current_time.strftime('%Y-%m-%d %H:%M:%S') + r'\par')
        rtf_content.append(r'{\b Messages: }' + str(message_count) + r'\par')
        rtf_content.append(r'{\b Processed By: }' + f"{provider} / {model}" + r'\par')
        rtf_content.append(r'\par')
        
        # Conversation
        for idx, msg in enumerate(messages):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            
            approx_time = current_time - datetime.timedelta(
                minutes=(len(messages) - idx) * 2
            )
            timestamp_str = approx_time.strftime("%H:%M:%S")
            
            if role == "user":
                rtf_content.append(r'{\b YOU [' + timestamp_str + r']}\par')
            else:
                rtf_content.append(r'{\b AI [' + timestamp_str + r']}\par')
            
            safe_content = content.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
            for line in safe_content.split('\n'):
                rtf_content.append(line + r'\par')
            rtf_content.append(r'\par')
        
        rtf_content.append(r'}')
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(rtf_content))
        
        if show_messages:
            from tkinter import messagebox
            messagebox.showinfo("Saved", f"✅ Thread saved as RTF:\n{filepath}")
        return True, filepath
        
    except Exception as e:
        # Fallback to TXT
        txt_path = filepath.replace('.rtf', '.txt')
        if show_messages:
            from tkinter import messagebox
            messagebox.showerror("RTF Error", f"Failed to create RTF:\n{str(e)}\n\nSaving as TXT instead...")
        return _export_thread_as_txt(txt_path, messages, metadata, current_time, show_messages)


def _export_thread_as_pdf(filepath, messages, metadata, current_time, show_messages) -> Tuple[bool, str]:
    """Export conversation thread as PDF"""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.colors import HexColor
    except ImportError:
        # Fallback to TXT
        txt_path = filepath.replace('.pdf', '.txt')
        if show_messages:
            from tkinter import messagebox
            messagebox.showerror("Error",
                "reportlab library not installed.\n\n"
                "Install with: pip install reportlab\n\n"
                "Falling back to TXT format...")
        return _export_thread_as_txt(txt_path, messages, metadata, current_time, show_messages)
    
    doc_title = metadata.get('doc_title', 'Unknown Document')
    source_info = metadata.get('source_info', 'N/A')
    published_date = metadata.get('published_date')
    fetched_date = metadata.get('fetched_date', 'N/A')
    provider = metadata.get('provider', 'N/A')
    model = metadata.get('model', 'N/A')
    message_count = metadata.get('message_count', len(messages) // 2)
    
    pdf_doc = SimpleDocTemplate(filepath, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=18,
        spaceAfter=20
    )
    header_style = ParagraphStyle(
        'CustomHeader',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=HexColor('#2c3e50')
    )
    user_style = ParagraphStyle(
        'UserStyle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=HexColor('#2E4053'),
        fontName='Helvetica-Bold'
    )
    ai_style = ParagraphStyle(
        'AIStyle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=HexColor('#16537E'),
        fontName='Helvetica-Bold'
    )
    
    # Add title
    story.append(Paragraph("Conversation Thread", title_style))
    story.append(Spacer(1, 12))
    
    # Add metadata
    story.append(Paragraph("Source Document Information", header_style))
    story.append(Paragraph(f"<b>Title:</b> {_escape_pdf_text(doc_title)}", styles['Normal']))
    story.append(Paragraph(f"<b>Source:</b> {_escape_pdf_text(source_info)}", styles['Normal']))
    if published_date and published_date != 'N/A':
        story.append(Paragraph(f"<b>Published:</b> {published_date}", styles['Normal']))
    story.append(Paragraph(f"<b>Imported:</b> {fetched_date}", styles['Normal']))
    story.append(Spacer(1, 12))
    
    story.append(Paragraph("Conversation Details", header_style))
    story.append(Paragraph(
        f"<b>Date:</b> {current_time.strftime('%Y-%m-%d %H:%M:%S')}", 
        styles['Normal']
    ))
    story.append(Paragraph(f"<b>Messages:</b> {message_count}", styles['Normal']))
    story.append(Paragraph(
        f"<b>Processed By:</b> {provider} / {model}", 
        styles['Normal']
    ))
    story.append(Spacer(1, 20))
    
    # Add conversation
    for idx, msg in enumerate(messages):
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        
        approx_time = current_time - datetime.timedelta(
            minutes=(len(messages) - idx) * 2
        )
        timestamp_str = approx_time.strftime("%H:%M:%S")
        
        if role == "user":
            story.append(Paragraph(f"YOU [{timestamp_str}]", user_style))
        else:
            story.append(Paragraph(f"AI [{timestamp_str}]", ai_style))
        
        # Add content with markdown formatting and paragraph preservation
        _split_into_pdf_paragraphs(content, story, styles['Normal'])
        story.append(Spacer(1, 12))
    
    pdf_doc.build(story)
    
    if show_messages:
        from tkinter import messagebox
        messagebox.showinfo("Saved", f"✅ Thread saved as PDF:\n{filepath}")
    return True, filepath


# =============================================================================
# SHARED HELPERS - Markdown processing for Word documents
# =============================================================================

def _add_markdown_content_to_docx(doc, content: str):
    """
    Add markdown-formatted content to a Word document.
    Supports: **bold**, *italic*, # headers, and bullet points.
    Collapses consecutive blank lines to avoid double paragraph markers.
    """
    from docx.shared import Pt
    
    lines = content.split('\n')
    last_was_empty = False
    
    for line in lines:
        # Skip empty lines but track for spacing
        if not line.strip():
            if not last_was_empty:
                last_was_empty = True
            continue
        
        last_was_empty = False
        
        # Headers: # Header or ## Header
        if line.strip().startswith('#'):
            level = 0
            for char in line:
                if char == '#':
                    level += 1
                else:
                    break
            header_text = line.strip('#').strip()
            level = min(level, 4)  # Cap at heading level 4
            doc.add_heading(header_text, level=level)
            continue
        
        # Bullet points: - item or * item
        if line.strip().startswith(('- ', '* ')):
            bullet_text = line.strip()[2:].strip()
            para = doc.add_paragraph(style='List Bullet')
            _add_inline_markdown_to_paragraph(para, bullet_text)
            continue
        
        # Regular paragraph with inline formatting
        para = doc.add_paragraph()
        _add_inline_markdown_to_paragraph(para, line)


def _add_inline_markdown_to_paragraph(paragraph, text: str):
    """
    Add text to a paragraph with inline markdown formatting.
    Supports: **bold** and *italic*
    """
    import re
    
    # Pattern to match **bold** and *italic*
    pattern = r'(\*\*[^*]+\*\*|\*[^*]+\*)'
    
    parts = re.split(pattern, text)
    
    for part in parts:
        if not part:
            continue
        
        if part.startswith('**') and part.endswith('**'):
            # Bold text
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith('*') and part.endswith('*'):
            # Italic text
            run = paragraph.add_run(part[1:-1])
            run.italic = True
        else:
            # Regular text
            paragraph.add_run(part)
