import os
import uuid
import threading
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.schemas import Document, Chunk
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/documents", tags=["documents"])
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
MAX_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))

def run_in_background(document_id: str):
    from workers.processor import process_document
    process_document(document_id)

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
    document = Document(
        filename=file.filename,
        file_path=file_path,
        status="PENDING",
        file_size=len(contents)
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    thread = threading.Thread(target=run_in_background, args=(document.id,))
    thread.daemon = True
    thread.start()
    print(f"Background thread started for: {document.id}")
    return {
        "message": "Document uploaded! Processing started.",
        "document_id": document.id,
        "filename": document.filename,
        "status": document.status,
        "size_mb": round(size_mb, 2)
    }

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
    chunks = db.query(Chunk).filter(
        Chunk.document_id == document_id
    ).order_by(Chunk.chunk_index).all()
    return {
        "document": document.filename,
        "status": document.status,
        "total_chunks": len(chunks),
        "chunks": [c.to_dict() for c in chunks]
    }