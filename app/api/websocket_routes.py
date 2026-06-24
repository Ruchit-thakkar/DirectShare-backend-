from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from app.rooms.room_manager import room_manager
from app.core.websocket_manager import websocket_manager

router = APIRouter(prefix="/ws", tags=["websockets"])

@router.websocket("/{room_code}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_code: str,
    role: str = Query(...),
    client_id: str = Query(...),
    display_name: str = Query("")
):
    """
    WebSocket endpoint for real-time control events and state updates.
    """
    room_code_upper = room_code.upper()
    room = room_manager.get_room(room_code_upper)

    if not room:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Room not found")
        return

    if role == "sender":
        if room.sender_id != client_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized sender ID")
            return
        room.sender_connected = True
    elif role == "receiver":
        room_manager.join_room(room_code_upper, client_id, display_name)
    else:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid role")
        return

    await websocket_manager.connect(room_code_upper, client_id, role, websocket)
    websocket_manager.start()

    try:
        if role == "sender":
            receivers_state = {}
            for rec_id, rec in room.receivers.items():
                receivers_state[rec_id] = {
                    "id": rec.id,
                    "display_name": rec.display_name,
                    "connected": rec.connected,
                    "download_progress": rec.download_progress
                }

            files_state = {}
            for f_id, f in room.files.items():
                files_state[f_id] = {
                    "id": f.id,
                    "name": f.name,
                    "size": f.size,
                    "total_chunks": f.total_chunks,
                    "mime_type": f.mime_type,
                    "uploaded_chunks": list(f.uploaded_chunks)
                }

            await websocket_manager.send_json(websocket, {
                "type": "room_state",
                "room_id": room.room_id,
                "sender_name": room.sender_name,
                "sender_connected": room.sender_connected,
                "files": files_state,
                "receivers": receivers_state
            })
            
            await websocket_manager.broadcast_to_room(
                room_code_upper, 
                {"type": "sender_connected"}, 
                exclude_receivers=False
            )

        elif role == "receiver":
            files_state = {}
            for f_id, f in room.files.items():
                files_state[f_id] = {
                    "id": f.id,
                    "name": f.name,
                    "size": f.size,
                    "total_chunks": f.total_chunks,
                    "mime_type": f.mime_type,
                    "is_upload_complete": len(f.uploaded_chunks) == f.total_chunks
                }

            rec_progress = room.receivers[client_id].download_progress

            await websocket_manager.send_json(websocket, {
                "type": "files_available",
                "room_id": room.room_id,
                "files": files_state,
                "progress": rec_progress
            })

            await websocket_manager.send_to_sender(room_code_upper, {
                "type": "receiver_joined",
                "receiver_id": client_id,
                "display_name": display_name
            })

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            websocket_manager.update_activity(room_code_upper, client_id, role)

            if msg_type == "pong":
                continue

            elif msg_type == "ping":
                await websocket_manager.send_json(websocket, {"type": "pong"})

            elif msg_type == "accept_download":
                if role == "receiver":
                    file_id = data.get("file_id")
                    await websocket_manager.send_to_sender(room_code_upper, {
                        "type": "download_started",
                        "receiver_id": client_id,
                        "file_id": file_id
                    })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WebSocket] Route Error in {room_code} for {client_id}: {e}")
    finally:
        websocket_manager.disconnect(room_code_upper, client_id, role)
        
        room = room_manager.disconnect_client(room_code_upper, client_id, role)
        
        if room:
            if role == "receiver":
                await websocket_manager.send_to_sender(room_code_upper, {
                    "type": "receiver_left",
                    "receiver_id": client_id
                })
            elif role == "sender":
                await websocket_manager.broadcast_to_room(room_code_upper, {
                    "type": "sender_disconnected"
                }, exclude_receivers=False)
