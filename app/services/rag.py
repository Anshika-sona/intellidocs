import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def build_rag_prompt(question: str, chunks: list) -> str:
    """Builds the prompt with context chunks injected."""
    context_parts = []
    for i, chunk in enumerate(chunks):
        source = f"{chunk['filename']} (page {chunk.get('page_number', '?')})"
        context_parts.append(f"[Source {i+1}: {source}]\n{chunk['text']}")

    context = "\n\n---\n\n".join(context_parts)

    prompt = f"""You are a helpful document assistant. Answer the user's question based ONLY on the provided context below.

RULES:
- Answer ONLY from the context provided
- If the answer is not in the context, say "I could not find this information in the uploaded documents"
- Always cite your sources like this: [Source: filename, page X]
- Be concise and direct

CONTEXT:
{context}

QUESTION: {question}

ANSWER:"""
    return prompt


def generate_answer(question: str, chunks: list) -> dict:
    """Returns complete answer all at once."""
    if not chunks:
        return {
            "answer": "I could not find any relevant information in your documents.",
            "sources": []
        }

    print(f"Generating answer for: '{question}'")
    prompt = build_rag_prompt(question, chunks)

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that answers questions based strictly on provided document context."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1024,
        temperature=0.1
    )

    answer = response.choices[0].message.content
    sources = []
    seen = set()
    for chunk in chunks:
        source = f"{chunk['filename']} - page {chunk.get('page_number', '?')}"
        if source not in seen:
            sources.append(source)
            seen.add(source)

    print("Answer generated successfully")
    return {
        "answer": answer,
        "sources": sources,
        "chunks_used": len(chunks)
    }


def generate_answer_stream(question: str, chunks: list):
    """
    Streams the answer word by word.
    This is a Python generator — it yields tokens one by one.
    
    How it works:
    - Groq sends back tokens as they're generated
    - We yield each token immediately
    - FastAPI sends each token to the browser via SSE
    - Browser displays them as they arrive = streaming effect
    """
    if not chunks:
        yield "I could not find any relevant information in your documents."
        return

    print(f"Streaming answer for: '{question}'")
    prompt = build_rag_prompt(question, chunks)

    # stream=True tells Groq to send tokens as they're generated
    stream = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that answers questions based strictly on provided document context."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1024,
        temperature=0.1,
        stream=True  # THIS is what enables streaming
    )

    # Yield each token as it arrives
    for chunk in stream:
        token = chunk.choices[0].delta.content
        if token is not None:
            yield token