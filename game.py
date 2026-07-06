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

    # === 5 LOẠI MÈO CƠ BẢN ===
    TACO_CAT = "Taco Cat"
    CATTERMELON = "Cattermelon"
    HAIRY_POTATO_CAT = "Hairy Potato Cat"
    RAINBOW_RALPHING_CAT = "Rainbow Ralphing Cat"
    BEARD_CAT = "Beard Cat"


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

        # === BỘ BÀI CÓ 5 LOẠI MÈO ===
        deck = (
            [CardType.ATTACK] * 4 +
            [CardType.SKIP] * 4 +
            [CardType.FAVOR] * 4 +
            [CardType.SHUFFLE] * 3 +
            [CardType.SEE_THE_FUTURE] * 5 +
            [CardType.NOPE] * 5 +
            # 5 loại mèo cơ bản
            [CardType.TACO_CAT] * 4 +
            [CardType.CATTERMELON] * 4 +
            [CardType.HAIRY_POTATO_CAT] * 4 +
            [CardType.RAINBOW_RALPHING_CAT] * 4 +
            [CardType.BEARD_CAT] * 4
        )
        random.shuffle(deck)

        for p in players:
            for _ in range(7):
                if deck:
                    p.hand.append(deck.pop())

        # Exploding Kitten
        kittens_count = max(3, len(players) - 1)
        self.deck = deck + [CardType.EXPLODING_KITTEN] * kittens_count
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
            self.message = f"Game Over! {winner.username if winner else ''} thắng!"
            return

        self.turn_index = (self.turn_index + 1) % len(alive_players)
        self.turns_to_take = 1
        self.message = f"Đến lượt của {alive_players[self.turn_index].username}"

    # ==================== HỖ TRỢ COMBO MÈO ====================
    CAT_CARDS = {
        CardType.TACO_CAT,
        CardType.CATTERMELON,
        CardType.HAIRY_POTATO_CAT,
        CardType.RAINBOW_RALPHING_CAT,
        CardType.BEARD_CAT
    }

    def is_cat_card(self, card):
        return card in self.CAT_CARDS

    def play_card(self, player_id, card_index, target_id=None):
        player = self.room.players.get(player_id)
        if not player or not player.alive:
            return False, "DEAD_OR_NOT_FOUND"

        if card_index < 0 or card_index >= len(player.hand):
            return False, "INVALID_CARD"

        card = player.hand[card_index]

        # Xử lý Nope
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

        # === COMBO MÈO ===
        if self.is_cat_card(card):
            if not target_id:
                return False, "CAT_NEEDS_TARGET"

            cat_count = sum(1 for c in player.hand if c == card)
            if cat_count < 2:
                return False, "NOT_ENOUGH_CATS"

            # Lấy 2 lá mèo ra
            removed = 0
            for i in range(len(player.hand) - 1, -1, -1):
                if player.hand[i] == card and removed < 2:
                    self.discard_pile.append(player.hand.pop(i))
                    removed += 1

            self.action_stack.append({
                "card": card,
                "player_id": player_id,
                "target_id": target_id,
                "is_cat_combo": True
            })
            target_name = self.room.players[target_id].username
            self.message = f"{player.username} dùng 2 {card} ăn cắp từ {target_name}"
            return True, "CAT_COMBO_PLAYED"

        # Các lá bài thường
        player.hand.pop(card_index)
        self.action_stack.append({"card": card, "player_id": player_id, "target_id": target_id})
        self.message = f"{player.username} đánh lá {card}. Chờ NOPE (5s)..."
        return True, "CARD_PLAYED"

    def resolve_action(self):
        if not self.action_stack:
            return None, False

        action = self.action_stack[0]
        nopes = len([a for a in self.action_stack if a["card"] == CardType.NOPE])

        for a in self.action_stack:
            if a.get("is_cat_combo") or a["card"] != CardType.NOPE:
                self.discard_pile.append(a["card"])

        self.action_stack = []

        if nopes % 2 != 0:
            self.message = f"Lá {action['card']} đã bị HỦY bởi NOPE!"
            return action, False

        # === THỰC THI COMBO MÈO ===
        if action.get("is_cat_combo"):
            target = self.room.players.get(action["target_id"])
            player = self.room.players.get(action["player_id"])

            if target and target.hand:
                stolen = random.choice(target.hand)
                target.hand.remove(stolen)
                player.hand.append(stolen)
                self.message = f"{player.username} đã ăn cắp 1 lá từ {target.username}!"
            return action, True

        # Các lá bài khác
        card = action["card"]
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

        return action, True

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