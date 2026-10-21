#!/usr/bin/env python3
"""Builds survival/zz_survival.pk3: a copy of the 'pit' arena with a new entity
lump (player start + wave spawners). No map compiler needed."""
import math, os, random, struct, sys, zipfile

GAME = os.path.expanduser("~/.steam/steam/steamapps/common/Jedi Outcast/GameData/base")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "survival")
MAP = "survival_pit"
CX, CY, FLOOR = 672, -1088, 16     # arena center, spawn height (floor is z=-8)
RING = 190                         # spawn ring radius (floor waypoints reach ~200)

# NPC types from ext_data/npcs.cfg per wave (index = wave-1); types are cycled, so repeats = more of that type.
S, O, W, R = "StormTrooper", "STOfficer", "SwampTrooper", "Reborn"
TIERS = [
    [S], [S],
    [S, S, O], [S, S, O],
    [S, O, W], [S, O, W],
    [S, O, W, R], [S, O, W, R],
    [W, O, R], [W, O, R],
    [R, W, O, "RocketTrooper"], [R, W, O, "RocketTrooper"],
    [R, "RebornFencer", O], [R, "RebornFencer", O],
    ["RocketTrooper", R, "RebornFencer"], ["RocketTrooper", R, "RebornFencer"],
    ["RebornForceUser", R, "RocketTrooper", "ShadowTrooper"], ["RebornForceUser", R, "RocketTrooper", "ShadowTrooper"],
    ["RebornForceUser", "ShadowTrooper", "RebornFencer", "RocketTrooper"],
    ["RebornBoss", "ShadowTrooper", "RebornForceUser"],
]
WAVES = len(TIERS)
size = lambda n: 3 + n // 2         # wave n (1-based) enemy count
START_DELAY = 6                     # not used for wave 1 (spawns at load)
BREAK = 5                           # seconds between waves
STAGGER = 0.6                       # seconds between spawns within a wave (spawned in pairs to save entities)

ents = []
def ent(**kv): ents.append(kv)

def pos(i, n, w):
    a = 2 * math.pi * (i / n) + w * 0.7
    return "%d %d %d" % (CX + RING * math.cos(a), CY + RING * math.sin(a), FLOOR)

# --- drops & force upgrades ---------------------------------------------------------------
SEED = int(sys.argv[1]) if len(sys.argv) > 1 else random.randrange(10**6)
rng = random.Random(SEED)
UPGRADE_EVERY = 2                   # a force upgrade appears every N waves

# health/shield drop table: (item classname, weight). One is picked at random each wave.
DROPS = [("item_shield_sm_instant", 2), ("item_medpak_instant", 1), ("item_shield_lrg_instant", 1)]

# 8 force powers + 3 saber skills, each with levels 1-3. Saber offense/defense start at 1.
POWERS = [("jump", "SET_FORCE_JUMP_LEVEL"), ("push", "SET_FORCE_PUSH_LEVEL"),
          ("pull", "SET_FORCE_PULL_LEVEL"), ("speed", "SET_FORCE_SPEED_LEVEL"),
          ("heal", "SET_FORCE_HEAL_LEVEL"), ("grip", "SET_FORCE_GRIP_LEVEL"),
          ("mindtrick", "SET_FORCE_MINDTRICK_LEVEL"), ("lightning", "SET_FORCE_LIGHTNING_LEVEL"),
          ("saberthrow", "SET_SABER_THROW"), ("saberdefense", "SET_SABER_DEFENSE"),
          ("saberoffense", "SET_SABER_OFFENSE")]
START = {"saberdefense": 1, "saberoffense": 1}
NEED = (len(POWERS) + 1) // 2       # owned powers required at a level before the next tier opens

def next_upgrades(levels):
    """Upgrades allowed right now: (power, new_level). A power must be at level L-1 to reach L,
    and at least NEED powers must already be at level >= L-1 before any power may reach L (L>=2)."""
    out = []
    for p, _ in POWERS:
        L = levels[p] + 1
        if L > 3:
            continue
        if L >= 2 and sum(v >= L - 1 for v in levels.values()) < NEED:
            continue
        out.append((p, L))
    return out

def plan_upgrades(count):
    levels = {p: START.get(p, 0) for p, _ in POWERS}
    plan = []
    for _ in range(count):
        opts = next_upgrades(levels)
        if not opts:
            break
        p, L = rng.choice(opts)
        levels[p] = L
        plan.append((p, L))
    return plan

IBI_SET, IBI_AFFECT, IBI_END = 0x1a, 0x13, 0x19
def _str(v): v = v.encode() + b"\0"; return struct.pack("<ii", 4, len(v)) + v
def _blk(bid, *strs, flush=False):
    ms = [_str(x) for x in strs] + ([struct.pack("<iif", 6, 4, 56.0)] if flush else [])
    return struct.pack("<ii", bid, len(ms)) + b"\0" + b"".join(ms)
def ibi(sets):
    """Compiled ICARUS script: affect(kyle=player, FLUSH) then SET_x "value" for each pair."""
    body = _blk(IBI_AFFECT, "kyle", flush=True) + b"".join(_blk(IBI_SET, k, str(v)) for k, v in sets)
    return b"IBI\0" + struct.pack("<f", 1.57) + body + struct.pack("<ii", IBI_END, 0) + b"\0"

SCRIPTS = {}   # pk3 path -> bytes
def rand_spot():
    a, r = rng.uniform(0, 2 * math.pi), rng.uniform(40, 170)
    return "%d %d %d" % (CX + r * math.cos(a), CY + r * math.sin(a), FLOOR)

upgrades = plan_upgrades(WAVES // UPGRADE_EVERY)
POWER_KEY = dict(POWERS)
def script(*blocks): return b"IBI\0" + struct.pack("<f", 1.57) + b"".join(blocks) + struct.pack("<ii", IBI_END, 0) + b"\0"
IBI_USE = 30
SCRIPTS["scripts/zzsurv/kill.ibi"] = script(_blk(IBI_USE, "kill"))   # deathscript: pokes every "kill" counter
POINTS = 100
TOTAL_KILLS = sum(3 + n // 2 for n in range(1, WAVES + 1))
SCRIPTS["scripts/zzsurv/init.ibi"] = ibi([(k, START.get(p, 0)) for p, k in POWERS])

interval = lambda n: round((30 + 4 * n) / 3)   # seconds from wave n starting to wave n+1 starting

for n in range(1, WAVES + 1):
    cnt = size(n)
    types = TIERS[n - 1]
    nxt = "surv%d" % (n + 1) if n < WAVES else "victory"
    if n == 1:   # wave 1 spawns on map load (named classes spawn immediately)
        for i in range(cnt):
            kv = dict(target="surv1") if i == 0 else {}
            kv["deathscript"] = "zzsurv/kill"   # first spawn starts the wave clock
            ent(classname="NPC_Stormtrooper", origin=pos(i, cnt, n), angle=0, **kv)
    else:
        for i in range(cnt):
            ent(classname="NPC_spawner", NPC_type=types[i % len(types)], origin=pos(i, cnt, n),
                targetname="surv%dgo%d" % (n, i // 2), angle=0, deathscript="zzsurv/kill")
        ent(classname="target_print", targetname="surv%d" % n, message="Wave %d" % n)
        for g in range((cnt + 1) // 2):
            ent(classname="target_delay", targetname="surv%d" % n, wait=round(g * 2 * STAGGER + 0.1, 2),
                target="surv%dgo%d" % (n, g))
    ent(classname="target_delay", targetname="surv%d" % n, wait=interval(n), target=nxt)
    # health/shield drop: surv<n> fires target_random, which reveals one hidden item named drop<n>
    ent(classname="target_random", targetname="surv%d" % n, target="drop%d" % n, spawnflags=1)
    for cls, weight in DROPS:
        for _ in range(weight):
            ent(classname=cls, targetname="drop%d" % n, origin=rand_spot())
    if n % UPGRADE_EVERY == 0 and n // UPGRADE_EVERY <= len(upgrades):
        p, L = upgrades[n // UPGRADE_EVERY - 1]
        fp = "fp%d" % n
        SCRIPTS["scripts/zzsurv/%s.ibi" % fp] = ibi([(POWER_KEY[p], L)])
        ent(classname="item_battery", targetname="surv%d" % n, target=fp, origin=rand_spot())
        ent(classname="target_print", targetname="surv%d" % n, message="A force upgrade has appeared")
        ent(classname="target_scriptrunner", targetname=fp, usescript="zzsurv/" + fp, count=1, origin=rand_spot())
        ent(classname="target_print", targetname=fp, message="Force upgrade: %s level %d" % (p, L))
        print("wave %2d upgrade: %s -> %d" % (n, p, L))
    if n == 1:
        ent(classname="target_scriptrunner", targetname="surv1", usescript="zzsurv/init", count=1, origin=rand_spot())
for k in range(1, TOTAL_KILLS + 1):
    ent(classname="target_counter", targetname="kill", count=k, target="score%d" % k)
    ent(classname="target_print", targetname="score%d" % k, message="Kills: %d   Score: %d" % (k, k * POINTS))
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
        for path, data in SCRIPTS.items():
            z.writestr(path, data)
    print("seed", SEED, "- entities:", len(ents), "(limit ~1000)")
    print("wrote", pk3, "-", sum(size(n) for n in range(1, WAVES + 1)), "enemies over", WAVES, "waves")

main()
