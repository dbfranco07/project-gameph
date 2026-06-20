# Server
SERVER_TICK_RATE = 20  # ticks per second
TICK_DURATION = 1.0 / SERVER_TICK_RATE  # seconds per tick
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7777
MAX_PLAYERS = 10

# Client
CLIENT_FPS = 60
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720

# Camera (free-roam, Dota-style). Mouse near a screen edge pans the view; press
# the recenter key (1) to snap back to your hero.
EDGE_PAN_MARGIN = 40             # px from a screen edge that triggers panning
CAMERA_PAN_SPEED = 1400          # world units/sec while edge-panning

# Map
MAP_WIDTH = 6000
MAP_HEIGHT = 4000

# Gameplay
HERO_RADIUS = 20
HERO_MOVE_SPEED = 250  # units per second
HERO_BASE_HP = 600
HERO_BASE_MANA = 200

# Single lane runs horizontally across the middle of the map.
LANE_Y = MAP_HEIGHT / 2          # 2000
MID_X = MAP_WIDTH / 2            # 3000

# Each side: core (deepest) -> inner tower -> outer tower (closest to mid).
SPAWN_POSITIONS = {
    1: (500, LANE_Y),    # Team 1 spawn (at their core)
    2: (5500, LANE_Y),   # Team 2 spawn (at their core)
}

# Combat (base hero melee/ranged stats; data-driven heroes override these)
HERO_ATTACK_DAMAGE = 55
HERO_ATTACK_RANGE = 160
HERO_ATTACK_INTERVAL = 1.0       # seconds between auto-attacks
BASIC_PROJECTILE_SPEED = 1100    # speed of ranged basic-attack projectiles
BASIC_PROJECTILE_RADIUS = 10
ATTACK_CLICK_PIXELS = 14         # cursor pickup tolerance for "A + click enemy"
HERO_RESPAWN_BASE = 5.0          # base respawn seconds
HERO_RESPAWN_PER_LEVEL = 1.0     # extra seconds per hero level

# Win conditions
DEFAULT_KILL_TARGET = 20         # first team to this many hero kills wins

# Structures: towers + core. lane_order: outer=0, inner=1, core=2.
# A structure only takes damage once every same-team structure with a
# smaller lane_order has been destroyed (outer -> inner -> core).
TOWER_HP = 1600
TOWER_DAMAGE = 130
TOWER_RANGE = 620
TOWER_INTERVAL = 1.0
TOWER_RADIUS = 40
TOWER_PROJECTILE_SPEED = 900     # towers fire visible shots
CORE_HP = 3200
CORE_DAMAGE = 150
CORE_RADIUS = 60
STRUCTURE_GOLD = 150             # gold to the killer when a structure falls

# Lane structure positions (x along LANE_Y). Index by team.
STRUCTURES = {
    1: [  # (lane_order, x, kind)  kind in {"outer", "inner", "core"}
        (0, 2300, "outer"),
        (1, 1400, "inner"),
        (2, 500, "core"),
    ],
    2: [
        (0, 3700, "outer"),
        (1, 4600, "inner"),
        (2, 5500, "core"),
    ],
}

# Creeps / minions
MINION_HP = 130
MINION_DAMAGE = 18
MINION_RANGE = 160
MINION_INTERVAL = 1.0
MINION_SPEED = 130
MINION_RADIUS = 12
MINION_GOLD = 25
MINION_XP = 30
CREEP_WAVE_INTERVAL = 25.0       # seconds between waves
CREEP_WAVE_SIZE = 4              # minions per wave per team

# Economy / leveling
HERO_KILL_GOLD = 200
HERO_KILL_XP = 150
PASSIVE_GOLD_PER_SEC = 2.0
MANA_REGEN_PER_SEC = 5.0
HERO_HP_REGEN_PER_SEC = 3.0      # default slow hp regen (heroes may override)

# Last-hit economy: the killer gets full gold; nearby allies get a share of gold
# but full XP regardless of who landed the killing blow.
MINION_ASSIST_GOLD_FRACTION = 1.0 / 3.0
GOLD_SHARE_RADIUS = 900          # allies within this of a dying minion get share gold
XP_SHARE_RADIUS = 900            # allies within this of a dying minion get full XP

# Items
ITEM_SLOTS = 6                   # inventory capacity per hero
STARTING_GOLD = 600             # gold each hero starts a match with
MAX_LEVEL = 18
XP_BASE = 100                    # xp needed for level 2
XP_PER_LEVEL = 120               # extra xp per subsequent level
HP_PER_LEVEL = 80                # max-hp gained per level
DAMAGE_PER_LEVEL = 6             # attack-damage gained per level

# Vision (fog-of-war). Each alive unit reveals a radius for its team; enemies are
# only sent to a client when inside their team's vision. Structures are always
# visible to both teams (static map features).
VISION_RADIUS = 1500             # hero sight radius
HERO_VISION_RADIUS = VISION_RADIUS
MINION_VISION_RADIUS = 800
TOWER_VISION_RADIUS = 1200

# Colors
COLOR_BG = (40, 60, 30)
COLOR_TEAM1 = (70, 130, 255)   # Blue
COLOR_TEAM2 = (255, 70, 70)    # Red
COLOR_HEALTH_BG = (60, 60, 60)
COLOR_HEALTH = (50, 200, 50)
COLOR_MANA = (70, 120, 240)
COLOR_GRID = (50, 70, 40)
COLOR_TEXT = (240, 240, 240)
COLOR_PROJECTILE = (255, 230, 120)
COLOR_STRUCTURE_DEAD = (70, 70, 70)
COLOR_LANE = (60, 80, 50)
