import os
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API Configurations
    PROJECT_NAME: str = "Direct Share Backend"
    API_V1_STR: str = "/api"
    
    # CORS Origin
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "https://directshare007.netlify.app")
    
    # Storage Configuration
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    TEMP_STORAGE_DIR: Path = BASE_DIR / "storage" / "temp"
    
    # Room Lifecycles
    ROOM_EXPIRATION_HOURS: int = 24
    
    # Connection Heartbeats (in seconds)
    HEARTBEAT_INTERVAL: float = 15.0
    HEARTBEAT_TIMEOUT: float = 30.0  # client dead after this time without pong
    
    # Periodic Cleanup (in seconds)
    CLEANUP_INTERVAL: float = 1800.0  # Run cleanup task every 30 minutes

    class Config:
        case_sensitive = True
        env_prefix = "DS_"

# Initialize settings
settings = Settings()

# Ensure temp storage directory exists
os.makedirs(settings.TEMP_STORAGE_DIR, exist_ok=True)
