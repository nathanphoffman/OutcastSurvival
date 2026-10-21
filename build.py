#!/usr/bin/env python3
"""Builds survival/zz_survival.pk3: a copy of the 'pit' arena with a new entity
lump (player start + wave spawners). No map compiler needed."""
import math, os, struct, sys, zipfile

GAME = os.path.expanduser("~/.steam/steam/steamapps/common/Jedi Outcast/GameData/base")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "survival")
MAP = "survival_pit"
CX, CY, FLOOR = 672, -1088, 16     # arena center, spawn height (floor is z=-8)
RING = 190                         # spawn ring radius (floor waypoints reach ~200)

# (wave tiers) NPC types from ext_data/npcs.cfg, picked per wave; later waves mix harder types
TIERS = [
    ["StormTrooper"],
    ["StormTrooper", "STOfficer"],
    ["StormTrooper", "SwampTrooper", "Reborn"],
    ["Reborn", "RebornFencer", "StormTrooper"],
    ["RocketTrooper", "RebornFencer", "Reborn"],
    ["ShadowTrooper", "RebornForceUser", "RocketTrooper"],
    ["RebornForceUser", "ShadowTrooper", "RebornFencer", "RocketTrooper"],
    ["RebornBoss", "ShadowTrooper", "RebornForceUser"],
    ["RebornBoss", "RebornBoss", "ShadowTrooper2", "RebornForceUser"],
    ["Tavion", "RebornBoss", "ShadowTrooper2"],
]
WAVES = len(TIERS)
size = lambda n: 2 + 2 * n          # wave n (1-based) enemy count
START_DELAY = 6                     # not used for wave 1 (spawns at load)
BREAK = 5                           # seconds between waves
STAGGER = 0.6                       # seconds between spawns within a wave

ents = []
def ent(**kv): ents.append(kv)

def pos(i, n, w):
    a = 2 * math.pi * (i / n) + w * 0.7
    return "%d %d %d" % (CX + RING * math.cos(a), CY + RING * math.sin(a), FLOOR)

interval = lambda n: 30 + 4 * n     # seconds from wave n starting to wave n+1 starting

for n in range(1, WAVES + 1):
    cnt = size(n)
    types = TIERS[n - 1]
    nxt = "surv%d" % (n + 1) if n < WAVES else "victory"
    if n == 1:   # wave 1 spawns on map load (named classes spawn immediately)
        for i in range(cnt):
            kv = dict(target="surv1") if i == 0 else {}   # first spawn starts the wave clock
            ent(classname="NPC_Stormtrooper", origin=pos(i, cnt, n), angle=0, **kv)
    else:
        for i in range(cnt):
            ent(classname="NPC_spawner", NPC_type=types[i % len(types)], origin=pos(i, cnt, n),
                targetname="surv%dgo%d" % (n, i), angle=0)
        ent(classname="target_print", targetname="surv%d" % n, message="Wave %d" % n)
        for i in range(cnt):
            ent(classname="target_delay", targetname="surv%d" % n, wait=round(i * STAGGER + 0.1, 2),
                target="surv%dgo%d" % (n, i))
    ent(classname="target_delay", targetname="surv%d" % n, wait=interval(n), target=nxt)
ent(classname="target_print", targetname="victory", message="SURVIVED ALL %d WAVES" % WAVES)

def fmt(e):
    return "{\n" + "".join('"%s" "%s"\n' % kv for kv in e.items()) + "}\n"

def build_ents(orig):
    # keep world geometry/nav (worldspawn, waypoints, lights, point_combat); drop Tavion & old start
    keep = []
    for block in orig.split("}\n"):
        if '"NPC_Tavion"' in block or '"info_player_start"' in block or not block.strip():
            continue
        keep.append(block + "}\n")
    start = dict(classname="info_player_start", origin="%d %d %d" % (CX, CY, FLOOR), angle=0)
    return "".join(keep) + fmt(start) + "".join(fmt(e) for e in ents)

def main():
    with zipfile.ZipFile(os.path.join(GAME, "assets0.pk3")) as z:
        bsp = bytearray(z.read("maps/pit.bsp"))
    off, ln = struct.unpack_from("<ii", bsp, 8)
    new = build_ents(bsp[off:off + ln].decode("latin1").rstrip("\0")).encode("latin1") + b"\0"
    struct.pack_into("<ii", bsp, 8, len(bsp), len(new))   # append new lump at end of file
    bsp += new
    os.makedirs(OUT, exist_ok=True)
    pk3 = os.path.join(OUT, "zz_survival.pk3")
    with zipfile.ZipFile(pk3, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("maps/%s.bsp" % MAP, bytes(bsp))
    print("wrote", pk3, "-", sum(size(n) for n in range(1, WAVES + 1)), "enemies over", WAVES, "waves")

main()
