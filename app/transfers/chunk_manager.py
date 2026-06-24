import os
import shutil
import aiofiles
from pathlib import Path
from app.core.config import settings

CHUNK_SIZE = 524288  # 512 KB

class ChunkManager:
    def __init__(self, storage_dir: Path = settings.TEMP_STORAGE_DIR):
        self.storage_dir = storage_dir

    def get_room_dir(self, room_id: str) -> Path:
        """Get the directory path for a room's temp files."""
        return self.storage_dir / room_id.upper()

    def get_file_path(self, room_id: str, file_id: str) -> Path:
        """Get the file path for a specific file in a room."""
        return self.get_room_dir(room_id) / file_id

    async def write_chunk(self, room_id: str, file_id: str, chunk_index: int, data: bytes):
        """Write a chunk of data to the file at the correct offset using async file seeking."""
        file_path = self.get_file_path(room_id, file_id)
        room_dir = self.get_room_dir(room_id)

        os.makedirs(room_dir, exist_ok=True)

        if not file_path.exists():
            async with aiofiles.open(file_path, "wb") as f:
                pass

        offset = chunk_index * CHUNK_SIZE
        async with aiofiles.open(file_path, "r+b") as f:
            await f.seek(offset)
            await f.write(data)

    async def read_chunk(self, room_id: str, file_id: str, chunk_index: int, expected_size: int) -> bytes:
        """Read a chunk from the file at the correct offset."""
        file_path = self.get_file_path(room_id, file_id)
        if not file_path.exists():
            raise FileNotFoundError(f"File {file_id} not found in room {room_id}")

        offset = chunk_index * CHUNK_SIZE
        async with aiofiles.open(file_path, "rb") as f:
            await f.seek(offset)
            data = await f.read(expected_size)
            return data

    def delete_room_files(self, room_id: str) -> bool:
        """Delete all temporary files and the folder associated with a room."""
        room_dir = self.get_room_dir(room_id)
        if room_dir.exists() and room_dir.is_dir():
            shutil.rmtree(room_dir, ignore_errors=True)
            return True
        return False

# Global instance
chunk_manager = ChunkManager()
