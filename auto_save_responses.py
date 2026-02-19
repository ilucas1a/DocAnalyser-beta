"""
AUTO_SAVE_RESPONSES.PY - Drop-in Module
========================================

Add this file to your DocAnalyzer_DEV folder, then import it in main.py.

This is a self-contained module that handles AI response auto-saving.

USAGE IN MAIN.PY:
-----------------
1. Import at top:
   from auto_save_responses import ResponseAutoSaver

2. In your __init__:
   self.response_saver = ResponseAutoSaver()

3. After getting AI response:
   self.response_saver.save_response(
       response_text=response,
       prompt_name="Summary",
       source_document_id=self.current_document_id,
       provider="OpenAI",
       model="gpt-4",
       conversation_thread=self.current_thread
   )
"""

import datetime
from typing import Optional, List, Dict

class ResponseAutoSaver:
    """
    Handles automatic saving of AI responses to the Documents Library.
    """
    
    def __init__(self, enabled: bool = True):
        """
        Initialize the auto-saver.
        
        Args:
            enabled: Whether auto-save is enabled by default
        """
        self.enabled = enabled
        self.last_saved_doc_id = None
    
    def save_response(self,
                     response_text: str,
                     prompt_name: str = "AI Response",
                     source_document_id: Optional[str] = None,
                     provider: str = "Unknown",
                     model: str = "Unknown",
                     conversation_thread: Optional[List[Dict]] = None) -> Optional[str]:
        """
        Save an AI response to the Documents Library.
        
        Args:
            response_text: The AI response text to save
            prompt_name: Name of the prompt that was used
            source_document_id: ID of source document (if any)
            provider: AI provider name (OpenAI, Anthropic, etc.)
            model: Model name (gpt-4, claude-3, etc.)
            conversation_thread: Full conversation thread (optional)
            
        Returns:
            Document ID of saved response, or None if failed
        """
        if not self.enabled:
            print("⏭️  Auto-save disabled")
            return None
        
        if not response_text or not response_text.strip():
            print("⚠️  No response text to save")
            return None
        
        try:
            from document_library import (
                add_document_to_library,
                save_thread_to_document,
                get_document_by_id
            )
            
            # Create title
            title = self._create_title(
                prompt_name=prompt_name,
                source_document_id=source_document_id
            )
            
            # Prepare entries (split into paragraphs)
            entries = self._create_entries(response_text)
            
            # Prepare metadata
            metadata = {
                'editable': True,
                'created_by_ai': True,
                'ai_provider': provider,
                'ai_model': model,
                'prompt_name': prompt_name,
                'source_document_id': source_document_id,
                'created_at': datetime.datetime.now().isoformat(),
                'auto_saved': True
            }
            
            # Get source info if available
            source_info = f"AI Response - {provider} - {model}"
            if source_document_id:
                source_doc = get_document_by_id(source_document_id)
                if source_doc:
                    source_info += f" (based on: {source_doc.get('title', 'Unknown')})"
            
            # Add to library as "response" document
            doc_id = add_document_to_library(
                doc_type='ai_response',
                source=source_info,
                title=title,
                entries=entries,
                metadata=metadata,
                document_class='response'  # Makes it editable
            )
            
            print(f"✅ Auto-saved AI response: {title}")
            print(f"   Document ID: {doc_id}")
            
            # Save conversation thread if provided
            if conversation_thread and len(conversation_thread) > 0:
                thread_metadata = {
                    'model': model,
                    'provider': provider,
                    'last_updated': datetime.datetime.now().isoformat(),
                    'message_count': len([m for m in conversation_thread if m.get('role') == 'user'])
                }
                
                save_thread_to_document(doc_id, conversation_thread, thread_metadata)
                print(f"   + Saved conversation thread ({thread_metadata['message_count']} messages)")
            
            self.last_saved_doc_id = doc_id
            return doc_id
            
        except Exception as e:
            print(f"❌ Failed to auto-save response: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _create_title(self, prompt_name: str, source_document_id: Optional[str]) -> str:
        """Create an appropriate title for the response document"""
        if source_document_id:
            try:
                from document_library import get_document_by_id
                source_doc = get_document_by_id(source_document_id)
                if source_doc:
                    source_title = source_doc.get('title', 'Unknown Document')
                    # Keep title concise
                    if len(source_title) > 50:
                        source_title = source_title[:50] + "..."
                    return f"[Response] {prompt_name}: {source_title}"
            except:
                pass
        
        # Fallback: timestamp-based title
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        return f"[Response] {prompt_name} - {timestamp}"
    
    def _create_entries(self, response_text: str) -> List[Dict]:
        """Convert response text into entries (paragraphs)"""
        # Split by double newlines (paragraphs)
        paragraphs = [p.strip() for p in response_text.split('\n\n') if p.strip()]
        
        # If no paragraphs found, treat whole text as one entry
        if not paragraphs:
            paragraphs = [response_text.strip()]
        
        entries = []
        for i, para in enumerate(paragraphs):
            entries.append({
                'text': para,
                'start': i,
                'timestamp': f'[{i}]'
            })
        
        return entries
    
    def enable(self):
        """Enable auto-save"""
        self.enabled = True
        print("✅ AI response auto-save ENABLED")
    
    def disable(self):
        """Disable auto-save"""
        self.enabled = False
        print("⏸️  AI response auto-save DISABLED")
    
    def toggle(self):
        """Toggle auto-save on/off"""
        self.enabled = not self.enabled
        status = "ENABLED" if self.enabled else "DISABLED"
        print(f"🔄 AI response auto-save {status}")
        return self.enabled
    
    def get_last_saved_id(self) -> Optional[str]:
        """Get the document ID of the last saved response"""
        return self.last_saved_doc_id


"""
EXAMPLE USAGE:
==============
"""

if __name__ == "__main__":
    # Demo usage
    print("ResponseAutoSaver Demo")
    print("=" * 60)
    
    saver = ResponseAutoSaver()
    
    # Example 1: Save a simple response
    doc_id = saver.save_response(
        response_text="This is a test AI response.\n\nIt has multiple paragraphs.\n\nAnd it should be saved to the library.",
        prompt_name="Test Prompt",
        provider="OpenAI",
        model="gpt-4"
    )
    
    print(f"\nSaved document ID: {doc_id}")
    
    # Example 2: Save with source document
    doc_id = saver.save_response(
        response_text="Summary of the YouTube video...",
        prompt_name="Summary",
        source_document_id="abc123",
        provider="OpenAI",
        model="gpt-4o"
    )
    
    print(f"\nSaved document ID: {doc_id}")
    
    # Example 3: Save with conversation thread
    thread = [
        {"role": "user", "content": "Summarize this document"},
        {"role": "assistant", "content": "Here is a summary..."}
    ]
    
    doc_id = saver.save_response(
        response_text="Here is a summary...",
        prompt_name="Summary",
        provider="Anthropic",
        model="claude-3-opus",
        conversation_thread=thread
    )
    
    print(f"\nSaved document ID: {doc_id}")
    
    # Toggle functionality
    saver.disable()
    saver.enable()
    saver.toggle()
