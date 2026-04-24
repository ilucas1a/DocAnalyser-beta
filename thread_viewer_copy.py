"""
thread_viewer_copy.py - Copy & Clipboard Mixin for ThreadViewerWindow

Extracted from thread_viewer.py to improve maintainability.
Handles all copy-to-clipboard operations, HTML generation for formatted copy,
CF_HTML Windows clipboard format, selection operations, and the copy dialog.

All methods access the parent ThreadViewerWindow's state via self.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import re
import datetime


class CopyMixin:
    """
    Mixin providing copy/clipboard operations for ThreadViewerWindow.
    
    Requires the following attributes on self:
        - thread_text: tk.Text widget
        - window: tk.Toplevel
        - current_thread: list of message dicts
        - current_document_text: str
        - source_documents: list of source doc dicts
        - doc_title, source_info, fetched_date, published_date: metadata strings
        - current_mode: 'source' or 'conversation'
        - model_var, provider_var: tk.StringVar
        - _set_status(): status display method
        - _escape_html(): HTML escape (provided by this mixin)
    """

    def _copy_source_only(self, plain_text=False):
        """
        Copy just the source document to clipboard.
        
        Args:
            plain_text: If True, copy as plain text. If False, copy as formatted HTML.
        """
        import sys
        
        if not self.current_document_text:
            self._set_status("⚠️ No source document available")
            return
        
        try:
            if plain_text:
                # Build plain text version with metadata header
                lines = []
                lines.append("SOURCE DOCUMENT INFORMATION:")
                lines.append(f"Title: {self.doc_title}")
                lines.append(f"Source: {self.source_info}")
                if hasattr(self, 'published_date') and self.published_date and self.published_date != 'N/A':
                    lines.append(f"Published: {self.published_date}")
                lines.append(f"Imported: {self.fetched_date}")
                lines.append("")
                lines.append("=" * 60)
                lines.append("")
                lines.append(self.current_document_text)
                
                content = "\n".join(lines)
                self.window.clipboard_clear()
                self.window.clipboard_append(content)
                self._set_status("✅ Source copied to clipboard (plain text)")
            else:
                # Build formatted HTML version
                html_parts = []
                
                # Add metadata header
                html_parts.append(f'<h1 style="color: #2C3E50; font-size: 16pt; text-align: center;">{self._escape_html(self.doc_title)}</h1>')
                html_parts.append('<hr style="border: 1px solid #ccc;">')
                html_parts.append('<p style="font-size: 10pt; color: #555;">')
                html_parts.append(f'<b>Source:</b> {self._escape_html(self.source_info)}<br>')
                if hasattr(self, 'published_date') and self.published_date and self.published_date != 'N/A':
                    html_parts.append(f'<b>Published:</b> {self.published_date}<br>')
                html_parts.append(f'<b>Imported:</b> {self.fetched_date}')
                html_parts.append('</p>')
                html_parts.append('<hr style="border: 1px solid #ccc;">')
                html_parts.append('<br>')
                
                # Add source document text - preserve paragraphs
                source_paragraphs = self.current_document_text.split('\n\n')
                for para in source_paragraphs:
                    if para.strip():
                        html_parts.append(f'<p style="margin: 8pt 0;">{self._escape_html(para.strip())}</p>')
                
                # Wrap in HTML document
                html_body = '\n'.join(html_parts)
                html_doc = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: Calibri, Arial, sans-serif; font-size: 11pt; line-height: 1.5; }}
</style>
</head>
<body>
{html_body}
</body>
</html>'''
                
                # Copy to clipboard based on platform
                if sys.platform == 'win32':
                    success = self._copy_html_to_clipboard_windows(html_doc)
                else:
                    # Fallback for non-Windows
                    self._copy_source_only(plain_text=True)
                    return
                
                if success:
                    self._set_status("✅ Source copied (formatted)! Paste into Word/Outlook.")
                else:
                    # Fallback to plain text
                    self._copy_source_only(plain_text=True)
                    
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Copy Error", f"Failed to copy source:\n{str(e)}")
            # Fallback to plain text
            try:
                if not plain_text:
                    self._copy_source_only(plain_text=True)
            except:
                pass

    def _fix_numbered_lists(self, text: str) -> str:
        """
        Fix markdown-style numbered lists where all items start with '1.'
        Convert them to properly sequential numbers (1, 2, 3, etc.)
        
        Handles the common AI pattern where numbered items have explanation
        paragraphs between them:
            1. **First point**
            The speaker argues that...
            
            1. **Second point**
            Meta-awareness is described as...
        """
        import re
        
        lines = text.split('\n')
        result = []
        list_counter = 0
        
        for line in lines:
            # Check if line starts with a number followed by period and space
            match = re.match(r'^(\s*)(\d+)\.\s+(.*)', line)
            
            if match:
                indent = match.group(1)
                content = match.group(3)
                list_counter += 1
                result.append(f"{indent}{list_counter}. {content}")
            else:
                # Reset counter only on structural breaks: headings, HRs, bullet lists
                stripped = line.strip()
                if (stripped.startswith('## ') or stripped.startswith('### ') or 
                    stripped.startswith('# ') or stripped == '---' or
                    stripped.startswith('- ') or stripped.startswith('* ') or
                    stripped.startswith('===')):
                    list_counter = 0
                # Empty lines and regular paragraphs do NOT reset counter
                # (AI often puts explanations between numbered items)
                result.append(line)
        
        return '\n'.join(result)

    def _get_formatted_thread_text(self) -> str:
        """
        Return thread content with markdown formatting reconstructed from the
        widget's font tags (bold, italic, header, numbered, bullet etc.).

        Uses _reconstruct_markdown_content so that:
          - Bold text becomes **text** (renders in WhatsApp, Discord, Slack etc.)
          - Headings become ## Heading
          - Numbered items keep their 1. 2. 3. sequence
          - Bullets keep their - prefix

        Falls back to plain .get() if reconstruction raises.
        """
        try:
            raw_lines = self.thread_text.get('1.0', tk.END).split('\n')
            content_lines = [(i + 1, line) for i, line in enumerate(raw_lines)]
            return self._reconstruct_markdown_content(content_lines)
        except Exception:
            return self.thread_text.get('1.0', tk.END)

    def _copy_thread(self):
        """Copy entire thread to clipboard, preserving markdown structure."""
        # Build metadata header
        metadata = []
        metadata.append("SOURCE DOCUMENT INFORMATION:")
        metadata.append(f"Title: {self.doc_title}")
        metadata.append(f"Source: {self.source_info}")
        if hasattr(self, 'published_date') and self.published_date and self.published_date != 'N/A':
            metadata.append(f"Published: {self.published_date}")
        metadata.append(f"Imported: {self.fetched_date}")
        metadata.append("")
        metadata.append("=" * 60)
        metadata.append("CONVERSATION THREAD")
        metadata.append("=" * 60)
        metadata.append("")

        header = "\n".join(metadata)

        # Reconstruct markdown from widget tags so bold (**text**), headings
        # (## Heading) and list numbering survive the copy to WhatsApp / other apps.
        thread_content = self._get_formatted_thread_text()

        # Fix numbered lists (convert any residual "1. 1. 1." to "1. 2. 3.")
        thread_content = self._fix_numbered_lists(thread_content)

        full_content = header + "\n" + thread_content

        self.window.clipboard_clear()
        self.window.clipboard_append(full_content)
        self._set_status("✅ Thread copied to clipboard")

    def _copy_thread_formatted(self):
        """
        Copy thread to clipboard as formatted HTML.
        If user made edits, saves them first. Otherwise uses original markdown.
        """
        import sys
        
        try:
            # Save edits if modifications were made (the save function checks edit_modified)
            # If no edits, this returns early and preserves original markdown in self.current_thread
            try:
                if self.current_mode == 'conversation' and self.current_thread:
                    self._save_edits_to_thread()
            except ValueError:
                # User cancelled save dialog
                return
            except Exception as e:
                print(f"⚠️ Error saving edits: {e}")
            
            # Now build HTML from the saved thread (which has markdown)
            html_content = self._thread_to_html()
            
            if not html_content:
                self._set_status("⚠️ No content to copy")
                return
            
            # Copy to clipboard based on platform
            if sys.platform == 'win32':
                success = self._copy_html_to_clipboard_windows(html_content)
            else:
                # Fallback for non-Windows: copy as plain text
                plain_text = self.thread_text.get('1.0', tk.END)
                plain_text = self._fix_numbered_lists(plain_text)
                self.window.clipboard_clear()
                self.window.clipboard_append(plain_text)
                self._set_status("ℹ️ Formatted copy is Windows-only. Plain text copied.")
                return
            
            if success:
                self._set_status("✅ Formatted content copied! Paste into Word/Outlook.")
            else:
                # Fallback to plain text
                plain_text = self.thread_text.get('1.0', tk.END)
                plain_text = self._fix_numbered_lists(plain_text)
                self.window.clipboard_clear()
                self.window.clipboard_append(plain_text)
                self._set_status("⚠️ HTML copy failed. Plain text copied instead.")
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Copy Error", f"Failed to copy formatted content:\n{str(e)}")
            # Fallback to plain text
            try:
                plain_text = self.thread_text.get('1.0', tk.END)
                plain_text = self._fix_numbered_lists(plain_text)
                self.window.clipboard_clear()
                self.window.clipboard_append(plain_text)
                self._set_status("⚠️ Error occurred. Plain text copied instead.")
            except:
                pass

    def _copy_expanded_only(self):
        """
        Copy only the expanded exchanges to clipboard as plain text.
        Collapsed exchanges are completely omitted (no headers, no indicators).
        Perfect for sharing specific exchanges without surrounding context.
        """
        exchanges = self._group_messages_into_exchanges()
        
        if not exchanges:
            self._set_status("⚠️ No exchanges to copy")
            return
        
        # Find which exchanges are expanded
        expanded_indices = [i for i in range(len(exchanges)) 
                          if self.exchange_expanded_state.get(i, True)]
        
        if not expanded_indices:
            self._set_status("⚠️ No exchanges are expanded. Expand the exchanges you want to copy.")
            return
        
        # Build content from expanded exchanges only
        content_parts = []
        
        # Add brief header
        content_parts.append(f"From: {self.doc_title}")
        content_parts.append(f"Source: {self.source_info}")
        content_parts.append("")
        content_parts.append("=" * 60)
        content_parts.append("")
        
        for idx in expanded_indices:
            exchange = exchanges[idx]
            
            # User message
            user_msg = exchange.get('user', {})
            user_content = user_msg.get('content', '')
            content_parts.append("YOU:")
            content_parts.append(user_content)
            content_parts.append("")
            
            # Assistant message
            assistant_msg = exchange.get('assistant', {})
            if assistant_msg:
                assistant_content = assistant_msg.get('content', '')
                provider = assistant_msg.get('provider', 'AI')
                content_parts.append(f"{provider}:")
                content_parts.append(assistant_content)
                content_parts.append("")
            
            # Separator between exchanges (if more than one expanded)
            if idx != expanded_indices[-1]:
                content_parts.append("-" * 40)
                content_parts.append("")
        
        full_content = "\n".join(content_parts)
        
        # Fix numbered lists (convert "1. 1. 1." to "1. 2. 3.")
        full_content = self._fix_numbered_lists(full_content)
        
        self.window.clipboard_clear()
        self.window.clipboard_append(full_content)
        
        count = len(expanded_indices)
        self._set_status(f"✅ Copied {count} expanded exchange{'s' if count != 1 else ''} (plain text)")

    def _copy_expanded_only_formatted(self):
        """
        Copy only the expanded exchanges to clipboard as formatted HTML.
        Collapsed exchanges are completely omitted.
        Uses the same HTML generation as _thread_to_html for consistency.
        """
        import sys
        
        try:
            exchanges = self._group_messages_into_exchanges()
            
            if not exchanges:
                self._set_status("⚠️ No exchanges to copy")
                return
            
            # Find which exchanges are expanded
            expanded_indices = []
            for i in range(len(exchanges)):
                is_expanded = self.exchange_expanded_state.get(i, True)
                if is_expanded:
                    expanded_indices.append(i)
            
            if not expanded_indices:
                self._set_status("⚠️ No exchanges are expanded. Expand the exchanges you want to copy.")
                return
            
            # Build a filtered thread containing only expanded exchanges
            filtered_thread = []
            for idx in expanded_indices:
                exchange = exchanges[idx]
                if 'user' in exchange:
                    filtered_thread.append(exchange['user'])
                if 'assistant' in exchange:
                    filtered_thread.append(exchange['assistant'])
            
            # Now build HTML using same approach as _thread_to_html
            html_parts = []
            
            # Add metadata header (styled <p> for Gmail compatibility)
            html_parts.append(f'<p style="color: #2C3E50; font-size: 16pt; font-weight: bold; text-align: center; margin: 0 0 8pt 0;">{self._escape_html(self.doc_title)}</p>')
            html_parts.append('<p style="border-bottom: 1px solid #ccc; margin: 0 0 8pt 0; padding: 0; line-height: 1px;">&nbsp;</p>')
            html_parts.append('<p style="font-size: 10pt; color: #555; margin: 4pt 0;">')
            html_parts.append(f'<b>Source:</b> {self._escape_html(self.source_info)}<br>')
            if hasattr(self, 'published_date') and self.published_date and self.published_date != 'N/A':
                html_parts.append(f'<b>Published:</b> {self.published_date}<br>')
            html_parts.append(f'<b>Imported:</b> {self.fetched_date}')
            html_parts.append('</p>')
            html_parts.append('<p style="border-bottom: 1px solid #ccc; margin: 0 0 8pt 0; padding: 0; line-height: 1px;">&nbsp;</p>')
            html_parts.append('<br>')
            
            # Process each message in the filtered thread (same as _thread_to_html)
            for msg in filtered_thread:
                role = msg.get('role', '')
                content = msg.get('content', '')
                timestamp = msg.get('timestamp', '')
                
                if role == 'user':
                    time_str = f" [{timestamp}]" if timestamp else ""
                    html_parts.append(f'<p style="color: #2E4053; font-weight: bold; margin-top: 15pt;">🧑 YOU{time_str}</p>')
                    # Convert user content (usually plain text)
                    html_parts.append(f'<p style="margin: 6pt 0;">{self._escape_html(content)}</p>')
                    
                elif role == 'assistant':
                    provider = msg.get('provider', 'AI')
                    model = msg.get('model', '')
                    time_str = f" [{timestamp}]" if timestamp else ""
                    
                    if model and model != provider:
                        label = f"🤖 {provider} ({model}){time_str}"
                    else:
                        label = f"🤖 {provider}{time_str}"
                    
                    html_parts.append(f'<p style="color: #16537E; font-weight: bold; margin-top: 15pt;">{self._escape_html(label)}</p>')
                    
                    # Convert assistant content (has markdown) - use same method as _thread_to_html
                    content_html = self._markdown_to_html_content(content)
                    html_parts.append(content_html)
                    
                    # Add divider (styled <p> for Gmail compatibility)
                    html_parts.append('<p style="border-bottom: 1px solid #ddd; margin: 15pt 0; padding: 0; line-height: 1px;">&nbsp;</p>')
            
            # Wrap in HTML document - inline styles on body, no <style> block (Gmail ignores it)
            html_body = '\n'.join(html_parts)
            html_doc = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
</head>
<body style="font-family: Calibri, Arial, sans-serif; font-size: 11pt; line-height: 1.5;">
{html_body}
</body>
</html>'''
            
            # Copy to clipboard based on platform
            if sys.platform == 'win32':
                success = self._copy_html_to_clipboard_windows(html_doc)
            else:
                # Fallback for non-Windows
                self._copy_expanded_only()  # Use plain text version
                return
            
            if success:
                count = len(expanded_indices)
                self._set_status(f"✅ Copied {count} expanded exchange{'s' if count != 1 else ''} (formatted)")
            else:
                # Fallback to plain text
                self._copy_expanded_only()
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Copy Error", f"Failed to copy formatted content:\n{str(e)}")
            # Fallback to plain text
            try:
                self._copy_expanded_only()
            except:
                pass

    def _copy_complete(self, plain_text=False):
        """
        Copy the source document AND the conversation thread to clipboard.
        
        Args:
            plain_text: If True, copy as plain text. If False, copy as formatted HTML.
        """
        import sys
        
        try:
            if not self.current_document_text:
                self._set_status("⚠️ No source document available")
                return
            
            if plain_text:
                # Build plain text version
                lines = []
                
                # Add metadata header
                lines.append("=" * 60)
                lines.append(f"TITLE: {self.doc_title}")
                lines.append(f"SOURCE: {self.source_info}")
                if hasattr(self, 'published_date') and self.published_date and self.published_date != 'N/A':
                    lines.append(f"PUBLISHED: {self.published_date}")
                lines.append(f"IMPORTED: {self.fetched_date}")
                lines.append("=" * 60)
                lines.append("")
                
                # Add source document
                lines.append("─" * 40)
                lines.append("SOURCE DOCUMENT")
                lines.append("─" * 40)
                lines.append("")
                lines.append(self.current_document_text)
                lines.append("")
                
                # Add conversation thread
                lines.append("─" * 40)
                lines.append("CONVERSATION THREAD")
                lines.append("─" * 40)
                lines.append("")
                
                # Add each message
                for msg in self.current_thread:
                    role = msg.get('role', '')
                    content = msg.get('content', '')
                    timestamp = msg.get('timestamp', '')
                    
                    if role == 'user':
                        time_str = f" [{timestamp}]" if timestamp else ""
                        lines.append(f"🧑 YOU{time_str}")
                        lines.append(content)
                        lines.append("")
                    elif role == 'assistant':
                        provider = msg.get('provider', 'AI')
                        model = msg.get('model', '')
                        time_str = f" [{timestamp}]" if timestamp else ""
                        
                        if model and model != provider:
                            label = f"🤖 {provider} ({model}){time_str}"
                        else:
                            label = f"🤖 {provider}{time_str}"
                        
                        lines.append(label)
                        lines.append(content)
                        lines.append("-" * 30)
                        lines.append("")
                
                # Copy to clipboard
                text = "\n".join(lines)
                # Fix numbered lists (convert "1. 1. 1." to "1. 2. 3.")
                text = self._fix_numbered_lists(text)
                self.window.clipboard_clear()
                self.window.clipboard_append(text)
                self._set_status("✅ Complete content copied (plain text)")
                
            else:
                # Build formatted HTML version
                html_parts = []
                
                # Add metadata header
                html_parts.append(f'<h1 style="color: #2C3E50; font-size: 16pt; text-align: center;">{self._escape_html(self.doc_title)}</h1>')
                html_parts.append('<hr style="border: 1px solid #ccc;">')
                html_parts.append('<p style="font-size: 10pt; color: #555;">')
                html_parts.append(f'<b>Source:</b> {self._escape_html(self.source_info)}<br>')
                if hasattr(self, 'published_date') and self.published_date and self.published_date != 'N/A':
                    html_parts.append(f'<b>Published:</b> {self.published_date}<br>')
                html_parts.append(f'<b>Imported:</b> {self.fetched_date}')
                html_parts.append('</p>')
                html_parts.append('<hr style="border: 1px solid #ccc;">')
                html_parts.append('<br>')
                
                # Add source document section
                html_parts.append('<h2 style="color: #34495E; font-size: 14pt; background-color: #EBF5FB; padding: 8pt; border-left: 4px solid #3498DB;">📄 Source Document</h2>')
                # Convert source document text - escape HTML and preserve paragraphs
                source_paragraphs = self.current_document_text.split('\n\n')
                for para in source_paragraphs:
                    if para.strip():
                        html_parts.append(f'<p style="margin: 8pt 0;">{self._escape_html(para.strip())}</p>')
                
                html_parts.append('<br>')
                html_parts.append('<hr style="border: 2px solid #3498DB; margin: 20pt 0;">')
                html_parts.append('<br>')
                
                # Add conversation thread section
                html_parts.append('<h2 style="color: #34495E; font-size: 14pt; background-color: #E8F8F5; padding: 8pt; border-left: 4px solid #1ABC9C;">💬 Conversation Thread</h2>')
                html_parts.append('<br>')
                
                # Add each message
                for msg in self.current_thread:
                    role = msg.get('role', '')
                    content = msg.get('content', '')
                    timestamp = msg.get('timestamp', '')
                    
                    if role == 'user':
                        time_str = f" [{timestamp}]" if timestamp else ""
                        html_parts.append(f'<p style="color: #2E4053; font-weight: bold; margin-top: 15pt;">🧑 YOU{time_str}</p>')
                        html_parts.append(f'<p style="margin: 6pt 0;">{self._escape_html(content)}</p>')
                        
                    elif role == 'assistant':
                        provider = msg.get('provider', 'AI')
                        model = msg.get('model', '')
                        time_str = f" [{timestamp}]" if timestamp else ""
                        
                        if model and model != provider:
                            label = f"🤖 {provider} ({model}){time_str}"
                        else:
                            label = f"🤖 {provider}{time_str}"
                        
                        html_parts.append(f'<p style="color: #16537E; font-weight: bold; margin-top: 15pt;">{self._escape_html(label)}</p>')
                        
                        # Convert assistant content (has markdown)
                        content_html = self._markdown_to_html_content(content)
                        html_parts.append(content_html)
                        
                        # Add divider
                        html_parts.append('<hr style="border: 1px solid #ddd; margin: 15pt 0;">')
                
                # Wrap in HTML document
                html_body = '\n'.join(html_parts)
                html_doc = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: Calibri, Arial, sans-serif; font-size: 11pt; line-height: 1.5; }}
h1, h2, h3 {{ font-weight: bold; }}
b, strong {{ font-weight: bold; }}
i, em {{ font-style: italic; }}
ul, ol {{ margin: 6pt 0; padding-left: 25pt; }}
li {{ margin: 4pt 0; }}
</style>
</head>
<body>
{html_body}
</body>
</html>'''
                
                # Copy to clipboard based on platform
                if sys.platform == 'win32':
                    success = self._copy_html_to_clipboard_windows(html_doc)
                else:
                    # Fallback for non-Windows
                    self._copy_complete(plain_text=True)
                    return
                
                if success:
                    self._set_status("✅ Complete content copied (formatted)! Paste into Word/Outlook.")
                else:
                    # Fallback to plain text
                    self._copy_complete(plain_text=True)
                    
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Copy Error", f"Failed to copy content:\n{str(e)}")
            # Fallback to plain text
            try:
                if not plain_text:
                    self._copy_complete(plain_text=True)
            except:
                pass

    def _thread_to_html(self) -> str:
        """
        Convert the current thread (with markdown) to HTML.
        Uses inline styles throughout for Gmail compatibility.

        Phase 1a of the export redesign:
          - Header comes from MetadataBlock (single source of truth for the
            metadata panel; renders Source(s) / URL / Published / Imported /
            AI in one place for both per-item docs and digests).
          - The opening user prompt (message index 0, role=user) is
            dropped.  For a briefing or digest the AI response IS the
            deliverable; echoing the prompt that produced it only adds
            noise to the copy.
          - The first AI response is rendered without the "🤖 AI" avatar
            label because its own title / headings already demarcate it.
          - Any follow-up user / AI turns keep their avatar labels so a
            reader can tell turns apart if the thread has had a
            conversation with it.
        """
        from thread_viewer_metadata import MetadataBlock

        html_parts: list = []

        # ── Metadata header ──────────────────────────────────────────────
        # Pull the full document dict so MetadataBlock can read metadata
        # fields (url, interviewee, ai_provider, etc.) that are not on
        # self as flat strings.  Fall back to self.* when the dict is
        # unavailable (standalone conversations, attachments-only mode).
        doc = None
        try:
            if getattr(self, "current_document_id", None):
                from document_library import get_document_by_id
                doc = get_document_by_id(self.current_document_id)
        except Exception:
            doc = None

        provider = self.provider_var.get() if getattr(self, "provider_var", None) else ""
        model    = self.model_var.get()    if getattr(self, "model_var",    None) else ""

        block = MetadataBlock.from_document(
            doc,
            fallback_provider   = provider,
            fallback_model      = model,
            fallback_title      = getattr(self, "doc_title",    "") or "",
            fallback_source_name= getattr(self, "source_info",  "") or "",
        )
        html_parts.extend(block.to_html_parts(self._escape_html))
        html_parts.append("<br>")

        # ── Message filtering rules ──────────────────────────────────────
        # If the thread opens with a user message, that's the prompt that
        # produced the first AI response - strip it from the export.  The
        # first AI turn then renders bare (no avatar), since the AI's own
        # title / headings already demarcate it.  All subsequent turns
        # render with avatars so follow-up exchanges remain readable.
        skip_first_user = bool(
            self.current_thread
            and self.current_thread[0].get("role") == "user"
        )
        first_assistant_idx = None
        for i, m in enumerate(self.current_thread):
            if skip_first_user and i == 0:
                continue
            if m.get("role") == "assistant":
                first_assistant_idx = i
                break

        # ── Render messages ──────────────────────────────────────────────
        for i, msg in enumerate(self.current_thread):
            role      = msg.get("role", "")
            content   = msg.get("content", "")
            timestamp = msg.get("timestamp", "")

            if skip_first_user and i == 0:
                continue

            if role == "user":
                # Follow-up user turn - keep the label so the reader can
                # tell the exchange apart from surrounding AI content.
                time_str = f" [{timestamp}]" if timestamp else ""
                html_parts.append(
                    '<p style="color: #2E4053; font-weight: bold; margin-top: 15pt;">'
                    f'🧑 YOU{time_str}</p>'
                )
                html_parts.append(
                    f'<p style="margin: 6pt 0;">{self._escape_html(content)}</p>'
                )

            elif role == "assistant":
                is_first_ai = (i == first_assistant_idx)

                if not is_first_ai:
                    ai_provider = msg.get("provider", "AI")
                    ai_model    = msg.get("model", "")
                    time_str    = f" [{timestamp}]" if timestamp else ""
                    if ai_model and ai_model != ai_provider:
                        label = f"🤖 {ai_provider} ({ai_model}){time_str}"
                    else:
                        label = f"🤖 {ai_provider}{time_str}"
                    html_parts.append(
                        '<p style="color: #16537E; font-weight: bold; margin-top: 15pt;">'
                        f'{self._escape_html(label)}</p>'
                    )

                # Normalise numbered lists before markdown-to-HTML.  The AI
                # commonly emits "1." for every item in a run, and the
                # renderer doesn't always cope when a run is interrupted
                # (e.g. by block quotes, which are heavily used in
                # subscription summaries that follow a "numbered point +
                # quotation" pattern).  Every other copy path in this file
                # calls _fix_numbered_lists too.
                normalised   = self._fix_numbered_lists(content)
                content_html = self._markdown_to_html_content(normalised)
                html_parts.append(content_html)

                # Divider after each AI turn.  For the first AI response
                # this separates the briefing from any follow-up; for
                # later AI turns it separates the exchange that follows.
                html_parts.append(
                    '<p style="border-bottom: 1px solid #ddd; margin: 15pt 0; '
                    'padding: 0; line-height: 1px;">&nbsp;</p>'
                )

        # Wrap in HTML document - inline styles on body, no <style> block
        # (Gmail ignores <style> blocks in pasted HTML).
        html_body = "\n".join(html_parts)
        html_doc  = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
</head>
<body style="font-family: Calibri, Arial, sans-serif; font-size: 11pt; line-height: 1.5;">
{html_body}
</body>
</html>'''

        return html_doc

    def _markdown_to_html_content(self, markdown_text: str) -> str:
        """
        Convert markdown text to HTML.
        Handles: **bold**, *italic*, ## headings, - bullets, numbered lists

        Layout note: heading paragraphs use a small (2pt) bottom margin so that
        the heading sits compactly above its body text rather than leaving an
        obvious gap. The top margin is kept larger (12pt / 10pt) to separate
        sections visually. This mirrors the compaction applied to the WhatsApp
        converter (no blank line after headings).
        """
        if not markdown_text:
            return ""
        
        lines = markdown_text.split('\n')
        html_parts = []
        in_list = False
        list_type = None
        list_counter = 0       # Current position in numbered list
        saved_ol_counter = 0   # Saved counter when bullet sub-list interrupts a numbered list
        
        for line in lines:
            stripped = line.strip()
            
            # Empty line - close bullet lists but preserve numbered list state
            # (AI output often has empty lines between numbered items)
            if not stripped:
                if in_list and list_type == 'ul':
                    html_parts.append('</ul>')
                    in_list = False
                    list_type = None
                # Don't reset ol_paragraphs counter on empty lines - only on actual content change
                continue
            
            # Horizontal rule (styled <p> instead of <hr> for Gmail)
            if stripped == '---':
                if in_list:
                    html_parts.append(f'</{list_type}>')
                    in_list = False
                list_type = None
                list_counter = 0
                saved_ol_counter = 0
                html_parts.append('<p style="border-bottom: 1px solid #ddd; margin: 8pt 0; padding: 0; line-height: 1px;">&nbsp;</p>')
                continue
            
            # Heading 2: ## Title (styled <p> instead of <h2> for Gmail)
            # Tight bottom margin (2pt) so the following paragraph sits close.
            # Phase 1c: a Pandoc-style {#anchor-id} is stripped from the
            # visible text and turned into id="anchor-id" on the paragraph
            # so internal [text](#anchor-id) links work.
            # ── Phase 1c fix1 marker ──────────────────────────────────
            # The regex is no longer anchored to end-of-line, so it also
            # catches headings whose {#id} is followed by trailing markup
            # like `## Sources {#sources} [[Back](#introduction)]`.
            if stripped.startswith('## '):
                if in_list:
                    html_parts.append(f'</{list_type}>')
                    in_list = False
                list_type = None
                list_counter = 0
                saved_ol_counter = 0
                raw = stripped[3:]
                m_anchor = re.search(r'\s*\{#([^}]+)\}\s*', raw)
                anchor_attr = ''
                if m_anchor:
                    anchor_attr = f' id="{m_anchor.group(1)}"'
                    raw = (raw[:m_anchor.start()] + ' ' + raw[m_anchor.end():]).strip()
                text = self._convert_inline_markdown(raw)
                html_parts.append(f'<p{anchor_attr} style="color: #2C3E50; font-size: 13pt; font-weight: bold; margin: 12pt 0 2pt 0;">{text}</p>')
                continue
            
            # Heading 3: ### Title (styled <p> instead of <h3> for Gmail)
            # Tight bottom margin (2pt) so the following paragraph sits close.
            # Phase 1c / fix1: a Pandoc-style {#anchor-id} anywhere in the
            # heading text is stripped and turned into id="anchor-id" on
            # the paragraph so internal [text](#anchor-id) links work.
            if stripped.startswith('### '):
                if in_list:
                    html_parts.append(f'</{list_type}>')
                    in_list = False
                list_type = None
                list_counter = 0
                saved_ol_counter = 0
                raw = stripped[4:]
                m_anchor = re.search(r'\s*\{#([^}]+)\}\s*', raw)
                anchor_attr = ''
                if m_anchor:
                    anchor_attr = f' id="{m_anchor.group(1)}"'
                    raw = (raw[:m_anchor.start()] + ' ' + raw[m_anchor.end():]).strip()
                text = self._convert_inline_markdown(raw)
                html_parts.append(f'<p{anchor_attr} style="color: #34495E; font-size: 12pt; font-weight: bold; margin: 10pt 0 2pt 0;">{text}</p>')
                continue
            
            # Bullet list: - item or * item
            if stripped.startswith('- ') or stripped.startswith('* '):
                if not in_list or list_type != 'ul':
                    if in_list:
                        # If we're interrupting a numbered list with bullets, save the counter
                        # so it continues correctly when the numbered list resumes.
                        if list_type == 'ol_paragraphs':
                            saved_ol_counter = list_counter
                        html_parts.append(f'</{list_type}>')
                    html_parts.append('<ul>')
                    in_list = True
                    list_type = 'ul'
                text = self._convert_inline_markdown(stripped[2:])
                html_parts.append(f'<li>{text}</li>')
                continue

            # Numbered list: 1. item
            # Use explicit numbers in paragraphs for better Gmail compatibility
            if re.match(r'^\d+\.\s+', stripped):
                # Close any bullet list if open
                if in_list and list_type == 'ul':
                    html_parts.append('</ul>')
                    in_list = False
                    list_type = None
                # Track numbered list counter (but don't use <ol> tags).
                # If transitioning from a bullet sub-list back to a numbered list,
                # restore the saved counter so numbering continues from where it left off.
                if list_type != 'ol_paragraphs':
                    list_type = 'ol_paragraphs'
                    list_counter = saved_ol_counter  # Restore (0 if truly new list)
                    saved_ol_counter = 0
                list_counter += 1
                text = self._convert_inline_markdown(re.sub(r'^\d+\.\s+', '', stripped))
                # Use paragraph with explicit number instead of <li> for Gmail compatibility
                html_parts.append(f'<p style="margin: 3pt 0 3pt 20pt;">{list_counter}. {text}</p>')
                continue
            
            # Block quote: > text
            if stripped.startswith('> '):
                # Block quotes between numbered items are common (the AI often
                # follows a numbered point with a quoted excerpt). Treat the
                # quote like an interruption that saves the counter, not a
                # structural break that resets it. Without this save, the
                # next numbered item restarts at 1 — visible as a bug in
                # email-formatted copies of subscription summaries that
                # follow a "numbered point + quotation" pattern.
                if in_list:
                    if list_type == 'ol_paragraphs':
                        saved_ol_counter = list_counter
                    html_parts.append(f'</{list_type}>')
                    in_list = False
                if list_type == 'ol_paragraphs':
                    saved_ol_counter = list_counter
                list_type = None
                # Do NOT reset list_counter — it's preserved in saved_ol_counter
                # and will be restored when the numbered list resumes.
                text = self._convert_inline_markdown(stripped[2:])
                html_parts.append(f'<blockquote style="margin: 6pt 0 6pt 20pt; padding-left: 10pt; border-left: 3px solid #ccc; color: #555; font-style: italic;">{text}</blockquote>')
                continue
            
            # Regular paragraph
            if in_list:
                html_parts.append(f'</{list_type}>')
                in_list = False
            # Only reset numbered list counter on structural breaks (headings, HR, etc.)
            # Regular paragraphs between numbered items should NOT reset the counter
            # because AI often puts explanation paragraphs between numbered points
            if list_type == 'ul':
                list_type = None
            # Keep list_type and list_counter alive for ol_paragraphs
            
            text = self._convert_inline_markdown(stripped)
            html_parts.append(f'<p style="margin: 6pt 0;">{text}</p>')
        
        # Close any remaining list
        if in_list:
            html_parts.append(f'</{list_type}>')
        
        return '\n'.join(html_parts)

    def _convert_inline_markdown(self, text: str) -> str:
        """Convert inline markdown (**bold**, *italic*, [text](url) links) to HTML.

        # ── Phase 1c: internal link support ─────────────────────────────
        The [text](url) pass was added in Phase 1c so that internal
        anchor links inside digests — e.g. `[Detail](#point-1)` and
        `[Back](#key-points)` — become clickable <a href> elements in
        the HTML copy.  Non-greedy brackets handle the [[Detail](#...)]
        double-bracket pattern by matching only the inner [text](url)
        pair and leaving the outer literal brackets alone.
        """
        if not text:
            return ""
        
        # Escape HTML first
        text = self._escape_html(text)

        # Convert [text](url) markdown links to <a href="url">text</a>.
        # Runs before bold/italic so that **bold** or *italic* inside
        # the link text still gets converted by the substitutions below.
        # The text class excludes BOTH '[' and ']' so a wrapping
        # [[Detail](#point-1)] pattern matches only the inner pair and
        # leaves the outer literal brackets alone.
        text = re.sub(
            r'\[([^\[\]]+)\]\(([^)]+)\)',
            lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>',
            text,
        )

        # Convert **bold** to <b>bold</b>
        text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
        
        # Convert *italic* to <i>italic</i>
        text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', text)
        
        return text

    def _text_widget_to_html(self) -> str:
        """
        Convert the Text widget content to HTML, preserving visual formatting.
        Reads the actual tags applied to text ranges in the widget.
        """
        # Get all content
        content = self.thread_text.get('1.0', 'end-1c')
        
        # Build HTML by scanning through the text and checking tags at each position
        html_parts = []
        
        # Add metadata header
        html_parts.append(f'<h1 style="color: #2C3E50; font-size: 16pt; text-align: center;">{self._escape_html(self.doc_title)}</h1>')
        html_parts.append('<hr style="border: 1px solid #ccc;">')
        html_parts.append('<p style="font-size: 10pt; color: #555;">')
        html_parts.append(f'<b>Source:</b> {self._escape_html(self.source_info)}<br>')
        if hasattr(self, 'published_date') and self.published_date and self.published_date != 'N/A':
            html_parts.append(f'<b>Published:</b> {self.published_date}<br>')
        html_parts.append(f'<b>Imported:</b> {self.fetched_date}')
        html_parts.append('</p>')
        html_parts.append('<hr style="border: 1px solid #ccc;">')
        html_parts.append('<br>')
        
        # Process text line by line to handle block-level formatting
        lines = content.split('\n')
        line_num = 1
        
        for line in lines:
            if not line:
                html_parts.append('<p>&nbsp;</p>')
                line_num += 1
                continue
            
            # Get the start index for this line
            line_start = f"{line_num}.0"
            
            # Check what tags are at the start of the line for block-level formatting
            tags_at_start = self.thread_text.tag_names(line_start)
            
            # Determine block-level style
            is_header = 'header' in tags_at_start
            is_user = 'user' in tags_at_start
            is_assistant = 'assistant' in tags_at_start
            is_divider = 'divider' in tags_at_start
            is_bullet = 'bullet' in tags_at_start
            is_exchange_header = 'exchange_header' in tags_at_start
            is_source_header = 'source_header' in tags_at_start
            
            # Handle divider lines
            if is_divider or line.strip().startswith('─' * 10):
                html_parts.append('<hr style="border: 1px solid #ddd; margin: 10pt 0;">')
                line_num += 1
                continue
            
            # Handle exchange/source headers (clickable in viewer)
            if is_exchange_header or is_source_header:
                bg_color = '#d4e6f1' if is_source_header else '#e8f4f8'
                html_parts.append(f'<p style="background-color: {bg_color}; padding: 5pt; font-weight: bold; color: #1a5276;">{self._escape_html(line)}</p>')
                line_num += 1
                continue
            
            # Handle user/assistant markers
            if is_user:
                html_parts.append(f'<p style="color: #2E4053; font-weight: bold; margin-top: 12pt;">{self._escape_html(line)}</p>')
                line_num += 1
                continue
            
            if is_assistant:
                html_parts.append(f'<p style="color: #16537E; font-weight: bold; margin-top: 12pt;">{self._escape_html(line)}</p>')
                line_num += 1
                continue
            
            # Handle headers
            if is_header:
                html_parts.append(f'<h2 style="color: #2c3e50; font-size: 13pt; margin: 12pt 0 6pt 0;">{self._escape_html(line)}</h2>')
                line_num += 1
                continue
            
            # Handle bullets
            if is_bullet or line.strip().startswith('•'):
                bullet_text = line.strip()
                if bullet_text.startswith('•'):
                    bullet_text = bullet_text[1:].strip()
                html_parts.append(f'<li style="margin: 3pt 0;">{self._process_inline_formatting(line_num, bullet_text)}</li>')
                line_num += 1
                continue
            
            # Regular paragraph - process inline formatting
            formatted_line = self._process_inline_formatting(line_num, line)
            html_parts.append(f'<p style="margin: 6pt 0;">{formatted_line}</p>')
            line_num += 1
        
        # Wrap in HTML document
        html_body = '\n'.join(html_parts)
        html_doc = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: Calibri, Arial, sans-serif; font-size: 11pt; line-height: 1.4; }}
h1, h2, h3 {{ font-weight: bold; }}
b, strong {{ font-weight: bold; }}
i, em {{ font-style: italic; }}
li {{ margin-left: 20pt; }}
</style>
</head>
<body>
{html_body}
</body>
</html>'''
        
        return html_doc

    def _process_inline_formatting(self, line_num: int, line_text: str) -> str:
        """
        Process inline formatting (bold, italic) for a line by checking tags at each character.
        Returns HTML string with <b> and <i> tags.
        """
        if not line_text:
            return ""
        
        result = []
        current_bold = False
        current_italic = False
        current_text = []
        
        for col, char in enumerate(line_text):
            pos = f"{line_num}.{col}"
            try:
                tags = self.thread_text.tag_names(pos)
            except:
                tags = ()
            
            is_bold = 'bold' in tags or 'header' in tags or 'user' in tags or 'assistant' in tags
            is_italic = 'italic' in tags
            
            # Check if formatting changed
            if is_bold != current_bold or is_italic != current_italic:
                # Flush current text with previous formatting
                if current_text:
                    text = self._escape_html(''.join(current_text))
                    if current_bold and current_italic:
                        result.append(f'<b><i>{text}</i></b>')
                    elif current_bold:
                        result.append(f'<b>{text}</b>')
                    elif current_italic:
                        result.append(f'<i>{text}</i>')
                    else:
                        result.append(text)
                    current_text = []
                
                current_bold = is_bold
                current_italic = is_italic
            
            current_text.append(char)
        
        # Flush remaining text
        if current_text:
            text = self._escape_html(''.join(current_text))
            if current_bold and current_italic:
                result.append(f'<b><i>{text}</i></b>')
            elif current_bold:
                result.append(f'<b>{text}</b>')
            elif current_italic:
                result.append(f'<i>{text}</i>')
            else:
                result.append(text)
        
        return ''.join(result)

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        if not text:
            return ""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;'))

    def _get_thread_content_with_markdown(self) -> str:
        """
        Get thread content, reconstructing markdown from the stored thread data.
        This ensures we have the original markdown formatting, not the display text.
        """
        lines = []
        
        # Add metadata header
        lines.append(f"**{self.doc_title}**")
        lines.append("")
        lines.append(f"**Source:** {self.source_info}")
        if hasattr(self, 'published_date') and self.published_date and self.published_date != 'N/A':
            lines.append(f"**Published:** {self.published_date}")
        lines.append(f"**Imported:** {self.fetched_date}")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # Add conversation exchanges from stored thread (preserves original markdown)
        for msg in self.current_thread:
            role = msg.get('role', '')
            content = msg.get('content', '')
            timestamp = msg.get('timestamp', '')
            
            if role == 'user':
                time_str = f" [{timestamp}]" if timestamp else ""
                lines.append(f"**🧑 YOU{time_str}**")
                lines.append("")
                lines.append(content)
                lines.append("")
            elif role == 'assistant':
                provider = msg.get('provider', 'AI')
                model = msg.get('model', '')
                time_str = f" [{timestamp}]" if timestamp else ""
                
                if model and model != provider:
                    label = f"**🤖 {provider} ({model}){time_str}**"
                else:
                    label = f"**🤖 {provider}{time_str}**"
                
                lines.append(label)
                lines.append("")
                lines.append(content)
                lines.append("")
                lines.append("---")
                lines.append("")
        
        return "\n".join(lines)

    def _markdown_to_html(self, markdown_text: str) -> str:
        """
        Convert markdown text to HTML for clipboard.
        Handles: **bold**, *italic*, ## headings, - bullets, numbered lists, --- hr

        Layout note: heading tags use a small (2pt) bottom margin so the body
        text sits close below. Matches the compaction applied in
        _markdown_to_html_content.
        """
        lines = markdown_text.split('\n')
        html_lines = []
        in_list = False
        list_type = None  # 'ul' or 'ol'
        
        for line in lines:
            stripped = line.strip()
            
            # Empty line - close any open list
            if not stripped:
                if in_list:
                    html_lines.append(f'</{list_type}>')
                    in_list = False
                    list_type = None
                html_lines.append('<p>&nbsp;</p>')
                continue
            
            # Horizontal rule
            if stripped == '---':
                if in_list:
                    html_lines.append(f'</{list_type}>')
                    in_list = False
                    list_type = None
                html_lines.append('<hr style="border: 1px solid #ccc;">')
                continue
            
            # Heading 2: ## Title
            if stripped.startswith('## '):
                if in_list:
                    html_lines.append(f'</{list_type}>')
                    in_list = False
                    list_type = None
                text = self._inline_markdown_to_html(stripped[3:])
                html_lines.append(f'<h2 style="color: #2C3E50; font-size: 16pt; margin: 12pt 0 2pt 0;">{text}</h2>')
                continue
            
            # Heading 3: ### Title
            if stripped.startswith('### '):
                if in_list:
                    html_lines.append(f'</{list_type}>')
                    in_list = False
                    list_type = None
                text = self._inline_markdown_to_html(stripped[4:])
                html_lines.append(f'<h3 style="color: #34495E; font-size: 13pt; margin: 10pt 0 2pt 0;">{text}</h3>')
                continue
            
            # Bullet list: - item or * item
            if stripped.startswith('- ') or stripped.startswith('* '):
                if not in_list or list_type != 'ul':
                    if in_list:
                        html_lines.append(f'</{list_type}>')
                    html_lines.append('<ul style="margin: 6pt 0; padding-left: 20pt;">')
                    in_list = True
                    list_type = 'ul'
                text = self._inline_markdown_to_html(stripped[2:])
                html_lines.append(f'<li style="margin: 3pt 0;">{text}</li>')
                continue
            
            # Numbered list: 1. item
            if re.match(r'^\d+\.\s+', stripped):
                if not in_list or list_type != 'ol':
                    if in_list:
                        html_lines.append(f'</{list_type}>')
                    html_lines.append('<ol style="margin: 6pt 0; padding-left: 20pt;">')
                    in_list = True
                    list_type = 'ol'
                text = self._inline_markdown_to_html(re.sub(r'^\d+\.\s+', '', stripped))
                html_lines.append(f'<li style="margin: 3pt 0;">{text}</li>')
                continue
            
            # Block quote: > text
            if stripped.startswith('> '):
                if in_list:
                    html_lines.append(f'</{list_type}>')
                    in_list = False
                    list_type = None
                text = self._inline_markdown_to_html(stripped[2:])
                html_lines.append(f'<blockquote style="margin: 6pt 0 6pt 20pt; padding-left: 10pt; border-left: 3px solid #ccc; color: #555; font-style: italic;">{text}</blockquote>')
                continue
            
            # Regular paragraph - close any open list first
            if in_list:
                html_lines.append(f'</{list_type}>')
                in_list = False
                list_type = None
            
            text = self._inline_markdown_to_html(stripped)
            html_lines.append(f'<p style="margin: 6pt 0;">{text}</p>')
        
        # Close any remaining open list
        if in_list:
            html_lines.append(f'</{list_type}>')
        
        # Wrap in basic HTML structure
        html_body = '\n'.join(html_lines)
        html_doc = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: Calibri, Arial, sans-serif; font-size: 11pt; line-height: 1.4; }}
h2 {{ font-weight: bold; }}
h3 {{ font-weight: bold; }}
b, strong {{ font-weight: bold; }}
i, em {{ font-style: italic; }}
</style>
</head>
<body>
{html_body}
</body>
</html>'''
        
        return html_doc

    def _inline_markdown_to_html(self, text: str) -> str:
        """Convert inline markdown (**bold**, *italic*) to HTML tags."""
        # Escape HTML special characters first
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        
        # Convert **bold** to <b>bold</b>
        text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
        
        # Convert *italic* to <i>italic</i> (but not ** which is bold)
        text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', text)
        
        return text

    def _copy_html_to_clipboard_windows(self, html_content: str) -> bool:
        """
        Copy HTML content to Windows clipboard in CF_HTML format.
        This allows pasting with formatting into Word, Outlook, etc.
        """
        # First try pywin32 if available (most reliable)
        try:
            import win32clipboard
            import win32con
            
            
            # Build CF_HTML data
            cf_html = self._build_cf_html(html_content)
            
            # Register HTML format
            CF_HTML = win32clipboard.RegisterClipboardFormat("HTML Format")
            
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                
                # Set HTML format - pywin32 expects bytes for custom formats
                cf_html_bytes = cf_html.encode('utf-8')
                win32clipboard.SetClipboardData(CF_HTML, cf_html_bytes)
                
                # Also set plain text as fallback
                plain_text = self._html_to_plain_text(html_content)
                win32clipboard.SetClipboardText(plain_text, win32con.CF_UNICODETEXT)
                
                return True
            finally:
                win32clipboard.CloseClipboard()
                
        except ImportError:
            pass
        except Exception as e:
            import traceback
            traceback.print_exc()
        
        # Fallback: use ctypes directly
        try:
            import ctypes
            
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            
            # Register HTML clipboard format
            CF_HTML = user32.RegisterClipboardFormatW("HTML Format")
            CF_UNICODETEXT = 13
            GMEM_MOVEABLE = 0x0002
            
            
            # Build CF_HTML data
            cf_html = self._build_cf_html(html_content)
            cf_html_bytes = cf_html.encode('utf-8') + b'\x00'
            
            
            # Open clipboard
            if not user32.OpenClipboard(None):
                return False
            
            try:
                user32.EmptyClipboard()
                
                # Allocate and set HTML data
                h_html = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(cf_html_bytes))
                if h_html:
                    p_html = kernel32.GlobalLock(h_html)
                    if p_html:
                        ctypes.memmove(p_html, cf_html_bytes, len(cf_html_bytes))
                        kernel32.GlobalUnlock(h_html)
                        result = user32.SetClipboardData(CF_HTML, h_html)
                        if not result:
                            kernel32.GlobalFree(h_html)
                    else:
                        pass
                else:
                    pass
                
                # Also set plain text
                plain_text = self._html_to_plain_text(html_content)
                plain_bytes = (plain_text + '\x00').encode('utf-16-le')
                
                h_text = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(plain_bytes))
                if h_text:
                    p_text = kernel32.GlobalLock(h_text)
                    if p_text:
                        ctypes.memmove(p_text, plain_bytes, len(plain_bytes))
                        kernel32.GlobalUnlock(h_text)
                        user32.SetClipboardData(CF_UNICODETEXT, h_text)
                
                return True
                
            finally:
                user32.CloseClipboard()
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False

    def _build_cf_html(self, html_content: str) -> str:
        """
        Build the CF_HTML clipboard format string.
        
        CF_HTML format requires a header with byte positions:
        Version:0.9
        StartHTML:XXXXXXXX
        EndHTML:XXXXXXXX
        StartFragment:XXXXXXXX
        EndFragment:XXXXXXXX
        <html>...<!--StartFragment-->CONTENT<!--EndFragment-->...</html>
        """
        # Markers
        START_FRAG = "<!--StartFragment-->"
        END_FRAG = "<!--EndFragment-->"
        
        # Find or create body section
        body_start = html_content.find('<body')
        if body_start == -1:
            # No body tag, wrap content
            html_with_markers = f"<html><body>{START_FRAG}{html_content}{END_FRAG}</body></html>"
        else:
            # Find end of body tag
            body_tag_end = html_content.find('>', body_start) + 1
            body_close = html_content.find('</body>')
            if body_close == -1:
                body_close = len(html_content)
            
            html_with_markers = (
                html_content[:body_tag_end] +
                START_FRAG +
                html_content[body_tag_end:body_close] +
                END_FRAG +
                html_content[body_close:]
            )
        
        # Header template - MUST use exact format with \r\n line endings
        # The numbers will be formatted as 8-digit zero-padded integers
        header_template = (
            "Version:0.9\r\n"
            "StartHTML:{:08d}\r\n"
            "EndHTML:{:08d}\r\n"
            "StartFragment:{:08d}\r\n"
            "EndFragment:{:08d}\r\n"
        )
        
        # Calculate header length (with placeholder values)
        dummy_header = header_template.format(0, 0, 0, 0)
        header_len = len(dummy_header.encode('utf-8'))
        
        # Calculate byte positions (must be byte positions, not character positions)
        html_bytes = html_with_markers.encode('utf-8')
        
        start_html = header_len
        end_html = header_len + len(html_bytes)
        
        # Find fragment markers in the byte string
        start_frag_marker_bytes = START_FRAG.encode('utf-8')
        end_frag_marker_bytes = END_FRAG.encode('utf-8')
        
        start_frag_pos = html_bytes.find(start_frag_marker_bytes)
        end_frag_pos = html_bytes.find(end_frag_marker_bytes)
        
        # StartFragment points to AFTER the marker, EndFragment points to BEFORE the marker
        start_fragment = header_len + start_frag_pos + len(start_frag_marker_bytes)
        end_fragment = header_len + end_frag_pos
        
        # Build final header with actual positions
        header = header_template.format(start_html, end_html, start_fragment, end_fragment)
        
        result = header + html_with_markers
        
        # Debug output
        
        return result

    def _html_to_plain_text(self, html: str) -> str:
        """Convert HTML to plain text as fallback."""
        # Remove HTML tags
        text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', '', text)
        # Decode HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        # Clean up whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text.strip()

    def _get_selected_text(self) -> str:
        """Get the currently selected text from the thread display, or None if no selection"""
        try:
            selected = self.thread_text.get(tk.SEL_FIRST, tk.SEL_LAST)
            return selected if selected.strip() else None
        except tk.TclError:
            # No selection
            return None
    
    def _format_selected_text(self, text: str) -> str:
        """
        Clean up and format selected text:
        - Fix spacing issues
        - Normalize indentation
        - Clean up line breaks
        """
        if not text:
            return ""
        
        lines = text.split('\n')
        formatted_lines = []
        
        for line in lines:
            # Strip trailing whitespace but preserve intentional indentation
            line = line.rstrip()
            # Normalize multiple spaces to single space (except at start)
            if line:
                indent = len(line) - len(line.lstrip())
                content = ' '.join(line.split())
                line = ' ' * indent + content if indent else content
            formatted_lines.append(line)
        
        # Join lines and clean up multiple blank lines
        result = '\n'.join(formatted_lines)
        # Replace 3+ consecutive newlines with 2
        while '\n\n\n' in result:
            result = result.replace('\n\n\n', '\n\n')
        
        return result.strip()
    
    def _copy_selection_to_clipboard(self):
        """Copy selected text to clipboard"""
        selected = self._get_selected_text()
        
        if not selected:
            self._set_status("⚠️ Please select text first")
            return
        
        formatted = self._format_selected_text(selected)
        
        # Fix numbered lists (convert "1. 1. 1." to "1. 2. 3.")
        formatted = self._fix_numbered_lists(formatted)
        
        self.window.clipboard_clear()
        self.window.clipboard_append(formatted)
        
        # Show brief confirmation
        word_count = len(formatted.split())
        self._set_status(f"✅ Selection copied ({word_count} words)")

    def _copy_selection_formatted(self):
        """Copy selected text to clipboard with HTML formatting preserved."""
        import sys
        
        # Check if there's a selection
        try:
            sel_start = self.thread_text.index(tk.SEL_FIRST)
            sel_end = self.thread_text.index(tk.SEL_LAST)
        except tk.TclError:
            self._set_status("⚠️ Please select text first")
            return
        
        # Get selected text and reconstruct markdown from visual formatting
        selected_text = self.thread_text.get(sel_start, sel_end)
        
        # Build list of (line_num, text) for the selection
        start_line, start_col = map(int, sel_start.split('.'))
        
        content_lines = []
        lines = selected_text.split('\n')
        current_line = start_line
        
        for i, line in enumerate(lines):
            col_offset = start_col if i == 0 else 0
            content_lines.append((current_line, col_offset, line))
            current_line += 1
        
        # Reconstruct markdown from visual formatting
        markdown_text = self._reconstruct_selection_markdown(content_lines)
        
        # Convert markdown to HTML
        html_content = self._selection_markdown_to_html(markdown_text)
        
        # Copy to clipboard
        if sys.platform == 'win32':
            success = self._copy_html_to_clipboard_windows(html_content)
        else:
            fixed_text = self._fix_numbered_lists(selected_text)
            self.window.clipboard_clear()
            self.window.clipboard_append(fixed_text)
            self._set_status("ℹ️ Formatted copy is Windows-only. Plain text copied.")
            return
        
        if success:
            word_count = len(selected_text.split())
            self._set_status(f"✅ Selection copied formatted ({word_count} words)")
        else:
            fixed_text = self._fix_numbered_lists(selected_text)
            self.window.clipboard_clear()
            self.window.clipboard_append(fixed_text)
            self._set_status("⚠️ HTML copy failed. Plain text copied.")

    def _reconstruct_selection_markdown(self, content_lines: list) -> str:
        """
        Reconstruct markdown from selected content lines.
        
        Args:
            content_lines: List of (line_number, col_offset, text) tuples
        """
        result_lines = []
        
        for line_num, col_offset, line_text in content_lines:
            if not line_text.strip():
                result_lines.append('')
                continue
            
            # Check block-level formatting
            line_start_pos = f"{line_num}.{col_offset}"
            try:
                tags_at_start = self.thread_text.tag_names(line_start_pos)
            except:
                tags_at_start = ()
            
            is_header = 'header' in tags_at_start
            is_bullet = 'bullet' in tags_at_start or line_text.strip().startswith('•')
            is_user = 'user' in tags_at_start
            is_assistant = 'assistant' in tags_at_start
            
            # Handle user/assistant markers - keep as-is
            if is_user or is_assistant:
                result_lines.append(line_text)
                continue
            
            # Handle dividers
            if line_text.strip().startswith('─' * 10):
                result_lines.append('---')
                continue
            
            # Handle headers
            if is_header:
                clean_text = line_text.strip()
                if not clean_text.startswith('## '):
                    clean_text = f"## {clean_text}"
                result_lines.append(clean_text)
                continue
            
            # Handle bullets
            if is_bullet:
                clean_text = line_text.strip()
                if clean_text.startswith('•'):
                    clean_text = clean_text[1:].strip()
                if not clean_text.startswith('- '):
                    clean_text = f"- {clean_text}"
                result_lines.append(clean_text)
                continue
            
            # Regular line - check for inline bold/italic
            formatted = self._reconstruct_line_inline_markdown(line_num, col_offset, line_text)
            result_lines.append(formatted)
        
        return '\n'.join(result_lines)

    def _reconstruct_line_inline_markdown(self, line_num: int, col_offset: int, text: str) -> str:
        """Reconstruct inline markdown for a single line."""
        if not text:
            return ""
        
        result = []
        current_bold = False
        current_segment = []
        
        for i, char in enumerate(text):
            col = col_offset + i
            pos = f"{line_num}.{col}"
            
            try:
                tags = self.thread_text.tag_names(pos)
            except:
                tags = ()
            
            # Check for bold (excluding header/user/assistant which are whole-line bold)
            is_bold = 'bold' in tags and 'header' not in tags and 'user' not in tags and 'assistant' not in tags
            
            if is_bold != current_bold:
                if current_segment:
                    segment_text = ''.join(current_segment)
                    if current_bold:
                        result.append(f"**{segment_text}**")
                    else:
                        result.append(segment_text)
                    current_segment = []
                current_bold = is_bold
            
            current_segment.append(char)
        
        # Flush final segment
        if current_segment:
            segment_text = ''.join(current_segment)
            if current_bold:
                result.append(f"**{segment_text}**")
            else:
                result.append(segment_text)
        
        return ''.join(result)

    def _selection_markdown_to_html(self, markdown_text: str) -> str:
        """Convert selection markdown to HTML document."""
        content_html = self._markdown_to_html_content(markdown_text)
        
        html_doc = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: Calibri, Arial, sans-serif; font-size: 11pt; line-height: 1.5; }}
h2 {{ font-weight: bold; color: #2C3E50; font-size: 13pt; }}
b, strong {{ font-weight: bold; }}
ul, ol {{ margin: 6pt 0; padding-left: 25pt; }}
li {{ margin: 4pt 0; }}
</style>
</head>
<body>
{content_html}
</body>
</html>'''
        
        return html_doc

    def _selection_to_html(self, start_index: str, end_index: str) -> str:
        """
        Convert selected text range to HTML, preserving visual formatting.
        """
        # Get the selected text
        selected_text = self.thread_text.get(start_index, end_index)
        
        html_parts = []
        
        # Parse start position
        start_line, start_col = map(int, start_index.split('.'))
        end_line, end_col = map(int, end_index.split('.'))
        
        # Process each line in the selection
        lines = selected_text.split('\n')
        current_line = start_line
        
        for i, line in enumerate(lines):
            if not line:
                html_parts.append('<p>&nbsp;</p>')
                current_line += 1
                continue
            
            # Determine the column offset for this line
            if i == 0:
                col_offset = start_col
            else:
                col_offset = 0
            
            line_start = f"{current_line}.{col_offset}"
            
            # Check tags at start of line for block-level formatting
            try:
                tags_at_start = self.thread_text.tag_names(line_start)
            except:
                tags_at_start = ()
            
            is_header = 'header' in tags_at_start
            is_user = 'user' in tags_at_start
            is_assistant = 'assistant' in tags_at_start
            is_divider = 'divider' in tags_at_start
            is_bullet = 'bullet' in tags_at_start
            
            # Handle dividers
            if is_divider or line.strip().startswith('─' * 10):
                html_parts.append('<hr style="border: 1px solid #ddd;">')
                current_line += 1
                continue
            
            # Handle user/assistant markers
            if is_user:
                html_parts.append(f'<p style="color: #2E4053; font-weight: bold;">{self._escape_html(line)}</p>')
                current_line += 1
                continue
            
            if is_assistant:
                html_parts.append(f'<p style="color: #16537E; font-weight: bold;">{self._escape_html(line)}</p>')
                current_line += 1
                continue
            
            # Handle headers
            if is_header:
                html_parts.append(f'<h2 style="color: #2c3e50; font-size: 13pt;">{self._escape_html(line)}</h2>')
                current_line += 1
                continue
            
            # Handle bullets
            if is_bullet or line.strip().startswith('•'):
                bullet_text = line.strip()
                if bullet_text.startswith('•'):
                    bullet_text = bullet_text[1:].strip()
                formatted = self._process_inline_formatting_range(current_line, col_offset, line)
                html_parts.append(f'<li style="margin: 3pt 0;">{formatted}</li>')
                current_line += 1
                continue
            
            # Regular paragraph with inline formatting
            formatted = self._process_inline_formatting_range(current_line, col_offset, line)
            html_parts.append(f'<p style="margin: 6pt 0;">{formatted}</p>')
            current_line += 1
        
        # Wrap in HTML
        html_body = '\n'.join(html_parts)
        html_doc = f'''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Calibri, Arial, sans-serif; font-size: 11pt;">
{html_body}
</body>
</html>'''
        
        return html_doc

    def _process_inline_formatting_range(self, line_num: int, col_offset: int, line_text: str) -> str:
        """
        Process inline formatting for a specific range of text.
        """
        if not line_text:
            return ""
        
        result = []
        current_bold = False
        current_italic = False
        current_text = []
        
        for i, char in enumerate(line_text):
            col = col_offset + i
            pos = f"{line_num}.{col}"
            try:
                tags = self.thread_text.tag_names(pos)
            except:
                tags = ()
            
            is_bold = 'bold' in tags or 'header' in tags
            is_italic = 'italic' in tags
            
            if is_bold != current_bold or is_italic != current_italic:
                if current_text:
                    text = self._escape_html(''.join(current_text))
                    if current_bold and current_italic:
                        result.append(f'<b><i>{text}</i></b>')
                    elif current_bold:
                        result.append(f'<b>{text}</b>')
                    elif current_italic:
                        result.append(f'<i>{text}</i>')
                    else:
                        result.append(text)
                    current_text = []
                
                current_bold = is_bold
                current_italic = is_italic
            
            current_text.append(char)
        
        if current_text:
            text = self._escape_html(''.join(current_text))
            if current_bold and current_italic:
                result.append(f'<b><i>{text}</i></b>')
            elif current_bold:
                result.append(f'<b>{text}</b>')
            elif current_italic:
                result.append(f'<i>{text}</i>')
            else:
                result.append(text)
        
        return ''.join(result)
    
    def _save_selection(self, format_ext: str):
        """Save selected text to file in specified format with proper formatting"""
        selected = self._get_selected_text()
        
        if not selected:
            self._set_status("⚠️ Please select text first")
            return
        
        formatted = self._format_selected_text(selected)
        
        # Import the enhanced formatter
        from doc_formatter import save_formatted_document
        from utils import safe_filename
        from tkinter import filedialog
        
        # Prepare filename - use first few words of selection
        preview = ' '.join(formatted.split()[:5])
        if len(preview) > 30:
            preview = preview[:30]
        clean_name = safe_filename(f"Selection - {preview}")
        
        # Set up file dialog based on format
        format_map = {
            '.txt': ('txt', [("Text files", "*.txt"), ("All files", "*.*")]),
            '.docx': ('docx', [("Word documents", "*.docx"), ("All files", "*.*")]),
            '.rtf': ('rtf', [("RTF documents", "*.rtf"), ("All files", "*.*")]),
            '.pdf': ('pdf', [("PDF files", "*.pdf"), ("All files", "*.*")])
        }
        
        export_format, filetypes = format_map.get(format_ext, ('txt', [("All files", "*.*")]))
        
        filepath = filedialog.asksaveasfilename(
            parent=self.window,
            title="Save Selection As",
            defaultextension=format_ext,
            initialfile=f"{clean_name}{format_ext}",
            filetypes=filetypes
        )
        
        if not filepath:
            return  # User cancelled
        
        # Use enhanced formatter to save with proper formatting
        success = save_formatted_document(
            filepath=filepath,
            content_text=formatted,
            title=f"Selection from: {self.doc_title}",
            source=self.source_info,
            imported_date=self.fetched_date,
            doc_class="selection",
            export_format=export_format,
            published_date=getattr(self, 'published_date', None)
        )
        
        if success:
            filename = filepath.split('/')[-1].split('\\')[-1]  # Get just filename
            self._set_status(f"✅ Selection saved to {filename}")
        else:
            messagebox.showerror("Error", "Failed to save selection. Check console for details.")

    # ========== WhatsApp/Telegram Formatting ==========

    def _markdown_to_whatsapp(self, text: str) -> str:
        """
        Convert markdown text to WhatsApp/Telegram formatting.

        WhatsApp supports:
            *bold*      (markdown **bold**)
            _italic_    (markdown *italic*)
            ~strikethrough~
        ```monospace```
            Numbered and bullet lists work as-is

        Layout note: headings (# / ## / ###) are emitted on their own line with
        NO trailing blank line, so the paragraph that follows sits directly
        beneath the heading. This makes WhatsApp messages more compact — a
        single linebreak is enough visual separation in a messaging UI.

        The source markdown typically has `## Heading\\n\\nBody`, i.e. a blank
        line between heading and body. We suppress that blank line via the
        just_emitted_heading flag so the heading sits directly above its body
        text in the WhatsApp output.
        """
        if not text:
            return ""

        lines = text.split('\n')
        result_lines = []
        just_emitted_heading = False

        for line in lines:
            stripped = line.strip()

            if not stripped:
                # Suppress the blank line that commonly follows a heading in
                # source markdown (## Heading\n\nBody). Keeps heading-to-body
                # tight in WhatsApp output.
                if just_emitted_heading:
                    just_emitted_heading = False
                    continue
                result_lines.append('')
                continue

            # Any non-empty line resets the flag unless it's another heading
            # (handled below).
            just_emitted_heading = False

            # Horizontal rule → visual divider
            if stripped == '---':
                result_lines.append('————————————————————')
                continue

            # Heading 2: ## Title → *Title* (bold, no blank line after)
            if stripped.startswith('## '):
                heading_text = stripped[3:].strip()
                # Remove any inline markdown from heading before wrapping
                heading_text = self._strip_markdown_inline(heading_text)
                result_lines.append(f'*{heading_text}*')
                just_emitted_heading = True
                continue

            # Heading 3: ### Title → *Title* (bold, no blank line after)
            if stripped.startswith('### '):
                heading_text = stripped[4:].strip()
                heading_text = self._strip_markdown_inline(heading_text)
                result_lines.append(f'*{heading_text}*')
                just_emitted_heading = True
                continue

            # Heading 1: # Title → *TITLE* (bold, caps, no blank line after)
            if stripped.startswith('# ') and not stripped.startswith('## '):
                heading_text = stripped[2:].strip()
                heading_text = self._strip_markdown_inline(heading_text)
                result_lines.append(f'*{heading_text.upper()}*')
                just_emitted_heading = True
                continue

            # Bullet list: - item or * item → • item
            if stripped.startswith('- ') or stripped.startswith('* '):
                item_text = self._convert_inline_to_whatsapp(stripped[2:])
                result_lines.append(f'  • {item_text}')
                continue

            # Numbered list: passes through, just convert inline formatting
            if re.match(r'^\d+\.\s+', stripped):
                item_text = re.sub(r'^\d+\.\s+', '', stripped)
                num = re.match(r'^(\d+\.)\s+', stripped).group(1)
                item_text = self._convert_inline_to_whatsapp(item_text)
                result_lines.append(f'  {num} {item_text}')
                continue

            # Block quote: > text → ❝ text
            if stripped.startswith('> '):
                quote_text = self._convert_inline_to_whatsapp(stripped[2:])
                result_lines.append(f'  ❝ {quote_text}')
                continue

            # Regular paragraph: convert inline formatting
            result_lines.append(self._convert_inline_to_whatsapp(stripped))

        return '\n'.join(result_lines)
    
    def _convert_inline_to_whatsapp(self, text: str) -> str:
        """
        Convert inline markdown to WhatsApp formatting.
        Uses placeholders to avoid bold markers being caught by italic conversion.
        """
        if not text:
            return ""

        # Step 1: Bold **"quoted text"** → italic placeholder.
        # Quotations wrapped in bold markers are almost always meant to be
        # italic (the AI misuses ** instead of *).  Detect these first so they
        # become italic rather than bold in WhatsApp.
        ITALIC_MARK = '\x02WI\x03'
        BOLD_MARK   = '\x02WB\x03'

        def _maybe_italic_quote(m):
            inner = m.group(1).strip()
            # If the bold content is a quotation (starts/ends with " or \u2018/\u201c)
            # treat it as italic; otherwise treat as bold.
            if inner and inner[0] in ('"', '\u2018', '\u2019', '\u201c', '\u201d',
                                      "'", '\u2018', '\u2019'):
                return f'{ITALIC_MARK}{inner}{ITALIC_MARK}'
            return f'{BOLD_MARK}{m.group(1)}{BOLD_MARK}'

        text = re.sub(r'\*\*(.+?)\*\*', _maybe_italic_quote, text)

        # Step 2: Bold __text__ → bold placeholder
        text = re.sub(r'__(.+?)__', lambda m: f'{BOLD_MARK}{m.group(1)}{BOLD_MARK}', text)

        # Step 3: Italic *text* → _text_  (now safe, bold markers are placeholders)
        text = re.sub(r'\*(.+?)\*', r'_\1_', text)

        # Step 4: Replace placeholders with WhatsApp markers
        text = text.replace(ITALIC_MARK, '_')
        text = text.replace(BOLD_MARK, '*')

        # Inline code: `text` → ```text```
        text = re.sub(r'`([^`]+)`', r'```\1```', text)

        # Strikethrough: ~~text~~ → ~text~
        text = re.sub(r'~~(.+?)~~', r'~\1~', text)

        return text
    
    def _strip_markdown_inline(self, text: str) -> str:
        """Remove markdown inline formatting markers from text."""
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'_(.+?)_', r'\1', text)
        text = re.sub(r'`(.+?)`', r'\1', text)
        text = re.sub(r'~~(.+?)~~', r'\1', text)
        return text
    
    def _build_whatsapp_header(self) -> str:
        """Build a metadata header in WhatsApp-friendly plain text."""
        lines = []
        lines.append(f'*{self.doc_title}*')
        lines.append('————————————————————')
        lines.append(f'Source: {self.source_info}')
        if hasattr(self, 'published_date') and self.published_date and self.published_date != 'N/A':
            lines.append(f'Published: {self.published_date}')
        lines.append(f'Imported: {self.fetched_date}')
        lines.append('————————————————————')
        lines.append('')
        return '\n'.join(lines)
    
    def _thread_to_whatsapp(self, messages=None) -> str:
        """
        Convert thread messages to WhatsApp-formatted text.
        
        Args:
            messages: List of message dicts. If None, uses self.current_thread.
        """
        if messages is None:
            messages = self.current_thread
        
        if not messages:
            return ""
        
        parts = []
        parts.append(self._build_whatsapp_header())
        
        for msg in messages:
            role = msg.get('role', '')
            content = msg.get('content', '')
            timestamp = msg.get('timestamp', '')
            
            if role == 'user':
                time_str = f" [{timestamp}]" if timestamp else ""
                parts.append(f'*🧑 YOU{time_str}*')
                parts.append(content)
                parts.append('')
                
            elif role == 'assistant':
                provider = msg.get('provider', 'AI')
                model = msg.get('model', '')
                time_str = f" [{timestamp}]" if timestamp else ""
                
                if model and model != provider:
                    label = f"🤖 {provider} ({model}){time_str}"
                else:
                    label = f"🤖 {provider}{time_str}"
                
                parts.append(f'*{label}*')
                parts.append(self._markdown_to_whatsapp(content))
                parts.append('')
                parts.append('————————————————————')
                parts.append('')
        
        return '\n'.join(parts)
    
    def _copy_to_clipboard_plain(self, text: str):
        """Helper to copy plain text to clipboard."""
        self.window.clipboard_clear()
        self.window.clipboard_append(text)
    
    def _copy_source_whatsapp(self):
        """Copy source document in WhatsApp format."""
        if not self.current_document_text:
            self._set_status("⚠️ No source document available")
            return
        
        try:
            parts = []
            parts.append(self._build_whatsapp_header())
            parts.append(self.current_document_text)
            
            self._copy_to_clipboard_plain('\n'.join(parts))
            self._set_status("✅ Source copied (WhatsApp format)")
        except Exception as e:
            messagebox.showerror("Copy Error", f"Failed to copy:\n{str(e)}")
    
    def _copy_thread_whatsapp(self):
        """Copy all thread exchanges in WhatsApp format."""
        try:
            # Save edits if modifications were made
            try:
                if self.current_mode == 'conversation' and self.current_thread:
                    self._save_edits_to_thread()
            except ValueError:
                return
            except Exception:
                pass
            
            content = self._thread_to_whatsapp()
            if not content:
                self._set_status("⚠️ No content to copy")
                return
            
            self._copy_to_clipboard_plain(content)
            self._set_status("✅ Thread copied (WhatsApp format)")
        except Exception as e:
            messagebox.showerror("Copy Error", f"Failed to copy:\n{str(e)}")
    
    def _copy_expanded_whatsapp(self):
        """Copy only expanded exchanges in WhatsApp format."""
        try:
            exchanges = self._group_messages_into_exchanges()
            if not exchanges:
                self._set_status("⚠️ No exchanges to copy")
                return
            
            # Build filtered thread from expanded exchanges only
            filtered_thread = []
            expanded_count = 0
            for i in range(len(exchanges)):
                if self.exchange_expanded_state.get(i, True):
                    exchange = exchanges[i]
                    if 'user' in exchange:
                        filtered_thread.append(exchange['user'])
                    if 'assistant' in exchange:
                        filtered_thread.append(exchange['assistant'])
                    expanded_count += 1
            
            if not filtered_thread:
                self._set_status("⚠️ No exchanges are expanded")
                return
            
            content = self._thread_to_whatsapp(messages=filtered_thread)
            self._copy_to_clipboard_plain(content)
            self._set_status(f"✅ Copied {expanded_count} expanded exchange{'s' if expanded_count != 1 else ''} (WhatsApp format)")
        except Exception as e:
            messagebox.showerror("Copy Error", f"Failed to copy:\n{str(e)}")
    
    def _copy_complete_whatsapp(self):
        """Copy source + thread in WhatsApp format."""
        try:
            parts = []
            
            # Source document
            if self.current_document_text:
                parts.append(self._build_whatsapp_header())
                parts.append('*📄 SOURCE DOCUMENT*')
                parts.append('————————————————————')
                parts.append(self.current_document_text)
                parts.append('')
                parts.append('════════════════════')
                parts.append('')
            
            # Thread
            if self.current_thread:
                parts.append('*💬 CONVERSATION THREAD*')
                parts.append('————————————————————')
                parts.append('')
                
                for msg in self.current_thread:
                    role = msg.get('role', '')
                    content = msg.get('content', '')
                    timestamp = msg.get('timestamp', '')
                    
                    if role == 'user':
                        time_str = f" [{timestamp}]" if timestamp else ""
                        parts.append(f'*🧑 YOU{time_str}*')
                        parts.append(content)
                        parts.append('')
                    elif role == 'assistant':
                        provider = msg.get('provider', 'AI')
                        model = msg.get('model', '')
                        time_str = f" [{timestamp}]" if timestamp else ""
                        if model and model != provider:
                            label = f"🤖 {provider} ({model}){time_str}"
                        else:
                            label = f"🤖 {provider}{time_str}"
                        parts.append(f'*{label}*')
                        parts.append(self._markdown_to_whatsapp(content))
                        parts.append('')
                        parts.append('————————————————————')
                        parts.append('')
            
            content = '\n'.join(parts)
            if not content.strip():
                self._set_status("⚠️ No content to copy")
                return
            
            self._copy_to_clipboard_plain(content)
            self._set_status("✅ Complete content copied (WhatsApp format)")
        except Exception as e:
            messagebox.showerror("Copy Error", f"Failed to copy:\n{str(e)}")
    
    def _copy_selection_whatsapp(self):
        """Copy selected text in WhatsApp format."""
        try:
            selected = self._get_selected_text()
            if not selected or not selected.strip():
                self._set_status("⚠️ No text selected")
                return
            
            # Convert any markdown in the selection
            converted = self._markdown_to_whatsapp(selected)
            self._copy_to_clipboard_plain(converted)
            
            word_count = len(selected.split())
            self._set_status(f"✅ Selection copied ({word_count} words, WhatsApp format)")
        except Exception as e:
            messagebox.showerror("Copy Error", f"Failed to copy:\n{str(e)}")
    
    # ========== Copy Dialog ==========
    
    def _show_copy_dialog(self):
        """
        Show a unified dialog to choose what content to copy to clipboard.
        Includes: Source Only, All Exchanges, Expanded Only, Complete (Source+Thread), Selection
        """
        # Persist any in-progress edits so the copy reflects the current state.
        self._save_edits_before_refresh()

        # Create dialog window
        dialog = tk.Toplevel(self.window)
        dialog.title("Copy")
        dialog.transient(self.window)
        dialog.grab_set()
        
        # Center on parent window
        dialog.geometry("450x480")
        dialog_x = self.window.winfo_x() + (self.window.winfo_width() - 450) // 2
        dialog_y = self.window.winfo_y() + (self.window.winfo_height() - 480) // 2
        dialog.geometry(f"+{dialog_x}+{dialog_y}")
        
        # Main frame with padding
        main_frame = ttk.Frame(dialog, padding=15)
        main_frame.pack(fill='both', expand=True)
        
        # Title
        title_label = ttk.Label(main_frame, text="What do you want to copy?", 
                                font=('Segoe UI', 11, 'bold'))
        title_label.pack(anchor='w', pady=(0, 15))
        
        # Check if source document is available
        has_source = bool(self.current_document_text)
        
        # Check if thread exists
        has_thread = bool(self.current_thread and len(self.current_thread) > 0)
        
        # Default selection based on current mode
        if self.current_mode == 'source':
            default_choice = "source" if has_source else "thread"
        else:
            default_choice = "thread"
        
        # Variable to track selection
        copy_choice = tk.StringVar(value=default_choice)
        
        # Count expanded exchanges for the label
        exchanges = self._group_messages_into_exchanges()
        expanded_count = sum(1 for i in range(len(exchanges)) 
                           if self.exchange_expanded_state.get(i, True))
        total_count = len(exchanges)
        
        # Check if there's a text selection
        has_selection = False
        selection_word_count = 0
        try:
            selection = self.thread_text.get(tk.SEL_FIRST, tk.SEL_LAST)
            if selection.strip():
                has_selection = True
                selection_word_count = len(selection.split())
        except tk.TclError:
            pass
        
        # Option 1: Source Only
        opt1_frame = ttk.Frame(main_frame)
        opt1_frame.pack(fill='x', pady=5)
        
        source_rb = ttk.Radiobutton(opt1_frame, text="Source Only", variable=copy_choice, 
                                     value="source")
        source_rb.pack(anchor='w')
        
        if has_source:
            ttk.Label(opt1_frame, text="Just the original source document", 
                     foreground='gray').pack(anchor='w', padx=(20, 0))
        else:
            ttk.Label(opt1_frame, text="(Not available - no source document loaded)", 
                     foreground='red').pack(anchor='w', padx=(20, 0))
            source_rb.config(state='disabled')
        
        # Option 2: All Exchanges (Thread)
        opt2_frame = ttk.Frame(main_frame)
        opt2_frame.pack(fill='x', pady=5)
        
        thread_rb = ttk.Radiobutton(opt2_frame, text="All Exchanges", variable=copy_choice, 
                                     value="thread")
        thread_rb.pack(anchor='w')
        
        if has_thread:
            ttk.Label(opt2_frame, text=f"Copy all {total_count} exchange(s) to clipboard", 
                     foreground='gray').pack(anchor='w', padx=(20, 0))
        else:
            ttk.Label(opt2_frame, text="(Not available - no conversation yet)", 
                     foreground='red').pack(anchor='w', padx=(20, 0))
            thread_rb.config(state='disabled')
        
        # Option 3: Expanded Only
        opt3_frame = ttk.Frame(main_frame)
        opt3_frame.pack(fill='x', pady=5)
        
        expanded_text = f"Expanded Only ({expanded_count} of {total_count} exchanges)"
        expanded_rb = ttk.Radiobutton(opt3_frame, text=expanded_text, variable=copy_choice, 
                                       value="expanded")
        expanded_rb.pack(anchor='w')
        
        if has_thread and total_count > 0:
            ttk.Label(opt3_frame, text="Only exchanges you've expanded (collapsed ones are omitted)", 
                     foreground='gray').pack(anchor='w', padx=(20, 0))
        else:
            ttk.Label(opt3_frame, text="(Not available - no exchanges)", 
                     foreground='red').pack(anchor='w', padx=(20, 0))
            expanded_rb.config(state='disabled')
        
        # Option 4: Complete (Source + Thread)
        opt4_frame = ttk.Frame(main_frame)
        opt4_frame.pack(fill='x', pady=5)
        
        complete_rb = ttk.Radiobutton(opt4_frame, text="Complete: Source + Thread", 
                                       variable=copy_choice, value="complete")
        complete_rb.pack(anchor='w')
        
        if has_source and has_thread:
            ttk.Label(opt4_frame, text="Source document AND all conversation exchanges", 
                     foreground='gray').pack(anchor='w', padx=(20, 0))
        else:
            ttk.Label(opt4_frame, text="(Requires both source and thread)", 
                     foreground='red').pack(anchor='w', padx=(20, 0))
            complete_rb.config(state='disabled')
        
        # Option 5: Selection
        opt5_frame = ttk.Frame(main_frame)
        opt5_frame.pack(fill='x', pady=5)
        
        if has_selection:
            selection_text = f"Selection ({selection_word_count} words)"
            selection_rb = ttk.Radiobutton(opt5_frame, text=selection_text, 
                                           variable=copy_choice, value="selection")
            selection_rb.pack(anchor='w')
            ttk.Label(opt5_frame, text="Copy the currently selected text", 
                     foreground='gray').pack(anchor='w', padx=(20, 0))
        else:
            selection_rb = ttk.Radiobutton(opt5_frame, text="Selection", 
                                           variable=copy_choice, value="selection",
                                           state='disabled')
            selection_rb.pack(anchor='w')
            ttk.Label(opt5_frame, text="(No text selected - select text first to enable)", 
                     foreground='red').pack(anchor='w', padx=(20, 0))
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').pack(fill='x', pady=15)
        
        # Format selection
        format_frame = ttk.Frame(main_frame)
        format_frame.pack(fill='x', pady=5)
        
        ttk.Label(format_frame, text="Format:").pack(side='left')
        
        format_var = tk.StringVar(value="formatted")
        format_combo = ttk.Combobox(format_frame, textvariable=format_var, 
                                     values=["Plain Text", "Formatted (for Word/Email)", "Formatted (for WhatsApp/Telegram)"],
                                     state='readonly', width=32)
        format_combo.pack(side='left', padx=(10, 0))
        format_combo.current(1)  # Default to formatted
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=(20, 0))
        
        def on_copy():
            choice = copy_choice.get()
            fmt = format_var.get()
            is_plain = "Plain" in fmt
            is_whatsapp = "WhatsApp" in fmt
            dialog.destroy()
            
            if choice == "source":
                if is_whatsapp:
                    self._copy_source_whatsapp()
                else:
                    self._copy_source_only(plain_text=is_plain)
            elif choice == "thread":
                if is_plain:
                    self._copy_thread()
                elif is_whatsapp:
                    self._copy_thread_whatsapp()
                else:
                    self._copy_thread_formatted()
            elif choice == "expanded":
                if is_plain:
                    self._copy_expanded_only()
                elif is_whatsapp:
                    self._copy_expanded_whatsapp()
                else:
                    self._copy_expanded_only_formatted()
            elif choice == "complete":
                if is_whatsapp:
                    self._copy_complete_whatsapp()
                else:
                    self._copy_complete(plain_text=is_plain)
            elif choice == "selection":
                if is_plain:
                    self._copy_selection_to_clipboard()
                elif is_whatsapp:
                    self._copy_selection_whatsapp()
                else:
                    self._copy_selection_formatted()
        
        def on_cancel():
            dialog.destroy()
        
        ttk.Button(button_frame, text="Copy", command=on_copy, width=10).pack(side='right', padx=5)
        ttk.Button(button_frame, text="Cancel", command=on_cancel, width=10).pack(side='right')
        
        # Handle Enter and Escape
        dialog.bind('<Return>', lambda e: on_copy())
        dialog.bind('<Escape>', lambda e: on_cancel())
        
        # Focus on dialog
        dialog.focus_set()
        dialog.wait_window()

