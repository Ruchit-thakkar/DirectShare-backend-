"""
WebSocket endpoint for real-time room communication.

URL: ws://localhost:8000/ws/rooms/{room_id}
Query params:
  - role: "sender" | "receiver"
  - username: receiver's display name (required when role=receiver)
  - requestId: the request_id returned by POST /api/rooms/join (required for receivers)

Message protocol (JSON):
  { "event": "<event_name>", "data": { ... } }

Client → Server events:
  - accept_receiver   { requestId }
  - reject_receiver   { requestId }
  - start_transfer    {}
  - close_room        {}

Server → Client events (see PRD §5.2):
  All 10 specified events are sent as { "event": "...", "data": { ... } }
"""

import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.room_manager import room_manager
from app.services.transfer_manager import run_transfer

router = APIRouter(tags=["websocket"])


async def _send(ws: WebSocket, event: str, data: dict):
    try:
        await ws.send_json({"event": event, "data": data})
    except Exception:
        pass


@router.websocket("/ws/rooms/{room_id}")
async def room_websocket(
    websocket: WebSocket,
    room_id: str,
    role: str = "sender",
    username: str = "",
    requestId: str = "",
):
    await websocket.accept()

    room = room_manager.get_room(room_id)
    if not room:
        await _send(websocket, "error", {"message": "Room Not Found"})
        await websocket.close(code=4004)
        return

    if room.status == "closed":
        await _send(websocket, "room_closed", {})
        await websocket.close(code=4010)
        return

    # ── Sender connection ────────────────────────────────────────────────────
    if role == "sender":
        room.sender_ws = websocket
        await _send(websocket, "room_created", {
            "roomId": room.room_id,
            "roomCode": room.room_code,
            "qrCode": room.qr_code,
            "status": room.status,
        })

        try:
            while True:
                data = await websocket.receive_json()
                event = data.get("event")
                payload = data.get("data", {})

                if event == "accept_receiver":
                    req_id = payload.get("requestId")
                    receiver = room_manager.accept_receiver(room, req_id)
                    if receiver and receiver.websocket:
                        await _send(receiver.websocket, "join_accepted", {
                            "roomId": room.room_id,
                            "filename": room.filename,
                            "filesize": room.filesize,
                        })
                    # Notify sender of updated connected count
                    count = room_manager.connected_count(room)
                    await _send(websocket, "receiver_connected", {
                        "username": receiver.username if receiver else "",
                        "connectedCount": count,
                        "receivers": [
                            {"username": r.username, "status": r.status}
                            for r in room.receivers.values()
                            if r.status == "connected"
                        ],
                    })

                elif event == "reject_receiver":
                    req_id = payload.get("requestId")
                    receiver = room_manager.reject_receiver(room, req_id)
                    if receiver and receiver.websocket:
                        await _send(receiver.websocket, "join_rejected", {})

                elif event == "start_transfer":
                    if room.transfer_task is None or room.transfer_task.done():
                        room.transfer_task = asyncio.create_task(run_transfer(room_id))

                elif event == "close_room":
                    closed = room_manager.close_room(room_id)
                    # Notify all connected receivers
                    if closed:
                        for receiver in list(closed.receivers.values()):
                            if receiver.websocket:
                                await _send(receiver.websocket, "room_closed", {})
                    await _send(websocket, "room_closed", {})
                    await websocket.close()
                    return

        except WebSocketDisconnect:
            pass

        finally:
            if room.sender_ws is websocket:
                room.sender_ws = None

    # ── Receiver connection ──────────────────────────────────────────────────
    elif role == "receiver":
        # Attach this websocket to the matching ReceiverInfo
        receiver_info = room.receivers.get(requestId)
        if not receiver_info:
            await _send(websocket, "error", {"message": "Invalid request ID"})
            await websocket.close(code=4004)
            return

        receiver_info.websocket = websocket

        try:
            while True:
                # Receivers are mostly passive; they just listen for events.
                # We keep the loop alive with a ping-like receive.
                try:
                    await asyncio.wait_for(websocket.receive_json(), timeout=60.0)
                except asyncio.TimeoutError:
                    # Send a ping to keep the connection alive
                    await _send(websocket, "ping", {})
        except WebSocketDisconnect:
            pass

        finally:
            if receiver_info.websocket is websocket:
                receiver_info.websocket = None
            # Notify sender about disconnection
            if room.sender_ws and receiver_info.status == "connected":
                receiver_info.status = "disconnected"
                count = room_manager.connected_count(room)
                await _send(room.sender_ws, "receiver_disconnected", {
                    "username": receiver_info.username,
                    "connectedCount": count,
                    "receivers": [
                        {"username": r.username, "status": r.status}
                        for r in room.receivers.values()
                        if r.status == "connected"
                    ],
                })
