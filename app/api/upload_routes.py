from fastapi import APIRouter, Header, Query, Request, HTTPException, status, Response
from typing import List
from pydantic import BaseModel
from app.rooms.room_manager import room_manager
from app.transfers.upload_handler import handle_chunk_upload
from app.transfers.download_handler import handle_chunk_download

router = APIRouter(prefix="/rooms", tags=["rooms"])

class CreateRoomRequest(BaseModel):
    display_name: str
    client_id: str

class FileRegisterItem(BaseModel):
    id: str
    name: str
    size: int
    total_chunks: int
    mime_type: str

class RegisterFilesRequest(BaseModel):
    files: List[FileRegisterItem]

@router.post("")
async def create_room(payload: CreateRoomRequest):
    """Create a unique 6-character room code and register the sender."""
    try:
        room = room_manager.create_room(payload.client_id, payload.display_name)
        return {
            "room_id": room.room_id,
            "sender_id": room.sender_id,
            "sender_name": room.sender_name
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create room: {str(e)}"
        )

@router.post("/{room_code}/files")
async def register_files(
    room_code: str,
    payload: RegisterFilesRequest,
    x_client_id: str = Header(..., alias="X-Client-ID")
):
    """Register metadata of files to be sent. Executed by sender."""
    room = room_manager.get_room(room_code)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )
    
    if room.sender_id != x_client_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: Only the sender can register files"
        )

    files_data = [item.dict() for item in payload.files]
    success = room_manager.register_files(room_code, x_client_id, files_data)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to register files"
        )

    return {"status": "success", "files_registered": len(files_data)}

@router.get("/{room_code}/files")
async def get_room_files(
    room_code: str,
    x_client_id: str = Header(..., alias="X-Client-ID")
):
    """Retrieve list of files available in the room and the calling receiver's progress."""
    room = room_manager.get_room(room_code)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )

    is_sender = room.sender_id == x_client_id
    is_receiver = x_client_id in room.receivers

    if not is_sender and not is_receiver:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: Client must be a registered member of this room"
        )

    files_list = []
    for f in room.files.values():
        files_list.append({
            "id": f.id,
            "name": f.name,
            "size": f.size,
            "total_chunks": f.total_chunks,
            "mime_type": f.mime_type,
            "uploaded_chunks_count": len(f.uploaded_chunks),
            "is_upload_complete": len(f.uploaded_chunks) == f.total_chunks
        })

    progress = {}
    if is_receiver:
        receiver = room.receivers[x_client_id]
        progress = receiver.download_progress

    return {
        "room_id": room.room_id,
        "files": files_list,
        "progress": progress
    }

@router.post("/{room_code}/files/{file_id}/chunks/{chunk_index}")
async def upload_chunk(
    room_code: str,
    file_id: str,
    chunk_index: int,
    request: Request,
    checksum: str = Query(...),
    chunk_size: int = Query(...),
    x_client_id: str = Header(..., alias="X-Client-ID")
):
    """Upload a binary file chunk. Executed by the sender."""
    body_bytes = await request.body()
    
    result = await handle_chunk_upload(
        room_id=room_code,
        file_id=file_id,
        chunk_index=chunk_index,
        checksum=checksum,
        chunk_size=chunk_size,
        client_id=x_client_id,
        data=body_bytes
    )
    return result

@router.get("/{room_code}/files/{file_id}/chunks/{chunk_index}")
async def download_chunk(
    room_code: str,
    file_id: str,
    chunk_index: int,
    x_client_id: str = Header(..., alias="X-Client-ID")
):
    """Download a binary file chunk. Executed by a receiver."""
    data, headers = await handle_chunk_download(
        room_id=room_code,
        file_id=file_id,
        chunk_index=chunk_index,
        client_id=x_client_id
    )
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers=headers
    )
