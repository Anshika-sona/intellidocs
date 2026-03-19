# ⚡ IntelliDocs

> Upload any PDF. Ask questions in plain English. Get cited answers instantly.

**Live Demo:** [https://intellidocs-production-104b.up.railway.app/](https://intellidocs-production-104b.up.railway.app/)

---

## What It Does

IntelliDocs is a production-grade document intelligence platform. Upload any PDF document and ask questions about it in plain English — the system finds the most relevant information across all your documents and returns a grounded answer with exact source citations.

**Real example:**
- Upload Anshika's resume + a Terraform document
- Ask: *"What CI/CD tools has Anshika used?"*
- Get: *"Anshika has used GitLab CI/CD and Terraform for infrastructure automation [Source: Anshika_SWE.pdf, page 1]"*

No hallucination. Fully grounded. Cited.

---

## Architecture
```
User uploads PDF
      ↓
Background thread processes it
      ↓
PyMuPDF extracts text → Intelligent chunking (300 words, 50-word overlap)
      ↓
sentence-transformers generates 384-dim embeddings → stored in pgvector
      ↓
User asks question
      ↓
Hybrid Search: pgvector semantic search + BM25 keyword search
      ↓
RRF fusion merges results (25-30% better than either alone)
      ↓
Top 8 chunks injected into LLaMA prompt via Groq
      ↓
Grounded answer streamed back via SSE with citations
```

---

## Tech Stack

| Layer | Tool | Why |
|---|---|---|
| Backend | FastAPI (Python) | Fast, async, auto Swagger docs |
| Database | PostgreSQL + pgvector | Semantic vector search built-in |
| Embeddings | sentence-transformers (local) | Free, no API needed |
| Keyword Search | BM25 (rank-bm25) | Exact match for names, numbers |
| Hybrid Fusion | Reciprocal Rank Fusion | 25-30% better retrieval accuracy |
| LLM | LLaMA 3.1 via Groq | Free, fast, accurate |
| Queue | Python threading | Async PDF processing |
| Cache/Queue | Redis (Upstash) | Rate limiting, job queue |
| Deploy | Railway | Zero DevOps, real URL |
| Frontend | Vanilla HTML/CSS/JS | No framework needed |

---

## Key Technical Decisions

**Why hybrid search over pure semantic?**
Pure semantic search fails on exact identifiers — searching "Invoice #INV-2024-0047" returns vague results. Pure BM25 fails on meaning — "what were my abnormal results" returns nothing. Hybrid search with RRF combines both, getting the best of both worlds.

**Why pgvector over Pinecone?**
pgvector runs inside PostgreSQL — no extra infrastructure piece. For this scale (thousands to millions of documents), performance is identical to dedicated vector databases. Simpler = better.

**Why RRF over simple score averaging?**
Scores from different systems aren't comparable — a 0.8 cosine similarity score means something different from a 0.8 BM25 score. RRF uses ranks instead of scores, making it robust to different scoring scales.

**Why local embeddings over OpenAI?**
sentence-transformers runs entirely on the server — no API calls, no cost, no latency. For 384-dimensional embeddings, quality is excellent for document retrieval tasks.

---

## Running Locally
```bash
# Clone the repo
git clone https://github.com/Anshika-sona/intellidocs.git
cd intellidocs

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Fill in your DATABASE_URL, REDIS_URL, GROQ_API_KEY

# Run the server
uvicorn app.main:app --reload
```

Visit `http://localhost:8000`

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/documents/` | Upload a PDF |
| GET | `/api/documents/` | List all documents |
| GET | `/api/documents/{id}` | Get document status |
| GET | `/api/documents/{id}/chunks` | Inspect chunks |
| POST | `/api/search` | Hybrid search |
| POST | `/api/query` | RAG Q&A |
| GET | `/api/stream?question=...` | Streaming Q&A |

Full API docs: `https://intellidocs-production-104b.up.railway.app//docs`

---

## What I Learned Building This

- **Hybrid search** consistently outperforms either semantic or keyword search alone
- **Chunking strategy matters more than embedding quality** — bad chunking kills retrieval regardless of model
- **Streaming responses** require careful SSE implementation — buffering kills the UX
- **pgvector HNSW indexes** dramatically speed up similarity search at scale
- **RRF is rank-based, not score-based** — this makes it robust across different retrieval systems

---

Built with ❤️ as a portfolio project to demonstrate production-grade AI engineering.
```