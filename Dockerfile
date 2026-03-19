FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only torch first (much smaller than default)
RUN pip install --no-cache-dir torch==2.3.0 --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --no-deps sentence-transformers==3.0.0
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p uploads static

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]