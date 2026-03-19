import os

files = {
    'app/models/schemas.py': '''import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.db.database import Base

class Document(Base):
    __tablename__ = "documents"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    status = Column(String, default="PENDING")
    file_size = Column(Integer, nullable=True)
    page_count = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
    def to_dict(self):
        return {"id": self.id, "filename": self.filename, "status": self.status, "file_size": self.file_size, "page_count": self.page_count, "error_message": self.error_message, "created_at": str(self.created_at)}

class Chunk(Base):
    __tablename__ = "chunks"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=True)
    word_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    document = relationship("Document", back_populates="chunks")
    def to_dict(self):
        return {"id": self.id, "document_id": self.document_id, "text": self.text[:200] + "..." if len(self.text) > 200 else self.text, "chunk_index": self.chunk_index, "page_number": self.page_number, "word_count": self.word_count}
''',

    'app/main.py': '''import os
from fastapi import FastAPI
from dotenv import load_dotenv
from app.db.database import engine, test_connection
from app.models.schemas import Base
from app.api import documents

load_dotenv()

app = FastAPI(title="IntelliDocs", description="Document intelligence platform", version="0.1.0")

@app.on_event("startup")
async def startup_event():
    print("Starting IntelliDocs...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created!")
    test_connection()

app.include_router(documents.router)

@app.get("/health")
def health_check():
    return {"status": "healthy", "message": "IntelliDocs is running!"}
''',

    'app/services/ingestion.py': '''import fitz
import os

def extract_text_from_pdf(file_path: str) -> dict:
    print(f"Opening PDF: {file_path}")
    pdf = fitz.open(file_path)
    page_count = len(pdf)
    full_text = ""
    print(f"PDF has {page_count} pages")
    for page_number in range(page_count):
        page = pdf[page_number]
        page_text = page.get_text()
        full_text += f"\\n--- PAGE {page_number + 1} ---\\n"
        full_text += page_text
    pdf.close()
    full_text = full_text.strip()
    word_count = len(full_text.split())
    print(f"Extracted {word_count} words from PDF")
    return {"text": full_text, "page_count": page_count, "word_count": word_count}

def chunk_text(text: str, document_id: str) -> list:
    words = text.split()
    chunks = []
    chunk_size = 300
    overlap = 50
    step = chunk_size - overlap
    chunk_index = 0
    position = 0
    while position < len(words):
        chunk_words = words[position: position + chunk_size]
        chunk_text_content = " ".join(chunk_words)
        approx_page = (position // 250) + 1
        chunks.append({"document_id": document_id, "text": chunk_text_content, "chunk_index": chunk_index, "page_number": approx_page, "word_count": len(chunk_words)})
        chunk_index += 1
        position += step
        if len(chunk_words) < 50:
            break
    print(f"Split into {len(chunks)} chunks")
    return chunks
''',

    'workers/processor.py': '''import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.db.database import SessionLocal
from app.models.schemas import Document, Chunk
from app.services.ingestion import extract_text_from_pdf, chunk_text

def process_document(document_id: str):
    print(f"\\n--- Worker started for document: {document_id} ---")
    db = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            print(f"Document {document_id} not found!")
            return
        print(f"Processing: {document.filename}")
        document.status = "PROCESSING"
        db.commit()
        print("Status -> PROCESSING")
        result = extract_text_from_pdf(document.file_path)
        document.page_count = result["page_count"]
        db.commit()
        chunks_data = chunk_text(result["text"], document_id)
        print(f"Saving {len(chunks_data)} chunks...")
        for chunk_data in chunks_data:
            chunk = Chunk(document_id=chunk_data["document_id"], text=chunk_data["text"], chunk_index=chunk_data["chunk_index"], page_number=chunk_data["page_number"], word_count=chunk_data["word_count"])
            db.add(chunk)
        db.commit()
        document.status = "DONE"
        db.commit()
        print(f"--- Done! Pages: {result['page_count']}, Chunks: {len(chunks_data)} ---")
    except Exception as e:
        print(f"ERROR: {str(e)}")
        document.status = "FAILED"
        document.error_message = str(e)
        db.commit()
    finally:
        db.close()
''',

    'app/api/documents.py': '''import os
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from redis import Redis
from rq import Queue
from app.db.database import get_db
from app.models.schemas import Document, Chunk
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/documents", tags=["documents"])
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
MAX_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
REDIS_URL = os.getenv("REDIS_URL")

redis_conn = Redis.from_url(REDIS_URL, ssl_cert_reqs=None)
task_queue = Queue("documents", connection=redis_conn)

@router.post("/")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_SIZE_MB:
        raise HTTPException(status_code=400, detail=f"File too large. Max is {MAX_SIZE_MB}MB")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    with open(file_path, "wb") as f:
        f.write(contents)
    document = Document(filename=file.filename, file_path=file_path, status="PENDING", file_size=len(contents))
    db.add(document)
    db.commit()
    db.refresh(document)
    from workers.processor import process_document
    task_queue.enqueue(process_document, document.id)
    print(f"Job queued for document: {document.id}")
    return {"message": "Document uploaded! Processing started.", "document_id": document.id, "filename": document.filename, "status": document.status, "size_mb": round(size_mb, 2)}

@router.get("/")
def list_documents(db: Session = Depends(get_db)):
    documents = db.query(Document).order_by(Document.created_at.desc()).all()
    return {"total": len(documents), "documents": [doc.to_dict() for doc in documents]}

@router.get("/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document.to_dict()

@router.get("/{document_id}/chunks")
def get_document_chunks(document_id: str, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    chunks = db.query(Chunk).filter(Chunk.document_id == document_id).order_by(Chunk.chunk_index).all()
    return {"document": document.filename, "status": document.status, "total_chunks": len(chunks), "chunks": [c.to_dict() for c in chunks]}
'''
}

for filepath, content in files.items():
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Written: {filepath}")

print("\\nAll files written successfully!")
