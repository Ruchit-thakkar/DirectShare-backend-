import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict

router = APIRouter(tags=["webrtc_signaling"])

# In-memory mapping of active P2P rooms
# room_id -> { "sender": WebSocket, "receiver": WebSocket, "peer_names": { "sender": str, "receiver": str } }
p2p_rooms: Dict[str, dict] = {}

@router.websocket("/ws/signaling/{room_id}")
async def webrtc_signaling_websocket(
    websocket: WebSocket,
    room_id: str,
    peerId: str,
    role: str,
    displayName: str = ""
):
    await websocket.accept()
    
    if room_id not in p2p_rooms:
        p2p_rooms[room_id] = {
            "sender": None,
            "receiver": None,
            "peer_names": {}
        }
    
    room = p2p_rooms[room_id]
    room[role] = websocket
    room["peer_names"][role] = displayName or f"{role.capitalize()} Device"
    
    print(f"[WebSocket Signaling] Room {room_id}: {role} ({peerId}) connected.")
    
    # If both peers are connected, notify them of each other's names
    partner_role = "receiver" if role == "sender" else "sender"
    partner_ws = room[partner_role]
    
    if partner_ws:
        # Notify the newly connected peer of the existing partner
        await websocket.send_json({
            "type": "peer-joined",
            "peerName": room["peer_names"][partner_role]
        })
        # Notify the existing partner of the newly joined peer
        try:
            await partner_ws.send_json({
                "type": "peer-joined",
                "peerName": displayName or f"{role.capitalize()} Device"
            })
        except Exception:
            pass

    try:
        while True:
            data = await websocket.receive_json()
            # Relay JSON message directly to the partner WebSocket
            partner_ws = room["receiver" if role == "sender" else "sender"]
            if partner_ws:
                try:
                    await partner_ws.send_json(data)
                except Exception:
                    pass
    except WebSocketDisconnect:
        print(f"[WebSocket Signaling] Room {room_id}: {role} disconnected.")
    finally:
        if room[role] == websocket:
            room[role] = None
        # Clean up empty rooms
        if room["sender"] is None and room["receiver"] is None:
            p2p_rooms.pop(room_id, None)
