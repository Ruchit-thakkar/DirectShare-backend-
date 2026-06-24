import asyncio
import time
from app.core.config import settings
from app.rooms.room_manager import room_manager
from app.transfers.chunk_manager import chunk_manager
from app.core.websocket_manager import websocket_manager

_empty_room_since = {}

async def cleanup_room(room_id: str, reason: str = "Room expired"):
    """Perform complete teardown of a room, notifying clients and deleting disk files."""
    print(f"[Cleanup] Tearing down room {room_id}. Reason: {reason}")
    room_id_upper = room_id.upper()
    
    await websocket_manager.broadcast_to_room(room_id_upper, {
        "type": "room_closed",
        "reason": reason
    })

    if room_id_upper in websocket_manager.senders:
        for ws in list(websocket_manager.senders[room_id_upper].values()):
            try:
                await ws.close(code=1001, reason=reason)
            except Exception:
                pass
    if room_id_upper in websocket_manager.receivers:
        for ws in list(websocket_manager.receivers[room_id_upper].values()):
            try:
                await ws.close(code=1001, reason=reason)
            except Exception:
                pass

    if room_id_upper in websocket_manager.senders:
        del websocket_manager.senders[room_id_upper]
    if room_id_upper in websocket_manager.receivers:
        del websocket_manager.receivers[room_id_upper]

    for key in list(websocket_manager.last_activity.keys()):
        if key[0] == room_id_upper:
            del websocket_manager.last_activity[key]

    chunk_manager.delete_room_files(room_id_upper)
    room_manager.remove_room(room_id_upper)

    if room_id_upper in _empty_room_since:
        del _empty_room_since[room_id_upper]


async def run_cleanup_loop():
    """Periodic loop to clean up expired and idle rooms."""
    while True:
        try:
            await asyncio.sleep(settings.CLEANUP_INTERVAL)
            now = time.time()
            rooms_to_delete = []

            active_rooms = list(room_manager.rooms.values())

            for room in active_rooms:
                room_id = room.room_id.upper()
                
                if room.is_expired(settings.ROOM_EXPIRATION_HOURS):
                    rooms_to_delete.append((room_id, "Room exceeded 24 hours lifecycle limit"))
                    continue

                has_active_sender = room.sender_connected and (
                    room_id in websocket_manager.senders and len(websocket_manager.senders[room_id]) > 0
                )
                
                active_receivers_count = 0
                if room_id in websocket_manager.receivers:
                    active_receivers_count = len([
                        ws for ws in websocket_manager.receivers[room_id].values()
                    ])

                if not has_active_sender and active_receivers_count == 0:
                    if room_id not in _empty_room_since:
                        _empty_room_since[room_id] = now
                    
                    if now - _empty_room_since[room_id] > 3600:
                        rooms_to_delete.append((room_id, "Idle room: sender and receivers disconnected for more than 1 hour"))
                else:
                    if room_id in _empty_room_since:
                        del _empty_room_since[room_id]

            for room_id, reason in rooms_to_delete:
                await cleanup_room(room_id, reason)

        except Exception as e:
            print(f"[Cleanup] Error in cleanup loop: {e}")
