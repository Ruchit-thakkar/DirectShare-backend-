"""
Transfer Manager — Simulates file transfer progress.

Emits transfer_progress WebSocket events to sender and all connected
receivers at 500ms intervals. Completes when 100% is reached.
"""

import asyncio
import time
from typing import Optional

from app.services.room_manager import room_manager, Room


async def _send_ws(ws, event: str, data: dict):
    """Send a JSON WebSocket event, ignoring errors for closed connections."""
    try:
        import json
        await ws.send_json({"event": event, "data": data})
    except Exception:
        pass


async def run_transfer(room_id: str):
    """
    Simulate a file transfer for the room with the given room_id.

    Progress is emitted every 500ms. The simulated speed fluctuates
    slightly around 50 MB/s to give a realistic feel.
    """
    room = room_manager.get_room(room_id)
    if not room:
        return

    room.status = "transferring"
    filesize = room.filesize
    filename = room.filename

    transfer_data = {"filename": filename, "filesize": filesize}

    # Notify all parties that transfer has started
    if room.sender_ws:
        await _send_ws(room.sender_ws, "transfer_started", transfer_data)
    for receiver in room_manager.connected_receivers(room):
        if receiver.websocket:
            await _send_ws(receiver.websocket, "transfer_started", transfer_data)

    transferred = 0
    base_speed = max(10 * 1024 * 1024, filesize // 20)  # ~5% per tick at 500ms intervals
    start_time = time.monotonic()

    while transferred < filesize:
        await asyncio.sleep(0.5)

        # Re-check room still exists and isn't closed
        room = room_manager.get_room(room_id)
        if not room or room.status == "closed":
            return

        # Vary speed slightly (±20%)
        import random
        speed = int(base_speed * random.uniform(0.8, 1.2))
        transferred = min(transferred + speed, filesize)

        elapsed = time.monotonic() - start_time
        current_speed = transferred / max(elapsed, 0.001)
        remaining_bytes = filesize - transferred
        eta = int(remaining_bytes / max(current_speed, 1))
        percent = round((transferred / filesize) * 100, 1)

        progress_data = {
            "percent": percent,
            "transferred": transferred,
            "speed": int(current_speed),
            "eta": eta,
            "filename": filename,
            "filesize": filesize,
        }

        if room.sender_ws:
            await _send_ws(room.sender_ws, "transfer_progress", progress_data)
        for receiver in room_manager.connected_receivers(room):
            if receiver.websocket:
                await _send_ws(receiver.websocket, "transfer_progress", progress_data)

    # Transfer complete
    room = room_manager.get_room(room_id)
    if not room or room.status == "closed":
        return

    room.status = "completed"
    complete_data = {"filename": filename, "filesize": filesize}

    if room.sender_ws:
        await _send_ws(room.sender_ws, "transfer_completed", complete_data)
    for receiver in room_manager.connected_receivers(room):
        if receiver.websocket:
            await _send_ws(receiver.websocket, "transfer_completed", complete_data)
