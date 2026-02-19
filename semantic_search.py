"""
Semantic Search Module for DocAnalyser
======================================

This module provides semantic (meaning-based) search capabilities.
It converts documents to embeddings and finds similar content.

VERSION 2.0: Now supports chunk-level (paragraph) embeddings for more precise search.

Usage:
    from semantic_search import SemanticSearch, ChunkEmbeddingStorage
    
    # Initialize with your OpenAI API key
    ss = SemanticSearch(api_key="your-openai-key")
    
    # Generate embedding for text
    embedding, cost = ss.generate_embedding("Your text here")
    
    # For chunk-level search, use ChunkEmbeddingStorage
    storage = ChunkEmbeddingStorage("embeddings.json")
    
Author: Claude (for DocAnalyser project)
Date: November 2025
"""

import json
import os
import re
import math
from datetime import datetime
from typing import Optional, Tuple, List, Dict


class SemanticSearch:
    """
    Handles semantic search operations including embedding generation
    and similarity matching.
    """
    
    def __init__(self, api_key: str = "", provider: str = "openai"):
        """
        Initialize the semantic search module.
        
        Args:
            api_key: API key for the embedding provider
            provider: "openai" or "gemini"
        """
        self.api_key = api_key
        self.provider = provider.lower()
        
        # Model settings
        if self.provider == "openai":
            self.model = "text-embedding-3-small"
            self.dimensions = 1536
            self.cost_per_1k_tokens = 0.00002
        elif self.provider == "gemini":
            self.model = "embedding-001"
            self.dimensions = 768
            self.cost_per_1k_tokens = 0.00001  # Approximate
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    def generate_embedding(self, text: str) -> Tuple[list, float]:
        """
        Generate an embedding vector for the given text.
        
        Args:
            text: The text to embed
            
        Returns:
            Tuple of (embedding_vector, cost)
        """
        if not self.api_key:
            raise ValueError("API key is required for embedding generation")
        
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        
        # Truncate very long texts (most models have limits)
        max_chars = 25000  # ~6000 tokens, safe limit
        if len(text) > max_chars:
            text = text[:max_chars]
        
        if self.provider == "openai":
            return self._generate_openai_embedding(text)
        elif self.provider == "gemini":
            return self._generate_gemini_embedding(text)
    
    def generate_embeddings_batch(self, texts: List[str]) -> Tuple[List[list], float]:
        """
        Generate embeddings for multiple texts in a single API call.
        More efficient than calling generate_embedding multiple times.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            Tuple of (list of embedding vectors, total cost)
        """
        if not self.api_key:
            raise ValueError("API key is required for embedding generation")
        
        if not texts:
            return [], 0.0
        
        # Filter empty texts and truncate long ones
        max_chars = 8000  # Smaller limit for batch to stay under token limits
        processed_texts = []
        for text in texts:
            if text and text.strip():
                if len(text) > max_chars:
                    text = text[:max_chars]
                processed_texts.append(text)
        
        if not processed_texts:
            return [], 0.0
        
        if self.provider == "openai":
            return self._generate_openai_embeddings_batch(processed_texts)
        else:
            # Fallback to individual calls for other providers
            embeddings = []
            total_cost = 0.0
            for text in processed_texts:
                emb, cost = self.generate_embedding(text)
                embeddings.append(emb)
                total_cost += cost
            return embeddings, total_cost
    
    def _generate_openai_embedding(self, text: str) -> Tuple[list, float]:
        """Generate embedding using OpenAI API."""
        import urllib.request
        import urllib.error
        
        url = "https://api.openai.com/v1/embeddings"
        
        data = json.dumps({
            "model": self.model,
            "input": text
        }).encode('utf-8')
        
        request = urllib.request.Request(url, data=data)
        request.add_header("Content-Type", "application/json")
        request.add_header("Authorization", f"Bearer {self.api_key}")
        
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                
            embedding = result["data"][0]["embedding"]
            tokens_used = result["usage"]["total_tokens"]
            cost = (tokens_used / 1000) * self.cost_per_1k_tokens
            
            return embedding, cost
            
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            raise Exception(f"OpenAI API error: {e.code} - {error_body}")
        except Exception as e:
            raise Exception(f"Error generating embedding: {str(e)}")
    
    def _generate_openai_embeddings_batch(self, texts: List[str]) -> Tuple[List[list], float]:
        """Generate embeddings for multiple texts in one API call."""
        import urllib.request
        import urllib.error
        
        url = "https://api.openai.com/v1/embeddings"
        
        data = json.dumps({
            "model": self.model,
            "input": texts
        }).encode('utf-8')
        
        request = urllib.request.Request(url, data=data)
        request.add_header("Content-Type", "application/json")
        request.add_header("Authorization", f"Bearer {self.api_key}")
        
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.loads(response.read().decode('utf-8'))
            
            # Sort by index to maintain order
            data_sorted = sorted(result["data"], key=lambda x: x["index"])
            embeddings = [item["embedding"] for item in data_sorted]
            
            tokens_used = result["usage"]["total_tokens"]
            cost = (tokens_used / 1000) * self.cost_per_1k_tokens
            
            return embeddings, cost
            
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            raise Exception(f"OpenAI API error: {e.code} - {error_body}")
        except Exception as e:
            raise Exception(f"Error generating batch embeddings: {str(e)}")
    
    def _generate_gemini_embedding(self, text: str) -> Tuple[list, float]:
        """Generate embedding using Google Gemini API."""
        import urllib.request
        import urllib.error
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:embedContent?key={self.api_key}"
        
        data = json.dumps({
            "model": f"models/{self.model}",
            "content": {
                "parts": [{"text": text}]
            }
        }).encode('utf-8')
        
        request = urllib.request.Request(url, data=data)
        request.add_header("Content-Type", "application/json")
        
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                
            embedding = result["embedding"]["values"]
            # Gemini doesn't return token count, estimate it
            estimated_tokens = len(text) / 4
            cost = (estimated_tokens / 1000) * self.cost_per_1k_tokens
            
            return embedding, cost
            
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            raise Exception(f"Gemini API error: {e.code} - {error_body}")
        except Exception as e:
            raise Exception(f"Error generating embedding: {str(e)}")
    
    def cosine_similarity(self, vec1: list, vec2: list) -> float:
        """
        Calculate cosine similarity between two vectors.
        
        Args:
            vec1: First vector
            vec2: Second vector
            
        Returns:
            Similarity score between -1 and 1 (higher = more similar)
        """
        if len(vec1) != len(vec2):
            raise ValueError("Vectors must have the same length")
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)


# =========================================
# TEXT CHUNKING UTILITIES
# =========================================

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[Dict]:
    """
    Split text into overlapping chunks for embedding.
    
    Tries to split at paragraph boundaries first, then sentences,
    then falls back to word boundaries.
    
    Args:
        text: The text to chunk
        chunk_size: Target size of each chunk in words (approximate)
        overlap: Number of words to overlap between chunks
        
    Returns:
        List of dicts with 'text', 'start_char', 'end_char' keys
    """
    if not text or not text.strip():
        return []
    
    # Split into paragraphs first
    paragraphs = re.split(r'\n\s*\n', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    chunks = []
    current_chunk = []
    current_word_count = 0
    current_start = 0
    char_position = 0
    
    for para in paragraphs:
        para_words = para.split()
        para_word_count = len(para_words)
        
        # If this paragraph alone exceeds chunk size, split it
        if para_word_count > chunk_size:
            # First, save current chunk if any
            if current_chunk:
                chunk_text_str = '\n\n'.join(current_chunk)
                chunks.append({
                    'text': chunk_text_str,
                    'start_char': current_start,
                    'end_char': current_start + len(chunk_text_str),
                    'word_count': current_word_count
                })
                current_chunk = []
                current_word_count = 0
            
            # Split long paragraph by sentences
            sentences = re.split(r'(?<=[.!?])\s+', para)
            sent_chunk = []
            sent_word_count = 0
            sent_start = char_position
            
            for sentence in sentences:
                sent_words = len(sentence.split())
                
                if sent_word_count + sent_words > chunk_size and sent_chunk:
                    # Save this sentence chunk
                    chunk_text_str = ' '.join(sent_chunk)
                    chunks.append({
                        'text': chunk_text_str,
                        'start_char': sent_start,
                        'end_char': sent_start + len(chunk_text_str),
                        'word_count': sent_word_count
                    })
                    # Start new chunk with overlap
                    overlap_text = ' '.join(sent_chunk[-2:]) if len(sent_chunk) >= 2 else ''
                    sent_chunk = [overlap_text, sentence] if overlap_text else [sentence]
                    sent_word_count = len(' '.join(sent_chunk).split())
                    sent_start = char_position
                else:
                    sent_chunk.append(sentence)
                    sent_word_count += sent_words
            
            # Don't forget remaining sentences
            if sent_chunk:
                chunk_text_str = ' '.join(sent_chunk)
                chunks.append({
                    'text': chunk_text_str,
                    'start_char': sent_start,
                    'end_char': sent_start + len(chunk_text_str),
                    'word_count': sent_word_count
                })
            
            current_start = char_position + len(para) + 2  # +2 for paragraph break
            
        else:
            # Normal paragraph - add to current chunk
            if current_word_count + para_word_count > chunk_size and current_chunk:
                # Save current chunk
                chunk_text_str = '\n\n'.join(current_chunk)
                chunks.append({
                    'text': chunk_text_str,
                    'start_char': current_start,
                    'end_char': current_start + len(chunk_text_str),
                    'word_count': current_word_count
                })
                
                # Start new chunk - include last paragraph for context overlap
                if overlap > 0 and current_chunk:
                    last_para = current_chunk[-1]
                    last_words = last_para.split()
                    if len(last_words) > overlap:
                        overlap_text = ' '.join(last_words[-overlap:])
                        current_chunk = [overlap_text, para]
                        current_word_count = overlap + para_word_count
                    else:
                        current_chunk = [last_para, para]
                        current_word_count = len(last_para.split()) + para_word_count
                else:
                    current_chunk = [para]
                    current_word_count = para_word_count
                current_start = char_position
            else:
                current_chunk.append(para)
                current_word_count += para_word_count
        
        char_position += len(para) + 2  # +2 for \n\n
    
    # Don't forget the last chunk
    if current_chunk:
        chunk_text_str = '\n\n'.join(current_chunk)
        chunks.append({
            'text': chunk_text_str,
            'start_char': current_start,
            'end_char': current_start + len(chunk_text_str),
            'word_count': current_word_count
        })
    
    return chunks


def chunk_text_simple(text: str, chunk_size: int = 500) -> List[Dict]:
    """
    Simple chunking by paragraph boundaries.
    Groups paragraphs together until chunk_size is reached.
    
    Args:
        text: Text to chunk
        chunk_size: Target words per chunk
        
    Returns:
        List of chunk dicts
    """
    if not text or not text.strip():
        return []
    
    # Split by double newlines (paragraphs) or single newlines
    paragraphs = re.split(r'\n\s*\n|\n', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    chunks = []
    current_paras = []
    current_words = 0
    
    for para in paragraphs:
        para_words = len(para.split())
        
        # If adding this para exceeds limit and we have content, save chunk
        if current_words + para_words > chunk_size and current_paras:
            chunks.append({
                'text': '\n\n'.join(current_paras),
                'word_count': current_words
            })
            current_paras = []
            current_words = 0
        
        current_paras.append(para)
        current_words += para_words
    
    # Save final chunk
    if current_paras:
        chunks.append({
            'text': '\n\n'.join(current_paras),
            'word_count': current_words
        })
    
    return chunks


# =========================================
# CHUNK-LEVEL EMBEDDING STORAGE
# =========================================

class ChunkEmbeddingStorage:
    """
    Handles storage and retrieval of chunk-level document embeddings.
    Each document can have multiple chunks, each with its own embedding.
    """
    
    def __init__(self, storage_path: str = "embeddings.json"):
        """
        Initialize the chunk embedding storage.
        
        Args:
            storage_path: Path to the embeddings JSON file
        """
        self.storage_path = storage_path
        self.data = self._load()
    
    def _load(self) -> dict:
        """Load embeddings from file."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Migrate old format if needed
                if data.get("version") == "1.0":
                    data = self._migrate_v1_to_v2(data)
                return data
            except (json.JSONDecodeError, IOError):
                return self._empty_storage()
        return self._empty_storage()
    
    def _empty_storage(self) -> dict:
        """Return empty storage structure."""
        return {
            "version": "2.0",
            "provider": "openai",
            "model": "text-embedding-3-small",
            "documents": {}
        }
    
    def _migrate_v1_to_v2(self, old_data: dict) -> dict:
        """Migrate from v1 (single embedding per doc) to v2 (chunks)."""
        new_data = self._empty_storage()
        new_data["provider"] = old_data.get("provider", "openai")
        new_data["model"] = old_data.get("model", "text-embedding-3-small")
        
        # Convert old single-embedding format to chunk format
        for doc_id, doc_data in old_data.get("documents", {}).items():
            if "embedding" in doc_data:
                # Old format - convert to single chunk
                new_data["documents"][doc_id] = {
                    "chunks": [{
                        "text": "(full document)",
                        "embedding": doc_data["embedding"],
                        "start_char": 0,
                        "end_char": 0
                    }],
                    "generated_at": doc_data.get("generated_at", datetime.now().isoformat()),
                    "total_cost": doc_data.get("cost", 0.0),
                    "chunk_count": 1
                }
        
        return new_data
    
    def save(self):
        """Save embeddings to file."""
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f)  # No indent to save space (embeddings are large)
    
    def add_document_chunks(self, doc_id: str, chunks: List[Dict], 
                           embeddings: List[list], total_cost: float = 0.0):
        """
        Add chunk embeddings for a document.
        
        Args:
            doc_id: Document ID
            chunks: List of chunk dicts (with 'text', 'start_char', etc.)
            embeddings: List of embedding vectors (same length as chunks)
            total_cost: Total cost for generating these embeddings
        """
        if len(chunks) != len(embeddings):
            raise ValueError("Number of chunks must match number of embeddings")
        
        chunk_data = []
        for chunk, embedding in zip(chunks, embeddings):
            chunk_data.append({
                "text": chunk.get("text", "")[:500],  # Store preview only
                "embedding": embedding,
                "start_char": chunk.get("start_char", 0),
                "end_char": chunk.get("end_char", 0),
                "word_count": chunk.get("word_count", 0)
            })
        
        self.data["documents"][doc_id] = {
            "chunks": chunk_data,
            "generated_at": datetime.now().isoformat(),
            "total_cost": total_cost,
            "chunk_count": len(chunks)
        }
    
    def get_document_chunks(self, doc_id: str) -> Optional[List[Dict]]:
        """Get all chunks for a document."""
        doc_data = self.data["documents"].get(doc_id)
        if doc_data:
            return doc_data.get("chunks", [])
        return None
    
    def has_embedding(self, doc_id: str) -> bool:
        """Check if a document has embeddings."""
        return doc_id in self.data["documents"]
    
    def remove_embedding(self, doc_id: str):
        """Remove embeddings for a document."""
        if doc_id in self.data["documents"]:
            del self.data["documents"][doc_id]
    
    def get_all_chunks_flat(self) -> List[Dict]:
        """
        Get all chunks from all documents as a flat list.
        Each item includes doc_id for reference.
        
        Returns:
            List of dicts with 'doc_id', 'chunk_idx', 'text', 'embedding'
        """
        all_chunks = []
        for doc_id, doc_data in self.data["documents"].items():
            for idx, chunk in enumerate(doc_data.get("chunks", [])):
                all_chunks.append({
                    "doc_id": doc_id,
                    "chunk_idx": idx,
                    "text": chunk.get("text", ""),
                    "embedding": chunk.get("embedding", []),
                    "start_char": chunk.get("start_char", 0),
                    "end_char": chunk.get("end_char", 0)
                })
        return all_chunks
    
    def get_stats(self) -> dict:
        """Get statistics about stored embeddings."""
        docs = self.data["documents"]
        total_chunks = sum(d.get("chunk_count", len(d.get("chunks", []))) for d in docs.values())
        total_cost = sum(d.get("total_cost", 0) for d in docs.values())
        
        return {
            "total_documents": len(docs),
            "total_chunks": total_chunks,
            "total_cost": total_cost,
            "provider": self.data.get("provider", "unknown"),
            "model": self.data.get("model", "unknown"),
            "avg_chunks_per_doc": total_chunks / len(docs) if docs else 0
        }
    
    def set_metadata(self, provider: str, model: str):
        """Set the provider and model metadata."""
        self.data["provider"] = provider
        self.data["model"] = model


# Keep old class for backwards compatibility
class EmbeddingStorage(ChunkEmbeddingStorage):
    """Alias for backwards compatibility."""
    pass


# =========================================
# CHUNK-LEVEL SEMANTIC SEARCH
# =========================================

def search_chunks(query_embedding: list, storage: ChunkEmbeddingStorage, 
                  top_k: int = 20, threshold: float = 0.3) -> List[Dict]:
    """
    Search all chunks across all documents for similar content.
    
    Args:
        query_embedding: The embedding vector for the search query
        storage: ChunkEmbeddingStorage instance
        top_k: Maximum results to return
        threshold: Minimum similarity score (0-1)
        
    Returns:
        List of matching chunks with scores, sorted by similarity
    """
    ss = SemanticSearch()  # Just for cosine_similarity
    
    results = []
    all_chunks = storage.get_all_chunks_flat()
    
    for chunk in all_chunks:
        if not chunk.get("embedding"):
            continue
        
        similarity = ss.cosine_similarity(query_embedding, chunk["embedding"])
        
        if similarity >= threshold:
            results.append({
                "doc_id": chunk["doc_id"],
                "chunk_idx": chunk["chunk_idx"],
                "text": chunk["text"],
                "score": similarity,
                "score_percent": round(similarity * 100, 1),
                "start_char": chunk.get("start_char", 0),
                "end_char": chunk.get("end_char", 0)
            })
    
    # Sort by similarity (highest first)
    results.sort(key=lambda x: x["score"], reverse=True)
    
    return results[:top_k]


# =========================================
# TESTING
# =========================================

def test_semantic_search():
    """
    Test the semantic search module without making API calls.
    """
    print("🧪 Testing Semantic Search Module v2.0")
    print("=" * 50)
    
    # Test cosine similarity (no API needed)
    ss = SemanticSearch(api_key="test", provider="openai")
    
    vec1 = [1.0, 0.0, 0.0]
    vec2 = [1.0, 0.0, 0.0]
    vec3 = [0.0, 1.0, 0.0]
    
    sim_identical = ss.cosine_similarity(vec1, vec2)
    sim_orthogonal = ss.cosine_similarity(vec1, vec3)
    
    print(f"Identical vectors: {sim_identical:.2f} (expected: 1.00)")
    print(f"Orthogonal vectors: {sim_orthogonal:.2f} (expected: 0.00)")
    print("✅ Cosine similarity working!")
    
    # Test chunking
    test_text = """This is the first paragraph. It contains some text about a topic.

This is the second paragraph. It discusses something different entirely.

And here is a third paragraph. It wraps up the document nicely."""
    
    chunks = chunk_text_simple(test_text, chunk_size=20)
    print(f"\n✅ Chunking working! Created {len(chunks)} chunks from test text")
    
    # Test storage
    test_storage_path = "test_embeddings_v2.json"
    storage = ChunkEmbeddingStorage(test_storage_path)
    
    # Add test chunks
    test_chunks = [
        {"text": "First chunk", "start_char": 0, "end_char": 100, "word_count": 10},
        {"text": "Second chunk", "start_char": 100, "end_char": 200, "word_count": 15}
    ]
    test_embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    
    storage.add_document_chunks("test_doc", test_chunks, test_embeddings, total_cost=0.0001)
    storage.save()
    
    # Reload and verify
    storage2 = ChunkEmbeddingStorage(test_storage_path)
    chunks = storage2.get_document_chunks("test_doc")
    
    assert len(chunks) == 2, "Storage test failed - wrong chunk count"
    print("✅ Chunk storage working!")
    
    # Clean up
    if os.path.exists(test_storage_path):
        os.remove(test_storage_path)
    
    print("\n✅ All v2.0 tests passed!")
    return True


if __name__ == "__main__":
    test_semantic_search()
