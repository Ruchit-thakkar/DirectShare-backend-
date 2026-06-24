# Direct Share — Python FastAPI Backend

This is the complete server-relay file transfer backend for **Direct Share**, written in Python 3.12+ using FastAPI, WebSockets, and AsyncIO.

The backend uses a memory-efficient streaming architecture with direct file seeking to handle sequential file chunk transfers (512 KB) securely without bloating RAM.

---

## Technical Features

- **Server Relay (Non-P2P)**: High stability over NATs/firewalls by proxying file chunks.
- **WebSocket Connection Registry**: Real-time room events (created, joined, left, status progress, etc.) with a 15-second heartbeat ping/pong system to drop stale sockets.
- **Sequential Chunk Transfer Engine**: Chunks of size exactly 524288 bytes (512 KB) are streamed and stored in `backend/app/storage/temp/{room_code}/{file_id}`.
- **SHA256 Integrity Verification**: Every chunk upload validates its SHA256 checksum against headers before saving. Any corruption rejects and requires re-upload.
- **Disconnect & Resume Support**: Store receiver progress (`last_completed_chunk`) in-memory. If a receiver drops out, they can reconnect with the same client ID and request the files list to discover their resume point, continuing from chunk `last_completed_chunk + 1`.
- **CORS Protection**: Origin-isolated via `FRONTEND_URL` environment variable.
- **Multi-Receiver Isolation**: Receivers in a room cannot see other receivers, preserving security.
- **Automated Lifecycle Purge**: Background task that cleans up expired rooms (24 hours) or abandoned rooms (idle for 1 hour with sender disconnected).

---

## Local Setup & Development

### 1. Prerequisites
- Python 3.12+
- Node.js (for the frontend, running separately)

### 2. Install Dependencies
Run from the `backend/` folder:
```bash
pip install -r requirements.txt
```

### 3. Running Locally
Start the Uvicorn server:
```bash
# From within the backend/ folder
python -m uvicorn app.main:app --port 8000 --reload
```
The server will start at `http://localhost:8000`.

### 4. Running Verification Test
We have included a full integration suite simulating room setup, file metadata registration, concurrent downloads, late-joining, and connection drops/resumes.
With the server running on port 8000, run:
```bash
# From within the backend/ folder
python scripts/test_relay.py
```
You should see:
```text
[SUCCESS] ALL TESTS PASSED SUCCESSFULLY! SERVER RELAY TRANSFER WORKS PERFECTLY.
```

---

## API Endpoints

### 1. REST Endpoints (`/api/rooms`)
- `POST /api/rooms`: Create a new transfer room.
  - Body: `{ "display_name": "Alice", "client_id": "sender_uuid" }`
  - Returns: `{ "room_id": "A4D8F2", "sender_id": "...", "sender_name": "..." }`
- `POST /api/rooms/{room_code}/files`: Register file transfer lists (Sender only).
  - Headers: `X-Client-ID: <sender_client_id>`
  - Body: `{ "files": [{ "id": "file_uuid", "name": "movie.mp4", "size": 1200000, "total_chunks": 3, "mime_type": "video/mp4" }] }`
- `GET /api/rooms/{room_code}/files`: Retrieve room files and calling client's download progress.
  - Headers: `X-Client-ID: <client_id>`
- `POST /api/rooms/{room_code}/files/{file_id}/chunks/{chunk_index}`: Upload chunk binary.
  - Query Params: `checksum=<sha256_hex>&chunk_size=<bytes_count>`
  - Headers: `X-Client-ID: <sender_client_id>`
  - Body: Raw binary bytes (512 KB chunk payload)
- `GET /api/rooms/{room_code}/files/{file_id}/chunks/{chunk_index}`: Download chunk binary.
  - Headers: `X-Client-ID: <receiver_client_id>`
  - Returns: Chunk payload bytes + Response Headers containing `X-Checksum`, `X-Chunk-Index`, `X-Chunk-Size` for receiver integrity check.

### 2. WebSocket Endpoint
- `ws://localhost:8000/ws/{room_code}`
- Query Parameters:
  - `role`: `"sender"` or `"receiver"`
  - `client_id`: Unique identifier of the connection
  - `display_name`: Display name

---

## Railway Production Deploy

The backend is fully optimized for **Railway** deployment.

1. **Non-Root Execution**: Docker container runs as `appuser` (UID `10001`).
2. **Volatile Temp Storage**: A clean temp storage directory is automatically created at `/app/app/storage/temp`.
3. **Health Check**: Configured with a Docker-native Python health check checking `/health` every 30s.
4. **Configuration**: Set the environment variable `FRONTEND_URL` on Railway to your production Netlify frontend URL.
