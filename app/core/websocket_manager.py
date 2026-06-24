import asyncio
import time
from typing import Dict, Optional, Tuple
from fastapi import WebSocket
from app.core.config import settings

class ConnectionManager:
    def __init__(self):
        # Maps room_id -> sender_id -> WebSocket
        self.senders: Dict[str, Dict[str, WebSocket]] = {}
        # Maps room_id -> receiver_id -> WebSocket
        self.receivers: Dict[str, Dict[str, WebSocket]] = {}
        # Tracks last activity: (room_id, client_id, role) -> timestamp
        self.last_activity: Dict[Tuple[str, str, str], float] = {}
        # Reference to heartbeat task
        self._heartbeat_task: Optional[asyncio.Task] = None

    def start(self):
        """Start the heartbeat checker background loop."""
        if not self._heartbeat_task:
            self._heartbeat_task = asyncio.create_task(self._run_heartbeat())

    async def connect(self, room_id: str, client_id: str, role: str, websocket: WebSocket):
        """Accept connection and register it."""
        room_id_upper = room_id.upper()
        await websocket.accept()

        if role == "sender":
            if room_id_upper not in self.senders:
                self.senders[room_id_upper] = {}
            self.senders[room_id_upper][client_id] = websocket
        elif role == "receiver":
            if room_id_upper not in self.receivers:
                self.receivers[room_id_upper] = {}
            self.receivers[room_id_upper][client_id] = websocket

        self.last_activity[(room_id_upper, client_id, role)] = time.time()

    def disconnect(self, room_id: str, client_id: str, role: str):
        """Remove connection from registry."""
        room_id_upper = room_id.upper()
        key = (room_id_upper, client_id, role)
        if key in self.last_activity:
            del self.last_activity[key]

        if role == "sender" and room_id_upper in self.senders:
            if client_id in self.senders[room_id_upper]:
                del self.senders[room_id_upper][client_id]
            if not self.senders[room_id_upper]:
                del self.senders[room_id_upper]
        elif role == "receiver" and room_id_upper in self.receivers:
            if client_id in self.receivers[room_id_upper]:
                del self.receivers[room_id_upper][client_id]
            if not self.receivers[room_id_upper]:
                del self.receivers[room_id_upper]

    def update_activity(self, room_id: str, client_id: str, role: str):
        """Record activity (like a pong response)."""
        self.last_activity[(room_id.upper(), client_id, role)] = time.time()

    async def send_json(self, websocket: WebSocket, message: dict):
        """Send JSON message safely, catching connection errors."""
        try:
            await websocket.send_json(message)
        except Exception:
            pass  # Socket is probably closed, cleanup will handle it

    async def send_to_sender(self, room_id: str, message: dict):
        """Send message to the sender of the room."""
        room_id_upper = room_id.upper()
        if room_id_upper in self.senders:
            # Cast values to a list to prevent dictionary size changed RuntimeError
            sender_sockets = list(self.senders[room_id_upper].values())
            for ws in sender_sockets:
                await self.send_json(ws, message)

    async def send_to_receiver(self, room_id: str, receiver_id: str, message: dict):
        """Send message to a specific receiver."""
        room_id_upper = room_id.upper()
        if room_id_upper in self.receivers and receiver_id in self.receivers[room_id_upper]:
            await self.send_json(self.receivers[room_id_upper][receiver_id], message)

    async def broadcast_to_room(self, room_id: str, message: dict, exclude_receivers: bool = False):
        """Broadcast message to room members."""
        room_id_upper = room_id.upper()
        
        # Send to sender
        if room_id_upper in self.senders:
            sender_sockets = list(self.senders[room_id_upper].values())
            for ws in sender_sockets:
                await self.send_json(ws, message)
        
        # Send to receivers if not excluded
        if not exclude_receivers and room_id_upper in self.receivers:
            receiver_sockets = list(self.receivers[room_id_upper].values())
            for ws in receiver_sockets:
                await self.send_json(ws, message)

    async def _run_heartbeat(self):
        """Periodic heartbeat loop to ping all clients and drop inactive ones."""
        while True:
            try:
                await asyncio.sleep(settings.HEARTBEAT_INTERVAL)
                now = time.time()
                stale_connections = []

                # Find stale connections or send pings
                for (room_id, client_id, role), last_time in list(self.last_activity.items()):
                    websocket = None
                    if role == "sender" and room_id in self.senders:
                        websocket = self.senders[room_id].get(client_id)
                    elif role == "receiver" and room_id in self.receivers:
                        websocket = self.receivers[room_id].get(client_id)

                    if not websocket:
                        stale_connections.append((room_id, client_id, role, None))
                        continue

                    # If connection exceeded timeout without response
                    if now - last_time > settings.HEARTBEAT_TIMEOUT:
                        stale_connections.append((room_id, client_id, role, websocket))
                    else:
                        # Send ping
                        await self.send_json(websocket, {"type": "ping"})

                # Clean up stale connections
                for room_id, client_id, role, ws in stale_connections:
                    self.disconnect(room_id, client_id, role)
                    if ws:
                        try:
                            await ws.close(code=1001, reason="Heartbeat timeout")
                        except Exception:
                            pass
                        
                        from app.rooms.room_manager import room_manager
                        room = room_manager.disconnect_client(room_id, client_id, role)
                        if room and role == "receiver":
                            await self.send_to_sender(room_id, {
                                "type": "receiver_left",
                                "receiver_id": client_id
                            })
                            
            except Exception as e:
                print(f"[WebSocketManager] Error in heartbeat: {e}")

# Global instance
websocket_manager = ConnectionManager()
