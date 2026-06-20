"""Data-driven hero definitions.

Each hero is a plain dict: base stats + a list of up to 4 abilities. Abilities
reference reusable "kinds" implemented in `server/abilities.py`. Adding a new hero
is normally just adding an entry here — no new code unless you need a new ability kind.

Stat fields:
    hp, mana, move_speed, atk_dmg, atk_range, atk_interval (seconds per attack)
    atk_type: "melee" (instant hit) or "ranged" (fires a visible projectile)

Ability fields (by kind):
    all:        key, kind, name, cd (cooldown s), mana
    projectile: dmg, speed, radius, range
    dash:       dist
    area_dmg:   dmg, radius
    area_heal:  heal, radius
    target_dmg: dmg, range
    buff:       duration, speed_bonus, dmg_bonus, radius (0 = self only)
"""

HERO_DEFS: dict[str, dict] = {
    "ranger": {
        "name": "Ranger",
        "hp": 560,
        "mana": 280,
        "move_speed": 250,
        "atk_dmg": 50,
        "atk_range": 520,
        "atk_interval": 0.9,
        "atk_type": "ranged",
        "abilities": [
            {"key": "Q", "kind": "projectile", "name": "Piercing Shot",
             "dmg": 95, "speed": 950, "radius": 18, "range": 900, "cd": 5, "mana": 50},
            {"key": "W", "kind": "dash", "name": "Tumble",
             "dist": 320, "cd": 11, "mana": 40},
            {"key": "E", "kind": "buff", "name": "Hunter's Focus",
             "duration": 5, "speed_bonus": 90, "dmg_bonus": 25, "radius": 0,
             "cd": 16, "mana": 60},
            {"key": "R", "kind": "area_dmg", "name": "Arrow Storm",
             "dmg": 230, "radius": 360, "cd": 60, "mana": 100},
        ],
    },
    "brawler": {
        "name": "Brawler",
        "hp": 720,
        "mana": 180,
        "move_speed": 260,
        "atk_dmg": 62,
        "atk_range": 150,
        "atk_interval": 1.0,
        "atk_type": "melee",
        "abilities": [
            {"key": "Q", "kind": "target_dmg", "name": "Crushing Blow",
             "dmg": 130, "range": 220, "cd": 6, "mana": 35},
            {"key": "W", "kind": "dash", "name": "Charge",
             "dist": 380, "cd": 10, "mana": 45},
            {"key": "E", "kind": "buff", "name": "Battle Fury",
             "duration": 6, "speed_bonus": 60, "dmg_bonus": 35, "radius": 0,
             "cd": 18, "mana": 50},
            {"key": "R", "kind": "area_dmg", "name": "Earthshatter",
             "dmg": 260, "radius": 320, "cd": 70, "mana": 90},
        ],
    },
    "mender": {
        "name": "Mender",
        "hp": 600,
        "mana": 320,
        "move_speed": 245,
        "atk_dmg": 44,
        "atk_range": 480,
        "atk_interval": 1.0,
        "atk_type": "ranged",
        "abilities": [
            {"key": "Q", "kind": "projectile", "name": "Spirit Bolt",
             "dmg": 80, "speed": 850, "radius": 18, "range": 800, "cd": 4, "mana": 40},
            {"key": "W", "kind": "area_heal", "name": "Renewing Wave",
             "heal": 140, "radius": 300, "cd": 12, "mana": 70},
            {"key": "E", "kind": "dash", "name": "Blink",
             "dist": 340, "cd": 13, "mana": 50},
            {"key": "R", "kind": "area_heal", "name": "Sanctuary",
             "heal": 320, "radius": 420, "cd": 80, "mana": 120},
        ],
    },
}

DEFAULT_HERO = "ranger"
