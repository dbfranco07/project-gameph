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
| `--hero`     | `ranger`    | Hero to play; any id in `server/heroes/` (or pick one in the lobby). |
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

The two-terminal flow above is the primary supported way to play — server in one
terminal, a client in each other — and is covered end-to-end by
`tests/test_integration.py`, which drives a real server over real sockets.

---

## Playing with people over the internet

The server is deliberately host-agnostic: it is the same process whether it is
on your laptop or a VPS.

- **Same machine / LAN** — nothing special: `--server` and connect to
  `127.0.0.1` or your LAN IP.
- **Friends elsewhere** — use a **[playit.gg](https://playit.gg) TCP tunnel**.
  It needs no router config, does not expose your IP, and — unlike a VPN —
  requires your friends to install nothing at all:

  1. Install the playit agent on the machine hosting the game and claim a
     **TCP** tunnel pointing at `127.0.0.1:7777`.

     Installing it depends on the host OS — note that **playit ships no macOS
     binary**, despite what its download page implies:

     | Host | Install |
     |---|---|
     | Windows | `winget install DevelopedMethods.playit` |
     | Debian/Ubuntu | the apt repo in the [playit README](https://github.com/playit-cloud/playit-agent) |
     | macOS | build it (see below) |
     | Any (Docker) | `docker run --rm -it --net=host -e SECRET_KEY=<key> ghcr.io/playit-cloud/playit-agent:latest` — the image is `linux/amd64` + `linux/arm64`. On Docker Desktop for Mac `--net=host` does not reach the host, so point the tunnel's local address at `host.docker.internal:7777` instead. |

     Building on macOS (playit's own README says `cargo run --release`, which
     fails: the workspace has several binaries, so you must name them). You
     need two — `playitd` is the daemon that holds the tunnel, `playit-cli`
     controls it:

     ```sh
     curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
     git clone https://github.com/playit-cloud/playit-agent
     cd playit-agent
     cargo build --release -p playitd -p playit-cli   # ~1 min
     ```

     Then run `playitd` (it stays in the foreground), and in another terminal
     `playit-cli setup` to claim it against your playit.gg account. Check it
     with `playit-cli status`.

  2. **Creating the tunnel without paying.** playit's web UI gates the
     *custom TCP* tunnel form behind Premium ($3/month), but TCP itself is not
     a paid feature — the free plan includes 4 ports. Create the tunnel from
     the **"Supported Game"** list instead (Minecraft Java, Terraria and
     Project Zomboid are all plain TCP) and it costs nothing. The preset only
     picks a default port and a label; the tunnel just forwards TCP bytes, so
     it carries this game's protocol fine.

     The least fiddly version: pick the Minecraft Java preset and run the
     server on its port instead of editing the tunnel —
     `--server --host 0.0.0.0 --port 25565`.

  3. Otherwise run `uv run python main.py --server --host 0.0.0.0 --port 7777`
     and point the tunnel's local address at `127.0.0.1:7777`. Allow the
     firewall prompt on first run.
  4. Friends type the tunnel address it gives you — a hostname and port, e.g.
     `abc123.gl.joinmc.link` / `12345` — into the connect screen. Hostnames
     resolve fine; it does not have to be an IP.

  Alternatives: forward TCP 7777 on your router, join everyone to a
  **Tailscale** tailnet (great latency, but the free plan caps you at 3 users —
  awkward for a 5v5), or run the server on an always-on VM so it stays up
  without you hosting. Oracle Cloud's Always Free ARM instance is enough, and
  on Linux the playit agent installs from apt in one line (or you can skip the
  tunnel entirely and use the VM's public IP).

  **Not ngrok:** its free tier allows only 1 GB of transfer per month. At
  ~45 KB/s per client this game would exhaust that in roughly an hour and a
  half of 4-player play.

Practical notes when playing over the internet:

- **Everyone must run the same build.** The client sends `PROTOCOL_VERSION` on
  join and a mismatch is refused, so re-share the executable whenever it is
  bumped.
- **Reuse your name.** Reconnecting restores your parked hero only if you join
  with the same `--name`.
- **Check your upload.** A 5v5 host pushes ~3.7 Mbps up (see the table below),
  and a relay adds a hop on top. Start at 3v3 if you are unsure.

What the netcode does for you:

| | |
|---|---|
| **Bandwidth** | Snapshots are deltas — only entities that changed since your last one — and each hero's private HUD payload (cooldowns, inventory, gold, stat panel) is sent **only to its owner**. Together that is ~2.4x less traffic: roughly 45 KB/s per client, so a 5v5 host uploads ~3.7 Mbps. |
| **Latency** | `TCP_NODELAY` on both ends (Nagle would add up to ~40 ms), and each connection is read by its own task so one laggy player cannot stall the tick for everyone. |
| **Dropouts** | A disconnect during a match **parks your hero** instead of deleting it. Reconnect with the same `--name` and you get it back — level, gold, items and all. |
| **Stale clients** | The client sends its protocol version on join; a mismatch is refused with a readable message telling the player to update, instead of desyncing. |

Bump `PROTOCOL_VERSION` in `shared/protocol.py` whenever a wire change would
make an older client misbehave.

---

## Standalone executables (friends without Python)

Friends who don't have Python/`uv` installed can run a packaged executable instead of
the `uv run` commands above — same client, just bundled with `pyinstaller.spec`.

Sprites are procedural placeholders and `client/assets/**/*.png` is gitignored, so
**run `uv run python scripts/gen_all.py` before packaging** on a fresh clone or the
build ships with no art. The CI workflow does this for you.

- **Mac:** `uv run pyinstaller pyinstaller.spec --noconfirm --clean` produces
  `dist/ProjectGamePH.app` — double-click to run.
- **Windows:** the same command on a Windows machine produces `dist/ProjectGamePH.exe`.
  PyInstaller can't cross-compile, so the `.exe` must be built on Windows (or via the
  `.github/workflows/build-executables.yml` CI workflow on `windows-latest`, run manually
  from the Actions tab). Pushing a `v*` tag additionally publishes both builds to a
  **GitHub Release**, which is the easiest thing to hand to friends: one link, no
  GitHub account needed.

  **To cut a new release build (updates the `.exe` and `.app` for friends):**

  ```bash
  git tag v0.1.3          # bump past the latest tag (`git tag -l` to check)
  git push origin v0.1.3
  ```

  That's it — the tag push triggers `build-executables.yml`, which builds both
  platforms and attaches `ProjectGamePH-windows.zip` / `ProjectGamePH-macos.zip` to a new
  GitHub Release under that tag. Watch progress in the repo's **Actions** tab.

Windows will show a SmartScreen warning for an unsigned executable — "More info" →
"Run anyway". Tell your friends up front so nobody assumes it's malware.

The packaged app bundles the server as well as the client, so a friend can host with
`--server` if you'd rather not. Note that it is built windowed (`console=False`), so a
server run from the packaged app prints nothing.

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
  each hero's `atk_type` class attribute in `server/heroes/<hero>.py`.
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
economy, the ability system, projectiles, leveling, the stat/status layer (stacking rules,
lifecycle hooks, auras), the damage pipeline, items (recipes, passives, procs), and the
hero-authoring contracts.

`tests/herotest.py` provides `HeroTestCase`, a base class that spawns a hero and an enemy
in a real `GameState` and gives you `cast()` / `cast_at()` / `tick()`. Per-hero test modules
subclass it instead of repeating the same setup.

---

## Adding a hero

**Copy [server/heroes/_template.py](server/heroes/_template.py) to
`server/heroes/<your_hero>.py` and edit it. That is the whole workflow** — there is no
registry to update: the package auto-discovers every module in it, and the client learns the
ability bar from metadata sent over the wire, so no client code changes either.

Each hero is one class subclassing `HeroDef`. Stats are class attributes; each ability is a
method tagged with `@ability(...)` whose body composes the building blocks in
[server/skills.py](server/skills.py) — `projectile`, `dash`/`blink`, `hook`, `grapple`,
`area_dmg`, `area_heal`, `target_dmg`, `cone`, `line_aoe`, `knockback`, `shield`,
`stun_nearby`, `summon`, `pulse`, `toggle`. A hero's uniqueness is how it combines and
tweaks them.

Conditional passives should be an `Aura` (see [server/status/](server/status/)): attached
once, it toggles itself against a `condition()` instead of being rebuilt every tick. Set
`dynamic = True` when its numbers scale with rank or the battlefield.

Optional lifecycle hooks — `on_tick`, `on_ability_cast`, `on_spawn`, `on_death`, `on_level`,
`on_attack`, `on_hit_dealt`, `on_damage_taken`, `on_kill` — are dispatched generically, so a
new mechanic never needs a branch in the core systems.

Sprites go in `client/assets/heroes/<hero_id>/`; run
`uv run python scripts/gen_all.py` for procedural placeholders. Hero definitions and their
art references (`kind=` / `fx=`) are validated at server startup.

## Adding an item

Same shape: copy [server/items/_template.py](server/items/_template.py) into
`server/items/`. Items grant any stat in `server/stats.py` as modifiers (not writes to base
stats, so selling always reverses cleanly), and may declare `components` + `recipe_cost` to
build out of cheaper items, a `passive` Status for unique passives and on-hit/on-kill procs,
and any number of `@item_active` abilities.

---

## Architecture

- `shared/` — protocol (length-prefixed msgpack), enums, and the YAML config loader.
- `server/` — authoritative simulation. The whole tick is an ordered pipeline in
  [server/systems.py](server/systems.py) (`step()`), each mechanic a function over
  `GameState`. Adding a feature = add a system.
  - [server/stats.py](server/stats.py) — every temporary stat modifier, aggregated under a
    per-stat stacking rule behind a dirty-flag cache.
  - [server/status/](server/status/) — buffs, debuffs and auras as classes with lifecycle
    hooks, so effects carry their own behaviour instead of the systems special-casing them.
  - [server/damage.py](server/damage.py) — one hit resolved through an ordered list of
    stages (invuln, evade, crit, armor, reduction, absorb, apply, lifesteal, on-hit).
  - `server/heroes/` and `server/items/` — auto-discovered, one file per hero/item.
- `client/` — pygame: input -> intent messages, snapshot interpolation, a sprite-ready
  renderer (per-entity-type drawers), camera.
