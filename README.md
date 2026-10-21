# Outcast Survival

A wave-survival map for Jedi Outcast (single player). It reuses the game's `pit` arena and swaps
in new entities (player start + enemy spawners), so no map compiler is needed.

## Setup (once)
Link the mod folder into the game so it loads as its own game dir (`base` is untouched):

    cd "$HOME/.steam/steam/steamapps/common/Jedi Outcast/GameData"
    ln -s /home/nate/Code/OutcastSurvival/survival survival

## Build
    python3 build.py

Reads `pit.bsp` from the game's `assets0.pk3` and writes `survival/zz_survival.pk3`.

## Run
    ./run.sh

Rebuilds the map with a new random seed, then launches the game once with `+set fs_game survival +devmap survival_pit` (cheats on). Normal
launches from Steam are unaffected.

## How waves work
- Wave 1 (4 stormtroopers) spawns on map load; the first one starts the wave clock.
- Each later wave starts on a timer ((30 + 4n)/3 seconds after the previous wave started), whether or
  not you cleared the last one. Enemies spawn ~0.6s apart on a ring around the arena.
- 20 waves, 160 enemies total (3 + n/2 per wave). Enemy types per wave and timings are at the top of `build.py`.

## Drops and upgrades
- Every wave, one hidden health/shield pickup (small shield, medpak or large shield, weighted toward
  the small ones) appears at a random spot. Picked by the game's `target_random`, so it varies per run.
- Every 2nd wave a battery-looking pickup appears; grabbing it raises one force power one level
  (8 force powers + saber throw/defense/offense, levels 1-3). The sequence is chosen at build time
  (`./run.sh` rebuilds each launch; `python3 build.py <seed>` repeats one). Rules: a power must be at
  level L-1 before L, and at least half the powers (6 of 11) must be at level >= L-1 before any power can
  reach level L (L>=2).
- Upgrades are compiled ICARUS scripts (`scripts/zzsurv/*.ibi`) written by `build.py`; the format
  matches the game's own scripts byte for byte.
- At start all powers reset to 0 (saber offense/defense 1).

## Score
Every enemy has a `deathscript` that pokes a chain of `target_counter`s; the k-th death fires a
`target_print` showing "Kills: k   Score: k*100" (center of screen - the game has no way to draw a HUD
element from map entities). Costs ~2 entities per kill, so keep an eye on the entity count `build.py` prints.

## Notes
- Entity classnames are case-sensitive (`NPC_Stormtrooper`, not `NPC_StormTrooper`).
- Trigger names are prefixed `surv` because the map's waypoints already use `w1`..`w13`.
- NPC `target` fires on spawn, not death, so waves are timer-based.

## Self-built engine (OpenJO) - separate from Steam and other projects
- Source: `openjk/` (shallow clone of github.com/JACoders/OpenJK, GPLv2). Build output: `dist/`.
- Build: `cd openjk/build && ninja && ninja install` (configured for JK2 single player only;
  cmake flags in this repo's history: `-G Ninja -DCMAKE_INSTALL_PREFIX=../../dist` + `BuildJK2SP*=ON`, others OFF).
- Run: `./run_open.sh` (rebuilds the map, then starts the engine on `survival_pit`).
- `game/base` = symlinks to the Steam assets (read-only use) + our pk3; `game/OpenJK` -> `dist/JediOutcast/OpenJK`.
  Configs/saves go to `home/`, so nothing touches the Steam install or other mods.
- `openjk/`, `dist/`, `game/`, `home/` are git-ignored.
