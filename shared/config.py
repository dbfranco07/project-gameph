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

# Map (square so the three lanes are symmetric corner-to-corner).
MAP_WIDTH = 6000
MAP_HEIGHT = 6000
MAP_CENTER = (MAP_WIDTH / 2, MAP_HEIGHT / 2)  # 3000, 3000

# Gameplay
HERO_RADIUS = 20
HERO_MOVE_SPEED = 250  # units per second
HERO_BASE_HP = 600
HERO_BASE_MANA = 200

# Bases sit in opposite corners. Team 1 bottom-left, Team 2 top-right.
T1_CORE = (800, 5200)
T2_CORE = (5200, 800)

# Each lane is a polyline from Team 1's base to Team 2's base. Mid is the
# diagonal; top hugs the left+top edges, bot hugs the bottom+right edges. The
# corner waypoints are pushed toward the map corners so the (wide) lanes stay
# well separated from the mid diagonal.
LANES = ("top", "mid", "bot")
LANE_PATHS = {
    "mid": [T1_CORE, T2_CORE],
    "top": [T1_CORE, (520, 520), T2_CORE],
    "bot": [T1_CORE, (5480, 5480), T2_CORE],
}

# Visual width (px) of the lane strip drawn under the entities. Purely cosmetic
# — units are not confined to the lane.
LANE_WIDTH = 170

# Each side spawns minions at, and respawns heroes at, its core.
SPAWN_POSITIONS = {
    1: T1_CORE,
    2: T2_CORE,
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
DEFAULT_KILL_TARGET = 100         # first team to this many hero kills wins

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

# Tower placement along each lane polyline, as arc-length fractions from the
# Team 1 base (t=0) to the Team 2 base (t=1). lane_order: outer=0 (closest to
# mid, falls first) -> inner=1 -> base tower=2 (closest to own core).
# Index by team -> list of (lane_order, t, kind).
LANE_TOWERS = {
    1: [(2, 0.18, "base"), (1, 0.30, "inner"), (0, 0.42, "outer")],
    2: [(0, 0.58, "outer"), (1, 0.70, "inner"), (2, 0.82, "base")],
}

# Creeps / minions. Base values double as the melee minion's stats.
MINION_HP = 130
MINION_DAMAGE = 18
MINION_RANGE = 160
MINION_INTERVAL = 1.0
MINION_SPEED = 130
MINION_RADIUS = 12
MINION_GOLD = 25
MINION_XP = 30

# Ranged minion: fragile, hits from afar (fires a projectile), worth a bit more.
RANGED_MINION_HP = 90
RANGED_MINION_DAMAGE = 22
RANGED_MINION_RANGE = 500
RANGED_MINION_GOLD = 30
RANGED_MINION_XP = 35
RANGED_MINION_PROJECTILE_SPEED = 900

# Cart (siege) minion: tanky, slow, big bounty. Added every 4th wave per lane.
CART_MINION_HP = 600
CART_MINION_DAMAGE = 30
CART_MINION_RANGE = 200
CART_MINION_SPEED = 100
CART_MINION_RADIUS = 18
CART_MINION_GOLD = 60
CART_MINION_XP = 80

# Wave composition (per lane, per team, per wave).
CREEP_WAVE_INTERVAL = 25.0       # seconds between waves
CREEP_MELEE_PER_WAVE = 3
CREEP_RANGED_PER_WAVE = 1
CREEP_CART_EVERY = 4             # a cart joins each lane every Nth wave

# Neutral jungle camps (passive: idle until attacked, then fight back; respawn).
NEUTRAL_HP = 200
NEUTRAL_DAMAGE = 20
NEUTRAL_RANGE = 160
NEUTRAL_INTERVAL = 1.0
NEUTRAL_RADIUS = 14
NEUTRAL_GOLD = 40
NEUTRAL_XP = 45
NEUTRAL_RESPAWN = 60.0           # seconds to respawn a cleared camp
# Camps sit in the two triangular dead zones between mid and the side lanes.
# (center_x, center_y, monster_count)
JUNGLE_CAMPS = [
    (2100, 1800, 3),   # upper-left zone (between top and mid)
    (1700, 3100, 3),
    (3900, 4200, 3),   # lower-right zone (between mid and bot)
    (4300, 2900, 3),
]

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
