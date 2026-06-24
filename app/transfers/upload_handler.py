from fastapi import HTTPException, status
from app.rooms.room_manager import room_manager
from app.transfers.chunk_manager import chunk_manager, CHUNK_SIZE
from app.services.checksum import verify_sha256
from app.core.websocket_manager import websocket_manager

async def handle_chunk_upload(
    room_id: str,
    file_id: str,
    chunk_index: int,
    checksum: str,
    chunk_size: int,
    client_id: str,
    data: bytes
):
    """
    Handle uploading a single file chunk:
    - Verifies room and ownership.
    - Validates SHA256.
    - Writes chunk asynchronously to disk.
    - Updates room transfer state.
    - Dispatches WebSocket status notifications.
    """
    room = room_manager.get_room(room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room {room_id} not found"
        )

    if room.sender_id != client_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: Only the room sender can upload files"
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

    expected_chunk_size = CHUNK_SIZE
    if chunk_index == file_meta.total_chunks - 1:
        expected_chunk_size = file_meta.size - (chunk_index * CHUNK_SIZE)

    if len(data) != expected_chunk_size or chunk_size != expected_chunk_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chunk size mismatch. Expected: {expected_chunk_size}, Got payload: {len(data)}, Requested: {chunk_size}"
        )

    if not verify_sha256(data, checksum):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Integrity check failed: checksum mismatch for chunk {chunk_index}"
        )

    await chunk_manager.write_chunk(room_id, file_id, chunk_index, data)

    is_fully_uploaded = room_manager.mark_chunk_uploaded(room_id, file_id, chunk_index)
    
    # Wake up any waiting download requests for this chunk
    room_manager.trigger_chunk_event(room_id, file_id, chunk_index)

    uploaded_chunks_count = len(file_meta.uploaded_chunks)
    progress_percentage = (uploaded_chunks_count / file_meta.total_chunks) * 100

    await websocket_manager.send_to_sender(room_id, {
        "type": "upload_progress",
        "file_id": file_id,
        "chunk_index": chunk_index,
        "progress": round(progress_percentage, 1),
        "completed_chunks": list(file_meta.uploaded_chunks)
    })

    if is_fully_uploaded:
        await websocket_manager.broadcast_to_room(room_id, {
            "type": "upload_completed",
            "file_id": file_id
        })

    return {"status": "success", "chunk_index": chunk_index}
