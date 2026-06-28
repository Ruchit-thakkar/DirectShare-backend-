import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Main] Direct Share backend starting up...")
    yield
    print("[Main] Direct Share backend shutting down...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan
)

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001", "http://127.0.0.1:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Room-ID", "X-File-ID", "X-Chunk-Index", "X-Chunk-Size", "X-Checksum"]
)

# Include WebRTC Signaling WebSocket Router
from app.api.signaling import router as signaling_router
app.include_router(signaling_router)

@app.get("/")
def home():
    """Welcome route."""
    return {
        "status": "online",
        "message": "Direct Share Server Relay Service is running.",
        "version": "1.0.0"
    }

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
