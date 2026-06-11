import os
import json
import shutil
import tempfile
import asyncio
from typing import Optional, List
from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import sys
import os
# Ensure the backend directory is in the import path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ingestion.manager import IngestionManager
from database.vector_store import VectorStoreManager
from database.llm import LLMManager

app = FastAPI(title="Social Data RAG Backend")

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins in development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory ingestion state tracking
ingestion_state = {
    "status": "idle",       # "idle", "processing", "completed", "failed"
    "progress": 0,          # 0 to 100
    "current_step": "",
    "total_posts": 0,
    "total_chunks": 0,
    "error": None
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

def load_config() -> dict:
    """Loads configuration from file and/or environment variables."""
    config = {
        "llm_provider": os.environ.get("LLM_PROVIDER", "local"),
        "embedding_provider": os.environ.get("EMBEDDING_PROVIDER", "local"),
        "openai_api_key": os.environ.get("OPENAI_API_KEY", ""),
        "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
        "groq_api_key": os.environ.get("GROQ_API_KEY", ""),
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                saved = json.load(f)
                config.update(saved)
        except Exception as e:
            print(f"Error loading config.json: {e}")
            
    return config

def save_config(config: dict):
    """Saves configuration to file."""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Error saving config.json: {e}")

# Initialize core services
db_path = os.path.join(BASE_DIR, "chroma_db")
config = load_config()
vector_store = VectorStoreManager(db_path=db_path, default_provider=config["embedding_provider"])
ingestion_manager = IngestionManager()
llm_manager = LLMManager()

class QueryRequest(BaseModel):
    question: str
    top_k: Optional[int] = 5
    platform: Optional[str] = None
    llm_provider: Optional[str] = None
    embedding_provider: Optional[str] = None

class SettingsRequest(BaseModel):
    llm_provider: str
    embedding_provider: str
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None

async def run_background_ingestion(temp_file_path: str, filename: str):
    """Asynchronous background task to ingest and index files without blocking the server."""
    global ingestion_state
    ingestion_state["status"] = "processing"
    ingestion_state["progress"] = 10
    ingestion_state["current_step"] = "Extracting uploaded archive..."
    ingestion_state["error"] = None
    
    current_config = load_config()
    
    try:
        # 1. Parse files
        await asyncio.sleep(0.5)  # yield control to loop
        ingestion_state["progress"] = 25
        ingestion_state["current_step"] = f"Parsing content from {filename}..."
        
        posts, profiles = ingestion_manager.ingest_zip(temp_file_path)
        
        total_posts = len(posts)
        total_profiles = len(profiles)
        
        ingestion_state["total_posts"] = total_posts
        ingestion_state["progress"] = 50
        ingestion_state["current_step"] = f"Chunking and embedding {total_posts} posts..."
        
        if total_posts == 0 and total_profiles == 0:
            raise ValueError("No compatible LinkedIn, Twitter, or Instagram data found in the uploaded file.")

        # 2. Vector DB Upload
        await asyncio.sleep(0.5)
        
        # Save profiles first
        if profiles:
            vector_store.upsert_profiles(profiles)
            
        # Chunk, embed and upsert posts
        # We pass the API key if OpenAI embeddings are configured
        emb_provider = current_config["embedding_provider"]
        api_key = current_config["openai_api_key"] if emb_provider == "openai" else None
        
        # Perform chunking/upsertion
        total_chunks = vector_store.upsert_posts(
            posts=posts,
            provider=emb_provider,
            api_key=api_key
        )
        
        ingestion_state["total_chunks"] = total_chunks
        ingestion_state["progress"] = 100
        ingestion_state["status"] = "completed"
        ingestion_state["current_step"] = "Ingestion completed successfully!"
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        ingestion_state["status"] = "failed"
        ingestion_state["error"] = str(e)
        ingestion_state["current_step"] = "Ingestion failed."
    finally:
        # Clean up temporary upload file
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                pass

@app.post("/api/ingest/upload")
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Receives data export file/zip and triggers background ingestion pipeline."""
    global ingestion_state
    if ingestion_state["status"] == "processing":
        raise HTTPException(status_code=400, detail="An ingestion pipeline is already running.")
        
    # Write to a temporary file
    temp_dir = tempfile.mkdtemp()
    temp_file_path = os.path.join(temp_dir, file.filename)
    
    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Schedule background ingestion
    background_tasks.add_task(run_background_ingestion, temp_file_path, file.filename)
    
    return {"message": "Upload successful. Ingestion started in background."}

@app.get("/api/ingest/status")
async def get_ingestion_status():
    """Poll endpoint for the frontend to monitor ingestion progress."""
    return ingestion_state

@app.get("/api/ingest/stats")
async def get_database_stats():
    """Retrieves metadata counts and statistical facts from vector store."""
    stats = vector_store.get_stats()
    return stats

@app.post("/api/chat")
async def chat_endpoint(req: QueryRequest = Body(...)):
    """Performs similarity search in ChromaDB and returns a streaming LLM response."""
    current_config = load_config()
    
    llm_provider = req.llm_provider or current_config["llm_provider"]
    emb_provider = req.embedding_provider or current_config["embedding_provider"]
    
    # Check for keys
    api_key = ""
    if llm_provider == "openai" or emb_provider == "openai":
        api_key = current_config["openai_api_key"]
        if not api_key:
            raise HTTPException(status_code=400, detail="OpenAI API Key is missing. Configure it in Settings.")
    elif llm_provider == "gemini" or llm_provider == "local":
        api_key = current_config["gemini_api_key"]
        if not api_key:
            raise HTTPException(status_code=400, detail="Gemini API Key is missing. Configure it in Settings.")
    elif llm_provider == "groq":
        api_key = current_config["groq_api_key"]
        if not api_key:
            raise HTTPException(status_code=400, detail="Groq API Key is missing. Configure it in Settings.")

    # 1. Retrieve similar chunks
    try:
        emb_api_key = current_config["openai_api_key"] if emb_provider == "openai" else None
        context_chunks = vector_store.query_similarity(
            query=req.question,
            top_k=req.top_k,
            platform=req.platform,
            provider=emb_provider,
            api_key=emb_api_key
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query database: {str(e)}")

    # 2. Build prompt
    prompt = llm_manager.build_rag_prompt(req.question, context_chunks)

    # 3. Stream back LLM completion
    async def response_streamer():
        # First send the retrieved context citations as meta-information
        citations = []
        for idx, chunk in enumerate(context_chunks):
            meta = chunk["metadata"]
            citations.append({
                "index": idx + 1,
                "platform": meta.get("platform"),
                "timestamp": meta.get("timestamp"),
                "author": meta.get("author"),
                "original_id": meta.get("original_id"),
                "snippet": chunk["document"][:200] + "..." if len(chunk["document"]) > 200 else chunk["document"]
            })
            
        # Yield citation header
        yield "METADATA_START\n"
        yield json.dumps({"citations": citations}) + "\n"
        yield "METADATA_END\n\n"
        
        # Resolve 'local' provider to 'gemini' for the LLM call
        resolved_llm_provider = "gemini" if llm_provider == "local" else llm_provider
        llm_model = current_config.get("llm_model") or (
            "gemini-2.0-flash" if resolved_llm_provider == "gemini" 
            else "llama-3.3-70b-versatile" if resolved_llm_provider == "groq" 
            else "gpt-4o-mini"
        )
        
        # Yield actual response content stream
        async for text_chunk in llm_manager.generate_stream(prompt, provider=resolved_llm_provider, api_key=api_key, model=llm_model):
            yield text_chunk

    return StreamingResponse(response_streamer(), media_type="text/event-stream")

@app.get("/api/settings")
async def get_settings():
    """Retrieves current API settings, masking sensitive keys for security."""
    current_config = load_config()
    
    def mask_key(k: str) -> str:
        if not k:
            return ""
        if len(k) <= 8:
            return "*****"
        return f"{k[:4]}...{k[-4:]}"
        
    return {
        "llm_provider": current_config["llm_provider"],
        "embedding_provider": current_config["embedding_provider"],
        "has_openai_key": bool(current_config["openai_api_key"]),
        "has_gemini_key": bool(current_config["gemini_api_key"]),
        "has_groq_key": bool(current_config["groq_api_key"]),
        "masked_openai_key": mask_key(current_config["openai_api_key"]),
        "masked_gemini_key": mask_key(current_config["gemini_api_key"]),
        "masked_groq_key": mask_key(current_config["groq_api_key"])
    }

@app.post("/api/settings")
async def update_settings(req: SettingsRequest):
    """Updates API provider selections and API keys in config.json."""
    current_config = load_config()
    
    current_config["llm_provider"] = req.llm_provider
    current_config["embedding_provider"] = req.embedding_provider
    
    # Only update keys if they are provided (not null/empty, or if they are changing)
    # Allows updating other settings without re-sending full keys
    if req.openai_api_key is not None:
        if req.openai_api_key.strip() != "" and not req.openai_api_key.startswith("..."):
            current_config["openai_api_key"] = req.openai_api_key.strip()
        elif req.openai_api_key.strip() == "":
            current_config["openai_api_key"] = ""
            
    if req.gemini_api_key is not None:
        if req.gemini_api_key.strip() != "" and not req.gemini_api_key.startswith("..."):
            current_config["gemini_api_key"] = req.gemini_api_key.strip()
        elif req.gemini_api_key.strip() == "":
            current_config["gemini_api_key"] = ""
            
    if req.groq_api_key is not None:
        if req.groq_api_key.strip() != "" and not req.groq_api_key.startswith("..."):
            current_config["groq_api_key"] = req.groq_api_key.strip()
        elif req.groq_api_key.strip() == "":
            current_config["groq_api_key"] = ""

    save_config(current_config)
    
    # Dynamic reload of vector store default embedding provider
    global vector_store
    vector_store.default_provider = req.embedding_provider
    
    return {"message": "Settings updated successfully."}

@app.post("/api/clear")
async def clear_database():
    """Clears all vectors in the knowledge base."""
    global vector_store
    vector_store.clear_database()
    return {"message": "Vector database cleared successfully."}

# Serve static files from the compiled React frontend
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend", "dist")
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    print(f"Warning: Frontend static directory not found at {FRONTEND_DIR}. Frontend will not be served.")
