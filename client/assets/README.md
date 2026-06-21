# Client assets

Drop-in art for the client. Everything here is **optional**: when a sprite is
missing the renderer falls back to its primitive shapes, so the game always
runs. Loading + lookup lives in [`client/sprites.py`](../sprites.py).

## Hero sprites

```
client/assets/heroes/<hero_id>/<action>_<facing>.png          # single frame
client/assets/heroes/<hero_id>/<action>_<facing>_<frame>.png  # animated (0,1,2…)
client/assets/heroes/<hero_id>/<action>.png                   # non-directional
```

- `<hero_id>` matches the server hero id (e.g. `manananggal`), sent per-entity
  as `hid` in snapshots.
- `<facing>` is one of `n` / `e` / `s` / `w` (derived client-side from motion).
- PNGs should be square with transparency. Any size works — they're scaled to
  ~3× the entity radius at draw time. The placeholders are 64×64.

### Recognized actions

| action        | when it shows                                            |
|---------------|----------------------------------------------------------|
| `idle`        | unit standing still (also the universal fallback)        |
| `move`        | unit moving (animate with `_0`, `_1`, …)                 |
| `attack`      | reserved for auto-attack/Q (not yet triggered)           |
| `pounce`      | reserved for W dash (not yet triggered)                  |
| `split_flyer` | Manananggal's detached upper half (hero has `split` set) |
| `split_body`  | Manananggal's grounded lower body (the `body` entity)    |

Lookup falls back from `<action>_<facing>` → `<action>` → `idle_<facing>` →
`idle`, so a folder with only `idle_s.png` still renders for every state.

## Placeholders

`scripts/gen_sprites.py` procedurally generates the Manananggal placeholder set.
Regenerate with:

```
uv run python scripts/gen_sprites.py
```

Replace any file with real art of the same name to upgrade it — no code change.
