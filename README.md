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

Launches the game once with `+set fs_game survival +devmap survival_pit` (cheats on). Normal
launches from Steam are unaffected.

## How waves work
- Wave 1 (4 stormtroopers) spawns on map load; the first one starts the wave clock.
- Each later wave starts on a timer (30 + 4n seconds after the previous wave started), whether or
  not you cleared the last one. Enemies spawn ~0.6s apart on a ring around the arena.
- 10 waves, 130 enemies total. Enemy types per wave and timings are at the top of `build.py`.

## Notes
- Entity classnames are case-sensitive (`NPC_Stormtrooper`, not `NPC_StormTrooper`).
- Trigger names are prefixed `surv` because the map's waypoints already use `w1`..`w13`.
- NPC `target` fires on spawn, not death, so waves are timer-based.
