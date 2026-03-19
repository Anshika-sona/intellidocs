FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for PyMuPDF and Tesseract
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all app code
COPY . .

# Create uploads folder
RUN mkdir -p uploads

# Start the server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]