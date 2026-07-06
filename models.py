import time
from game import GameEngine

class Player:
    def __init__(self, player_id, username, avatar="default"):
        self.id = player_id
        self.username = username
        self.avatar = avatar
        self.websocket = None
        self.ready = False
        self.connected = True
        self.hand = []
        self.alive = True
        self.rank = 0
        self.statistics = {"wins": 0, "games_played": 0}
        self.disconnect_time = None

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "avatar": self.avatar,
            "ready": self.ready,
            "connected": self.connected,
            "hand_count": len(self.hand),
            "alive": self.alive,
            "rank": self.rank,
            "statistics": self.statistics
        }

    def to_private_dict(self):
        data = self.to_dict()
        data["hand"] = self.hand
        return data

class RoomSettings:
    def __init__(self, max_players=5, private=False, password="", allow_spectator=True, timer=30, expansion=None, language="vi"):
        self.max_players = max_players
        self.private = private
        self.password = password
        self.allow_spectator = allow_spectator
        self.timer = timer
        self.expansion = expansion if expansion is not None else []
        self.language = language

    def to_dict(self):
        return {
            "max_players": self.max_players,
            "private": self.private,
            "allow_spectator": self.allow_spectator,
            "timer": self.timer,
            "expansion": self.expansion,
            "language": self.language
        }

class Room:
    def __init__(self, room_id, host_id, settings=None):
        self.id = room_id
        self.host_id = host_id
        self.players = {}
        self.spectators = {}
        self.chat = []
        self.engine = GameEngine(self)
        self.settings = settings if settings else RoomSettings()
        self.status = "LOBBY"
        self.created_at = time.time()
        self.reconnect_tasks = {}

    def to_dict(self):
        return {
            "id": self.id,
            "host_id": self.host_id,
            "players": {pid: p.to_dict() for pid, p in self.players.items()},
            "spectators": {sid: s.to_dict() for sid, s in self.spectators.items()},
            "chat": self.chat[-50:],
            "game": self.engine.to_dict(),
            "settings": self.settings.to_dict(),
            "status": self.status,
            "created_at": self.created_at
        }