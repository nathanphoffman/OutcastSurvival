"""Generates the 'chasm' map as a Quake3-style .map file (brushes + lights + waypoints).

Layout (z up, units are game units; player is 56 tall):
  - central reactor core: a huge glowing column running from far below the map to the sky
  - hub deck around the core, with four spokes (bridges) out to four mid platforms
  - four raised diagonal platforms between them, reached by ramps from the outer rim
  - a big flat outer rim (the "exterior") with four corner pylons
  - open chasm below (hurt trigger), sealed by a sky box so it compiles without leaks
"""
import math
from itertools import combinations

TEX = dict(
    floor="textures/bespin/u_carbfloor",
    deck="textures/bespin/u_floor02",
    rim="textures/bespin/u_floor01",
    side="textures/bespin/u_casing01",
    under="textures/bespin/u_ceiling01",
    core="textures/bespin/u_tube",
    glow="textures/bespin/u_light02a",
    pylon="textures/bespin/u_wall02",
    sky="textures/bespin/sky",
    trigger="textures/system/trigger",
    clip="textures/system/caulk",
)

sub = lambda a, b: (a[0] - b[0], a[1] - b[1], a[2] - b[2])
cross = lambda a, b: (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
dot = lambda a, b: a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
norm = lambda a: math.sqrt(dot(a, a))

brushes = []      # list of brush strings
entities = []     # list of dicts
waypoints = []    # (x, y, z) walkable spots the AI can path through

def _faces(P):
    """Planes of the convex hull of point set P: [(normal, [vertices on the plane])]."""
    out, seen = [], set()
    for i, j, k in combinations(range(len(P)), 3):
        n = cross(sub(P[j], P[i]), sub(P[k], P[i]))
        ln = norm(n)
        if ln < 1e-6:
            continue
        n = tuple(c / ln for c in n)
        d = dot(n, P[i])
        ds = [dot(n, p) - d for p in P]
        if all(x <= 0.01 for x in ds):
            pass
        elif all(x >= -0.01 for x in ds):
            n, d = tuple(-c for c in n), -d
        else:
            continue
        key = (tuple(round(c, 3) for c in n), round(d, 1))
        if key in seen:
            continue
        seen.add(key)
        out.append((n, [p for p in P if abs(dot(n, p) - d) < 0.05]))
    return out

def _tex(n, top, side, bottom):
    return top if n[2] > 0.5 else bottom if n[2] < -0.5 else side

def convex(P, top, side=None, bottom=None):
    """Add a brush: the convex hull of P, textured by face direction."""
    side = side or TEX["side"]
    bottom = bottom or TEX["under"]
    lines = ["{"]
    for n, vs in _faces(P):
        a = vs[0]
        b = max(vs, key=lambda v: norm(sub(v, a)))
        c = max(vs, key=lambda v: norm(cross(sub(b, a), sub(v, a))))
        p0, p1, p2 = b, a, c
        if dot(cross(sub(p0, p1), sub(p2, p1)), n) < 0:
            p0, p2 = p2, p0
        pt = lambda p: "( %g %g %g )" % p
        lines.append("%s %s %s %s 0 0 0 0.25 0.25 0 0 0" % (pt(p0), pt(p1), pt(p2), _tex(n, top, side, bottom)[len("textures/"):]))
    lines.append("}")
    brushes.append("\n".join(lines))

def box(x0, y0, z0, x1, y1, z1, top, side=None, bottom=None):
    convex([(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], top, side, bottom)

def poly_pts(cx, cy, r, n, rot=0.0):
    return [(cx + r * math.cos(rot + 2 * math.pi * i / n), cy + r * math.sin(rot + 2 * math.pi * i / n)) for i in range(n)]

def prism(pts2, z0, z1, top, side=None, bottom=None):
    convex([(x, y, z) for x, y in pts2 for z in (z0, z1)], top, side, bottom)

def ring(r0, r1, z0, z1, n, top, side=None, bottom=None, rot=0.0):
    """Annulus as n trapezoid brushes."""
    for i in range(n):
        a0, a1 = rot + 2 * math.pi * i / n, rot + 2 * math.pi * (i + 1) / n
        quad = [(r0 * math.cos(a0), r0 * math.sin(a0)), (r1 * math.cos(a0), r1 * math.sin(a0)),
                (r1 * math.cos(a1), r1 * math.sin(a1)), (r0 * math.cos(a1), r0 * math.sin(a1))]
        prism(quad, z0, z1, top, side, bottom)

def rect_along(p, q, width, z0, z1, top, side=None, bottom=None, grow=0):
    """A flat bridge slab from p to q (xy), `width` wide, spanning z0..z1. grow extends both ends."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    ln = math.hypot(dx, dy)
    ux, uy = dx / ln, dy / ln
    nx, ny = -uy * width / 2, ux * width / 2
    p = (p[0] - ux * grow, p[1] - uy * grow)
    q = (q[0] + ux * grow, q[1] + uy * grow)
    prism([(p[0] + nx, p[1] + ny), (p[0] - nx, p[1] - ny), (q[0] - nx, q[1] - ny), (q[0] + nx, q[1] + ny)], z0, z1, top, side, bottom)

def ramp(p, q, width, z_low, z_high, thick, top, side=None, bottom=None):
    """Slope rising from z_low at p to z_high at q; underside is flat at z_low - thick."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    ln = math.hypot(dx, dy)
    ux, uy = dx / ln, dy / ln
    nx, ny = -uy * width / 2, ux * width / 2
    pts = []
    for s in (1, -1):
        pts += [(p[0] + s * nx, p[1] + s * ny, z_low), (p[0] + s * nx, p[1] + s * ny, z_low - thick),
                (q[0] + s * nx, q[1] + s * ny, z_high), (q[0] + s * nx, q[1] + s * ny, z_low - thick)]
    convex(pts, top, side, bottom)

def polar(r, deg, z=0):
    a = math.radians(deg)
    return (round(r * math.cos(a)), round(r * math.sin(a)), z)

def light(origin, intensity, color="1 1 1"):
    entities.append(dict(classname="light", origin="%d %d %d" % origin, light=intensity, _color=color))

def waypoint(p, tag=None):
    waypoints.append((round(p[0]), round(p[1]), round(p[2]) + 24))

# ----------------------------------------------------------------------------------------------
SKY_Z0, SKY_Z1, SKY_XY = -3400, 2800, 3200
THICK = 64                      # slab thickness
TOP = 0                         # main walking height
CORE_R, HUB_R0, HUB_R1 = 192, 192, 400
RIM_R0, RIM_R1 = 1300, 2150
SPAWNS = []                     # enemy spawn spots (x, y, z)
START = None
RAISED = 192

def build():
    # --- sky box (also lights the map from above) ---
    s, t = SKY_XY, 32
    box(-s - t, -s - t, SKY_Z0 - t, s + t, s + t, SKY_Z0, TEX["sky"], TEX["sky"], TEX["sky"])
    box(-s - t, -s - t, SKY_Z1, s + t, s + t, SKY_Z1 + t, TEX["sky"], TEX["sky"], TEX["sky"])
    box(-s - t, -s - t, SKY_Z0, -s, s + t, SKY_Z1, TEX["sky"], TEX["sky"], TEX["sky"])
    box(s, -s - t, SKY_Z0, s + t, s + t, SKY_Z1, TEX["sky"], TEX["sky"], TEX["sky"])
    box(-s, -s - t, SKY_Z0, s, -s, SKY_Z1, TEX["sky"], TEX["sky"], TEX["sky"])
    box(-s, s, SKY_Z0, s, s + t, SKY_Z1, TEX["sky"], TEX["sky"], TEX["sky"])

    # --- reactor core: a glowing column with energy rings, running through everything ---
    prism(poly_pts(0, 0, CORE_R, 16), SKY_Z0 + 8, SKY_Z1 - 8, TEX["core"], TEX["core"], TEX["core"])
    for k in range(-9, 8):
        z = k * 300
        prism(poly_pts(0, 0, CORE_R + 14, 16), z, z + 40, TEX["glow"], TEX["glow"], TEX["glow"])
        for a in (45, 135, 225, 315):
            light(polar(CORE_R + 140, a, z + 20), 500, "0.45 0.7 1")

    # --- hub deck around the core ---
    ring(HUB_R0 - 4, HUB_R1, TOP - THICK, TOP, 16, TEX["deck"], TEX["side"], TEX["under"])
    for i in range(8):
        waypoint(polar(300, 22.5 + 45 * i))
    # upper collar on the core
    ring(CORE_R - 4, CORE_R + 90, 540, 580, 16, TEX["deck"], TEX["side"], TEX["under"])

    # --- four cardinal platforms + spokes to the hub, bridges out to the rim ---
    for k in range(4):
        ang = 90 * k
        c = polar(800, ang)
        prism(poly_pts(c[0], c[1], 230, 8, math.radians(22.5 + ang)), TOP - THICK, TOP, TEX["floor"], TEX["side"], TEX["under"])
        # spoke from hub edge to platform
        rect_along(polar(HUB_R1 - 20, ang), polar(800 - 190, ang), 150, TOP - 40, TOP, TEX["deck"], TEX["side"], TEX["under"])
        # bridge from platform out to the rim
        rect_along(polar(800 + 190, ang), polar(RIM_R0 + 20, ang), 150, TOP - 40, TOP, TEX["deck"], TEX["side"], TEX["under"])
        for r in (480, 560, 640, 720):
            waypoint(polar(r, ang))
        for r in (800, 880, 960, 1040, 1120, 1200, 1280):
            waypoint(polar(r, ang))
        for da in (-1, 1):
            waypoint(polar(800, ang + da * 14))
        SPAWNS.append(tuple(round(v) for v in polar(800, ang, TOP + 24)))
        for rr in (800, 1120):   # lights over each platform/bridge
            light(polar(rr, ang, 260), 700, "0.8 0.9 1")

    # --- raised diagonal platforms, reached by ramps from the rim ---
    for k in range(4):
        ang = 45 + 90 * k
        c = polar(780, ang)
        prism(poly_pts(c[0], c[1], 190, 8, math.radians(22.5 + ang)), RAISED - THICK, RAISED, TEX["floor"], TEX["side"], TEX["under"])
        # ramp from the rim inward to the platform edge
        ramp(polar(RIM_R0 + 20, ang), polar(780 + 160, ang), 190, TOP, RAISED, 40, TEX["deck"], TEX["side"], TEX["under"])
        for r in (780, 880):
            waypoint(polar(r, ang, RAISED))
        for r in (1000, 1100, 1200, 1300):
            waypoint(polar(r, ang, RAISED * (1300 - r) / (1300 - 940) if r > 940 else RAISED))
        SPAWNS.append(tuple(round(v) for v in polar(780, ang, RAISED + 24)))
        light(polar(780, ang, RAISED + 260), 700, "1 0.85 0.7")

    # --- outer rim: the big flat exterior ---
    ring(RIM_R0, RIM_R1, TOP - THICK, TOP, 32, TEX["rim"], TEX["side"], TEX["under"])
    for rr in (1400, 1700, 1950):
        for i in range(24):
            ang = 15 * i + (7.5 if rr == 1700 or rr == 1950 else 0)
            waypoint(polar(rr, ang))
    for i in range(16):
        SPAWNS.append(tuple(round(v) for v in polar(1750 if i % 2 else 1950, 22.5 * i, TOP + 24)))
        light(polar(1700, 22.5 * i, 300), 800, "1 1 0.95")
    # corner pylons on the rim
    for k in range(4):
        c = polar(2000, 45 + 90 * k)
        box(c[0] - 70, c[1] - 70, TOP, c[0] + 70, c[1] + 70, 1100, TEX["pylon"], TEX["pylon"], TEX["pylon"])
        prism(poly_pts(c[0], c[1], 85, 8), 1100, 1140, TEX["glow"], TEX["glow"], TEX["glow"])
        light((c[0], c[1], 1180), 1200, "0.5 0.75 1")

    # --- hurt volume far below the platforms (the chasm) ---
    box(-s, -s, -2000, s, s, -1900, TEX["trigger"], TEX["trigger"], TEX["trigger"])
    trig = brushes.pop()
    entities.append(dict(classname="trigger_hurt", spawnflags=44, dmg=10000, _brush=trig))

    global START
    START = polar(300, 270, TOP + 24)
    entities.append(dict(classname="info_player_start", origin="%d %d %d" % START, angle=90))

def to_map(extra_entities=()):
    """Full .map text. extra_entities: dicts (point entities) appended after the geometry."""
    out = ['// entity 0', '{', '"classname" "worldspawn"']
    out += ['// brush %d\n%s' % (i, b) for i, b in enumerate(brushes)]
    out.append('}')
    for n, e in enumerate(list(entities) + list(extra_entities), 1):
        out.append('// entity %d\n{' % n)
        out += ['"%s" "%s"' % (k, v) for k, v in e.items() if k != "_brush"]
        if "_brush" in e:
            out.append(e["_brush"])
        out.append('}')
    for p in waypoints:
        out.append('{\n"classname" "waypoint"\n"origin" "%d %d %d"\n}' % p)
    return "\n".join(out) + "\n"

build()
