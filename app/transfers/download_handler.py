from fastapi import HTTPException, status
from app.rooms.room_manager import room_manager
from app.transfers.chunk_manager import chunk_manager, CHUNK_SIZE
from app.services.checksum import calculate_sha256
from app.core.websocket_manager import websocket_manager

async def handle_chunk_download(
    room_id: str,
    file_id: str,
    chunk_index: int,
    client_id: str
):
    """
    Handle downloading a single file chunk:
    - Verifies room and receiver credentials.
    - Confirms if chunk has been uploaded.
    - Reads chunk asynchronously from disk.
    - Computes checksum of chunk for headers.
    - Updates receiver's progress and sends updates via WebSocket.
    """
    room = room_manager.get_room(room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room {room_id} not found"
        )

    if client_id not in room.receivers:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: Client is not registered as a receiver in this room"
        )

    if file_id not in room.files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File {file_id} is not registered in room {room_id}"
        )

    file_meta = room.files[file_id]

    if chunk_index < 0 or chunk_index >= file_meta.total_chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid chunk index {chunk_index}. Total chunks: {file_meta.total_chunks}"
        )

    if chunk_index not in file_meta.uploaded_chunks:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Chunk {chunk_index} has not been uploaded by the sender yet"
        )

    expected_chunk_size = CHUNK_SIZE
    if chunk_index == file_meta.total_chunks - 1:
        expected_chunk_size = file_meta.size - (chunk_index * CHUNK_SIZE)

    try:
        data = await chunk_manager.read_chunk(room_id, file_id, chunk_index, expected_chunk_size)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chunk file not found on disk"
        )

    checksum = calculate_sha256(data)

    room_manager.update_receiver_progress(room_id, client_id, file_id, chunk_index)

    progress_percentage = ((chunk_index + 1) / file_meta.total_chunks) * 100

    await websocket_manager.send_to_sender(room_id, {
        "type": "download_progress",
        "file_id": file_id,
        "receiver_id": client_id,
        "chunk_index": chunk_index,
        "progress": round(progress_percentage, 1)
    })

    if chunk_index == file_meta.total_chunks - 1:
        await websocket_manager.send_to_sender(room_id, {
            "type": "download_completed",
            "file_id": file_id,
            "receiver_id": client_id
        })
        await websocket_manager.send_to_receiver(room_id, client_id, {
            "type": "download_completed",
            "file_id": file_id
        })

    headers = {
        "X-Room-ID": room_id,
        "X-File-ID": file_id,
        "X-Chunk-Index": str(chunk_index),
        "X-Chunk-Size": str(len(data)),
        "X-Checksum": checksum,
    }

    return data, headers
