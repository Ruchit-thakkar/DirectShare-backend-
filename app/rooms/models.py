from pydantic import BaseModel, Field
from typing import Dict, Set, List, Optional
import time

class FileMetadata(BaseModel):
    id: str
    name: str
    size: int
    total_chunks: int
    mime_type: str
    uploaded_chunks: Set[int] = Field(default_factory=set)

    class Config:
        json_encoders = {
            set: list
        }

class ReceiverState(BaseModel):
    id: str
    display_name: str
    connected: bool = True
    # Maps file_id -> last completed chunk index (e.g. { "file_abc": 14 })
    download_progress: Dict[str, int] = Field(default_factory=dict)

class Room(BaseModel):
    room_id: str
    sender_id: str
    sender_name: str
    sender_connected: bool = True
    files: Dict[str, FileMetadata] = Field(default_factory=dict)
    receivers: Dict[str, ReceiverState] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)

    def is_expired(self, expiration_hours: int) -> bool:
        expiration_seconds = expiration_hours * 3600
        return (time.time() - self.created_at) > expiration_seconds
