"""
Room Manager — In-memory room registry for DirectShare.

Handles room creation, code generation, QR code generation,
receiver tracking, and room lifecycle.
"""

import uuid
import asyncio
import base64
import io
import random
import string
from dataclasses import dataclass, field
from typing import Optional
from fastapi import WebSocket

import qrcode
from qrcode.image.pil import PilImage


def _generate_room_code(length: int = 6) -> str:
    """Generate a short human-readable alphanumeric room code, e.g. XK9472."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))


def _generate_qr_code(content: str) -> str:
    """Generate a base64-encoded PNG QR code for the given content string."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=2,
    )
    qr.add_data(content)
    qr.make(fit=True)
    img = qr.make_image(image_factory=PilImage)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    b64 = base64.b64encode(buffer.read()).decode('utf-8')
    return f"data:image/png;base64,{b64}"


@dataclass
class ReceiverInfo:
    request_id: str
    username: str
    status: str = "pending"   # pending | connected | rejected
    websocket: Optional[WebSocket] = None


@dataclass
class Room:
    room_id: str
    room_code: str
    qr_code: str
    sender_username: str
    filename: str
    filesize: int
    status: str = "waiting"   # waiting | transferring | completed | closed
    sender_ws: Optional[WebSocket] = None
    receivers: dict = field(default_factory=dict)   # request_id → ReceiverInfo
    transfer_task: Optional[asyncio.Task] = None


class RoomManager:
    """Singleton in-memory room store."""

    def __init__(self):
        # room_id → Room
        self._rooms: dict[str, Room] = {}
        # room_code → room_id (for O(1) lookup by code)
        self._code_index: dict[str, str] = {}

    def create_room(
        self,
        username: str,
        filename: str,
        filesize: int,
        frontend_base_url: str = "http://localhost:3000",
    ) -> Room:
        room_id = str(uuid.uuid4())

        # Ensure room code is unique
        while True:
            room_code = _generate_room_code()
            if room_code not in self._code_index:
                break

        qr_content = f"{frontend_base_url}/receive?code={room_code}"
        qr_code = _generate_qr_code(qr_content)

        room = Room(
            room_id=room_id,
            room_code=room_code,
            qr_code=qr_code,
            sender_username=username,
            filename=filename,
            filesize=filesize,
        )
        self._rooms[room_id] = room
        self._code_index[room_code] = room_id
        return room

    def get_room(self, room_id: str) -> Optional[Room]:
        return self._rooms.get(room_id)

    def get_room_by_code(self, room_code: str) -> Optional[Room]:
        room_id = self._code_index.get(room_code.upper())
        if room_id:
            return self._rooms.get(room_id)
        return None

    def close_room(self, room_id: str) -> Optional[Room]:
        room = self._rooms.get(room_id)
        if room:
            room.status = "closed"
            if room_id in self._rooms:
                del self._rooms[room_id]
            if room.room_code in self._code_index:
                del self._code_index[room.room_code]
        return room

    def add_join_request(self, room: Room, username: str) -> ReceiverInfo:
        request_id = str(uuid.uuid4())
        receiver = ReceiverInfo(request_id=request_id, username=username)
        room.receivers[request_id] = receiver
        return receiver

    def accept_receiver(self, room: Room, request_id: str) -> Optional[ReceiverInfo]:
        receiver = room.receivers.get(request_id)
        if receiver:
            receiver.status = "connected"
        return receiver

    def reject_receiver(self, room: Room, request_id: str) -> Optional[ReceiverInfo]:
        receiver = room.receivers.get(request_id)
        if receiver:
            receiver.status = "rejected"
        return receiver

    def connected_count(self, room: Room) -> int:
        return sum(1 for r in room.receivers.values() if r.status == "connected")

    def connected_receivers(self, room: Room) -> list[ReceiverInfo]:
        return [r for r in room.receivers.values() if r.status == "connected"]


# Global singleton
room_manager = RoomManager()
