import asyncio
import hashlib
import json
import math
import sys
import aiohttp

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"
API_PREFIX = "/api/rooms"

def compute_sha256(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()

async def run_test():
    file_size = 1220000
    chunk_size = 524288
    file_id = "test-movie-id-999"
    file_name = "test_movie.mp4"
    original_data = bytes([i % 256 for i in range(file_size)])
    original_sha256 = compute_sha256(original_data)
    
    total_chunks = math.ceil(file_size / chunk_size)
    print(f"[*] Generated dummy file of size {file_size} bytes ({total_chunks} chunks). SHA256: {original_sha256}")
    
    sender_id = "alice-sender-111"
    receiver_a_id = "bob-receiver-222"
    receiver_b_id = "charlie-receiver-333"
    receiver_c_id = "dave-receiver-444"

    async with aiohttp.ClientSession() as session:
        # STEP 1: Sender creates room
        print("\n[STEP 1] Sender creating room...")
        create_payload = {
            "display_name": "Alice (Sender)",
            "client_id": sender_id
        }
        async with session.post(f"{BASE_URL}{API_PREFIX}", json=create_payload) as resp:
            if resp.status != 200:
                print(f"[-] Failed to create room: {await resp.text()}")
                sys.exit(1)
            room_data = await resp.json()
            room_id = room_data["room_id"]
            print(f"[+] Room created successfully. Code: {room_id}")

        # STEP 2: Sender registers file metadata
        print("\n[STEP 2] Sender registering file metadata...")
        register_payload = {
            "files": [
                {
                    "id": file_id,
                    "name": file_name,
                    "size": file_size,
                    "total_chunks": total_chunks,
                    "mime_type": "video/mp4"
                }
            ]
        }
        headers = {"X-Client-ID": sender_id}
        async with session.post(f"{BASE_URL}{API_PREFIX}/{room_id}/files", json=register_payload, headers=headers) as resp:
            if resp.status != 200:
                print(f"[-] Failed to register file: {await resp.text()}")
                sys.exit(1)
            print("[+] File registered successfully.")

        # STEP 3: Connect Sender WebSocket
        print("\n[STEP 3] Connecting Sender WebSocket...")
        sender_ws_url = f"{WS_URL}/ws/{room_id}?role=sender&client_id={sender_id}&display_name=Alice"
        
        async with session.ws_connect(sender_ws_url) as sender_ws:
            print("[+] Sender WebSocket connected.")
            init_msg = await sender_ws.receive_json()
            print(f"[Sender WS] Received initial state: {init_msg.get('type')}")

            # STEP 4: Connect Receiver A
            print("\n[STEP 4] Connecting Receiver A (Bob)...")
            receiver_a_ws_url = f"{WS_URL}/ws/{room_id}?role=receiver&client_id={receiver_a_id}&display_name=Bob"
            async with session.ws_connect(receiver_a_ws_url) as receiver_a_ws:
                print("[+] Receiver A WebSocket connected.")
                rec_a_init = await receiver_a_ws.receive_json()
                print(f"[Receiver A WS] Received state: {rec_a_init.get('type')}")
                
                sender_notification = await sender_ws.receive_json()
                print(f"[Sender WS] Notification: {sender_notification}")
                
                print("[*] Receiver A accepting download...")
                await receiver_a_ws.send_json({
                    "type": "accept_download",
                    "file_id": file_id
                })
                
                sender_notification = await sender_ws.receive_json()
                print(f"[Sender WS] Notification: {sender_notification}")
                if sender_notification.get("type") == "download_started":
                    start_upload_notification = await sender_ws.receive_json()
                    print(f"[Sender WS] Start upload notification: {start_upload_notification}")

                # STEP 5: Sender uploads chunks
                print("\n[STEP 5] Sender uploading chunks...")
                for i in range(total_chunks):
                    start = i * chunk_size
                    end = min(start + chunk_size, file_size)
                    chunk_bytes = original_data[start:end]
                    chunk_sha256 = compute_sha256(chunk_bytes)
                    
                    print(f"[*] Uploading chunk {i} ({len(chunk_bytes)} bytes)...")
                    upload_url = f"{BASE_URL}{API_PREFIX}/{room_id}/files/{file_id}/chunks/{i}?checksum={chunk_sha256}&chunk_size={len(chunk_bytes)}"
                    async with session.post(upload_url, data=chunk_bytes, headers={"X-Client-ID": sender_id}) as resp:
                        if resp.status != 200:
                            print(f"[-] Chunk {i} upload failed: {await resp.text()}")
                            sys.exit(1)
                        print(f"[+] Chunk {i} uploaded successfully.")
                    
                    progress_msg = await sender_ws.receive_json()
                    print(f"[Sender WS] Progress notification: {progress_msg}")
                
                complete_msg = await sender_ws.receive_json()
                print(f"[Sender WS] Completion notification: {complete_msg}")

                # STEP 6: Receiver A downloads chunks
                print("\n[STEP 6] Receiver A downloading chunks...")
                downloaded_file_data = bytearray()
                for i in range(total_chunks):
                    download_url = f"{BASE_URL}{API_PREFIX}/{room_id}/files/{file_id}/chunks/{i}"
                    async with session.get(download_url, headers={"X-Client-ID": receiver_a_id}) as resp:
                        if resp.status != 200:
                            print(f"[-] Chunk {i} download failed: {await resp.text()}")
                            sys.exit(1)
                        
                        rec_checksum = resp.headers.get("X-Checksum")
                        chunk_data = await resp.read()
                        
                        if compute_sha256(chunk_data) != rec_checksum:
                            print("[-] Integrity check failed: hash mismatch in downloaded chunk")
                            sys.exit(1)
                        
                        downloaded_file_data.extend(chunk_data)
                        print(f"[+] Chunk {i} downloaded and verified ({len(chunk_data)} bytes).")
                    
                    sender_dl_msg = await sender_ws.receive_json()
                    print(f"[Sender WS] Receiver A download progress: {sender_dl_msg}")

                rec_a_done_msg = await receiver_a_ws.receive_json()
                print(f"[Receiver A WS] Download done message: {rec_a_done_msg}")
                
                sender_dl_complete = await sender_ws.receive_json()
                print(f"[Sender WS] Receiver A download complete: {sender_dl_complete}")
                
                downloaded_sha256 = compute_sha256(bytes(downloaded_file_data))
                assert downloaded_sha256 == original_sha256, "Receiver A downloaded file hash mismatch!"
                print("[+] SUCCESS: Receiver A file matched original hash exactly!")

            # STEP 7: Late Joiner Receiver B
            print("\n[STEP 7] Late Receiver B (Charlie) joins...")
            receiver_b_ws_url = f"{WS_URL}/ws/{room_id}?role=receiver&client_id={receiver_b_id}&display_name=Charlie"
            async with session.ws_connect(receiver_b_ws_url) as receiver_b_ws:
                print("[+] Receiver B connected.")
                rec_b_init = await receiver_b_ws.receive_json()
                print(f"[Receiver B WS] Received state: {rec_b_init.get('type')}")
                
                sender_notification = await sender_ws.receive_json()
                print(f"[Sender WS] Notification: {sender_notification}")
                
                await receiver_b_ws.send_json({"type": "accept_download", "file_id": file_id})
                sender_notification = await sender_ws.receive_json()
                print(f"[Sender WS] Notification: {sender_notification}")
                
                downloaded_file_data_b = bytearray()
                for i in range(total_chunks):
                    download_url = f"{BASE_URL}{API_PREFIX}/{room_id}/files/{file_id}/chunks/{i}"
                    async with session.get(download_url, headers={"X-Client-ID": receiver_b_id}) as resp:
                        chunk_data = await resp.read()
                        downloaded_file_data_b.extend(chunk_data)
                    
                    sender_dl_msg = await sender_ws.receive_json()
                    print(f"[Sender WS] Receiver B download progress: {sender_dl_msg}")
                
                rec_b_done_msg = await receiver_b_ws.receive_json()
                print(f"[Receiver B WS] Download done: {rec_b_done_msg}")
                
                sender_dl_complete = await sender_ws.receive_json()
                print(f"[Sender WS] Receiver B download complete: {sender_dl_complete}")
                
                downloaded_sha256_b = compute_sha256(bytes(downloaded_file_data_b))
                assert downloaded_sha256_b == original_sha256, "Receiver B downloaded file hash mismatch!"
                print("[+] SUCCESS: Receiver B file matched original hash exactly!")

            # STEP 8: Reconnection and Resume Testing (Receiver C)
            print("\n[STEP 8] Reconnect & Resume Receiver C (Dave) joins...")
            receiver_c_ws_url = f"{WS_URL}/ws/{room_id}?role=receiver&client_id={receiver_c_id}&display_name=Dave"
            
            async with session.ws_connect(receiver_c_ws_url) as receiver_c_ws:
                print("[+] Receiver C connected.")
                rec_c_init = await receiver_c_ws.receive_json()
                print(f"[Receiver C WS] Received files list: {rec_c_init.get('type')}")
                
                sender_notification = await sender_ws.receive_json()
                print(f"[Sender WS] Notification: {sender_notification}")
                
                await receiver_c_ws.send_json({"type": "accept_download", "file_id": file_id})
                sender_notification = await sender_ws.receive_json()
                print(f"[Sender WS] Notification: {sender_notification}")
                
                download_url = f"{BASE_URL}{API_PREFIX}/{room_id}/files/{file_id}/chunks/0"
                async with session.get(download_url, headers={"X-Client-ID": receiver_c_id}) as resp:
                    assert resp.status == 200, "C chunk 0 download failed"
                    chunk_0_data = await resp.read()
                    print("[+] Receiver C downloaded chunk 0.")
                
                sender_dl_msg = await sender_ws.receive_json()
                print(f"[Sender WS] Receiver C download progress: {sender_dl_msg}")
                
                print("[*] Simulating connection drop: closing Receiver C WebSocket...")
            
            sender_notification = await sender_ws.receive_json()
            print(f"[Sender WS] Receiver C disconnected: {sender_notification}")
            
            await asyncio.sleep(1)
            
            print("[*] Simulating reconnection: Dave reconnects...")
            async with session.ws_connect(receiver_c_ws_url) as receiver_c_ws:
                print("[+] Receiver C reconnected.")
                rec_c_reinit = await receiver_c_ws.receive_json()
                print(f"[Receiver C WS] Received files list and progress state: {rec_c_reinit}")
                
                progress_dict = rec_c_reinit.get("progress", {})
                last_completed = progress_dict.get(file_id, -1)
                print(f"[Receiver C WS] Server indicates last completed chunk was: {last_completed}")
                assert last_completed == 0, "Server failed to store resume progress!"
                
                sender_notification = await sender_ws.receive_json()
                print(f"[Sender WS] Receiver C reconnected notification: {sender_notification}")
                
                downloaded_file_data_c = bytearray(chunk_0_data)
                for i in range(1, total_chunks):
                    download_url = f"{BASE_URL}{API_PREFIX}/{room_id}/files/{file_id}/chunks/{i}"
                    async with session.get(download_url, headers={"X-Client-ID": receiver_c_id}) as resp:
                        chunk_data = await resp.read()
                        downloaded_file_data_c.extend(chunk_data)
                        print(f"[+] Resumed and downloaded chunk {i}")
                    
                    sender_dl_msg = await sender_ws.receive_json()
                    print(f"[Sender WS] Receiver C resumed progress: {sender_dl_msg}")
                
                rec_c_done_msg = await receiver_c_ws.receive_json()
                print(f"[Receiver C WS] Download done: {rec_c_done_msg}")
                
                sender_dl_complete = await sender_ws.receive_json()
                print(f"[Sender WS] Receiver C download complete: {sender_dl_complete}")
                
                downloaded_sha256_c = compute_sha256(bytes(downloaded_file_data_c))
                assert downloaded_sha256_c == original_sha256, "Receiver C downloaded file hash mismatch!"
                print("[+] SUCCESS: Receiver C file matched original hash exactly after resuming!")

    print("\n[SUCCESS] ALL TESTS PASSED SUCCESSFULLY! SERVER RELAY TRANSFER WORKS PERFECTLY.")

if __name__ == "__main__":
    try:
        asyncio.run(run_test())
    except ConnectionRefusedError:
        print("[-] Error: Could not connect to server. Make sure FastAPI server is running on http://localhost:8000")
        sys.exit(1)
