from enum import IntEnum


class Team(IntEnum):
    NONE = 0
    TEAM1 = 1
    TEAM2 = 2


class EntityType(IntEnum):
    HERO = 1
    MINION = 2
    TOWER = 3
    BASE = 4
    PROJECTILE = 5


class GamePhase(IntEnum):
    WAITING = 0   # Waiting for players
    PLAYING = 1   # Game in progress
    FINISHED = 2  # Game over


class MsgType(IntEnum):
    # Client -> Server
    JOIN = 1
    MOVE = 2
    ATTACK = 3
    USE_ABILITY = 4
    BUY_ITEM = 5
    SELL_ITEM = 6
    START_GAME = 7
    CHAT = 8
    STOP = 9

    # Server -> Client
    SNAPSHOT = 10
    JOIN_ACK = 11
    EVENT = 12
    GAME_OVER = 13
    PLAYER_LIST = 14
