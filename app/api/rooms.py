"""
Room REST API routes.

POST /api/rooms/create  — Create a new share room
POST /api/rooms/join    — Request to join a room
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.room_manager import room_manager

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


# ── Request / Response models ────────────────────────────────────────────────

class CreateRoomRequest(BaseModel):
    username: str
    filename: str
    filesize: int


class CreateRoomResponse(BaseModel):
    roomId: str
    roomCode: str
    qrCode: str
    status: str


class JoinRoomRequest(BaseModel):
    username: str
    roomCode: str


class JoinRoomResponse(BaseModel):
    success: bool
    message: str
    requestId: str | None = None
    roomId: str | None = None
    filename: str | None = None
    filesize: int | None = None


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/create", response_model=CreateRoomResponse)
async def create_room(body: CreateRoomRequest):
    """Create a new share room and return connection details."""
    room = room_manager.create_room(
        username=body.username,
        filename=body.filename,
        filesize=body.filesize,
    )
    return CreateRoomResponse(
        roomId=room.room_id,
        roomCode=room.room_code,
        qrCode=room.qr_code,
        status=room.status,
    )


@router.post("/join", response_model=JoinRoomResponse)
async def join_room(body: JoinRoomRequest):
    """
    Validate the room code and create a pending join request.

    The actual approval notification is pushed to the sender via WebSocket.
    """
    room = room_manager.get_room_by_code(body.roomCode)

    if not room:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail={"success": False, "message": "Room Not Found"},
        )

    if room.status == "closed":
        from fastapi import HTTPException
        raise HTTPException(
            status_code=410,
            detail={"success": False, "message": "Room Closed"},
        )

    # Create a pending join request
    receiver = room_manager.add_join_request(room, body.username)

    # Push join_requested event to the sender via their WebSocket
    if room.sender_ws:
        try:
            await room.sender_ws.send_json({
                "event": "join_requested",
                "data": {
                    "requestId": receiver.request_id,
                    "username": receiver.username,
                },
            })
        except Exception:
            pass  # Sender may have disconnected; receiver will handle timeout

    return JoinRoomResponse(
        success=True,
        message="Join request sent to sender",
        requestId=receiver.request_id,
        roomId=room.room_id,
        filename=room.filename,
        filesize=room.filesize,
    )
