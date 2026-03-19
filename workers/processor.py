import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import SessionLocal
from app.models.schemas import Document, Chunk
from app.services.ingestion import extract_text_from_pdf, chunk_text
from app.services.search import generate_embedding


def process_document(document_id: str):
    """
    Runs in background when a PDF is uploaded.
    Now does 4 things:
    1. Extracts text from PDF
    2. Splits into chunks
    3. Generates embedding for each chunk
    4. Saves everything to database
    """

    print(f"\n--- Worker started for document: {document_id} ---")

    db = SessionLocal()

    try:
        # Find document in DB
        document = db.query(Document).filter(
            Document.id == document_id
        ).first()

        if not document:
            print(f"Document {document_id} not found!")
            return

        print(f"Processing: {document.filename}")

        # Update status
        document.status = "PROCESSING"
        db.commit()
        print("Status → PROCESSING")

        # Step 1 - Extract text
        result = extract_text_from_pdf(document.file_path)
        document.page_count = result["page_count"]
        db.commit()

        # Step 2 - Chunk the text
        chunks_data = chunk_text(result["text"], document_id)
        print(f"Created {len(chunks_data)} chunks")

        # Step 3 - Generate embeddings and save
        print("Generating embeddings for each chunk...")

        for i, chunk_data in enumerate(chunks_data):

            # Generate embedding for this chunk
            print(f"  Embedding chunk {i+1}/{len(chunks_data)}...")
            embedding = generate_embedding(chunk_data["text"])

            # Save chunk with embedding
            chunk = Chunk(
                document_id=chunk_data["document_id"],
                text=chunk_data["text"],
                chunk_index=chunk_data["chunk_index"],
                page_number=chunk_data["page_number"],
                word_count=chunk_data["word_count"],
                embedding=embedding
            )
            db.add(chunk)

        db.commit()

        # Mark as DONE
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