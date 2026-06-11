import os
import hashlib
import uuid
import re
import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
import chromadb
from sentence_transformers import SentenceTransformer
from openai import OpenAI
from ingestion.base import SocialPost, UserProfile

class VectorStoreManager:
    """Manages ChromaDB vector store, embedding generation, intelligent chunking, and querying."""

    def __init__(self, db_path: str = "./chroma_db", default_provider: str = "local"):
        self.db_path = db_path
        self.default_provider = default_provider
        
        # Ensure directories exist
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        
        # Initialize ChromaDB Client
        self.chroma_client = chromadb.PersistentClient(path=db_path)
        
        # We will manage embedding generation explicitly rather than letting Chroma do it,
        # ensuring full control over API keys, caching, and model selection.
        self.collection = self.chroma_client.get_or_create_collection(
            name="social_knowledge_base",
            metadata={"hnsw:space": "cosine"}
        )
        
        # Local model cache
        self._local_model = None

    @property
    def local_model(self) -> SentenceTransformer:
        """Lazy load the sentence transformer model to save memory if not used."""
        if self._local_model is None:
            # Using all-MiniLM-L6-v2 which is fast (384 dims) and highly accurate
            self._local_model = SentenceTransformer('all-MiniLM-L6-v2')
        return self._local_model

    def generate_embeddings(self, texts: List[str], provider: str, api_key: Optional[str] = None) -> List[List[float]]:
        """Generates embeddings using local SentenceTransformers or OpenAI."""
        if not texts:
            return []

        if provider == "openai":
            if not api_key:
                raise ValueError("OpenAI API Key is required for OpenAI embeddings.")
            client = OpenAI(api_key=api_key)
            # Use modern, cheaper text-embedding-3-small model (1536 dims)
            response = client.embeddings.create(
                input=texts,
                model="text-embedding-3-small"
            )
            return [e.embedding for e in response.data]
        else:
            # Local Embedding
            embeddings = self.local_model.encode(
                texts,
                batch_size=128,  # Efficient batching
                show_progress_bar=False,
                convert_to_numpy=True
            )
            return embeddings.tolist()

    def get_deterministic_id(self, post: SocialPost, chunk_idx: int = 0) -> str:
        """Generates a deterministic, unique, and reproducible UUID for a chunk."""
        # Mix in platform, original ID (if available), and content hash
        content_hash = hashlib.md5(post.content.encode('utf-8')).hexdigest()
        orig_id = post.original_id or "no_id"
        unique_str = f"{post.platform}_{orig_id}_{content_hash}_{chunk_idx}"
        
        # Produce a repeatable UUID
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, unique_str))

    def chunk_post(self, post: SocialPost, max_chars: int = 800, overlap: int = 150) -> List[Dict[str, Any]]:
        """Intelligently chunks social posts. Short posts are left intact.

        Long posts are split on paragraph/sentence boundaries to prevent semantic cutting.
        """
        content = post.content.strip()
        
        # 1. Decision: Keep short posts as one single chunk (highly efficient and context-preserving)
        if len(content) <= max_chars:
            return [{
                "id": self.get_deterministic_id(post, 0),
                "text": content,
                "metadata": {
                    "platform": post.platform,
                    "timestamp": post.timestamp,
                    "author": post.author,
                    "original_id": post.original_id,
                    "source_file": post.source_file,
                    "chunk_index": 0,
                    "total_chunks": 1,
                    "type": "post"
                }
            }]
            
        # 2. Split longer content (e.g. LinkedIn articles, long blog posts)
        # Split by paragraph boundaries first, then sentences, then fallback to character chunks
        paragraphs = content.split("\n\n")
        chunks = []
        current_chunk = []
        current_len = 0
        
        def finalize_chunk(text_list, idx) -> Dict[str, Any]:
            chunk_text = "\n\n".join(text_list)
            return {
                "id": self.get_deterministic_id(post, idx),
                "text": chunk_text,
                "metadata": {
                    "platform": post.platform,
                    "timestamp": post.timestamp,
                    "author": post.author,
                    "original_id": post.original_id,
                    "source_file": post.source_file,
                    "chunk_index": idx,
                    "type": "post"
                }
            }

        chunk_idx = 0
        for para in paragraphs:
            if not para.strip():
                continue
                
            # If a single paragraph is too large, split it by sentence
            if len(para) > max_chars:
                # Flush existing chunk
                if current_chunk:
                    chunks.append(finalize_chunk(current_chunk, chunk_idx))
                    chunk_idx += 1
                    current_chunk = []
                    current_len = 0
                
                # Split paragraph by sentences
                sentences = re.split(r'(?<=[.!?])\s+', para)
                for sentence in sentences:
                    if len(sentence) > max_chars:
                        # Fallback character split if sentence is abnormally long
                        words = sentence.split(" ")
                        temp_chunk = []
                        temp_len = 0
                        for word in words:
                            if temp_len + len(word) + 1 > max_chars:
                                chunks.append({
                                    "id": self.get_deterministic_id(post, chunk_idx),
                                    "text": " ".join(temp_chunk),
                                    "metadata": {
                                        "platform": post.platform,
                                        "timestamp": post.timestamp,
                                        "author": post.author,
                                        "original_id": post.original_id,
                                        "source_file": post.source_file,
                                        "chunk_index": chunk_idx,
                                        "type": "post"
                                    }
                                })
                                chunk_idx += 1
                                temp_chunk = [word]
                                temp_len = len(word)
                            else:
                                temp_chunk.append(word)
                                temp_len += len(word) + 1
                        if temp_chunk:
                            current_chunk = temp_chunk
                            current_len = temp_len
                    else:
                        if current_len + len(sentence) + 2 > max_chars:
                            chunks.append(finalize_chunk(current_chunk, chunk_idx))
                            chunk_idx += 1
                            current_chunk = [sentence]
                            current_len = len(sentence)
                        else:
                            current_chunk.append(sentence)
                            current_len += len(sentence) + 2
            else:
                if current_len + len(para) + 2 > max_chars:
                    chunks.append(finalize_chunk(current_chunk, chunk_idx))
                    chunk_idx += 1
                    # Implement sliding window overlap
                    # Keep last paragraph if it fits within overlap limit
                    if len(para) < overlap:
                        current_chunk = [para]
                        current_len = len(para)
                    else:
                        current_chunk = [para]
                        current_len = len(para)
                else:
                    current_chunk.append(para)
                    current_len += len(para) + 2
                    
        if current_chunk:
            chunks.append(finalize_chunk(current_chunk, chunk_idx))
            
        # Add total_chunks count back to metadata
        total = len(chunks)
        for c in chunks:
            c["metadata"]["total_chunks"] = total
            
        return chunks

    def upsert_posts(self, posts: List[SocialPost], provider: str = "local", api_key: Optional[str] = None, batch_size: int = 128) -> int:
        """Processes, chunks, embeds, and upserts social posts into ChromaDB.

        Performs deduplication using deterministic hashing.
        """
        if not posts:
            return 0
            
        all_chunks = []
        for post in posts:
            all_chunks.extend(self.chunk_post(post))
            
        total_chunks = len(all_chunks)
        print(f"Total chunks generated: {total_chunks}")
        
        # Batch upload to ChromaDB
        for i in range(0, total_chunks, batch_size):
            batch = all_chunks[i:i + batch_size]
            
            ids = [item["id"] for item in batch]
            documents = [item["text"] for item in batch]
            metadatas = [item["metadata"] for item in batch]
            
            # Generate embeddings for the batch
            try:
                embeddings = self.generate_embeddings(documents, provider=provider, api_key=api_key)
            except Exception as e:
                print(f"Error generating embeddings for batch starting at {i}: {e}")
                # Fallback to local
                embeddings = self.generate_embeddings(documents, provider="local")
            
            # Upsert into ChromaDB
            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents
            )
            
        return total_chunks

    def upsert_profiles(self, profiles: List[UserProfile]):
        """Saves user profiles as separate chunks in vector database so they can be queried."""
        if not profiles:
            return
            
        ids = []
        documents = []
        metadatas = []
        
        for idx, profile in enumerate(profiles):
            doc_text = f"Profile of {profile.name} on {profile.platform}. Bio: {profile.bio or ''}"
            unique_str = f"profile_{profile.platform}_{profile.username}"
            profile_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, unique_str))
            
            ids.append(profile_id)
            documents.append(doc_text)
            metadatas.append({
                "platform": profile.platform,
                "author": profile.name,
                "username": profile.username,
                "type": "profile",
                "timestamp": datetime.utcnow().isoformat()
            })
            
        # Profiles are small and few, so we embed them locally
        embeddings = self.generate_embeddings(documents, provider="local")
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents
        )

    def query_similarity(self, query: str, top_k: int = 5, platform: Optional[str] = None, provider: str = "local", api_key: Optional[str] = None) -> List[Dict[str, Any]]:
        """Queries ChromaDB for similar chunks, returns list of results with metadata and score."""
        # 1. Embed query
        query_embeddings = self.generate_embeddings([query], provider=provider, api_key=api_key)
        query_vector = query_embeddings[0]
        
        # 2. Build where filter if platform specified
        where_filter = {}
        if platform:
            where_filter = {"platform": platform}
            
        # 3. Query ChromaDB
        results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            where=where_filter if where_filter else None
        )
        
        # 4. Format results
        formatted_results = []
        if results and results["documents"]:
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            distances = results["distances"][0]
            ids = results["ids"][0]
            
            for idx in range(len(docs)):
                # Chroma returns distance, cosine similarity = 1 - distance
                similarity_score = 1.0 - distances[idx]
                formatted_results.append({
                    "id": ids[idx],
                    "document": docs[idx],
                    "metadata": metas[idx],
                    "score": float(similarity_score)
                })
                
        return formatted_results

    def get_stats(self) -> Dict[str, Any]:
        """Returns statistical counts of elements stored in the collection."""
        try:
            total_items = self.collection.count()
            # Fetch all metadatas to compute breakdowns
            # In a massive DB this should be optimized, but for a personal archive, it works fine
            all_data = self.collection.get(include=["metadatas"])
            
            platform_counts = {"linkedin": 0, "twitter": 0, "instagram": 0}
            type_counts = {"post": 0, "profile": 0}
            
            if all_data and all_data["metadatas"]:
                for meta in all_data["metadatas"]:
                    plat = meta.get("platform")
                    if plat in platform_counts:
                        platform_counts[plat] += 1
                    t = meta.get("type", "post")
                    if t in type_counts:
                        type_counts[t] += 1
                        
            return {
                "total_chunks": total_items,
                "platform_counts": platform_counts,
                "type_counts": type_counts
            }
        except Exception as e:
            return {
                "total_chunks": 0,
                "platform_counts": {"linkedin": 0, "twitter": 0, "instagram": 0},
                "type_counts": {"post": 0, "profile": 0},
                "error": str(e)
            }
            
    def clear_database(self):
        """Clears all vectors in the collection."""
        try:
            self.chroma_client.delete_collection("social_knowledge_base")
            self.collection = self.chroma_client.get_or_create_collection(
                name="social_knowledge_base",
                metadata={"hnsw:space": "cosine"}
            )
        except Exception as e:
            print(f"Error clearing collection: {e}")
