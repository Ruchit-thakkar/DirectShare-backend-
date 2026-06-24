import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.upload_routes import router as upload_router
from app.api.websocket_routes import router as ws_router
from app.services.cleanup import run_cleanup_loop

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Main] Direct Share backend starting up...")
    
    from app.core.websocket_manager import websocket_manager
    websocket_manager.start()

    cleanup_task = asyncio.create_task(run_cleanup_loop())
    
    yield
    
    print("[Main] Direct Share backend shutting down...")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

# Initialize FastAPI App
app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan
)

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Room-ID", "X-File-ID", "X-Chunk-Index", "X-Chunk-Size", "X-Checksum"]
)

# Register routers
app.include_router(upload_router, prefix=settings.API_V1_STR)
app.include_router(ws_router)

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
