import fitz
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
        full_text += f"\n--- PAGE {page_number + 1} ---\n"
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
