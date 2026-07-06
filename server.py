import asyncio
import websockets
import json
import uuid
import os
import time
from room_manager import RoomManager
from game import CardType

room_manager = RoomManager()

async def send_to_client(websocket, event, data, error=None):
    payload = {"event": event, "data": data}
    if error:
        payload["error"] = error
    try:
        await websocket.send(json.dumps(payload))
    except websockets.exceptions.ConnectionClosed:
        pass

async def broadcast_to_room(room_id, payload_builder=None):
    if room_id not in room_manager.rooms:
        return
    room = room_manager.rooms[room_id]
    
    for pid, p in list(room.players.items()) + list(room.spectators.items()):
        if p.connected and p.websocket and not p.websocket.closed:
            payload = payload_builder(pid) if payload_builder else {"event": "ROOM_STATE", "data": room.to_dict()}
            try:
                await p.websocket.send(json.dumps(payload))
            except Exception:
                pass

def build_room_state(room, viewer_id):
    state = room.to_dict()
    if viewer_id in room.players:
        state["players"][viewer_id] = room.players[viewer_id].to_private_dict()
    return {"event": "ROOM_STATE", "data": state}

async def nope_timer(room_id):
    try:
        await asyncio.sleep(5)
        if room_id in room_manager.rooms:
            room = room_manager.rooms[room_id]
            original_action, executed = room.engine.resolve_action()
            
            if executed and original_action["card"] == CardType.SEE_THE_FUTURE:
                player_ws = room.players[original_action["player_id"]].websocket
                if player_ws:
                    await send_to_client(player_ws, "FUTURE_CARDS", {"cards": room.engine.future_cards})
                    
            await broadcast_to_room(room_id, lambda pid: build_room_state(room, pid))
    except asyncio.CancelledError:
        pass

async def handle_client(websocket, path):
    client_id = str(uuid.uuid4())
    current_room_id = None
    player_id = None

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                event = data.get("event")
                payload = data.get("payload", {})
            except json.JSONDecodeError:
                continue

            if event == "CREATE_ROOM":
                player_id = payload.get("player_id", client_id)
                username = payload.get("username", "Unknown")
                avatar = payload.get("avatar", "default")
                settings = payload.get("settings", {})
                
                room, player = room_manager.create_room(player_id, username, avatar, settings)
                player.websocket = websocket
                current_room_id = room.id
                room_manager.client_room_map[websocket] = (current_room_id, player_id)
                
                await send_to_client(websocket, "ROOM_CREATED", {"room_id": room.id})
                await send_to_client(websocket, "ROOM_STATE", room.to_dict())

            elif event == "JOIN_ROOM":
                room_id = payload.get("room_id")
                player_id = payload.get("player_id", client_id)
                username = payload.get("username", "Unknown")
                avatar = payload.get("avatar", "default")
                password = payload.get("password", "")
                
                room, status = room_manager.join_room(room_id, player_id, username, avatar, password)
                if not room:
                    await send_to_client(websocket, "ERROR", None, status)
                    continue
                    
                if player_id in room.players:
                    room.players[player_id].websocket = websocket
                elif player_id in room.spectators:
                    room.spectators[player_id].websocket = websocket
                    
                current_room_id = room_id
                room_manager.client_room_map[websocket] = (current_room_id, player_id)
                await broadcast_to_room(current_room_id, lambda pid: build_room_state(room, pid))

            elif event == "RECONNECT":
                room_id = payload.get("room_id")
                player_id = payload.get("player_id")
                room, status = room_manager.reconnect(room_id, player_id, websocket)
                if not room:
                    await send_to_client(websocket, "ERROR", None, status)
                    continue
                current_room_id = room_id
                room_manager.client_room_map[websocket] = (current_room_id, player_id)
                await broadcast_to_room(current_room_id, lambda pid: build_room_state(room, pid))

            elif event == "LEAVE_ROOM":
                if current_room_id:
                    room_manager.leave_room(current_room_id, player_id)
                    if current_room_id in room_manager.rooms:
                        room = room_manager.rooms[current_room_id]
                        await broadcast_to_room(current_room_id, lambda pid: build_room_state(room, pid))
                    current_room_id = None
                    if websocket in room_manager.client_room_map:
                        del room_manager.client_room_map[websocket]

            elif event == "KICK_PLAYER":
                if not current_room_id or current_room_id not in room_manager.rooms: continue
                room = room_manager.rooms[current_room_id]
                target_id = payload.get("target_id")
                if player_id == room.host_id and target_id in room.players and target_id != player_id:
                    target_ws = room.players[target_id].websocket
                    room_manager.leave_room(current_room_id, target_id)
                    if target_ws:
                        await send_to_client(target_ws, "KICKED", {"message": "You were kicked by the host."})
                    await broadcast_to_room(current_room_id, lambda pid: build_room_state(room, pid))

            elif event == "TRANSFER_HOST":
                if not current_room_id or current_room_id not in room_manager.rooms: continue
                room = room_manager.rooms[current_room_id]
                target_id = payload.get("target_id")
                if player_id == room.host_id and target_id in room.players:
                    room.host_id = target_id
                    await broadcast_to_room(current_room_id, lambda pid: build_room_state(room, pid))

            elif event == "READY":
                if not current_room_id or current_room_id not in room_manager.rooms: continue
                room = room_manager.rooms[current_room_id]
                if player_id in room.players and room.status == "LOBBY":
                    room.players[player_id].ready = True
                    await broadcast_to_room(current_room_id, lambda pid: build_room_state(room, pid))

            elif event == "UNREADY":
                if not current_room_id or current_room_id not in room_manager.rooms: continue
                room = room_manager.rooms[current_room_id]
                if player_id in room.players and room.status == "LOBBY":
                    room.players[player_id].ready = False
                    await broadcast_to_room(current_room_id, lambda pid: build_room_state(room, pid))

            elif event == "START_GAME":
                if not current_room_id or current_room_id not in room_manager.rooms: continue
                room = room_manager.rooms[current_room_id]
                if player_id != room.host_id:
                    await send_to_client(websocket, "ERROR", None, "ONLY_HOST_CAN_START")
                    continue
                room.engine.start_game()
                await broadcast_to_room(current_room_id, lambda pid: build_room_state(room, pid))

            elif event == "PLAY_CARD":
                if not current_room_id or current_room_id not in room_manager.rooms: continue
                room = room_manager.rooms[current_room_id]
                card_index = payload.get("card_index")
                target_id = payload.get("target_id")
                
                success, msg = room.engine.play_card(player_id, card_index, target_id)
                if not success:
                    await send_to_client(websocket, "ERROR", None, msg)
                    continue
                    
                if room.engine.nope_task:
                    room.engine.nope_task.cancel()
                room.engine.nope_task = asyncio.create_task(nope_timer(current_room_id))
                
                await broadcast_to_room(current_room_id, lambda pid: build_room_state(room, pid))

            elif event == "DRAW_CARD":
                if not current_room_id or current_room_id not in room_manager.rooms: continue
                room = room_manager.rooms[current_room_id]
                
                success, msg = room.engine.draw_card(player_id)
                if not success:
                    await send_to_client(websocket, "ERROR", None, msg)
                    continue
                    
                await broadcast_to_room(current_room_id, lambda pid: build_room_state(room, pid))

            elif event == "PLACE_DEFUSE":
                if not current_room_id or current_room_id not in room_manager.rooms: continue
                room = room_manager.rooms[current_room_id]
                position = payload.get("position", 0)
                
                success, msg = room.engine.place_defuse(player_id, position)
                if not success:
                    await send_to_client(websocket, "ERROR", None, msg)
                    continue
                    
                await broadcast_to_room(current_room_id, lambda pid: build_room_state(room, pid))

            elif event == "ROOM_CHAT":
                if not current_room_id or current_room_id not in room_manager.rooms: continue
                room = room_manager.rooms[current_room_id]
                msg_text = payload.get("message", "")
                if not msg_text: continue
                
                sender = room.players.get(player_id) or room.spectators.get(player_id)
                chat_msg = {
                    "id": str(uuid.uuid4()),
                    "sender_id": player_id,
                    "username": sender.username if sender else "Unknown",
                    "message": msg_text,
                    "timestamp": time.time()
                }
                room.chat.append(chat_msg)
                if len(room.chat) > 50: room.chat.pop(0)
                await broadcast_to_room(current_room_id, lambda pid: {"event": "CHAT_UPDATE", "data": chat_msg})

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if websocket in room_manager.client_room_map:
            room_id, pid = room_manager.client_room_map[websocket]
            await room_manager.handle_disconnect(room_id, pid, lambda rid, d: broadcast_to_room(rid, lambda _: d))
            del room_manager.client_room_map[websocket]

async def main():
    # Render sẽ cung cấp biến môi trường PORT. Nếu chạy ở máy tính (local), nó sẽ dùng mặc định 8765
    port = int(os.environ.get("PORT", 8765)) 
    
    # Bắt buộc phải là "0.0.0.0" để server đám mây có thể mở mạng ra ngoài Internet
    async with websockets.serve(handle_client, "0.0.0.0", port):
        print(f"Server WebSocket đang chạy tại cổng {port} ...")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())