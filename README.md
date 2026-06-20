# project-gameph — a single-lane Lite MOBA

A small authoritative-server MOBA in Python (pygame-ce client, asyncio server) you
can play with friends in 2v2–5v5. One lane, towers + core, creep waves, gold/XP/levels,
and data-driven heroes with abilities. Built to grow feature-by-feature.

---

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). Install dependencies:

```bash
uv sync
```

Everything below is launched through `main.py`, which dispatches to the server when
`--server` is passed and to the pygame client otherwise.

---

## Starting the game (CLI)

A match needs **one server** plus **one client per player**. The server is headless
(no window) and authoritative; clients connect to it over TCP.

### 1. Start the server (one machine hosts)

```bash
uv run python main.py --server
```

Server flags:

| Flag       | Default     | Description                                   |
|------------|-------------|-----------------------------------------------|
| `--host`   | `127.0.0.1` | Address to bind. Use `0.0.0.0` to accept LAN / remote players. |
| `--port`   | `7777`      | TCP port to listen on.                        |

Examples:

```bash
# Local only (you + clients on the same machine)
uv run python main.py --server

# Let other machines connect (LAN, Tailscale, VPS, etc.)
uv run python main.py --server --host 0.0.0.0 --port 7777
```

### 2. Each player starts a client

```bash
uv run python main.py --name Alice --hero ranger
```

Client flags:

| Flag         | Default     | Description                                                        |
|--------------|-------------|--------------------------------------------------------------------|
| `--name`     | `Player`    | Display name shown above your hero.                                |
| `--hero`     | `ranger`    | Hero to play: `ranger`, `brawler`, or `mender` (see `data/heroes.py`). |
| `--host`     | `127.0.0.1` | Server address to connect to.                                      |
| `--port`     | `7777`      | Server port.                                                       |
| `--ktarget`  | server default (`20`) | Kill target to win. Only the **host who presses Space** sets the match's value. |

Examples:

```bash
# Connect to a server on another machine
uv run python main.py --name Bob --hero brawler --host 192.168.1.50 --port 7777

# Host the lobby AND play on the same machine: run the server in one terminal,
# then a client in another. The first client to press Space starts the match.
uv run python main.py --name Alice --hero mender --ktarget 30
```

### 3. Start the match

Once everyone has joined (you'll see each hero on the map), **any player presses
`Space`** to begin. Teams are auto-assigned to keep sides balanced as players join.

---

## Controls

| Input          | Action                                            |
|----------------|---------------------------------------------------|
| **Right-click**| Move your hero to that point                       |
| **A** then **left-click** | Attack command. Click an enemy to **focus** it (chase + attack until it dies); click the ground to **attack-move** there. |
| **S**          | Stop — cancel current movement and focus target     |
| **Q / W / E / R** | Cast the corresponding ability, aimed at the mouse cursor |
| **Space**      | Start the match (while in the WAITING phase)        |
| **Esc**        | Quit the client                                     |

Your hero also auto-attacks the nearest valid enemy in range on its own, so positioning
with right-click is enough for basic fighting. Use **A + click** when you want to commit to
a specific target and chase it, and **S** to hold position.

**Melee vs ranged:** each hero is melee or ranged. Melee heroes (e.g. `brawler`) hit
instantly at short range. Ranged heroes (e.g. `ranger`, `mender`) and towers fire a visible
projectile that travels to the target — you can see the shots fly. Projectiles are tinted by
the shooter's team.

---

## How to play (current rules)

**Goal:** be the first team to either reach the **kill target** (default 20, set with
`--ktarget`) **or destroy the enemy core.**

**The map** is a single horizontal lane. Each side has three structures along it:

```
[Core] — [Inner tower] — [Outer tower] —— mid —— [Outer tower] — [Inner tower] — [Core]
   \________ Team 1 ________/                        \________ Team 2 ________/
```

**Structures (towers + core):**
- Towers and the core auto-attack enemies in range and hit hard.
- A structure is **invulnerable until the more-outer structure on its side is destroyed**
  — you must kill the outer tower, then the inner tower, before you can damage the core.
- Destroying a structure rewards the killing hero with gold.

**Creeps (minions):**
- A wave of minions spawns for each team roughly every 25 seconds and pushes down the lane.
- Minions auto-attack enemy minions, heroes, and (vulnerable) structures, and stop to fight
  when an enemy is in range.
- Killing a minion grants gold and XP.

**Heroes:**
- Auto-attack the nearest valid enemy in range (heroes prefer enemy heroes, then minions,
  then structures). Press **A** and click an enemy to override this and focus a chosen
  target; press **S** to stop and hold.
- Are **melee** (instant short-range hits) or **ranged** (fire a visible projectile). See
  each hero's `atk_type` in `data/heroes.py`.
- Gain **gold** (from kills, minions, structures, and a small passive trickle) and **XP**
  (from kills and minions). Reaching an XP threshold **levels you up** (up to level 18),
  increasing max HP and attack damage.
- Killing an enemy hero scores a point for your team and grants bonus gold/XP. When you die
  you respawn at your base after a short, level-scaled timer.

**Abilities:** each hero has four abilities (Q/W/E/R) with cooldowns and mana costs, built
from reusable kinds — projectiles, dashes, area damage, area heals, single-target damage,
and self/area buffs. Mana regenerates over time; cooldowns are shown on the ability bar.

**Winning:** the match ends immediately when a team reaches the kill target or loses its
core. The client shows **VICTORY** or **DEFEAT**.

> Note: there are no AI bots yet (planned next). With a single client, heroes that respawn
> at base won't automatically walk back into the fight — the game is meant to be played with
> friends on both teams. Solo, you can still move around, push the lane, last-hit minions,
> and test abilities.

---

## Running the tests

Tests use the standard-library `unittest` runner.

```bash
# Run the whole suite
uv run python -m unittest discover -s tests

# Verbose (lists every test)
uv run python -m unittest discover -s tests -v

# Run a single test module
uv run python -m unittest tests.test_combat

# Run a single test case or method
uv run python -m unittest tests.test_abilities.TestAbilityCast
uv run python -m unittest tests.test_abilities.TestAbilityCast.test_projectile_hits_target
```

What's covered: protocol round-trips, entities, game state, movement, combat &
death/respawn, scoring & win conditions, structure invulnerability order, creep spawning &
economy, the data-driven ability system, projectiles, and leveling.

---

## Adding a hero

Add an entry to `HERO_DEFS` in [data/heroes.py](data/heroes.py): base stats + up to four
abilities. Abilities are composed from reusable kinds implemented in
[server/abilities.py](server/abilities.py): `projectile`, `dash`, `area_dmg`, `area_heal`,
`target_dmg`, `buff`. New hero = new data; a genuinely new mechanic = one new block. Hero
definitions are validated at server startup.

---

## Architecture

- `shared/` — protocol (length-prefixed msgpack), enums/config, hero schema (UI-agnostic).
- `server/` — authoritative simulation. The whole tick is an ordered pipeline in
  [server/systems.py](server/systems.py) (`step()`), each mechanic a function over
  `GameState`. Adding a feature = add a system.
- `client/` — pygame: input -> intent messages, snapshot interpolation, a sprite-ready
  renderer (per-entity-type drawers), camera.
