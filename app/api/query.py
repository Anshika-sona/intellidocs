import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db.database import get_db
from app.services.search import semantic_search, bm25_search, hybrid_search
from app.services.rag import generate_answer, generate_answer_stream

router = APIRouter(prefix="/api", tags=["search & query"])


class SearchRequest(BaseModel):
    query: str
    top_k: int = 8
    mode: str = "hybrid"


class QueryRequest(BaseModel):
    question: str
    top_k: int = 8


@router.post("/search")
def search_documents(request: SearchRequest, db: Session = Depends(get_db)):
    """Search documents and return raw chunks."""
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    if request.mode == "semantic":
        results = semantic_search(request.query, db, top_k=request.top_k)
    elif request.mode == "bm25":
        results = bm25_search(request.query, db, top_k=request.top_k)
    else:
        results = hybrid_search(request.query, db, top_k=request.top_k)

    if not results:
        return {
            "query": request.query,
            "mode": request.mode,
            "total_results": 0,
            "results": [],
            "message": "No results found."
        }

    return {
        "query": request.query,
        "mode": request.mode,
        "total_results": len(results),
        "results": results
    }


@router.post("/query")
def query_documents(request: QueryRequest, db: Session = Depends(get_db)):
    """Ask a question — returns complete answer with citations."""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    print(f"\nQuery: '{request.question}'")

    chunks = hybrid_search(request.question, db, top_k=request.top_k)

    if not chunks:
        return {
            "question": request.question,
            "answer": "I could not find any relevant information in your documents.",
            "sources": [],
            "chunks_used": 0
        }

    result = generate_answer(request.question, chunks)

    return {
        "question": request.question,
        "answer": result["answer"],
        "sources": result["sources"],
        "chunks_used": result["chunks_used"]
    }


@router.get("/stream")
def stream_answer(question: str, db: Session = Depends(get_db)):
    """
    Streams the answer word by word — like ChatGPT.
    
    How to use:
    GET /api/stream?question=What companies has Anshika worked at?
    
    The browser receives tokens one by one as they're generated.
    """
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    print(f"\nStreaming query: '{question}'")

    # Get relevant chunks
    chunks = hybrid_search(question, db, top_k=8)

    # Get sources for the response header
    sources = []
    seen = set()
    for chunk in chunks:
        source = f"{chunk['filename']} - page {chunk.get('page_number', '?')}"
        if source not in seen:
            sources.append(source)
            seen.add(source)

    def token_generator():
        """
        Generator function that yields tokens one by one.
        First sends sources as metadata, then streams the answer.
        """
        # First send sources as a special metadata line
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

        # Then stream each token
        for token in generate_answer_stream(question, chunks):
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

        # Send done signal
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        token_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )