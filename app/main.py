import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from app.db.database import engine, test_connection
from app.models.schemas import Base
from app.api import documents
from app.api import query

load_dotenv()

app = FastAPI(
    title="IntelliDocs",
    description="Document intelligence platform",
    version="0.1.0"
)

@app.on_event("startup")
async def startup_event():
    print("Starting IntelliDocs...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created!")
    test_connection()

app.include_router(documents.router)
app.include_router(query.router)

# Serve the frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_frontend():
    return FileResponse("static/index.html")

@app.get("/health")
def health_check():
    return {"status": "healthy", "message": "IntelliDocs is running!"}