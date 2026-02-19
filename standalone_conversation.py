"""
standalone_conversation.py - Handle saving standalone AI conversations
======================================================================

When a user runs a prompt without loading a source document, this module
provides functionality to save the conversation to the Documents Library.

Features:
- Detects standalone conversation state
- Generates suggested title using AI
- Shows save dialog with editable title
- Creates document and saves thread
"""

import tkinter as tk
from tkinter import ttk, messagebox
import datetime
from typing import Callable, Optional, Tuple, Dict, Any


class StandaloneConversationManager:
    """Manages standalone conversations (AI chats without source documents)"""
    
    def __init__(self):
        self.conversation_saved = False
        self.saved_document_id = None
    
    def reset(self):
        """Reset state for new conversation"""
        self.conversation_saved = False
        self.saved_document_id = None
    
    def is_standalone_conversation(self, current_document_id: Optional[str], 
                                    current_thread: list,
                                    thread_message_count: int) -> bool:
        """
        Check if we're in a standalone conversation state.
        
        Returns True if:
        - No source document is loaded (current_document_id is None)
        - There IS a conversation (thread has messages)
        - The conversation hasn't already been saved
        """
        has_no_source = current_document_id is None
        has_conversation = thread_message_count > 0 and len(current_thread) > 0
        not_saved = not self.conversation_saved
        
        # DEBUG OUTPUT
        print(f"\n🔍 STANDALONE CHECK:")
        print(f"   current_document_id: {current_document_id!r}")
        print(f"   has_no_source: {has_no_source}")
        print(f"   thread_message_count: {thread_message_count}")
        print(f"   current_thread length: {len(current_thread) if current_thread else 0}")
        print(f"   has_conversation: {has_conversation}")
        print(f"   conversation_saved: {self.conversation_saved}")
        print(f"   not_saved: {not_saved}")
        print(f"   RESULT: {has_no_source and has_conversation and not_saved}")
        
        return has_no_source and has_conversation and not_saved
    
    def generate_title_with_ai(self, prompt_text: str, response_text: str,
                                provider: str, model: str, api_key: str,
                                ai_handler, config: dict) -> str:
        """
        Generate a suggested title using the AI.
        
        Falls back to first words of prompt if API call fails.
        """
        # Truncate for efficiency
        prompt_preview = prompt_text[:200] if prompt_text else ""
        response_preview = response_text[:200] if response_text else ""
        
        title_prompt = f"""Based on this conversation, suggest a brief descriptive title (3-6 words, no quotes, no punctuation at end):

User asked: {prompt_preview}
AI responded about: {response_preview}

Respond with ONLY the title, nothing else:"""
        
        try:
            messages = [{"role": "user", "content": title_prompt}]
            
            success, result = ai_handler.call_ai_provider(
                provider=provider,
                model=model,
                messages=messages,
                api_key=api_key,
                lm_studio_url=config.get("lm_studio_base_url", "http://localhost:1234/v1")
            )
            
            if success and result:
                # Clean up the title
                title = result.strip().strip('"\'').strip()
                # Limit length
                if len(title) > 50:
                    title = title[:50]
                if title:
                    return title
        except Exception as e:
            print(f"⚠️ Title generation failed: {e}")
        
        # Fallback: first 6 words of prompt
        return self._fallback_title(prompt_text)
    
    def _fallback_title(self, prompt_text: str) -> str:
        """Generate fallback title from first words of prompt"""
        if not prompt_text:
            return "Untitled Conversation"
        
        words = prompt_text.split()[:6]
        title = " ".join(words)
        if len(title) > 40:
            title = title[:40]
        return title + "..." if len(prompt_text.split()) > 6 else title
    
    def show_save_dialog(self, parent: tk.Tk, suggested_title: str,
                         on_save: Callable[[str], None],
                         on_skip: Callable[[], None]) -> None:
        """
        Show dialog asking user if they want to save the standalone conversation.
        
        Args:
            parent: Parent window
            suggested_title: AI-generated or fallback title
            on_save: Callback with final title when user saves
            on_skip: Callback when user skips saving
        """
        dialog = tk.Toplevel(parent)
        dialog.title("Save Conversation?")
        dialog.geometry("450x220")
        dialog.transient(parent)
        dialog.grab_set()
        
        # Center on parent
        dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 450) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 220) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Icon and title
        header_frame = ttk.Frame(dialog)
        header_frame.pack(fill=tk.X, padx=20, pady=(15, 10))
        
        ttk.Label(header_frame, text="💬", font=('Arial', 24)).pack(side=tk.LEFT)
        ttk.Label(header_frame, text="Save Standalone Conversation?", 
                  font=('Arial', 12, 'bold')).pack(side=tk.LEFT, padx=10)
        
        # Explanation
        ttk.Label(dialog, 
                  text="This conversation isn't linked to a source document.\nWould you like to save it to the Documents Library?",
                  font=('Arial', 10)).pack(padx=20, pady=(0, 10))
        
        # Title input
        title_frame = ttk.Frame(dialog)
        title_frame.pack(fill=tk.X, padx=20, pady=5)
        
        ttk.Label(title_frame, text="Title:", font=('Arial', 9)).pack(anchor=tk.W)
        
        title_var = tk.StringVar(value=suggested_title)
        title_entry = ttk.Entry(title_frame, textvariable=title_var, width=50, font=('Arial', 10))
        title_entry.pack(fill=tk.X, pady=(2, 0))
        title_entry.select_range(0, tk.END)
        title_entry.focus_set()
        
        ttk.Label(title_frame, text="(You can edit this title)", 
                  font=('Arial', 8), foreground='gray').pack(anchor=tk.W)
        
        # Buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=20, pady=15)
        
        def do_save():
            title = title_var.get().strip()
            if not title:
                messagebox.showwarning("Title Required", "Please enter a title for the conversation.")
                return
            dialog.destroy()
            on_save(title)
        
        def do_skip():
            dialog.destroy()
            on_skip()
        
        save_btn = ttk.Button(btn_frame, text="💾 Save & Continue", command=do_save, width=18)
        save_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        skip_btn = ttk.Button(btn_frame, text="Skip (Don't Save)", command=do_skip, width=18)
        skip_btn.pack(side=tk.LEFT)
        
        # Bind Enter to save
        title_entry.bind('<Return>', lambda e: do_save())
        dialog.bind('<Escape>', lambda e: do_skip())
        
        # Wait for dialog
        dialog.wait_window()
    
    def save_conversation(self, title: str, current_thread: list,
                          provider: str, model: str,
                          prompt_text: str) -> Optional[str]:
        """
        Save the standalone conversation to the Documents Library.
        
        Creates a document of type 'standalone_conversation' with the thread.
        
        Returns:
            Document ID if successful, None otherwise
        """
        from document_library import add_document_to_library, save_thread_to_document
        
        try:
            # Create document title
            full_title = f"Standalone conversation - {title}"
            
            # The "content" is the original prompt (so there's something to show in preview)
            entries = [{"text": prompt_text, "location": "Original prompt"}]
            
            # Create the document
            doc_id = add_document_to_library(
                doc_type="standalone_conversation",
                source="Standalone conversation",
                title=full_title,
                entries=entries,
                document_class="product",  # Editable
                metadata={
                    "editable": True,
                    "standalone": True,
                    "created": datetime.datetime.now().isoformat()
                }
            )
            
            if doc_id:
                # Save the thread
                thread_metadata = {
                    'model': model,
                    'provider': provider,
                    'last_updated': datetime.datetime.now().isoformat(),
                    'message_count': len([m for m in current_thread if m.get('role') == 'user']),
                    'standalone': True
                }
                
                save_thread_to_document(doc_id, current_thread, thread_metadata)
                
                self.conversation_saved = True
                self.saved_document_id = doc_id
                
                print(f"✅ Standalone conversation saved: {full_title}")
                return doc_id
            
        except Exception as e:
            print(f"❌ Failed to save standalone conversation: {e}")
            import traceback
            traceback.print_exc()
        
        return None


# Global instance
_manager = StandaloneConversationManager()


def get_standalone_manager() -> StandaloneConversationManager:
    """Get the global standalone conversation manager"""
    return _manager


def check_and_prompt_standalone_save(
    parent: tk.Tk,
    current_document_id: Optional[str],
    current_thread: list,
    thread_message_count: int,
    provider: str,
    model: str,
    api_key: str,
    config: dict,
    ai_handler,
    on_complete: Callable[[bool, Optional[str]], None]
) -> bool:
    """
    Check if we're in standalone mode and prompt to save if so.
    
    Args:
        parent: Parent window
        current_document_id: Current document ID (None if standalone)
        current_thread: Current conversation thread
        thread_message_count: Number of messages in thread
        provider: AI provider name
        model: AI model name  
        api_key: API key
        config: App config
        ai_handler: AI handler for title generation
        on_complete: Callback(was_saved, doc_id) called when done
    
    Returns:
        True if dialog was shown (caller should wait), False if not standalone
    """
    print(f"\n📞 check_and_prompt_standalone_save CALLED")
    
    manager = get_standalone_manager()
    
    if not manager.is_standalone_conversation(current_document_id, current_thread, thread_message_count):
        # Not standalone - proceed normally
        # DON'T call on_complete here - caller will handle it when we return False
        print("   → Not standalone, returning False")
        return False
    
    print("   → IS standalone, showing dialog...")
    
    # Extract prompt and response from thread
    prompt_text = ""
    response_text = ""
    for msg in current_thread:
        if msg.get('role') == 'user' and not prompt_text:
            prompt_text = msg.get('content', '')
        elif msg.get('role') == 'assistant' and not response_text:
            response_text = msg.get('content', '')
    
    print(f"   → Prompt: {prompt_text[:50]}...")
    print(f"   → Response: {response_text[:50]}...")
    
    # Generate title
    parent.config(cursor="wait")
    parent.update()
    
    suggested_title = manager.generate_title_with_ai(
        prompt_text, response_text, provider, model, api_key, ai_handler, config
    )
    
    parent.config(cursor="")
    
    print(f"   → Suggested title: {suggested_title}")
    
    def on_save(title: str):
        doc_id = manager.save_conversation(
            title=title,
            current_thread=current_thread,
            provider=provider,
            model=model,
            prompt_text=prompt_text
        )
        on_complete(True, doc_id)
    
    def on_skip():
        on_complete(False, None)
    
    # Show dialog
    manager.show_save_dialog(parent, suggested_title, on_save, on_skip)
    
    return True


def reset_standalone_state():
    """Reset standalone conversation state (call when loading new document)"""
    print("🔄 reset_standalone_state() called")
    get_standalone_manager().reset()
