import random
import string
import asyncio
import time
from models import Room, RoomSettings, Player

class RoomManager:
    def __init__(self):
        self.rooms = {}
        self.client_room_map = {} 

    def generate_room_code(self):
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if code not in self.rooms:
                return code

    def create_room(self, player_id, username, avatar, settings_data):
        room_id = self.generate_room_code()
        settings = RoomSettings(
            max_players=settings_data.get("max_players", 5),
            private=settings_data.get("private", False),
            password=settings_data.get("password", ""),
            allow_spectator=settings_data.get("allow_spectator", True),
            timer=settings_data.get("timer", 30),
            expansion=settings_data.get("expansion", []),
            language=settings_data.get("language", "vi")
        )
        
        room = Room(room_id, player_id, settings)
        host_player = Player(player_id, username, avatar)
        room.players[player_id] = host_player
        self.rooms[room_id] = room
        return room, host_player

    def join_room(self, room_id, player_id, username, avatar, password=""):
        if room_id not in self.rooms:
            return None, "ROOM_NOT_FOUND"
            
        room = self.rooms[room_id]
        
        if room.settings.private and room.settings.password != password:
            return None, "INVALID_PASSWORD"
            
        if player_id in room.players or player_id in room.spectators:
            return None, "ALREADY_IN_ROOM"
            
        if len(room.players) >= room.settings.max_players:
            if room.settings.allow_spectator:
                spectator = Player(player_id, username, avatar)
                room.spectators[player_id] = spectator
                return room, "SPECTATOR_JOINED"
            return None, "ROOM_FULL"
            
        if room.status != "LOBBY":
            return None, "GAME_ALREADY_STARTED"
            
        new_player = Player(player_id, username, avatar)
        room.players[player_id] = new_player
        return room, "PLAYER_JOINED"

    def leave_room(self, room_id, player_id):
        if room_id not in self.rooms:
            return None
            
        room = self.rooms[room_id]
        
        if player_id in room.players:
            del room.players[player_id]
        elif player_id in room.spectators:
            del room.spectators[player_id]
            
        if len(room.players) == 0:
            del self.rooms[room_id]
            return "ROOM_DELETED"
            
        if player_id == room.host_id and len(room.players) > 0:
            new_host_id = list(room.players.keys())[0]
            room.host_id = new_host_id
            
        return "LEFT"
        
    async def handle_disconnect(self, room_id, player_id, broadcast_callback):
        if room_id not in self.rooms:
            return
        room = self.rooms[room_id]
        
        if player_id in room.players:
            room.players[player_id].connected = False
            room.players[player_id].websocket = None
            room.players[player_id].disconnect_time = time.time()
            
            await broadcast_callback(room_id, {"event": "ROOM_STATE", "data": room.to_dict()})
            
            task = asyncio.create_task(self._reconnect_timeout(room_id, player_id, broadcast_callback))
            room.reconnect_tasks[player_id] = task

    async def _reconnect_timeout(self, room_id, player_id, broadcast_callback):
        try:
            await asyncio.sleep(60)
            if room_id in self.rooms:
                room = self.rooms[room_id]
                if player_id in room.players and not room.players[player_id].connected:
                    status = self.leave_room(room_id, player_id)
                    if status != "ROOM_DELETED" and room_id in self.rooms:
                        await broadcast_callback(room_id, {"event": "ROOM_STATE", "data": room.to_dict()})
        except asyncio.CancelledError:
            pass

    def reconnect(self, room_id, player_id, websocket):
        if room_id not in self.rooms:
            return None, "ROOM_NOT_FOUND"
            
        room = self.rooms[room_id]
        
        if player_id in room.players:
            if player_id in room.reconnect_tasks:
                room.reconnect_tasks[player_id].cancel()
                del room.reconnect_tasks[player_id]
            
            room.players[player_id].connected = True
            room.players[player_id].websocket = websocket
            room.players[player_id].disconnect_time = None
            return room, "RECONNECTED"
            
        return None, "PLAYER_NOT_IN_ROOM"