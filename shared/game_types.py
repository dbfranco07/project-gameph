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


class CastType(IntEnum):
    """How an ability is aimed by the client before it is sent to the server.

    The client reads this (delivered as ability metadata in JOIN_ACK) to decide
    its targeting UX: NONE casts immediately; the others enter a "pending cast"
    state and wait for a click to resolve the target.
    """
    NONE = 0     # instant self/auto cast (no target needed)
    POINT = 1    # ground-target: resolves to a world point (tx, ty)
    UNIT = 2     # unit-target: resolves to an entity under the cursor (tid)
    VECTOR = 3   # directional: (tx, ty) interpreted as a direction from the caster
    PASSIVE = 4  # not castable; shown on the bar, effect lives in hero hooks


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
    SELECT_TEAM = 15    # lobby: switch to team 1/2
    SELECT_HERO = 16    # lobby: pick a hero_id

    # Server -> Client
    SNAPSHOT = 10
    JOIN_ACK = 11
    EVENT = 12
    GAME_OVER = 13
    PLAYER_LIST = 14    # lobby roster broadcast (teams/heroes/host)
    LOBBY_WELCOME = 17  # sent once on join: your client id, host flag, catalogs
