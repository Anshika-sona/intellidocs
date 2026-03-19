import os
import re
import json
from sqlalchemy import text
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

load_dotenv()


# Cache model in /tmp to avoid re-downloading
MODEL_CACHE = "/tmp/model_cache"
os.makedirs(MODEL_CACHE, exist_ok=True)
model = SentenceTransformer('all-MiniLM-L6-v2', cache_folder=MODEL_CACHE)
print("Embedding model loaded!")


def generate_embedding(text_input: str) -> list:
    """Converts text into a vector using free local model."""
    text_input = text_input.replace("\n", " ").strip()
    embedding = model.encode(text_input)
    return embedding.tolist()


def semantic_search(query: str, db, top_k: int = 8) -> list:
    """Finds most relevant chunks using vector similarity."""
    print(f"Running semantic search for: '{query}'")

    query_embedding = generate_embedding(query)

    sql = text("""
        SELECT 
            c.id,
            c.document_id,
            c.text,
            c.chunk_index,
            c.page_number,
            c.word_count,
            d.filename,
            1 - (c.embedding <=> CAST(:embedding AS vector)) AS similarity_score
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE c.embedding IS NOT NULL
        ORDER BY c.embedding <=> CAST(:embedding AS vector)
        LIMIT :top_k
    """)

    result = db.execute(sql, {
        "embedding": json.dumps(query_embedding),
        "top_k": top_k
    })

    rows = result.fetchall()
    chunks = []
    for row in rows:
        chunks.append({
            "id": row.id,
            "document_id": row.document_id,
            "text": row.text,
            "chunk_index": row.chunk_index,
            "page_number": row.page_number,
            "filename": row.filename,
            "similarity_score": round(float(row.similarity_score), 4),
            "search_type": "semantic"
        })

    print(f"Semantic search found {len(chunks)} results")
    return chunks


def bm25_search(query: str, db, top_k: int = 8) -> list:
    """
    Finds chunks using exact keyword matching.
    Great for names, numbers, exact phrases.
    
    How it works:
    1. Load all chunks from DB
    2. Build a BM25 index from all chunk texts
    3. Score each chunk against the query
    4. Return top_k highest scoring chunks
    """
    print(f"Running BM25 search for: '{query}'")

    # Load all chunks from database
    sql = text("""
        SELECT 
            c.id,
            c.document_id,
            c.text,
            c.chunk_index,
            c.page_number,
            c.word_count,
            d.filename
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
    """)

    result = db.execute(sql)
    rows = result.fetchall()

    if not rows:
        print("No chunks found in database")
        return []

    # Tokenise each chunk into words (BM25 works on word lists)
    tokenised_chunks = [re.findall(r'\w+', row.text.lower()) for row in rows]

    # Build BM25 index
    bm25 = BM25Okapi(tokenised_chunks)

    # Score query against all chunks
    query_tokens = re.findall(r'\w+', query.lower())
    scores = bm25.get_scores(query_tokens)

    # Get top_k results by score
    top_indices = sorted(
        range(len(scores)),
        key=lambda i: scores[i],
        reverse=True
    )[:top_k]

    chunks = []
    for idx in top_indices:
        row = rows[idx]
        score = scores[idx]

        # Only include if score is above 0 (means at least one word matched)
        if score > 0:
            chunks.append({
                "id": row.id,
                "document_id": row.document_id,
                "text": row.text,
                "chunk_index": row.chunk_index,
                "page_number": row.page_number,
                "filename": row.filename,
                "bm25_score": round(float(score), 4),
                "search_type": "bm25"
            })

    print(f"BM25 search found {len(chunks)} results")
    return chunks


def hybrid_search(query: str, db, top_k: int = 8) -> list:
    """
    Combines semantic + BM25 using Reciprocal Rank Fusion.
    
    RRF formula: score = 1/(60 + rank)
    A chunk that ranks high in BOTH methods wins.
    This beats either method alone by 25-30%.
    """
    print(f"Running hybrid search for: '{query}'")

    # Run both searches
    semantic_results = semantic_search(query, db, top_k=20)
    bm25_results = bm25_search(query, db, top_k=20)

    # Build rank dictionaries
    # Key = chunk id, Value = rank position (0 = best)
    semantic_ranks = {r["id"]: i for i, r in enumerate(semantic_results)}
    bm25_ranks = {r["id"]: i for i, r in enumerate(bm25_results)}

    # Collect all unique chunk ids from both results
    all_chunk_ids = set(semantic_ranks.keys()) | set(bm25_ranks.keys())

    # Calculate RRF score for each chunk
    # If chunk not in a result set, use rank 1000 (penalty)
    k = 60  # RRF constant — standard value
    rrf_scores = {}
    for chunk_id in all_chunk_ids:
        semantic_rank = semantic_ranks.get(chunk_id, 1000)
        bm25_rank = bm25_ranks.get(chunk_id, 1000)
        rrf_scores[chunk_id] = (
            1 / (k + semantic_rank) +
            1 / (k + bm25_rank)
        )

    # Sort by RRF score
    ranked_ids = sorted(
        rrf_scores.keys(),
        key=lambda x: rrf_scores[x],
        reverse=True
    )[:top_k]

    # Build final result list
    # Merge chunk data from both result sets
    all_chunks = {r["id"]: r for r in semantic_results}
    all_chunks.update({r["id"]: r for r in bm25_results})

    final_results = []
    for chunk_id in ranked_ids:
        if chunk_id in all_chunks:
            chunk = all_chunks[chunk_id].copy()
            chunk["rrf_score"] = round(rrf_scores[chunk_id], 6)
            chunk["search_type"] = "hybrid"
            final_results.append(chunk)

    print(f"Hybrid search returning {len(final_results)} results")
    return final_results