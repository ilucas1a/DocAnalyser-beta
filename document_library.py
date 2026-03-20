"""
document_library.py - Document Library Management
Handles document storage, retrieval, and processed outputs management

VERSION 2.0: Now supports document_class field for source vs product documents
VERSION 2.2-DEBUG: COMPREHENSIVE debug logging for branch/pre_created tracking
"""

import os
import sys
import json
import hashlib
import datetime
from typing import Dict, List, Optional, Tuple

# Import from our modules
from config import *
from utils import save_json_atomic

def _safe_flush():
    """Safely flush stdout - no-op if stdout is not a real file handle (e.g. Windows GUI)."""
    try:
        _out = sys.stdout
        if _out and hasattr(_out, 'flush'):
            _out.flush()
    except (OSError, AttributeError, ValueError):
        pass
from document_fetcher import clean_text_encoding

# --- SQLite feature flag (Stage B) ---
# Set to False to revert to embeddings.json file-based storage
USE_SQLITE_EMBEDDINGS = True

# --- SQLite feature flag (Stage D) ---
# Set to False to revert to document_library.json file-based storage
USE_SQLITE_DOCUMENTS = True


def _db_doc_to_lib_format(db_doc: dict) -> dict:
    """Convert a db_manager document dict to the JSON library format
    that all existing callers expect.

    Mapping:
        doc_type   -> type
        created_at -> fetched
    """
    if db_doc is None:
        return None
    return {
        "id":             db_doc.get("id"),
        "type":           db_doc.get("doc_type", db_doc.get("type", "")),
        "source":         db_doc.get("source", ""),
        "title":          db_doc.get("title", ""),
        "fetched":        db_doc.get("created_at", db_doc.get("fetched", "")),
        "entry_count":    db_doc.get("entry_count", 0),
        "metadata":       db_doc.get("metadata") or {},
        "document_class": db_doc.get("document_class", "source"),
    }


class SqliteEmbeddingStorage:
    """
    Drop-in adapter matching ChunkEmbeddingStorage interface
    but backed by SQLite via db_manager.
    Passed to search_chunks() and other consumers unchanged.
    """

    def __init__(self):
        import db_manager as db
        db.init_database()
        self._db = db

    def has_embedding(self, doc_id: str) -> bool:
        return self._db.db_has_embeddings(doc_id)

    def add_document_chunks(self, doc_id, chunks, embeddings, total_cost=0.0):
        self._db.db_save_embeddings(
            doc_id=doc_id, chunks=chunks,
            embeddings=embeddings, cost=total_cost,
            model="text-embedding-3-small",
        )

    def save(self):
        pass  # SQLite commits inside db_manager

    def get_document_chunks(self, doc_id):
        return self._db.db_get_embeddings(doc_id) or None

    def remove_embedding(self, doc_id):
        self._db.db_delete_embeddings(doc_id)

    def get_all_chunks_flat(self):
        return self._db.db_get_all_embeddings_flat()

    def get_stats(self):
        rows = self._db.db_get_all_embeddings_flat()
        doc_ids = set(r["doc_id"] for r in rows)
        total_cost_rows = self._db.get_connection().execute(
            "SELECT COALESCE(SUM(cost), 0) as total FROM embeddings"
        ).fetchone()
        return {
            "total_documents": len(doc_ids),
            "total_chunks": len(rows),
            "total_cost": total_cost_rows["total"] if total_cost_rows else 0.0,
            "provider": "openai",
            "model": "text-embedding-3-small",
            "avg_chunks_per_doc": len(rows) / len(doc_ids) if doc_ids else 0,
        }


def _get_embedding_storage():
    """Return the correct embedding storage backend."""
    if USE_SQLITE_EMBEDDINGS:
        return SqliteEmbeddingStorage()
    from semantic_search import ChunkEmbeddingStorage
    return ChunkEmbeddingStorage(get_embeddings_path())



# -------------------------
# Library Configuration
# -------------------------

def ensure_library():
    """Ensure library file exists with proper structure"""
    if not os.path.exists(LIBRARY_PATH):
        save_json_atomic(LIBRARY_PATH, {"documents": []})


def load_library() -> Dict:
    """Load the document library from disk"""
    ensure_library()
    try:
        with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        save_json_atomic(LIBRARY_PATH, {"documents": []})
        return {"documents": []}


def save_library(library: Dict):
    """Save the document library to disk"""
    save_json_atomic(LIBRARY_PATH, library)


# -------------------------
# Document Management
# -------------------------

def generate_doc_id(source: str, doc_type: str) -> str:
    """
    Generate a unique document ID based on source and type

    Args:
        source: Document source (file path, URL, etc.)
        doc_type: Type of document (file, web, youtube, etc.)

    Returns:
        12-character hex string ID
    """
    combined = f"{doc_type}:{source}"
    return hashlib.md5(combined.encode()).hexdigest()[:12]


def add_document_to_library(doc_type: str, source: str, title: str, entries: List[Dict],
                            metadata: Dict = None, document_class: str = "source") -> str:
    """
    Add or update a document in the library

    Args:
        doc_type: Type of document (file, web, youtube, audio, etc.)
        source: Source identifier (file path, URL, etc.)
        title: Document title
        entries: List of document entries/segments
        metadata: Optional metadata dictionary
        document_class: "source" (read-only) or "product" (editable AI output)

    Returns:
        Document ID
    """
    import sys
    
    # === DEBUG: Log incoming call with ALL parameters ===
    print(f"\n{'='*70}")
    print(f"📥 add_document_to_library CALLED (V2.2-DEBUG)")
    print(f"   title: {title}")
    print(f"   doc_type: {doc_type}")
    print(f"   document_class: {document_class}")
    print(f"   source: {source}")
    _safe_flush()
    
    print(f"   metadata type: {type(metadata)}")
    print(f"   entries count: {len(entries) if entries else 0}")
    _safe_flush()
    
    print(f"{'='*70}")
    _safe_flush()

    doc_id = generate_doc_id(source, doc_type)

    # --- SQLite path (Stage D) ---
    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        if metadata is None:
            metadata = {}
        if "editable" not in metadata:
            metadata["editable"] = (document_class == "product")
        # Check if updating an existing document
        existing = db.db_get_document(doc_id)
        if existing:
            metadata["last_edited"] = datetime.datetime.now().isoformat()
        db.db_add_document(
            doc_id=doc_id, doc_type=doc_type, source=source, title=title,
            entry_count=len(entries), metadata=metadata,
            document_class=document_class,
        )
        db.db_save_entries(doc_id, entries)
        print(f"📚 SQLite: saved doc {doc_id} + {len(entries)} entries")
        _safe_flush()
        _trigger_auto_embedding(doc_id)
        return doc_id

    print("📚 Step 1: Calling load_library()...")
    _safe_flush()
    library = load_library()
    print(f"📚 Step 1 DONE: Loaded {len(library.get('documents', []))} documents")
    _safe_flush()
    print("📚 Step 2: Generating doc_id...")
    _safe_flush()
    doc_id = generate_doc_id(source, doc_type)
    print(f"📚 Step 2 DONE: doc_id = {doc_id}")
    _safe_flush()

    # Check if document already exists
    print("📚 Step 3: Checking for existing document...")
    _safe_flush()
    existing_idx = None
    for idx, doc in enumerate(library["documents"]):
        if doc.get("id") == doc_id:
            existing_idx = idx
            break
    print(f"📚 Step 3 DONE: existing_idx = {existing_idx}")
    _safe_flush()

    # Prepare metadata
    if metadata is None:
        metadata = {}
    
    # Set editable flag based on document_class
    if "editable" not in metadata:
        metadata["editable"] = (document_class == "product")
    
    # Add last_edited timestamp if this is an existing document being updated
    if existing_idx is not None:
        metadata["last_edited"] = datetime.datetime.now().isoformat()

    # Create document metadata
    doc_data = {
        "id": doc_id,
        "type": doc_type,
        "document_class": document_class,  # NEW: "source" or "product"
        "source": source,
        "title": title,
        "fetched": datetime.datetime.now().isoformat(),
        "entry_count": len(entries),
        "metadata": metadata
    }

    # === DEBUG: Log what we're about to save ===
    print(f"   📝 SAVING doc_data:")
    print(f"      doc_id: {doc_id}")
    print(f"      metadata being saved: {doc_data.get('metadata')}")
    print(f"      pre_created in saved metadata: {doc_data.get('metadata', {}).get('pre_created', '🚫 NOT PRESENT')}")

    # Save entries to separate file
    print("📚 Step 4: Saving entries file...")
    _safe_flush()
    entries_file = os.path.join(DATA_DIR, f"doc_{doc_id}_entries.json")
    save_json_atomic(entries_file, entries)
    print(f"📚 Step 4 DONE: Saved to {entries_file}")
    _safe_flush()

    # Update or add document
    if existing_idx is not None:
        library["documents"][existing_idx] = doc_data
        print(f"   ✅ UPDATED existing document at index {existing_idx}")
    else:
        library["documents"].append(doc_data)
        print(f"   ✅ ADDED new document (total docs: {len(library['documents'])})")

    # No limit - keep all documents!
    # Users can manage their library via the cache manager if needed

    print("📚 Step 5: Saving library...")
    _safe_flush()
    save_library(library)
    print("📚 Step 5 DONE: Library saved")
    _safe_flush()
    
    # === DEBUG: Verify it was saved correctly ===
    verify_lib = load_library()
    for vdoc in verify_lib["documents"]:
        if vdoc.get("id") == doc_id:
            print(f"   🔍 VERIFY after save:")
            print(f"      metadata in library: {vdoc.get('metadata')}")
            print(f"      pre_created value: {vdoc.get('metadata', {}).get('pre_created', '🚫 NOT FOUND')}")
            break
    print(f"{'='*70}\n")
    
    # Auto-generate embedding if enabled
    print("📚 Step 6: Triggering auto-embedding...")
    _safe_flush()
    _trigger_auto_embedding(doc_id)
    print("📚 Step 6 DONE")
    _safe_flush()
    
    print(f"📚 ✅ add_document_to_library COMPLETE - returning {doc_id}")
    _safe_flush()
    return doc_id


def _trigger_auto_embedding(doc_id: str):
    """
    Trigger automatic embedding generation if enabled in settings.
    Runs in background thread to not block UI.
    
    Args:
        doc_id: Document ID to generate embedding for
    """
    import threading
    from config_manager import load_config
    
    config = load_config()
    
    # Check if auto-embedding is enabled
    if not config.get("auto_generate_embeddings", False):
        return
    
    # Check for OpenAI API key
    openai_key = config.get("keys", {}).get("OpenAI (ChatGPT)", "")
    if not openai_key:
        print("⚠️ Auto-embedding skipped: No OpenAI API key configured")
        return
    
    def generate_in_background():
        try:
            success, msg, cost, chunk_count = generate_embedding_for_doc(doc_id, openai_key)
            if success:
                print(f"✅ Auto-embedded document: {chunk_count} chunks, ${cost:.5f}")
                # Log cost
                from cost_tracker import log_cost
                if cost > 0:
                    log_cost(
                        provider="OpenAI (ChatGPT)",
                        model="text-embedding-3-small",
                        cost=cost,
                        document_title=f"Auto-embed (doc {doc_id[:8]})",
                        prompt_name="auto_embedding"
                    )
            else:
                print(f"⚠️ Auto-embedding failed: {msg}")
        except Exception as e:
            print(f"❌ Auto-embedding error: {str(e)}")
    
    # Run in background thread
    thread = threading.Thread(target=generate_in_background, daemon=True)
    thread.start()



def update_document_entries(doc_id: str, new_entries: List[Dict]) -> bool:
    """
    Update the entries for an existing document
    
    Args:
        doc_id: Document ID
        new_entries: New list of entries to save
        
    Returns:
        True if successful, False otherwise
    """
    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        doc = db.db_get_document(doc_id)
        if not doc:
            return False
        # Check if document is editable
        meta = doc.get("metadata") or {}
        if not meta.get("editable", False):
            print(f"Warning: Attempted to edit non-editable document {doc_id}")
            return False
        meta["last_edited"] = datetime.datetime.now().isoformat()
        db.db_save_entries(doc_id, new_entries)
        db.db_update_document(doc_id, entry_count=len(new_entries), metadata=meta)
        return True

    library = load_library()
    
    # Find the document
    doc_idx = None
    for idx, doc in enumerate(library["documents"]):
        if doc.get("id") == doc_id:
            doc_idx = idx
            break
    
    if doc_idx is None:
        return False
    
    # Check if document is editable
    if not library["documents"][doc_idx].get("metadata", {}).get("editable", False):
        print(f"Warning: Attempted to edit non-editable document {doc_id}")
        return False
    
    # Update entry count and last_edited timestamp
    library["documents"][doc_idx]["entry_count"] = len(new_entries)
    library["documents"][doc_idx]["metadata"]["last_edited"] = datetime.datetime.now().isoformat()
    
    # Save updated entries to file
    entries_file = os.path.join(DATA_DIR, f"doc_{doc_id}_entries.json")
    save_json_atomic(entries_file, new_entries)
    
    # Save library
    save_library(library)
    
    return True


def convert_document_to_source(doc_id: str) -> bool:
    """
    Convert a product document to a source document (makes it read-only)
    
    Args:
        doc_id: Document ID
        
    Returns:
        True if successful, False otherwise
    """
    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        doc = db.db_get_document(doc_id)
        if not doc:
            return False
        meta = doc.get("metadata") or {}
        meta["editable"] = False
        meta["converted_to_source"] = datetime.datetime.now().isoformat()
        return db.db_update_document(doc_id, document_class="source", metadata=meta)

    library = load_library()
    
    # Find the document
    doc_idx = None
    for idx, doc in enumerate(library["documents"]):
        if doc.get("id") == doc_id:
            doc_idx = idx
            break
    
    if doc_idx is None:
        return False
    
    # Update document class and editable flag
    library["documents"][doc_idx]["document_class"] = "source"
    library["documents"][doc_idx]["metadata"]["editable"] = False
    library["documents"][doc_idx]["metadata"]["converted_to_source"] = datetime.datetime.now().isoformat()
    
    # Save library
    save_library(library)
    
    return True


def load_document_entries(doc_id: str) -> Optional[List[Dict]]:
    """
    Load document entries from disk

    Args:
        doc_id: Document ID

    Returns:
        List of entries or None if not found
    """
    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        entries = db.db_get_entries(doc_id)
        if entries:
            for entry in entries:
                if 'text' in entry and isinstance(entry['text'], str):
                    entry['text'] = clean_text_encoding(entry['text'])
        return entries

    entries_file = os.path.join(DATA_DIR, f"doc_{doc_id}_entries.json")
    if not os.path.exists(entries_file):
        return None

    try:
        with open(entries_file, "r", encoding="utf-8") as f:
            entries = json.load(f)

        # Clean up text in entries
        for entry in entries:
            if 'text' in entry and isinstance(entry['text'], str):
                entry['text'] = clean_text_encoding(entry['text'])

        return entries
    except Exception:
        return None


def get_recent_documents(limit: int = 10) -> List[Dict]:
    """
    Get most recently added/updated documents

    Args:
        limit: Maximum number of documents to return

    Returns:
        List of document metadata dictionaries
    """
    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        # db_get_all_documents already returns newest first
        all_docs = db.db_get_all_documents()
        return [_db_doc_to_lib_format(d) for d in all_docs[:limit]]

    library = load_library()
    docs = library.get("documents", [])
    sorted_docs = sorted(docs, key=lambda x: x.get("fetched", ""), reverse=True)
    return sorted_docs[:limit]


def get_document_count() -> int:
    """
    Get the total number of documents in the library.
    
    Returns:
        Total document count
    """
    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        return db.db_get_document_count()

    library = load_library()
    return len(library.get("documents", []))


def get_document_by_id(doc_id: str) -> Optional[Dict]:
    """
    Get a document from the library by ID

    Args:
        doc_id: Document ID

    Returns:
        Document metadata dictionary or None if not found
    """
    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        row = db.db_get_document(doc_id)
        return _db_doc_to_lib_format(row) if row else None

    library = load_library()
    for doc in library["documents"]:
        if doc.get("id") == doc_id:
            return doc
    return None


def get_all_documents() -> List[Dict]:
    """
    Get all documents in the library

    Returns:
        List of all document metadata dictionaries
    """
    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        return [_db_doc_to_lib_format(d) for d in db.db_get_all_documents()]

    library = load_library()
    return library.get("documents", [])


def rename_document(doc_id: str, new_title: str) -> bool:
    """
    Rename a document in the library.
    
    Args:
        doc_id: Document ID
        new_title: New title for the document
    
    Returns:
        True if successful, False otherwise
    """
    if not new_title or not new_title.strip():
        return False

    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        doc = db.db_get_document(doc_id)
        if not doc:
            return False
        old_title = doc.get("title", "Untitled")
        meta = doc.get("metadata") or {}
        meta["title"] = new_title.strip()
        meta["original_title"] = old_title
        meta["renamed_date"] = datetime.datetime.now().isoformat()
        return db.db_update_document(doc_id, title=new_title.strip(), metadata=meta)

    library = load_library()
    
    for doc in library["documents"]:
        if doc.get("id") == doc_id:
            old_title = doc.get("title", "Untitled")
            doc["title"] = new_title.strip()
            
            # Also update title in metadata if present
            if "metadata" in doc and isinstance(doc["metadata"], dict):
                doc["metadata"]["title"] = new_title.strip()
                doc["metadata"]["original_title"] = old_title
                doc["metadata"]["renamed_date"] = datetime.datetime.now().isoformat()
            
            save_library(library)
            return True
    
    return False

def delete_document(doc_id: str) -> bool:
    """
    Delete a document and all its associated data

    Args:
        doc_id: Document ID

    Returns:
        True if successful, False otherwise
    """
    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        # Soft-delete in DB (entries, conversations, outputs cascade)
        result = db.db_delete_document(doc_id, hard=False)
        # Also clean up any JSON entries file that may exist from before migration
        entries_file = os.path.join(DATA_DIR, f"doc_{doc_id}_entries.json")
        if os.path.exists(entries_file):
            try:
                os.remove(entries_file)
            except Exception:
                pass
        return result

    library = load_library()

    # Find and remove the document
    doc_idx = None
    for idx, doc in enumerate(library["documents"]):
        if doc.get("id") == doc_id:
            doc_idx = idx
            break

    if doc_idx is None:
        return False

    # Remove document from library
    library["documents"].pop(doc_idx)
    save_library(library)

    # Delete entries file
    entries_file = os.path.join(DATA_DIR, f"doc_{doc_id}_entries.json")
    if os.path.exists(entries_file):
        try:
            os.remove(entries_file)
        except Exception:
            pass

    # Delete all processed outputs for this document
    outputs = get_processed_outputs_for_document(doc_id)
    for output in outputs:
        delete_processed_output(doc_id, output.get("id"))

    return True


# -------------------------
# Processed Outputs Management
# -------------------------

def add_processed_output_to_document(doc_id: str, prompt_name: str, prompt_text: str,
                                     provider: str, model: str, output_text: str,
                                     notes: str = "") -> Optional[str]:
    """
    Add a processed output (AI summary, analysis, etc.) to a document

    Args:
        doc_id: Document ID
        prompt_name: Name of the prompt used
        prompt_text: Full prompt text
        provider: AI provider name (OpenAI, Anthropic, etc.)
        model: Model name
        output_text: Generated output text
        notes: Optional user notes

    Returns:
        Output ID if successful, None otherwise
    """
    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        if not db.db_get_document(doc_id):
            return None
        output_id = hashlib.md5(
            f"{doc_id}_{datetime.datetime.now().isoformat()}".encode()
        ).hexdigest()[:12]
        db.db_add_processed_output(
            doc_id=doc_id, output_id=output_id,
            prompt_name=prompt_name, prompt_text=prompt_text,
            provider=provider, model=model,
            output_text=output_text, notes=notes,
        )
        return output_id

    library = load_library()

    # Find the document
    doc_idx = None
    for idx, doc in enumerate(library["documents"]):
        if doc.get("id") == doc_id:
            doc_idx = idx
            break

    if doc_idx is None:
        return None

    # Ensure processed_outputs list exists
    if "processed_outputs" not in library["documents"][doc_idx]:
        library["documents"][doc_idx]["processed_outputs"] = []

    # Create output ID
    output_id = hashlib.md5(f"{doc_id}_{datetime.datetime.now().isoformat()}".encode()).hexdigest()[:12]

    # Create output metadata
    output_data = {
        "id": output_id,
        "timestamp": datetime.datetime.now().isoformat(),
        "prompt_name": prompt_name,
        "prompt_text": prompt_text,
        "provider": provider,
        "model": model,
        "notes": notes,
        "preview": output_text[:200] + "..." if len(output_text) > 200 else output_text
    }

    # Save full output to separate file
    output_file = os.path.join(DATA_DIR, f"output_{output_id}.txt")
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output_text)
    except Exception as e:
        print(f"Warning: Could not save output file: {e}")
        return None

    # Add to library
    library["documents"][doc_idx]["processed_outputs"].append(output_data)
    save_library(library)

    return output_id


def get_processed_outputs_for_document(doc_id: str) -> List[Dict]:
    """
    Get all processed outputs for a document

    Args:
        doc_id: Document ID

    Returns:
        List of output metadata dictionaries
    """
    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        rows = db.db_get_processed_outputs(doc_id)
        # Map DB keys to the format UI callers expect
        return [{
            "id": r.get("id"),
            "timestamp": r.get("created_at", ""),
            "prompt_name": r.get("prompt_name", ""),
            "prompt_text": r.get("prompt_text", ""),
            "provider": r.get("provider", ""),
            "model": r.get("model", ""),
            "notes": r.get("notes", ""),
            "preview": r.get("preview", ""),
        } for r in rows]

    library = load_library()

    for doc in library["documents"]:
        if doc.get("id") == doc_id:
            return doc.get("processed_outputs", [])

    return []


def load_processed_output(output_id: str) -> Optional[str]:
    """
    Load the full text of a processed output

    Args:
        output_id: Output ID

    Returns:
        Output text or None if not found
    """
    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        return db.db_load_processed_output(output_id)

    output_file = os.path.join(DATA_DIR, f"output_{output_id}.txt")
    if not os.path.exists(output_file):
        return None

    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return None


def delete_processed_output(doc_id: str, output_id: str) -> bool:
    """
    Delete a processed output from a document

    Args:
        doc_id: Document ID
        output_id: Output ID

    Returns:
        True if successful, False otherwise
    """
    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        return db.db_delete_processed_output(doc_id, output_id)

    library = load_library()

    # Find the document
    doc_idx = None
    for idx, doc in enumerate(library["documents"]):
        if doc.get("id") == doc_id:
            doc_idx = idx
            break

    if doc_idx is None:
        return False

    # Find and remove the output
    outputs = library["documents"][doc_idx].get("processed_outputs", [])
    for idx, output in enumerate(outputs):
        if output.get("id") == output_id:
            outputs.pop(idx)
            library["documents"][doc_idx]["processed_outputs"] = outputs
            save_library(library)

            # Delete the output file
            output_file = os.path.join(DATA_DIR, f"output_{output_id}.txt")
            if os.path.exists(output_file):
                try:
                    os.remove(output_file)
                except Exception:
                    pass

            return True

    return False


# -------------------------
# Library Statistics & Utilities
# -------------------------

def get_library_stats() -> Dict:
    """
    Get statistics about the document library

    Returns:
        Dictionary with library statistics
    """
    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        all_docs = db.db_get_all_documents()
        doc_types = {}
        doc_classes = {"source": 0, "product": 0}
        total_outputs = 0
        for d in all_docs:
            dt = d.get("doc_type", "unknown")
            doc_types[dt] = doc_types.get(dt, 0) + 1
            dc = d.get("document_class", "source")
            doc_classes[dc] = doc_classes.get(dc, 0) + 1
            outputs = db.db_get_processed_outputs(d["id"])
            total_outputs += len(outputs)
        return {
            "total_documents": len(all_docs),
            "source_documents": doc_classes.get("source", 0),
            "product_documents": doc_classes.get("product", 0),
            "total_processed_outputs": total_outputs,
            "document_types": doc_types,
            "last_updated": datetime.datetime.now().isoformat(),
        }

    library = load_library()
    docs = library.get("documents", [])

    total_outputs = 0
    doc_types = {}
    doc_classes = {"source": 0, "product": 0}

    for doc in docs:
        # Count document types
        doc_type = doc.get("type", "unknown")
        doc_types[doc_type] = doc_types.get(doc_type, 0) + 1
        
        # Count document classes
        doc_class = doc.get("document_class", "source")
        doc_classes[doc_class] = doc_classes.get(doc_class, 0) + 1

        # Count processed outputs
        total_outputs += len(doc.get("processed_outputs", []))

    return {
        "total_documents": len(docs),
        "source_documents": doc_classes.get("source", 0),
        "product_documents": doc_classes.get("product", 0),
        "total_processed_outputs": total_outputs,
        "document_types": doc_types,
        "last_updated": datetime.datetime.now().isoformat()
    }


def search_documents(query: str, search_in: str = "all") -> List[Dict]:
    """
    Search documents by title, source, or type

    Args:
        query: Search query string
        search_in: Where to search ("title", "source", "type", or "all")

    Returns:
        List of matching document metadata dictionaries
    """
    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        results = [_db_doc_to_lib_format(d) for d in db.db_search_documents(query)]
        # db_search_documents searches all fields; filter if caller wants specific field
        if search_in == "title":
            results = [r for r in results if query.lower() in r.get("title", "").lower()]
        elif search_in == "source":
            results = [r for r in results if query.lower() in r.get("source", "").lower()]
        elif search_in == "type":
            results = [r for r in results if query.lower() in r.get("type", "").lower()]
        return results

    library = load_library()
    docs = library.get("documents", [])
    query_lower = query.lower()

    results = []
    for doc in docs:
        match = False

        if search_in in ["title", "all"]:
            if query_lower in doc.get("title", "").lower():
                match = True

        if search_in in ["source", "all"]:
            if query_lower in doc.get("source", "").lower():
                match = True

        if search_in in ["type", "all"]:
            if query_lower in doc.get("type", "").lower():
                match = True

        if match:
            results.append(doc)

    return results


# -------------------------
# Thread Persistence Management
# -------------------------

def save_thread_to_document(doc_id: str, thread: List[Dict], thread_metadata: Dict = None) -> bool:
    """
    Save conversation thread to a document

    Args:
        doc_id: Document ID
        thread: List of thread messages (role, content)
        thread_metadata: Optional metadata (model, provider, timestamps)

    Returns:
        True if successful
        
    Note: Threads should only be saved to Response/Thread documents, not Source documents.
          Source documents should remain clean - use save_thread_as_new_document instead
          to create a new response document linked to the source.
    """
    # Check if this is a source document - warn but allow for backward compatibility
    if is_source_document(doc_id):
        print(f"⚠️ WARNING: Saving thread to source document {doc_id}. "
              f"Consider using save_thread_as_new_document instead.")

    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        doc = db.db_get_document(doc_id)
        if not doc:
            return False
        if thread_metadata is None:
            thread_metadata = {}
        thread_metadata["last_updated"] = datetime.datetime.now().isoformat()
        thread_metadata["message_count"] = len([m for m in thread if m.get("role") == "user"])
        db.db_save_conversation(doc_id, thread, thread_metadata)
        # Clear pre_created flag if thread has user messages
        user_msg_count = len([m for m in thread if m.get("role") == "user"])
        if user_msg_count > 0:
            meta = doc.get("metadata") or {}
            if meta.get("pre_created", False):
                meta["pre_created"] = False
                db.db_update_document(doc_id, metadata=meta)
        return True

    library = load_library()

    # Find document
    doc_idx = None
    for idx, doc in enumerate(library["documents"]):
        if doc.get("id") == doc_id:
            doc_idx = idx
            break

    if doc_idx is None:
        return False

    # Prepare thread metadata
    if thread_metadata is None:
        thread_metadata = {}

    thread_metadata["last_updated"] = datetime.datetime.now().isoformat()
    thread_metadata["message_count"] = len([m for m in thread if m.get("role") == "user"])

    # Save thread data
    library["documents"][doc_idx]["conversation_thread"] = thread
    library["documents"][doc_idx]["thread_metadata"] = thread_metadata
    
    # === DEBUG: Log pre_created clearing ===
    user_msg_count = len([m for m in thread if m.get("role") == "user"])
    print(f"\n🔧 save_thread_to_document (V2.2-DEBUG):")
    print(f"   doc_id: {doc_id}")
    print(f"   user messages in thread: {user_msg_count}")
    
    # Clear pre_created flag if this thread now has content
    # This removes the "processing" indicator from the branch selector
    if user_msg_count > 0:
        metadata = library["documents"][doc_idx].get("metadata", {})
        pre_created_before = metadata.get("pre_created", "NOT SET")
        print(f"   pre_created BEFORE: {pre_created_before}")
        if metadata.get("pre_created", False):
            metadata["pre_created"] = False
            library["documents"][doc_idx]["metadata"] = metadata
            print(f"   ✅ CLEARED pre_created flag (was True, now False)")
        else:
            print(f"   ℹ️ pre_created was already False or not set")

    save_library(library)
    return True


def load_thread_from_document(doc_id: str) -> tuple[Optional[List[Dict]], Optional[Dict]]:
    """
    Load conversation thread from a document

    Args:
        doc_id: Document ID

    Returns:
        Tuple of (thread messages list, thread metadata dict) or (None, None)
    """
    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        conv = db.db_get_conversation(doc_id)
        if conv and conv.get("messages"):
            return conv["messages"], conv.get("metadata", {})
        return None, None

    library = load_library()

    for doc in library["documents"]:
        if doc.get("id") == doc_id:
            thread = doc.get("conversation_thread", [])
            metadata = doc.get("thread_metadata", {})

            if thread:
                return thread, metadata
            else:
                return None, None

    return None, None


def clear_thread_from_document(doc_id: str) -> bool:
    """
    Clear conversation thread from a document

    Args:
        doc_id: Document ID

    Returns:
        True if successful
    """
    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        return db.db_clear_conversation(doc_id)

    library = load_library()

    doc_idx = None
    for idx, doc in enumerate(library["documents"]):
        if doc.get("id") == doc_id:
            doc_idx = idx
            break

    if doc_idx is None:
        return False

    # Clear thread data
    if "conversation_thread" in library["documents"][doc_idx]:
        del library["documents"][doc_idx]["conversation_thread"]
    if "thread_metadata" in library["documents"][doc_idx]:
        del library["documents"][doc_idx]["thread_metadata"]

    save_library(library)
    return True


"""
Thread Persistence Functions for document_library.py

Add these functions to your document_library.py file.
These will enable saving and loading conversation threads with documents.
"""

import datetime
import json




def save_thread_as_new_document(original_doc_id: str, thread: list, metadata: dict) -> str:
    """
    Save a conversation thread as a NEW document in the library with [Thread] prefix
    This creates a separate entry so you can have both the original document and the thread

    Args:
        original_doc_id: ID of the original document
        thread: List of message dictionaries
        metadata: Thread metadata

    Returns:
        str: New document ID or None if failed
    """
    try:
        if USE_SQLITE_DOCUMENTS:
            import db_manager as db
            import uuid
            orig = db.db_get_document(original_doc_id)
            if not orig:
                print(f"⚠️ Could not find original document: {original_doc_id}")
                return None
            thread_doc_id = str(uuid.uuid4())
            original_title = orig.get("title", "Unknown Document")
            clean_title = original_title
            for prefix in ("[Source]", "[Product]"):
                if clean_title.startswith(prefix):
                    clean_title = clean_title.replace(prefix, "", 1).strip()
            thread_title = f"[Thread] {clean_title}"
            thread_meta = {
                "original_document_id": original_doc_id,
                "original_title": original_title,
                "model": metadata.get("model", "Unknown"),
                "provider": metadata.get("provider", "Unknown"),
                "message_count": metadata.get("message_count", 0),
                "thread_created": metadata.get("last_updated",
                                               datetime.datetime.now().isoformat()),
            }
            db.db_add_document(
                doc_id=thread_doc_id,
                doc_type="conversation_thread",
                source=f"Thread from: {orig.get('source', 'Unknown')}",
                title=thread_title,
                entry_count=0,
                metadata=thread_meta,
                document_class="thread",
            )
            db.db_save_conversation(thread_doc_id, thread, metadata)
            print(f"✅ SQLite: saved thread as new document: {thread_title}")
            return thread_doc_id

        lib = load_library()
        library = lib.get("documents", [])

        # Find original document to get its info
        original_doc = None
        for doc in library:
            if doc.get("id") == original_doc_id:
                original_doc = doc
                break

        if not original_doc:
            print(f"⚠️ Could not find original document: {original_doc_id}")
            return None

        # Create new document for the thread
        import uuid
        thread_doc_id = str(uuid.uuid4())

        # Format the title with [Thread] prefix
        original_title = original_doc.get("title", "Unknown Document")
        
        # Strip any existing [Source] or other prefixes
        clean_title = original_title
        if clean_title.startswith("[Source]"):
            clean_title = clean_title.replace("[Source]", "", 1).strip()
        if clean_title.startswith("[Product]"):
            clean_title = clean_title.replace("[Product]", "", 1).strip()
        
        thread_title = f"[Thread] {clean_title}"

        # Create thread document entry
        thread_doc = {
            "id": thread_doc_id,
            "title": thread_title,
            "source": f"Thread from: {original_doc.get('source', 'Unknown')}",
            "type": "conversation_thread",
            "document_class": "thread",
            "created": datetime.datetime.now().isoformat(),
            "fetched": datetime.datetime.now().isoformat(),  # Required for library display
            "metadata": {
                "original_document_id": original_doc_id,
                "original_title": original_title,
                "model": metadata.get("model", "Unknown"),
                "provider": metadata.get("provider", "Unknown"),
                "message_count": metadata.get("message_count", 0),
                "thread_created": metadata.get("last_updated", datetime.datetime.now().isoformat())
            },
            "conversation_thread": thread,
            "thread_metadata": metadata,
            # Store the conversation as text for preview
            "text": format_thread_as_text(thread)
        }

        # Add to library
        library.append(thread_doc)
        save_library({"documents": library})

        print(f"✅ Saved thread as new document: {thread_title}")
        return thread_doc_id

    except Exception as e:
        print(f"❌ Error saving thread as document: {e}")
        import traceback
        traceback.print_exc()
        return None


def format_thread_as_text(thread: list) -> str:
    """
    Format a conversation thread as readable text

    Args:
        thread: List of message dictionaries

    Returns:
        str: Formatted conversation text
    """
    lines = []
    lines.append("=" * 80)
    lines.append("CONVERSATION THREAD")
    lines.append("=" * 80)
    lines.append("")

    for i, message in enumerate(thread, 1):
        role = message.get("role", "unknown").upper()
        content = message.get("content", "")

        if role == "USER":
            lines.append(f"[{i}] USER:")
            lines.append("-" * 80)
            lines.append(content)
            lines.append("")
        elif role == "ASSISTANT":
            lines.append(f"[{i}] ASSISTANT:")
            lines.append("-" * 80)
            lines.append(content)
            lines.append("")
        elif role == "SYSTEM":
            lines.append(f"[{i}] SYSTEM:")
            lines.append("-" * 80)
            lines.append(content)
            lines.append("")

    lines.append("=" * 80)
    lines.append(f"END OF CONVERSATION ({len([m for m in thread if m.get('role') == 'user'])} exchanges)")
    lines.append("=" * 80)

    return "\n".join(lines)


def get_threads_for_document(doc_id: str) -> list:
    """
    Get all saved thread documents related to a specific document

    Args:
        doc_id: Original document ID

    Returns:
        list: List of thread documents
    """
    try:
        if USE_SQLITE_DOCUMENTS:
            import db_manager as db
            branches = db.db_get_branches_for_source(doc_id)
            return [_db_doc_to_lib_format(b) for b in branches
                    if b.get("doc_type") == "conversation_thread"]

        lib = load_library()
        library = lib.get("documents", [])
        threads = []

        for doc in library:
            if doc.get("type") == "conversation_thread":
                if doc.get("metadata", {}).get("original_document_id") == doc_id:
                    threads.append(doc)

        return threads

    except Exception as e:
        print(f"⚠️ Warning: Could not get threads: {e}")
        return []


def get_response_branches_for_source(source_doc_id: str) -> List[Dict]:
    """
    Get all response/conversation branches linked to a source document.
    Returns info formatted for the branch picker dialog.
    
    Includes branches that are:
    - Currently processing (pre_created=True but no exchanges yet)
    - Have at least 1 exchange
    
    Args:
        source_doc_id: ID of the source document
        
    Returns:
        List of dicts with branch info:
        [{'doc_id': str, 'title': str, 'exchange_count': int, 'last_updated': str}, ...]
    """
    # === DEBUG: Comprehensive logging ===
    print(f"\n{'='*70}")
    print(f"🔍 get_response_branches_for_source CALLED (V2.2-DEBUG)")
    print(f"   source_doc_id: {source_doc_id}")
    print(f"{'='*70}")
    
    try:
        if USE_SQLITE_DOCUMENTS:
            import db_manager as db
            db_branches = db.db_get_branches_for_source(source_doc_id)
            branches = []
            for bd in db_branches:
                meta = bd.get("metadata") or {}
                # Load conversation to count exchanges
                conv = db.db_get_conversation(bd["id"])
                thread = conv.get("messages", []) if conv else []
                exchange_count = len([m for m in thread if m.get("role") == "user"])
                is_pre_created = meta.get("pre_created", False)
                is_manually_created = meta.get("manually_created", False)
                if exchange_count == 0 and not is_pre_created:
                    continue
                is_processing = (exchange_count == 0 and is_pre_created and not is_manually_created)
                branches.append({
                    'doc_id': bd["id"],
                    'title': bd.get("title", "Untitled"),
                    'exchange_count': exchange_count,
                    'last_updated': bd.get("updated_at") or bd.get("created_at") or "",
                    'is_processing': is_processing,
                })
            branches.sort(key=lambda x: x.get('last_updated') or '', reverse=True)
            return branches

        lib = load_library()
        library = lib.get("documents", [])
        branches = []
        
        # === DEBUG: Count matching documents ===
        matching_docs = []
        for doc in library:
            metadata = doc.get("metadata", {})
            original_id = metadata.get("original_document_id") or metadata.get("parent_document_id")
            if original_id == source_doc_id:
                matching_docs.append(doc)
        
        print(f"   📚 Total docs in library: {len(library)}")
        print(f"   📋 Docs linked to source {source_doc_id}: {len(matching_docs)}")
        
        for doc in library:
            # Check if this document is a response/thread linked to the source
            metadata = doc.get("metadata", {})
            original_id = metadata.get("original_document_id") or metadata.get("parent_document_id")
            
            if original_id == source_doc_id:
                # This is a response document linked to our source
                thread_metadata = doc.get("thread_metadata", {})
                thread = doc.get("conversation_thread", [])
                
                # Count exchanges (user messages)
                exchange_count = len([m for m in thread if m.get("role") == "user"])
                
                # Check if this is a pre-created branch (currently processing)
                is_pre_created = metadata.get("pre_created", False)
                
                # === DEBUG: Log each document's state ===
                print(f"\n   📄 Found linked doc: {doc.get('title')}")
                print(f"      doc_id: {doc.get('id')}")
                print(f"      exchange_count: {exchange_count}")
                print(f"      metadata keys: {list(metadata.keys())}")
                print(f"      pre_created in metadata: {'pre_created' in metadata}")
                print(f"      pre_created value: {is_pre_created}")
                print(f"      type(pre_created): {type(is_pre_created)}")
                
                # Skip empty documents UNLESS they are pre-created (still processing)
                # or manually created by user. These should be shown so user knows they exist.
                is_manually_created = metadata.get("manually_created", False)
                
                if exchange_count == 0 and not is_pre_created:
                    print(f"      ❌ SKIPPING: exchange_count=0 AND pre_created={is_pre_created}")
                    print(f"ℹ️ Skipping empty response branch: {doc.get('title')} (no exchanges, not pre_created)")
                    continue
                
                if exchange_count == 0 and is_pre_created:
                    print(f"      ✅ INCLUDING: exchange_count=0 BUT pre_created=True (manually_created={is_manually_created})")
                    print(f"ℹ️ Including pre-created branch: {doc.get('title')}")
                
                if exchange_count > 0:
                    print(f"      ✅ INCLUDING: has {exchange_count} exchanges")
                
                # Only show processing indicator for auto-created branches (not manually created ones)
                # Auto-created branches with 0 exchanges are still waiting for AI response
                # Manually created branches with 0 exchanges are just empty and ready for use
                is_processing = (exchange_count == 0 and is_pre_created and not is_manually_created)
                
                branches.append({
                    'doc_id': doc.get('id'),
                    'title': doc.get('title', 'Untitled'),
                    'exchange_count': exchange_count,
                    'last_updated': thread_metadata.get('last_updated', doc.get('fetched', '')),
                    'is_processing': is_processing
                })
        
        # Sort by last_updated (most recent first)
        branches.sort(key=lambda x: x.get('last_updated', ''), reverse=True)
        
        print(f"\n   ✅ RESULT: Returning {len(branches)} branches")
        for b in branches:
            print(f"      - {b['title']} (exchanges={b['exchange_count']}, processing={b.get('is_processing', False)})")
        print(f"{'='*70}\n")
        
        return branches
        
    except Exception as e:
        print(f"⚠️ Warning: Could not get response branches: {e}")
        import traceback
        traceback.print_exc()
        return []


def is_source_document(doc_id: str) -> bool:
    """
    Check if a document is a source document (not a response/thread).
    
    Source documents should never have threads attached directly -
    threads should be attached to response documents instead.
    
    Args:
        doc_id: Document ID to check
        
    Returns:
        True if this is a source document, False if it's a response/thread
    """
    doc = get_document_by_id(doc_id)
    if not doc:
        return False
    
    doc_class = doc.get("document_class", "source")
    doc_type = doc.get("type", "")
    
    # Thread/conversation documents are NOT source documents
    if doc_class in ("thread", "product", "response"):
        return False
    if doc_type == "conversation_thread":
        return False
    
    # Check if this document has a parent (meaning it's a response)
    metadata = doc.get("metadata", {})
    if metadata.get("original_document_id") or metadata.get("parent_document_id"):
        return False
    
    # Default: it's a source document
    return True


def delete_thread_document(thread_doc_id: str) -> bool:
    """
    Delete a thread document from the library

    Args:
        thread_doc_id: Thread document ID

    Returns:
        bool: True if successful
    """
    if USE_SQLITE_DOCUMENTS:
        import db_manager as db
        return db.db_delete_document(thread_doc_id, hard=False)

    try:
        lib = load_library()
        library = lib.get("documents", [])

        # Find and remove thread
        library = [doc for doc in library if doc.get("id") != thread_doc_id]

        save_library({"documents": library})
        print(f"🗑️ Deleted thread document: {thread_doc_id}")
        return True

    except Exception as e:
        print(f"❌ Error deleting thread: {e}")
        return False


# -------------------------
# Semantic Search Integration (Chunk-Level)
# -------------------------

def get_embeddings_path() -> str:
    """Get the path to the embeddings storage file."""
    return os.path.join(DATA_DIR, "embeddings.json")


def get_documents_needing_embeddings() -> List[Dict]:
    """
    Get all documents that don't have embeddings yet.
    
    Returns:
        List of document metadata dicts that need embeddings
    """
    storage = _get_embedding_storage()
    all_docs = get_all_documents()  # respects USE_SQLITE_DOCUMENTS
    
    needs_embedding = []
    for doc in all_docs:
        doc_id = doc.get("id", "")
        if doc_id and not storage.has_embedding(doc_id):
            needs_embedding.append(doc)
    
    return needs_embedding


def get_embedding_stats() -> Dict:
    """
    Get statistics about document embeddings.
    
    Returns:
        Dict with embedding statistics
    """
    storage = _get_embedding_storage()
    all_docs = get_all_documents()  # respects USE_SQLITE_DOCUMENTS
    
    total_docs = len(all_docs)
    indexed_count = 0
    
    for doc in all_docs:
        if storage.has_embedding(doc.get("id", "")):
            indexed_count += 1
    
    stats = storage.get_stats()
    stats["total_library_documents"] = total_docs
    stats["indexed_documents"] = indexed_count
    stats["unindexed_documents"] = total_docs - indexed_count
    stats["coverage_percent"] = (indexed_count / total_docs * 100) if total_docs > 0 else 0
    
    return stats


def perform_semantic_search(query: str, api_key: str, top_k: int = 30, 
                            threshold: float = 0.3) -> List[Dict]:
    """
    Perform chunk-level semantic search across documents.
    
    Args:
        query: Search query text
        api_key: OpenAI API key for generating query embedding
        top_k: Maximum number of chunk results to return
        threshold: Minimum similarity score (0-1)
        
    Returns:
        List of matching chunks with similarity scores and document info
    """
    from semantic_search import SemanticSearch, search_chunks
    
    storage = _get_embedding_storage()
    all_docs = get_all_documents()  # respects USE_SQLITE_DOCUMENTS
    
    # Build doc lookup
    doc_lookup = {doc.get("id", ""): doc for doc in all_docs}
    
    # Generate query embedding
    ss = SemanticSearch(api_key=api_key, provider="openai")
    query_embedding, _ = ss.generate_embedding(query)
    
    # Search chunks
    chunk_results = search_chunks(query_embedding, storage, top_k=top_k, threshold=threshold)
    
    # Group results by document and add document info
    # Also deduplicate - keep best chunk per document
    seen_docs = {}
    formatted_results = []
    
    for result in chunk_results:
        doc_id = result["doc_id"]
        doc = doc_lookup.get(doc_id, {})
        
        result_entry = {
            "doc_id": doc_id,
            "chunk_idx": result["chunk_idx"],
            "chunk_text": result["text"],
            "score": result["score"],
            "score_percent": result["score_percent"],
            "title": doc.get("title", "Unknown"),
            "type": doc.get("type", "unknown"),
            "source": doc.get("source", ""),
            "fetched": doc.get("fetched", ""),
            "document": doc
        }
        
        # Track best result per document
        if doc_id not in seen_docs:
            seen_docs[doc_id] = len(formatted_results)
            formatted_results.append(result_entry)
        else:
            # Update if this chunk has better score (shouldn't happen as results are sorted)
            existing_idx = seen_docs[doc_id]
            if result["score"] > formatted_results[existing_idx]["score"]:
                formatted_results[existing_idx] = result_entry
    
    return formatted_results


def perform_semantic_search_all_chunks(query: str, api_key: str, top_k: int = 50, 
                                       threshold: float = 0.3) -> List[Dict]:
    """
    Perform chunk-level semantic search returning ALL matching chunks.
    (Not grouped by document - shows every matching paragraph)
    
    Args:
        query: Search query text
        api_key: OpenAI API key
        top_k: Maximum chunks to return
        threshold: Minimum similarity score
        
    Returns:
        List of matching chunks with scores
    """
    from semantic_search import SemanticSearch, search_chunks
    
    storage = _get_embedding_storage()
    all_docs = get_all_documents()  # respects USE_SQLITE_DOCUMENTS
    doc_lookup = {doc.get("id", ""): doc for doc in all_docs}
    
    # Generate query embedding
    ss = SemanticSearch(api_key=api_key, provider="openai")
    query_embedding, _ = ss.generate_embedding(query)
    
    # Search chunks
    chunk_results = search_chunks(query_embedding, storage, top_k=top_k, threshold=threshold)
    
    # Add document info to each chunk
    for result in chunk_results:
        doc = doc_lookup.get(result["doc_id"], {})
        result["title"] = doc.get("title", "Unknown")
        result["type"] = doc.get("type", "unknown")
        result["document"] = doc
    
    return chunk_results


def generate_embedding_for_doc(doc_id: str, api_key: str, 
                               chunk_size: int = 400) -> Tuple[bool, str, float, int]:
    """
    Generate and store chunk-level embeddings for a document.
    
    Args:
        doc_id: Document ID
        api_key: OpenAI API key
        chunk_size: Target words per chunk
        
    Returns:
        Tuple of (success, message, cost, chunk_count)
    """
    from semantic_search import SemanticSearch, chunk_text_simple
    from utils import entries_to_text
    
    # Load document
    doc = get_document_by_id(doc_id)
    if not doc:
        return False, "Document not found", 0.0, 0
    
    # Load entries and convert to text
    entries = load_document_entries(doc_id)
    if not entries:
        return False, "No entries found for document", 0.0, 0
    
    text = entries_to_text(entries)
    if not text or len(text.strip()) < 50:
        return False, "Document text too short", 0.0, 0
    
    # Add title for better context
    title = doc.get("title", "")
    if title:
        text = f"{title}\n\n{text}"
    
    try:
        # Chunk the text
        chunks = chunk_text_simple(text, chunk_size=chunk_size)
        
        if not chunks:
            return False, "Could not create chunks from document", 0.0, 0
        
        # Generate embeddings for all chunks
        ss = SemanticSearch(api_key=api_key, provider="openai")
        
        # Use batch API for efficiency (up to 20 at a time)
        all_embeddings = []
        total_cost = 0.0
        batch_size = 20
        
        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i:i+batch_size]
            batch_texts = [c["text"] for c in batch_chunks]
            
            embeddings, cost = ss.generate_embeddings_batch(batch_texts)
            all_embeddings.extend(embeddings)
            total_cost += cost
        
        # Store in chunk storage
        storage = _get_embedding_storage()
        storage.add_document_chunks(doc_id, chunks, all_embeddings, total_cost=total_cost)
        storage.save()
        
        return True, f"Created {len(chunks)} chunks", total_cost, len(chunks)
        
    except Exception as e:
        return False, f"Error: {str(e)}", 0.0, 0


def remove_embedding_for_doc(doc_id: str) -> bool:
    """
    Remove the embeddings for a document.
    
    Args:
        doc_id: Document ID
        
    Returns:
        True if removed, False otherwise
    """
    storage = _get_embedding_storage()
    if storage.has_embedding(doc_id):
        storage.remove_embedding(doc_id)
        storage.save()
        return True
    return False


def has_embedding(doc_id: str) -> bool:
    """
    Check if a document has embeddings.
    
    Args:
        doc_id: Document ID
        
    Returns:
        True if embedding exists
    """
    storage = _get_embedding_storage()
    return storage.has_embedding(doc_id)


def get_document_chunk_count(doc_id: str) -> int:
    """
    Get the number of chunks for a document.
    
    Args:
        doc_id: Document ID
        
    Returns:
        Number of chunks, or 0 if not indexed
    """
    storage = _get_embedding_storage()
    chunks = storage.get_document_chunks(doc_id)
    return len(chunks) if chunks else 0


# Example usage:
"""
# In Main.py, you can use these functions like this:

# 1. Auto-save thread when switching documents (already implemented):
self.save_current_thread()  # Saves to the current document

# 2. Load saved thread when opening a document (already implemented):
self.load_saved_thread()  # Loads from the current document

# 3. Save thread as a separate library entry:
def save_thread_to_library(self):
    '''Save current thread as a new document with [Thread] prefix'''
    if not self.current_document_id or not self.current_thread:
        messagebox.showinfo("No Thread", "No conversation thread to save.")
        return

    metadata = {
        "model": self.model_var.get(),
        "provider": self.provider_var.get(),
        "last_updated": datetime.datetime.now().isoformat(),
        "message_count": self.thread_message_count
    }

    from document_library import save_thread_as_new_document
    thread_id = save_thread_as_new_document(
        self.current_document_id,
        self.current_thread,
        metadata
    )

    if thread_id:
        messagebox.showinfo(
            "Thread Saved",
            f"Conversation thread saved to library!\n\n"
            f"Messages: {self.thread_message_count}\n"
            f"You can find it in the Documents Library with [Thread] prefix."
        )
        self.refresh_library()
"""
