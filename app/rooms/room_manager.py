import string
import random
from typing import Dict, List, Optional
from app.rooms.models import Room, FileMetadata, ReceiverState

class RoomManager:
    def __init__(self):
        # Maps room_id (e.g. "A4D8F2") -> Room object
        self.rooms: Dict[str, Room] = {}

    def _generate_code(self, length: int = 6) -> str:
        """Generate a random alphanumeric uppercase string."""
        chars = string.ascii_uppercase + string.digits
        return "".join(random.choices(chars, k=length))

    def generate_room_id(self) -> str:
        """Generate a unique room ID."""
        while True:
            code = self._generate_code()
            if code not in self.rooms:
                return code

    def create_room(self, sender_id: str, sender_name: str) -> Room:
        """Create a new room and register the sender."""
        room_id = self.generate_room_id()
        room = Room(
            room_id=room_id,
            sender_id=sender_id,
            sender_name=sender_name,
            sender_connected=True
        )
        self.rooms[room_id] = room
        return room

    def get_room(self, room_id: str) -> Optional[Room]:
        """Get room by ID. Case-insensitive lookup."""
        return self.rooms.get(room_id.upper())

    def join_room(self, room_id: str, receiver_id: str, display_name: str) -> Optional[Room]:
        """Add or reconnect a receiver in the room."""
        room = self.get_room(room_id)
        if not room:
            return None

        if receiver_id in room.receivers:
            # Reconnection flow
            receiver = room.receivers[receiver_id]
            receiver.connected = True
            if display_name:
                receiver.display_name = display_name
        else:
            # New receiver joining
            room.receivers[receiver_id] = ReceiverState(
                id=receiver_id,
                display_name=display_name,
                connected=True
            )
        return room

    def register_files(self, room_id: str, sender_id: str, files_data: List[dict]) -> bool:
        """Register the files metadata for the room. Only sender can do this."""
        room = self.get_room(room_id)
        if not room or room.sender_id != sender_id:
            return False

        for f in files_data:
            file_id = f.get("id")
            if file_id:
                room.files[file_id] = FileMetadata(
                    id=file_id,
                    name=f.get("name", "unnamed"),
                    size=f.get("size", 0),
                    total_chunks=f.get("total_chunks", 1),
                    mime_type=f.get("mime_type", "application/octet-stream")
                )
        return True

    def mark_chunk_uploaded(self, room_id: str, file_id: str, chunk_index: int) -> bool:
        """Mark a chunk as uploaded for a file. Returns True if all chunks are now uploaded."""
        room = self.get_room(room_id)
        if not room or file_id not in room.files:
            return False

        file_meta = room.files[file_id]
        file_meta.uploaded_chunks.add(chunk_index)
        return len(file_meta.uploaded_chunks) == file_meta.total_chunks

    def update_receiver_progress(self, room_id: str, receiver_id: str, file_id: str, chunk_index: int) -> bool:
        """Update receiver's last completed chunk index. Returns True if successfully updated."""
        room = self.get_room(room_id)
        if not room or receiver_id not in room.receivers or file_id not in room.files:
            return False

        receiver = room.receivers[receiver_id]
        current_val = receiver.download_progress.get(file_id, -1)
        if chunk_index > current_val:
            receiver.download_progress[file_id] = chunk_index
            return True
        return False

    def disconnect_client(self, room_id: str, client_id: str, role: str) -> Optional[Room]:
        """Mark sender or receiver as disconnected."""
        room = self.get_room(room_id)
        if not room:
            return None

        if role == "sender" and room.sender_id == client_id:
            room.sender_connected = False
        elif role == "receiver" and client_id in room.receivers:
            room.receivers[client_id].connected = False
        return room

    def remove_room(self, room_id: str) -> bool:
        """Remove a room from the registry."""
        room_id_upper = room_id.upper()
        if room_id_upper in self.rooms:
            del self.rooms[room_id_upper]
            return True
        return False

# Global instance
room_manager = RoomManager()
