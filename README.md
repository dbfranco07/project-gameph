# project-gameph — a 3-lane Lite MOBA

A small authoritative-server MOBA in Python (pygame-ce client, asyncio server) you
can play with friends in 2v2–5v5. Three lanes (top/mid/bot), towers + core, creep
waves with cart minions, a neutral jungle, gold/XP/levels, and data-driven heroes with
abilities. Built to grow feature-by-feature.

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

## Standalone executables (friends without Python)

Friends who don't have Python/`uv` installed can run a packaged executable instead of
the `uv run` commands above — same client, just bundled with `pyinstaller.spec`.

- **Mac:** `uv run pyinstaller pyinstaller.spec --noconfirm --clean` produces
  `dist/ProjectGamePH.app` — double-click to run.
- **Windows:** the same command on a Windows machine produces `dist/ProjectGamePH.exe`.
  PyInstaller can't cross-compile, so the `.exe` must be built on Windows (or via the
  `.github/workflows/build-executables.yml` CI workflow on `windows-latest`, run manually
  from the Actions tab or by pushing a `v*` tag — download the artifact from there).

The packaged app still needs a server to connect to (it doesn't bundle one) — the host
runs `uv run python main.py --server ...` as usual, and friends point their executable at
the host's address from the connect screen.

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

**The map** is a square with the two bases in opposite corners and **three lanes**
connecting them: **mid** runs diagonally, **top** hugs the left/top edges, and **bot**
hugs the bottom/right edges. Each lane has **three towers per side** (outer → inner →
base), and each team has a single **core** at its base.

```
        +------------- TOP -------------+
        |  o   o   o                    |
        | o                          \  |    o = lane tower
   (T1) BASE                       (MID) BASE (T2)
        |  \                          o |    jungle camps sit in the
        |   (MID)                     o |    dead zones between lanes
        +------------- BOT -------------+
```

**Structures (towers + core):**
- Towers and the core auto-attack enemies in range and hit hard.
- Within a lane, a tower is **invulnerable until the more-outer tower in that same lane is
  destroyed** (outer → inner → base).
- The **core becomes attackable once any one lane's three towers are destroyed.** Destroy
  the core to win.
- Destroying a structure rewards the killing hero with gold.

**Creeps (minions):**
- Every ~25 seconds each team spawns a wave **in every lane**: 3 melee + 1 ranged minion.
- Every **4th wave** also adds a **cart (siege) minion** to each lane — tankier and slower,
  but worth much more gold and XP.
- Minions auto-attack enemy minions, heroes, and (vulnerable) structures, and stop to fight
  when an enemy is in range.
- Killing a minion grants gold and XP.

**Jungle (neutral camps):**
- Neutral monster camps sit in the no-lane dead zones between the lanes.
- They are **passive** — they idle until attacked, then the whole camp fights back.
- A cleared camp **respawns after a delay**. Clearing a camp rewards the killer's team.

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
