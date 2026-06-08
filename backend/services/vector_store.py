import sqlite3
import re
import json
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from google import genai
from google.genai import errors
from backend.config import settings

class VectorStore:
    def __init__(self):
        self.mode = settings.RUN_MODE
        self.client = None
        self._init_gemini_client()
        self._init_db()

    def _init_gemini_client(self):
        """Initializes the Gemini API client if API key is provided."""
        if settings.GEMINI_API_KEY:
            try:
                self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
            except Exception as e:
                print(f"Error initializing Gemini client in VectorStore: {e}")
        else:
            print("WARNING: GEMINI_API_KEY is not configured. Falling back to mock embeddings.")

    def _init_db(self):
        """Initializes the database schema (SQLite or PostgreSQL)."""
        if self.mode == "local":
            conn = sqlite3.connect(settings.sqlite_db_path)
            cursor = conn.cursor()
            # Table to store SEC filing chunks
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS filing_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    ticker TEXT,
                    filing_type TEXT,
                    date TEXT,
                    url TEXT,
                    section TEXT,
                    content TEXT,
                    embedding TEXT -- JSON array of floats
                )
            """)
            conn.commit()
            conn.close()
            print(f"SQLite Vector Database initialized at {settings.sqlite_db_path}")
        else:
            # We delay pgvector import and connection so SQLite doesn't require asyncpg/pgvector to run
            try:
                import asyncpg
                # In production, tables will be initialized asynchronously or via migrations.
                # We will provide an async initialization helper for pgvector.
                print("Production Mode: PostgreSQL pgvector client ready.")
            except ImportError:
                print("WARNING: asyncpg not installed. Falling back to local mode.")
                self.mode = "local"
                self._init_db()

    async def initialize_postgres(self):
        """Creates table and index in Postgres with pgvector extension."""
        if self.mode != "production":
            return
            
        import asyncpg
        conn = None
        try:
            conn = await asyncpg.connect(settings.database_url)
            # Create extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            # Create table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS filing_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    ticker VARCHAR(12),
                    filing_type VARCHAR(10),
                    date VARCHAR(20),
                    url TEXT,
                    section VARCHAR(100),
                    content TEXT,
                    embedding vector(768)
                )
            """)
            # Create index
            await conn.execute("CREATE INDEX IF NOT EXISTS filing_chunks_embedding_idx ON filing_chunks USING hnsw (embedding vector_cosine_ops)")
            print("PostgreSQL pgvector tables and HNSW index verified successfully.")
        except Exception as e:
            print(f"Failed to initialize PostgreSQL pgvector database: {e}. Falling back to SQLite.")
            self.mode = "local"
            self._init_db()
        finally:
            if conn:
                await conn.close()

    def get_embedding(self, text: str) -> List[float]:
        """Generates a 768-dimension embedding from Gemini or mock vector if API key is missing."""
        if not text:
            return [0.0] * 768

        if self.client:
            try:
                response = self.client.models.embed_content(
                    model="text-embedding-004",
                    contents=text
                )
                if response and response.embedding and response.embedding.values:
                    return response.embedding.values
            except Exception as e:
                print(f"Gemini embedding generation failed: {e}. Generating fallback mock vector.")
        
        # Consistent mock embedding generation for demo using simple word hash
        # To make it slightly semantic: count specific financial keywords to bias the vector
        vector = np.zeros(768)
        keywords = ["risk", "revenue", "cloud", "competitor", "profit", "liability", "debt", "ai", "growth", "margin"]
        for idx, word in enumerate(keywords):
            count = len(re.findall(r'\b' + word + r'\b', text.lower()))
            if count > 0:
                vector[idx] = count * 0.5
        
        # Add hash-based deterministic noise
        hash_val = abs(hash(text))
        for idx in range(10, 768):
            vector[idx] = ((hash_val * (idx + 1)) % 1000) / 1000.0 - 0.5
            
        # Normalize vector to unit length
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
            
        return vector.tolist()

    async def save_chunks(self, chunks: List[Dict[str, Any]]):
        """Saves a batch of text chunks and their embeddings to the active vector database."""
        if not chunks:
            return

        if self.mode == "local":
            conn = sqlite3.connect(settings.sqlite_db_path)
            cursor = conn.cursor()
            
            # Prepare rows
            rows = []
            for chunk in chunks:
                # Generate embedding synchronously
                emb = self.get_embedding(chunk["content"])
                rows.append((
                    chunk["chunk_id"],
                    chunk["ticker"],
                    chunk["filing_type"],
                    chunk["date"],
                    chunk["url"],
                    chunk["section"],
                    chunk["content"],
                    json.dumps(emb)
                ))
            
            cursor.executemany("""
                INSERT OR REPLACE INTO filing_chunks 
                (chunk_id, ticker, filing_type, date, url, section, content, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)
            
            conn.commit()
            conn.close()
            print(f"Saved {len(chunks)} chunks to SQLite vector store for {chunks[0]['ticker']}")
        else:
            import asyncpg
            conn = None
            try:
                conn = await asyncpg.connect(settings.database_url)
                
                # Prepare rows for pgvector insertion
                rows = []
                for chunk in chunks:
                    emb = self.get_embedding(chunk["content"])
                    rows.append((
                        chunk["chunk_id"],
                        chunk["ticker"],
                        chunk["filing_type"],
                        chunk["date"],
                        chunk["url"],
                        chunk["section"],
                        chunk["content"],
                        emb
                    ))
                
                # Batch insert
                await conn.executemany("""
                    INSERT INTO filing_chunks 
                    (chunk_id, ticker, filing_type, date, url, section, content, embedding)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding
                """, rows)
                print(f"Saved {len(chunks)} chunks to Postgres vector store for {chunks[0]['ticker']}")
            except Exception as e:
                print(f"Postgres save failed: {e}. Retrying with SQLite fallback.")
                self.mode = "local"
                self._init_db()
                await self.save_chunks(chunks)
            finally:
                if conn:
                    await conn.close()

    async def similarity_search(self, ticker: str, query: str, limit: int = 4) -> List[Dict[str, Any]]:
        """Queries the vector store for chunks matching the input query using cosine similarity."""
        query_emb = self.get_embedding(query)
        ticker = ticker.upper().strip()

        if self.mode == "local":
            conn = sqlite3.connect(settings.sqlite_db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT chunk_id, ticker, filing_type, date, url, section, content, embedding FROM filing_chunks WHERE ticker = ?",
                (ticker,)
            )
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                return []
                
            # Compute cosine similarity in memory
            query_vector = np.array(query_emb)
            results = []
            
            for row in rows:
                if not row[7]:
                    continue
                db_vector = np.array(json.loads(row[7]))
                # Cosine similarity formula: (A . B) / (||A|| * ||B||)
                dot_product = np.dot(query_vector, db_vector)
                query_norm = np.linalg.norm(query_vector)
                db_norm = np.linalg.norm(db_vector)
                
                similarity = dot_product / (query_norm * db_norm) if query_norm > 0 and db_norm > 0 else 0.0
                
                results.append({
                    "score": float(similarity),
                    "chunk_id": row[0],
                    "ticker": row[1],
                    "filing_type": row[2],
                    "date": row[3],
                    "url": row[4],
                    "section": row[5],
                    "content": row[6]
                })
            
            # Sort by similarity score descending
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:limit]
        else:
            import asyncpg
            conn = None
            try:
                conn = await asyncpg.connect(settings.database_url)
                # Cosine distance operator in pgvector is <=>
                # Cosine similarity is 1 - Cosine distance
                rows = await conn.fetch("""
                    SELECT chunk_id, ticker, filing_type, date, url, section, content,
                           (1 - (embedding <=> $1::vector)) as similarity
                    FROM filing_chunks
                    WHERE ticker = $2
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                """, query_emb, ticker, limit)
                
                results = []
                for row in rows:
                    results.append({
                        "score": float(row["similarity"]),
                        "chunk_id": row["chunk_id"],
                        "ticker": row["ticker"],
                        "filing_type": row["filing_type"],
                        "date": row["date"],
                        "url": row["url"],
                        "section": row["section"],
                        "content": row["content"]
                    })
                return results
            except Exception as e:
                print(f"Postgres search failed: {e}. Falling back to SQLite search.")
                self.mode = "local"
                self._init_db()
                return await self.similarity_search(ticker, query, limit)
            finally:
                if conn:
                    await conn.close()

vector_store = VectorStore()
