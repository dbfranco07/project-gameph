# Client assets

Drop-in art for the client. Everything here is **optional**: when a sprite is
missing the renderer falls back to its primitive shapes, so the game always
runs. Loading + lookup lives in [`client/sprites.py`](../sprites.py); the
procedural generators that fill these folders live in [`scripts/`](../../scripts).

## The contract (procedural now, pixel-art later)

The renderer never cares *how* a PNG was made — it only loads by path. So
replacing the procedural placeholders with hand-drawn pixel-art later is a pure
drop-in: write PNGs to the same paths/sizes/names, no code change.

```
client/assets/<category>/<key>/<action>_<facing>.png          # single frame
client/assets/<category>/<key>/<action>_<facing>_<frame>.png  # animated (0,1,2…)
client/assets/<category>/<key>/<action>.png                   # non-directional
```

- `<facing>` is one of `n` / `e` / `s` / `w` (derived client-side from motion),
  or omitted for non-directional art.
- PNGs are square RGBA, **center-anchored**, scaled to ~3× the entity radius at
  draw time. Placeholders are 64×64 (terrain tiles excepted).
- Lookup falls back `<action>_<facing>` → `<action>` → `idle_<facing>` → `idle`,
  so a sparse folder still renders for every state.

## Categories

| category      | key                                   | actions / stems |
|---------------|---------------------------------------|-----------------|
| `heroes`      | hero id (`hid` in snapshots)          | `idle` `move` `attack` `q` `w` `e` `r` `split_flyer` `split_body` |
| `projectiles` | `<hero>_<key>` (e.g. `tiktik_q`)       | `fly` (+ `tiktik_q/tongue_head`, `tongue_mid`) |
| `effects`     | fx name (`smash`, `earthshatter`, `arrowstorm`, `sanctuary`, `renewwave`, `hit_phys`, `hit_special`) | `play_0…` one-shot sequence |
| `entities`    | `minion_melee/ranged/cart/neutral`, `tower`, `base`, `rune` | `idle` `move` (`core`/`dead` for structures) |
| `terrain`     | — (files directly in `terrain/`)       | `ground.png` `river.png` `lane.png` (tileable) |

### Hero actions

| action                | when it shows                                            |
|-----------------------|----------------------------------------------------------|
| `idle` / `move`       | standing / moving (animate `move` with `_0`, `_1`)       |
| `attack`              | auto-attack (also the attacker lunge)                    |
| `q` / `w` / `e` / `r` | one-shot cast pose, played for ~0.4s after the ability fires (server sends a transient `cast` flag) |
| `split_flyer`         | Manananggal's detached upper half (hero has `split` set) |
| `split_body`          | Manananggal's grounded lower body (the `body` entity)    |

## Regenerating placeholders

```
uv run python scripts/gen_all.py            # everything
uv run python scripts/gen_sprite_kapre.py   # one hero
```

Generators share [`scripts/spritelib.py`](../../scripts/spritelib.py), which
enforces the sizes/naming above. Replace any file with real art of the same name
to upgrade it — no code change.
