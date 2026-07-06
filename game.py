import random

class CardType:
    DEFUSE = "Defuse"
    EXPLODING_KITTEN = "Exploding Kitten"
    ATTACK = "Attack"
    SKIP = "Skip"
    FAVOR = "Favor"
    SHUFFLE = "Shuffle"
    SEE_THE_FUTURE = "See the Future"
    NOPE = "Nope"
    TACO_CAT = "Taco Cat"

class GameEngine:
    def __init__(self, room):
        self.room = room
        self.deck = []
        self.discard_pile = []
        self.turn_index = 0
        self.turns_to_take = 1
        self.action_stack = []
        self.state = "LOBBY"
        self.message = "Chờ người chơi..."
        self.nope_task = None
        self.future_cards = []

    def start_game(self):
        players = list(self.room.players.values())
        for p in players:
            p.hand = [CardType.DEFUSE]
            p.alive = True

        deck = [CardType.ATTACK] * 4 + [CardType.SKIP] * 4 + \
               [CardType.FAVOR] * 4 + [CardType.SHUFFLE] * 4 + \
               [CardType.SEE_THE_FUTURE] * 5 + [CardType.NOPE] * 5 + \
               [CardType.TACO_CAT] * 8
        random.shuffle(deck)

        for p in players:
            for _ in range(7):
                p.hand.append(deck.pop())

        kittens_count = len(players) - 1
        defuses_count = 6 - len(players)

        self.deck = deck + [CardType.EXPLODING_KITTEN] * kittens_count + [CardType.DEFUSE] * defuses_count
        random.shuffle(self.deck)

        self.turn_index = 0
        self.turns_to_take = 1
        self.action_stack = []
        self.discard_pile = []
        self.state = "PLAYING"
        self.message = "Trò chơi bắt đầu!"
        self.room.status = "PLAYING"

    def get_current_player_id(self):
        alive_players = [p for p in self.room.players.values() if p.alive]
        if not alive_players:
            return None
        return alive_players[self.turn_index % len(alive_players)].id

    def next_turn(self):
        alive_players = [p for p in self.room.players.values() if p.alive]
        if len(alive_players) <= 1:
            self.state = "GAME_OVER"
            winner = alive_players[0] if alive_players else None
            self.message = f"Game Over! {winner.username if winner else 'Không ai'} thắng!"
            return

        self.turn_index = (self.turn_index + 1) % len(alive_players)
        self.turns_to_take = 1
        self.message = f"Đến lượt của {alive_players[self.turn_index].username}"

    def draw_card(self, player_id):
        if self.state != "PLAYING" or player_id != self.get_current_player_id():
            return False, "NOT_YOUR_TURN"
        
        if self.action_stack:
            return False, "ACTION_PENDING"

        card = self.deck.pop(0)
        player = self.room.players[player_id]

        if card == CardType.EXPLODING_KITTEN:
            if CardType.DEFUSE in player.hand:
                player.hand.remove(CardType.DEFUSE)
                self.discard_pile.append(CardType.DEFUSE)
                self.state = "WAITING_DEFUSE"
                self.message = f"{player.username} rút trúng BOM! Đang dùng Defuse..."
                return True, "DEFUSE_NEEDED"
            else:
                player.alive = False
                self.discard_pile.append(CardType.EXPLODING_KITTEN)
                self.message = f"BÙM! {player.username} đã chết!"
                self.turns_to_take -= 1
                if self.turns_to_take <= 0 or not player.alive:
                    self.next_turn()
                return True, "EXPLODED"
        else:
            player.hand.append(card)
            self.message = f"{player.username} đã rút bài an toàn."
            self.turns_to_take -= 1
            if self.turns_to_take <= 0:
                self.next_turn()
            return True, "DRAWN_SAFE"

    def play_card(self, player_id, card_index, target_id=None):
        if self.state != "PLAYING":
            return False, "NOT_PLAYING"
            
        player = self.room.players.get(player_id)
        if not player or not player.alive:
            return False, "DEAD_OR_NOT_FOUND"
            
        if card_index < 0 or card_index >= len(player.hand):
            return False, "INVALID_CARD"
            
        card = player.hand[card_index]
        
        if card == CardType.NOPE:
            if not self.action_stack:
                return False, "NOTHING_TO_NOPE"
            player.hand.pop(card_index)
            self.action_stack.append({"card": card, "player_id": player_id})
            self.message = f"{player.username} quăng NOPE!"
            return True, "NOPE_PLAYED"
        
        if player_id != self.get_current_player_id():
            return False, "NOT_YOUR_TURN"
            
        if self.action_stack:
            return False, "ACTION_PENDING"
            
        player.hand.pop(card_index)
        self.action_stack.append({"card": card, "player_id": player_id, "target_id": target_id})
        self.message = f"{player.username} đánh lá {card}. Chờ NOPE (5s)..."
        return True, "CARD_PLAYED"

    def resolve_action(self):
        if not self.action_stack:
            return None, False
            
        original_action = self.action_stack[0]
        nopes = len([a for a in self.action_stack if a["card"] == CardType.NOPE])
        
        for action in self.action_stack:
            self.discard_pile.append(action["card"])
            
        self.action_stack = []
        
        if nopes % 2 != 0:
            self.message = f"Lá {original_action['card']} đã bị HỦY bởi NOPE!"
            return original_action, False
            
        card = original_action["card"]
        self.message = f"Lá {card} được thực thi!"
        
        if card == CardType.ATTACK:
            self.turns_to_take = 0
            self.next_turn()
            self.turns_to_take = 2
        elif card == CardType.SKIP:
            self.turns_to_take -= 1
            if self.turns_to_take <= 0:
                self.next_turn()
        elif card == CardType.SHUFFLE:
            random.shuffle(self.deck)
        elif card == CardType.SEE_THE_FUTURE:
            self.future_cards = self.deck[:3]
            
        return original_action, True

    def place_defuse(self, player_id, position):
        if self.state != "WAITING_DEFUSE" or player_id != self.get_current_player_id():
            return False, "INVALID_DEFUSE_STATE"
            
        position = max(0, min(position, len(self.deck)))
        self.deck.insert(position, CardType.EXPLODING_KITTEN)
        self.state = "PLAYING"
        self.message = f"{self.room.players[player_id].username} đã giấu lại BOM!"
        
        self.turns_to_take -= 1
        if self.turns_to_take <= 0:
            self.next_turn()
            
        return True, "DEFUSE_PLACED"

    def to_dict(self):
        return {
            "deck_count": len(self.deck),
            "discard_top": self.discard_pile[-1] if self.discard_pile else None,
            "current_turn": self.get_current_player_id(),
            "turns_to_take": self.turns_to_take,
            "action_stack": self.action_stack,
            "state": self.state,
            "message": self.message
        }