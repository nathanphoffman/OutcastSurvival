"""Generates the BattleDroid: a Ghoul2 model (.glm) skinned onto the game's own humanoid skeleton, plus its
texture, glow map, shader, skin and NPC definition. build.py calls files() and packs the result into the pk3.

How the mesh is made: the body is built from boxes / cylinders / spheres (see build_parts). Each vertex copies the
bone weights of the nearest vertices on the stormtrooper model (restricted to a body-part group, see SRC), so the
robot bends at the same joints the humanoid animations expect. The stormtrooper's bolt-on (tag) surfaces are copied
so the engine still finds *head_eyes, *r_hand, ... and a few new ones are added for the cannons and missile pods.
Everything is in model space: x = character's left, y = back (front is -y), z = up. Soles at z ~ 3, head top ~ 74."""
import math, os, random, struct, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "battledroid"
DIR = "models/players/" + NAME
SHADER = DIR + "/droid"
TEMPLATE = "models/players/stormtrooper/model.glm"
GLA = "models/players/_humanoid/_humanoid.gla"

# --- small vector helpers ----------------------------------------------------------------------------------
add = lambda a, b: (a[0] + b[0], a[1] + b[1], a[2] + b[2])
sub = lambda a, b: (a[0] - b[0], a[1] - b[1], a[2] - b[2])
mul = lambda a, k: (a[0] * k, a[1] * k, a[2] * k)
dot = lambda a, b: a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
cross = lambda a, b: (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
lerp = lambda a, b, t: add(mul(a, 1 - t), mul(b, t))
def norm(a):
    l = math.sqrt(dot(a, a)) or 1.0
    return (a[0] / l, a[1] / l, a[2] / l)

def perp(d, hint):
    """Unit vector perpendicular to d, as close to hint as possible."""
    return norm(sub(hint, mul(d, dot(hint, d))))

# --- reading the stock files ---------------------------------------------------------------------------------
def read_asset(game_dir, path):
    for pk in sorted(os.listdir(game_dir)):
        if pk.lower().endswith(".pk3"):
            with zipfile.ZipFile(os.path.join(game_dir, pk)) as z:
                if path in z.namelist():
                    return z.read(path)
    raise FileNotFoundError(path)

cstr = lambda b: b.split(b"\0")[0].decode()

def parse_bones(gla):
    nb = struct.unpack_from("<i", gla, 84)[0]   # mdxaHeader_t.numBones
    names = []
    for i in range(nb):
        off = 100 + struct.unpack_from("<i", gla, 100 + 4 * i)[0]
        names.append(cstr(gla[off:off + 64]))
    return names

class Template:
    """The stormtrooper model.glm, parsed far enough to copy surfaces and bone weights from it."""
    def __init__(self, data):
        self.d = data
        h = struct.unpack_from("<ii64s64siiiiiii", data, 0)
        self.numBones, self.numLODs, self.ofsLODs, self.numSurfaces, self.ofsHier = h[5], h[6], h[7], h[8], h[9]
        self.hier = []
        for i in range(self.numSurfaces):
            o = 164 + struct.unpack_from("<i", data, 164 + 4 * i)[0]
            flags = struct.unpack_from("<I", data, o + 64)[0]
            parent = struct.unpack_from("<i", data, o + 136)[0]
            self.hier.append(dict(name=cstr(data[o:o + 64]), flags=flags, shader=cstr(data[o + 68:o + 132]), parent=parent))
        self.ofsSurf = []
        for i in range(self.numSurfaces):
            self.ofsSurf.append(self.ofsLODs + 4 + struct.unpack_from("<i", data, self.ofsLODs + 4 + 4 * i)[0])
        self.index = {h["name"].lower(): i for i, h in enumerate(self.hier)}

    def blob(self, i):
        so = self.ofsSurf[i]
        return bytearray(self.d[so:so + struct.unpack_from("<i", self.d, so + 36)[0]])

    def verts(self, i):
        """[(pos, [(global_bone, weight), ...])] for surface i."""
        so = self.ofsSurf[i]
        nv, ofv, nbr, ofbr = struct.unpack_from("<4i", self.d, so + 12)[0], struct.unpack_from("<i", self.d, so + 16)[0], \
            struct.unpack_from("<i", self.d, so + 28)[0], struct.unpack_from("<i", self.d, so + 32)[0]
        refs = struct.unpack_from("<%di" % nbr, self.d, so + ofbr)
        out = []
        for j in range(nv):
            nx, ny, nz, x, y, z, packed = struct.unpack_from("<6fI", self.d, so + ofv + 32 * j)
            bw = struct.unpack_from("<4B", self.d, so + ofv + 32 * j + 28)
            n = (packed >> 30) + 1
            ws, total = [], 0.0
            for k in range(n):
                bone = refs[(packed >> (5 * k)) & 31]
                if k == n - 1:
                    w = 1.0 - total
                else:
                    w = (bw[k] | ((packed >> (12 + 2 * k)) & 0x300)) / 1023.0
                    total += w
                ws.append((bone, max(w, 0.0)))
            out.append(((x, y, z), ws))
        return out

    def winding(self):
        """+1 if a front-facing triangle's (b-a)x(c-a) points along its vertex normals, else -1."""
        i = self.index["torso"]
        so = self.ofsSurf[i]
        nt, oft, ofv = struct.unpack_from("<i", self.d, so + 20)[0], struct.unpack_from("<i", self.d, so + 24)[0], struct.unpack_from("<i", self.d, so + 16)[0]
        votes = 0
        for t in range(nt):
            a, b, c = struct.unpack_from("<3i", self.d, so + oft + 12 * t)
            v = [struct.unpack_from("<6f", self.d, so + ofv + 32 * k) for k in (a, b, c)]
            p = [x[3:6] for x in v]
            nrm = tuple(sum(x[k] for x in v) for k in range(3))
            votes += 1 if dot(cross(sub(p[1], p[0]), sub(p[2], p[0])), nrm) > 0 else -1
        return 1 if votes > 0 else -1

# --- the texture atlas: 4x4 cells of 256px ---------------------------------------------------------------------
CELLS = dict(armor=(0, 0), armor2=(1, 0), joint=(2, 0), glow=(3, 0), barrel=(0, 1), face=(1, 1), chest=(2, 1),
             pod=(3, 1), foot=(0, 2), vent=(1, 2), pauldron=(2, 2), dark=(3, 2))
def region(name, pad=0.004):
    c, r = CELLS[name]
    return (c / 4 + pad, r / 4 + pad, (c + 1) / 4 - pad, (r + 1) / 4 - pad)

def paint_textures():
    from PIL import Image, ImageDraw, ImageFilter
    rnd = random.Random(7)
    S = 256
    diff = Image.new("RGB", (1024, 1024), (0, 0, 0))
    glow = Image.new("RGB", (1024, 1024), (0, 0, 0))

    def plate(base, seam=(30, 34, 40), rivets=True, wear=14):
        im = Image.new("RGB", (S, S), base)
        d = ImageDraw.Draw(im)
        for _ in range(2600):   # brushed-metal speckle
            x, y = rnd.randrange(S), rnd.randrange(S)
            k = rnd.randint(-wear, wear)
            d.point((x, y), tuple(max(0, min(255, c + k)) for c in base))
        for _ in range(26):     # scratches
            x, y = rnd.randrange(S), rnd.randrange(S)
            l = rnd.randint(8, 40)
            k = rnd.randint(25, 60)
            d.line((x, y, x + l, y + rnd.randint(-3, 3)), fill=tuple(min(255, c + k) for c in base))
        d.rectangle((0, 0, S - 1, S - 1), outline=seam, width=5)             # panel border
        d.line((0, S // 2, S, S // 2), fill=seam, width=3)
        d.line((S // 2, 0, S // 2, S // 2), fill=seam, width=2)
        if rivets:
            for x in (14, S // 2, S - 14):
                for y in (14, S // 2, S - 14):
                    d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=tuple(min(255, c + 40) for c in base), outline=seam)
        return im

    def put(img, name, im):
        c, r = CELLS[name]
        img.paste(im, (c * S, r * S))

    # gunmetal armor and darker armor with a hazard band
    put(diff, "armor", plate((92, 100, 112)))
    a2 = plate((58, 62, 70))
    d = ImageDraw.Draw(a2)
    for x in range(-S, S * 2, 28):
        d.polygon([(x, S - 52), (x + 14, S - 52), (x + 14 + 24, S - 8), (x + 24, S - 8)], fill=(210, 160, 20))
    d.rectangle((0, S - 52, S, S - 49), fill=(20, 20, 20))
    d.rectangle((0, S - 8, S, S - 5), fill=(20, 20, 20))
    put(diff, "armor2", a2)
    # joints: dark ribbed metal
    j = plate((38, 40, 46), seam=(14, 14, 16), rivets=False)
    d = ImageDraw.Draw(j)
    for y in range(6, S, 14):
        d.line((0, y, S, y), fill=(20, 21, 24), width=4)
        d.line((0, y + 4, S, y + 4), fill=(78, 82, 92), width=1)
    put(diff, "joint", j)
    # plain glowing orange (energy cells, thruster vents)
    put(diff, "glow", Image.new("RGB", (S, S), (255, 120, 40)))
    put(glow, "glow", Image.new("RGB", (S, S), (255, 100, 30)))
    # barrel: dark steel with long vents
    b = plate((46, 48, 54), seam=(16, 16, 18), rivets=False)
    d = ImageDraw.Draw(b)
    for x in range(20, S, 36):
        d.rectangle((x, 30, x + 10, S - 30), fill=(14, 14, 16), outline=(70, 74, 84))
    put(diff, "barrel", b)
    # face: dark helmet plate with a red visor slit
    f = plate((54, 58, 66), rivets=False)
    d = ImageDraw.Draw(f)
    d.rectangle((26, 92, S - 26, 128), fill=(12, 4, 4), outline=(10, 10, 10), width=3)
    d.rectangle((34, 102, S - 34, 118), fill=(255, 40, 20))
    for y in range(160, 232, 12):   # mouth grille
        d.line((70, y, S - 70, y), fill=(14, 14, 16), width=5)
    put(diff, "face", f)
    g = Image.new("RGB", (S, S), (0, 0, 0))
    d = ImageDraw.Draw(g)
    d.rectangle((34, 102, S - 34, 118), fill=(255, 30, 10))
    put(glow, "face", g.filter(ImageFilter.GaussianBlur(2)))
    # chest: front plate with a reactor window
    ch = plate((84, 90, 102))
    d = ImageDraw.Draw(ch)
    d.rectangle((70, 60, S - 70, 196), fill=(10, 10, 12), outline=(160, 160, 40), width=4)
    d.ellipse((88, 84, S - 88, 172), fill=(255, 110, 30), outline=(255, 220, 120), width=3)
    d.ellipse((112, 108, S - 112, 148), fill=(255, 235, 170))
    for x in (30, S - 30):    # hazard ticks
        d.line((x, 40, x, 216), fill=(210, 160, 20), width=6)
    put(diff, "chest", ch)
    g = Image.new("RGB", (S, S), (0, 0, 0))
    d = ImageDraw.Draw(g)
    d.ellipse((88, 84, S - 88, 172), fill=(255, 90, 20))
    d.ellipse((112, 108, S - 112, 148), fill=(255, 220, 140))
    put(glow, "chest", g.filter(ImageFilter.GaussianBlur(5)))
    # missile pod front: four dark tubes
    p = plate((60, 64, 72))
    d = ImageDraw.Draw(p)
    for cx in (S // 4, 3 * S // 4):
        for cy in (S // 4, 3 * S // 4):
            d.ellipse((cx - 44, cy - 44, cx + 44, cy + 44), fill=(10, 10, 12), outline=(140, 140, 150), width=4)
            d.ellipse((cx - 30, cy - 30, cx + 30, cy + 30), fill=(30, 12, 8))
    put(diff, "pod", p)
    g = Image.new("RGB", (S, S), (0, 0, 0))
    d = ImageDraw.Draw(g)
    for cx in (S // 4, 3 * S // 4):
        for cy in (S // 4, 3 * S // 4):
            d.ellipse((cx - 10, cy - 10, cx + 10, cy + 10), fill=(255, 70, 20))
    put(glow, "pod", g.filter(ImageFilter.GaussianBlur(3)))
    # feet: rubber tread
    t = plate((34, 34, 38), seam=(14, 14, 16), rivets=False)
    d = ImageDraw.Draw(t)
    for y in range(8, S, 20):
        d.line((0, y, S, y), fill=(18, 18, 20), width=6)
    put(diff, "foot", t)
    # vent grille
    v = plate((44, 46, 52), seam=(14, 14, 16))
    d = ImageDraw.Draw(v)
    for y in range(24, S - 20, 18):
        d.rectangle((28, y, S - 28, y + 8), fill=(12, 12, 14))
    put(diff, "vent", v)
    # pauldron: armor with yellow/black chevrons
    pa = plate((96, 104, 116))
    d = ImageDraw.Draw(pa)
    d.rectangle((0, 100, S, 156), fill=(24, 24, 26))
    for x in range(-S, S * 2, 40):
        d.polygon([(x, 156), (x + 18, 156), (x + 46, 100), (x + 28, 100)], fill=(214, 170, 24))
    put(diff, "pauldron", pa)
    put(diff, "dark", plate((26, 27, 31), seam=(10, 10, 12), rivets=False))
    return diff, glow

# --- mesh building -----------------------------------------------------------------------------------------------
class Surf:
    """A surface under construction: vertices (pos, normal, uv, source-group, fixed-bone) and triangles."""
    def __init__(self, name, src):
        self.name, self.src = name, src
        self.V, self.T = [], []

    def vert(self, p, n, uv, src=None, bone=None):
        self.V.append((p, norm(n), uv, src or self.src, bone))
        return len(self.V) - 1

    def tri(self, a, b, c):
        self.T.append((a, b, c))

def grid(s, org, du, dv, nu, nv, normal, reg, xf=None, src=None, bone=None):
    """A flat patch: org + du*i/nu + dv*j/nv. j=0 is the bottom edge (dv is usually +z)."""
    u0, v0, u1, v1 = reg
    idx = []
    for j in range(nv + 1):
        row = []
        for i in range(nu + 1):
            p = add(org, add(mul(du, i / nu), mul(dv, j / nv)))
            if xf:
                p = xf(p)
            row.append(s.vert(p, normal, (u0 + (u1 - u0) * i / nu, v1 - (v1 - v0) * j / nv), src, bone))
        idx.append(row)
    for j in range(nv):
        for i in range(nu):
            a, b, c, d = idx[j][i], idx[j][i + 1], idx[j + 1][i + 1], idx[j + 1][i]
            s.tri(a, b, c)
            s.tri(a, c, d)

def box(s, lo, hi, reg, sub=(1, 1, 1), faces=None, xf=None, src=None, bone=None):
    """Axis-aligned box. faces maps '+x','-x','+y','-y','+z','-z' to a different region (front is -y)."""
    faces = faces or {}
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    dx, dy, dz = (x1 - x0, 0, 0), (0, y1 - y0, 0), (0, 0, z1 - z0)
    R = lambda k: region(faces[k]) if k in faces else reg
    grid(s, (x1, y0, z0), dy, dz, sub[1], sub[2], (1, 0, 0), R("+x"), xf, src, bone)
    grid(s, (x0, y1, z0), mul(dy, -1), dz, sub[1], sub[2], (-1, 0, 0), R("-x"), xf, src, bone)
    grid(s, (x1, y1, z0), mul(dx, -1), dz, sub[0], sub[2], (0, 1, 0), R("+y"), xf, src, bone)
    grid(s, (x0, y0, z0), dx, dz, sub[0], sub[2], (0, -1, 0), R("-y"), xf, src, bone)
    grid(s, (x0, y0, z1), dx, dy, sub[0], sub[1], (0, 0, 1), R("+z"), xf, src, bone)
    grid(s, (x0, y1, z0), dx, mul(dy, -1), sub[0], sub[1], (0, 0, -1), R("-z"), xf, src, bone)

def cyl(s, p0, p1, r0, r1, reg, n=8, rings=1, caps=(True, True), src=None, bone=None):
    axis = sub(p1, p0)
    a = norm(axis)
    t = (1, 0, 0) if abs(a[0]) < 0.9 else (0, 1, 0)
    u = norm(cross(a, t))
    v = cross(a, u)
    u0, v0, u1, v1 = reg
    rows = []
    for j in range(rings + 1):
        f = j / rings
        c, r = lerp(p0, p1, f), r0 + (r1 - r0) * f
        row = []
        for i in range(n + 1):
            ang = 2 * math.pi * i / n
            d = add(mul(u, math.cos(ang)), mul(v, math.sin(ang)))
            nrm = add(d, mul(a, (r0 - r1) / (math.sqrt(dot(axis, axis)) or 1)))
            row.append(s.vert(add(c, mul(d, r)), nrm, (u0 + (u1 - u0) * i / n, v1 - (v1 - v0) * f), src, bone))
        rows.append(row)
    for j in range(rings):
        for i in range(n):
            s.tri(rows[j][i], rows[j][i + 1], rows[j + 1][i + 1])
            s.tri(rows[j][i], rows[j + 1][i + 1], rows[j + 1][i])
    for end, (c, r, nrm) in enumerate(((p0, r0, mul(a, -1)), (p1, r1, a))):
        if not caps[end]:
            continue
        mid = ((u0 + u1) / 2, (v0 + v1) / 2)
        ci = s.vert(c, nrm, mid, src, bone)
        ring = [s.vert(add(c, mul(add(mul(u, math.cos(2 * math.pi * i / n)), mul(v, math.sin(2 * math.pi * i / n))), r)),
                       nrm, mid, src, bone) for i in range(n + 1)]
        for i in range(n):
            s.tri(ci, ring[i], ring[i + 1])

def sphere(s, c, r, reg, n=8, scale=(1, 1, 1), src=None, bone=None):
    u0, v0, u1, v1 = reg
    rows = []
    for j in range(n + 1):
        phi = math.pi * j / n
        row = []
        for i in range(n * 2 + 1):
            th = 2 * math.pi * i / (n * 2)
            d = (math.sin(phi) * math.cos(th), math.sin(phi) * math.sin(th), math.cos(phi))
            p = add(c, (d[0] * r * scale[0], d[1] * r * scale[1], d[2] * r * scale[2]))
            row.append(s.vert(p, d, (u0 + (u1 - u0) * i / (n * 2), v0 + (v1 - v0) * j / n), src, bone))
        rows.append(row)
    for j in range(n):
        for i in range(n * 2):
            s.tri(rows[j][i], rows[j][i + 1], rows[j + 1][i + 1])
            s.tri(rows[j][i], rows[j + 1][i + 1], rows[j + 1][i])

# --- the robot design -------------------------------------------------------------------------------------------
# which stormtrooper surfaces each part copies its bone weights from
SRC = dict(
    hips=("hips", "hips_body"), torso=("torso", "torso_body", "torso_body_neck_augment"), head=("head",),
    l_leg=("l_leg", "l_leg_knee"), r_leg=("r_leg", "r_leg_knee"),
    l_arm=("l_arm", "l_arm_shoulder", "l_arm_sleeve"), r_arm=("r_arm", "r_arm_shoulder", "r_arm_sleeve"),
    l_hand=("l_hand", "l_hand_plate"), r_hand=("r_hand", "r_hand_plate"),
)
# Muzzle / pod tag positions (model space), used by the AI through the tag surface names.
ELBOW, WRIST = (13.8, 0.8, 46.0), (18.8, 0.3, 40.2)   # left side; the right side mirrors x
FOREARM = norm(sub(WRIST, ELBOW))                      # the cannons point along the forearm, so they follow the arm
CANNON_LEN = 17.0
FLASH_L = add(WRIST, mul(FOREARM, CANNON_LEN + 0.5))
FLASH_R = (-FLASH_L[0], FLASH_L[1], FLASH_L[2])
POD_L, POD_R = (9.0, -2.4, 64.5), (-9.0, -2.4, 64.5)

def build_parts():
    parts = {}
    def S(name, src):
        parts[name] = Surf(name, SRC[src] if src in SRC else src)
        return parts[name]

    A, A2, J, BR, FACE, CHEST, POD, FOOT, VENT, PAU, DARK, GLOW = (region(k) for k in
        ("armor", "armor2", "joint", "barrel", "face", "chest", "pod", "foot", "vent", "pauldron", "dark", "glow"))

    # ---- hips / waist ----
    s = S("hips", "hips")
    box(s, (-7.8, -5.2, 33.0), (7.8, 6.2, 41.0), A2, sub=(2, 1, 1), faces={"-y": "armor2"})
    box(s, (-3.6, -6.6, 31.5), (3.6, -5.0, 40.0), A, faces={"-y": "armor2"})            # front plate
    box(s, (-5.5, 4.8, 34.0), (5.5, 7.4, 40.0), VENT)                                    # rear vent
    s = S("hips_body", "hips")
    cyl(s, (0, 0.4, 40.2), (0, 0.4, 46.4), 4.6, 4.6, J, n=8, rings=2)                    # waist column
    for x in (-3.4, 3.4):
        cyl(s, (x, -3.2, 40.5), (x, -3.2, 46.0), 1.2, 1.2, BR, n=6)                      # hydraulic pistons

    # ---- torso ----
    s = S("torso", "torso")
    taper = lambda p: (p[0] * (0.78 + 0.22 * min(1.0, max(0.0, (p[2] - 45.0) / 14.0))), p[1], p[2])
    box(s, (-10.6, -6.0, 45.0), (10.6, 7.2, 63.0), A, sub=(2, 1, 3), xf=taper)
    box(s, (-6.8, -7.4, 48.0), (6.8, -5.8, 60.5), CHEST)                                 # reactor plate
    box(s, (-10.8, -6.2, 45.6), (10.8, 7.4, 48.2), A2)                                   # belt line
    s = S("torso_armor_neck_augment", "torso")
    box(s, (-6.4, -5.0, 61.4), (6.4, 5.6, 64.2), A2)                                     # collar
    s = S("torso_body", "torso")
    box(s, (-6.8, 7.0, 46.0), (6.8, 12.2, 60.0), VENT)                                   # power pack
    for x in (-4.0, 4.0):
        cyl(s, (x, 9.6, 60.0), (x, 9.6, 66.0), 1.9, 1.5, J, n=6)                         # exhaust stacks
    for sx, name in ((1, "pod_l"), (-1, "pod_r")):                                       # missile pods on the shoulders
        box(s, (sx * 9.0 - 3.0 if sx > 0 else sx * 9.0 - 3.0, -2.2, 61.5), (sx * 9.0 + 3.0, 8.0, 67.5), A2,
            faces={"-y": "pod"}, bone="thoracic")
    s = S("torso_body_neck_augment", "torso")
    cyl(s, (0, 0.4, 59.0), (0, 0.4, 64.0), 2.7, 2.5, J, n=8)                            # neck

    # ---- head ----
    s = S("head", "head")
    box(s, (-4.8, -5.4, 63.4), (4.8, 4.4, 72.6), A2, faces={"-y": "face"}, sub=(1, 1, 2),
        xf=lambda p: (p[0] * (1.0 - 0.1 * max(0.0, (p[2] - 68.0)) / 4.6), p[1], p[2]))
    box(s, (-5.2, -5.9, 69.4), (5.2, -2.0, 70.8), A)                                     # brow
    cyl(s, (-5.4, 0.2, 67.6), (-6.8, 0.2, 67.6), 2.2, 2.2, DARK, n=8)                    # ear caps
    cyl(s, (5.4, 0.2, 67.6), (6.8, 0.2, 67.6), 2.2, 2.2, DARK, n=8)
    sphere(s, (0, 0.3, 73.0), 2.0, A, n=5, scale=(1, 1, 0.7))                            # sensor dome
    cyl(s, (4.0, 1.5, 72.0), (4.4, 2.0, 79.0), 0.4, 0.25, DARK, n=4)                     # antenna

    # ---- legs ----
    for sx, side in ((1, "l"), (-1, "r")):
        k = lambda x, y, z: (sx * x, y, z)
        s = S(side + "_leg", side + "_leg")
        sphere(s, k(4.5, 0.2, 35.0), 4.6, J, n=5)                                        # hip joint
        cyl(s, k(4.4, 0.3, 35.0), k(7.4, 0.8, 22.4), 5.3, 4.6, A, n=8, rings=3)          # thigh
        box(s, (min(sx * 8.8, sx * 3.0), -6.4, 24.0), (max(sx * 8.8, sx * 3.0), -4.2, 34.0), A2)   # thigh plate
        cyl(s, k(7.6, 0.9, 20.6), k(10.9, 1.8, 8.6), 4.4, 3.5, A, n=8, rings=3)          # shin
        box(s, (min(sx * 12.2, sx * 8.4), 2.2, 11.0), (max(sx * 12.2, sx * 8.4), 7.0, 21.0), A2)   # calf armor
        box(s, (min(sx * 15.4, sx * 8.4), -10.6, 3.0), (max(sx * 15.4, sx * 8.4), 4.0, 7.2), FOOT,
            faces={"+z": "armor2"}, sub=(1, 2, 1))                                       # foot
        box(s, (min(sx * 14.8, sx * 8.9), -11.4, 3.2), (max(sx * 14.8, sx * 8.9), -7.8, 5.4), A2)   # toe cap
        s = S(side + "_leg_knee", side + "_leg")
        sphere(s, k(7.4, -0.3, 21.4), 5.0, J, n=6)
        box(s, (min(sx * 9.6, sx * 5.2), -6.6, 18.6), (max(sx * 9.6, sx * 5.2), -3.8, 24.4), A)   # knee guard

    # ---- arms (shoulder -> elbow -> forearm cannon) ----
    for sx, side in ((1, "l"), (-1, "r")):
        k = lambda x, y, z: (sx * x, y, z)
        xs = lambda a, b: (min(sx * a, sx * b), max(sx * a, sx * b))
        s = S(side + "_arm", side + "_arm")
        cyl(s, k(8.0, 1.1, 53.0), k(13.4, 0.9, 46.6), 4.0, 3.5, A, n=8, rings=3)         # upper arm
        s = S(side + "_arm_shoulder", side + "_arm")
        sphere(s, k(10.4, 1.0, 57.2), 5.6, PAU, n=6, scale=(1.0, 1.0, 0.85))             # pauldron
        s = S(side + "_arm_sleeve", side + "_arm")
        sphere(s, k(13.6, 0.9, 46.4), 4.4, J, n=6)                                       # elbow joint
        s = S(side + "_hand", side + "_hand")
        e, w = k(*ELBOW), k(*WRIST)
        d = norm(sub(w, e))
        out = perp(d, (sx, 0, 0))          # sideways / forwards relative to the forearm axis
        fwd = perp(d, (0, -1, 0))
        at = lambda t, o=(0, 0, 0): add(add(w, mul(d, t)), o)
        cyl(s, e, at(1.0), 4.9, 4.5, A2, n=8, rings=2)                                    # forearm
        s2 = S(side + "_hand_plate", side + "_hand")
        if side == "l":   # left: rotary pulse cannon
            cyl(s, at(0.5), at(5.0), 4.0, 4.0, J, n=8)                                    # breech
            for ang in (0, 2.094, 4.189):
                o = add(mul(out, 1.9 * math.cos(ang)), mul(fwd, 1.9 * math.sin(ang)))
                cyl(s, at(4.0, o), at(CANNON_LEN, o), 1.1, 1.1, BR, n=6)                  # three barrels
            cyl(s, at(11.0), at(13.5), 3.4, 3.4, J, n=8)                                  # barrel clamp
            cyl(s, at(CANNON_LEN - 0.6), at(CANNON_LEN), 3.3, 3.3, J, n=8)
            cyl(s2, at(-1.0, mul(out, 4.2)), at(7.0, mul(out, 4.2)), 3.0, 3.0, A2, n=8)  # ammo drum
        else:             # right: heavy blaster cannon
            cyl(s, at(0.5), at(5.0), 4.2, 3.6, J, n=8)
            cyl(s, at(4.0), at(CANNON_LEN), 2.6, 2.3, BR, n=8, rings=2)                   # fat barrel
            cyl(s, at(CANNON_LEN - 2.6), at(CANNON_LEN), 3.4, 3.4, J, n=8)                # muzzle brake
            cyl(s2, at(-1.0, mul(out, 4.0)), at(8.0, mul(out, 4.0)), 2.6, 2.6, A2, n=8)  # power cell
            cyl(s2, at(2.0, mul(fwd, -3.4)), at(CANNON_LEN - 3.0, mul(fwd, -3.4)), 0.8, 0.8, A, n=6)   # under rail
    return parts

# --- weights and file writing ----------------------------------------------------------------------------------------
def clean_bone(name):
    """Fold finger/tag bones into the hand so cannon parts never flap with finger anims."""
    low = name.lower()
    if low.startswith("r_d") or low == "mc7" or low == "rhang_tag_bone":
        return "rhand"
    if low.startswith("l_d") or low == "mc5":
        return "lhand"
    return name

def encode_vertex(pos, normal, weights, refs):
    ws = sorted(weights, key=lambda w: -w[1])[:4]
    tot = sum(w for _, w in ws) or 1.0
    ws = [(b, w / tot) for b, w in ws]
    n = len(ws)
    packed = (n - 1) << 30
    bw = [0, 0, 0, 0]
    for k, (b, w) in enumerate(ws):
        if b not in refs:
            refs.append(b)
        packed |= (refs.index(b) & 31) << (5 * k)
        if k < n - 1:
            wi = max(0, min(1023, int(round(w * 1023))))
            bw[k] = wi & 255
            packed |= ((wi >> 8) & 3) << (20 + 2 * k)
    return struct.pack("<6fI4B", normal[0], normal[1], normal[2], pos[0], pos[1], pos[2], packed, *bw)

def make_glm(game_dir):
    gla = read_asset(game_dir, GLA)
    bones = parse_bones(gla)
    bone_index = {b.lower(): i for i, b in enumerate(bones)}
    tpl = Template(read_asset(game_dir, TEMPLATE))
    wind = tpl.winding()
    parts = build_parts()

    # source vertices per template surface, with finger bones folded into the hands
    srcv = {}
    def source(name):
        if name not in srcv:
            lst = []
            for pos, ws in tpl.verts(tpl.index[name]):
                fixed = {}
                for b, w in ws:
                    gi = bone_index[clean_bone(bones[b]).lower()]
                    fixed[gi] = fixed.get(gi, 0.0) + w
                lst.append((pos, list(fixed.items())))
            srcv[name] = lst
        return srcv[name]

    def weights_for(pos, groups):
        cand = []
        for g in groups:
            cand += source(g)
        best = sorted(cand, key=lambda c: (c[0][0] - pos[0]) ** 2 + (c[0][1] - pos[1]) ** 2 + (c[0][2] - pos[2]) ** 2)[:4]
        acc = {}
        for p, ws in best:
            d = math.sqrt((p[0] - pos[0]) ** 2 + (p[1] - pos[1]) ** 2 + (p[2] - pos[2]) ** 2) + 0.5
            for b, w in ws:
                acc[b] = acc.get(b, 0.0) + w / (d * d)
        return list(acc.items())

    def pack_surface(index, surf):
        refs, vbytes, ubytes = [], b"", b""
        for pos, nrm, uv, src, bone in surf.V:
            ws = [(bone_index[bone.lower()], 1.0)] if bone else weights_for(pos, src)
            vbytes += encode_vertex(pos, nrm, ws, refs)
            ubytes += struct.pack("<2f", uv[0], uv[1])
        if len(refs) > 32:
            raise ValueError("%s uses %d bones (max 32)" % (surf.name, len(refs)))
        tris = b""
        for a, b, c in surf.T:   # make every triangle wind the way the stock models do, judged by its vertex normals
            p = [surf.V[k][0] for k in (a, b, c)]
            n = tuple(sum(surf.V[k][1][i] for k in (a, b, c)) for i in range(3))
            if dot(cross(sub(p[1], p[0]), sub(p[2], p[0])), n) * wind < 0:
                b, c = c, b
            tris += struct.pack("<3i", a, b, c)
        return tris, vbytes, ubytes, refs

    # ---- tags: copy the stormtrooper's, move some, add the new ones ----
    new_tags = [("*flash1", "l_hand", "*l_hand", FLASH_L), ("*flash2", "r_hand", "*r_hand", FLASH_R),
                ("*pod_l", "torso", "*shldr_l", POD_L), ("*pod_r", "torso", "*shldr_r", POD_R)]
    moved = {"*l_hand": (19.4, 0.4, 40.0), "*r_hand": (-19.4, 0.4, 40.0)}

    def tag_blob(src_name, target):
        blob = tpl.blob(tpl.index[src_name.lower()])
        ofv, nv = struct.unpack_from("<2i", blob, 16)[0], struct.unpack_from("<i", blob, 12)[0]
        ps = [struct.unpack_from("<3f", blob, ofv + 32 * j + 12) for j in range(nv)]
        c = tuple(sum(p[k] for p in ps) / nv for k in range(3))
        if target is not None:
            for j, p in enumerate(ps):
                struct.pack_into("<3f", blob, ofv + 32 * j + 12, *add(p, sub(target, c)))
        return blob

    # ---- assemble the surface list (template order, then new tags) ----
    hier = [dict(h) for h in tpl.hier]
    blobs = []
    for i, h in enumerate(hier):
        name = h["name"]
        if name in parts:
            blobs.append(("gen", parts[name]))
            h["shader"] = SHADER
        elif h["flags"] & 1 and name in moved:
            blobs.append(("blob", tag_blob(name, moved[name])))
        else:
            blobs.append(("blob", tpl.blob(i)))
    # parts that exist in the robot but not as a template surface do not exist (all names above are template names)
    missing = [n for n in parts if n not in tpl.index]
    if missing:
        raise ValueError("no such surface in template: %s" % missing)
    for name, par, srcname, pos in new_tags:
        hier.append(dict(name=name, flags=1, shader="[nomaterial]", parent=tpl.index[par]))
        blobs.append(("blob", tag_blob(srcname, pos)))
    ns = len(hier)

    children = [[] for _ in hier]
    for i, h in enumerate(hier):
        if h["parent"] >= 0:
            children[h["parent"]].append(i)

    # hierarchy block
    entries = []
    for i, h in enumerate(hier):
        e = struct.pack("<64sI64siiii", h["name"].encode(), h["flags"], h["shader"].encode(), 0, h["parent"], len(children[i]), 0)[:-4]
        e += b"".join(struct.pack("<i", c) for c in children[i])
        entries.append(e)
    hier_off, pos_ = [], 0
    for e in entries:
        hier_off.append(pos_)
        pos_ += len(e)
    ofs_hier_start = 164 + 4 * ns
    hier_bytes = b"".join(struct.pack("<i", o + 4 * ns) for o in hier_off) + b"".join(entries)
    ofs_lods = 164 + len(hier_bytes)

    # surfaces
    surfs, offs = [], []
    lod_base = ofs_lods + 4 + 4 * ns
    cur = lod_base
    for i, (kind, obj) in enumerate(blobs):
        if kind == "gen":
            tris, vb, ub, refs = pack_surface(i, obj)
            nv, nt = len(obj.V), len(obj.T)
            head_size = 40
            ofs_tri = head_size
            ofs_v = ofs_tri + len(tris)
            ofs_ref = ofs_v + len(vb) + len(ub)
            end = ofs_ref + 4 * len(refs)
            body = struct.pack("<10i", 0, i, -cur, nv, ofs_v, nt, ofs_tri, len(refs), ofs_ref, end)
            body += tris + vb + ub + b"".join(struct.pack("<i", r) for r in refs)
        else:
            body = bytearray(obj)
            struct.pack_into("<2i", body, 4, i, -cur)
            body = bytes(body)
        surfs.append(body)
        offs.append(cur - (ofs_lods + 4))
        cur += len(body)
    lod_block = struct.pack("<i", cur - ofs_lods) + b"".join(struct.pack("<i", o) for o in offs) + b"".join(surfs)

    header = struct.pack("<ii64s64siiiiiii", 0x4d474c32, 6, ("%s/model.glm" % DIR).encode(), b"models/players/_humanoid/_humanoid",
                         0, len(bones), 1, ofs_lods, ns, ofs_hier_start, ofs_lods + len(lod_block))
    return header + hier_bytes + lod_block

def make_skin(glm_names):
    """model_default.skin: every on-surface uses the droid shader (tags and *_off caps keep their own)."""
    return "\n".join("%s,%s" % (n, SHADER) for n in glm_names) + "\n"

SHADER_TXT = """%(s)s
{
	qer_editorimage %(d)s/droid.tga
	{
		map %(d)s/droid.tga
		rgbGen lightingDiffuse
	}
	{
		map %(d)s/droid_glow.tga
		blendFunc GL_ONE GL_ONE
		rgbGen identity
	}
}
""" % dict(s=SHADER, d=DIR)

NPC_TXT = """BattleDroid
{
	fullName		"Battle Droid"
	playerModel		%(n)s
	class			battledroid
	health			420
	playerTeam		enemy
	enemyTeam		player
	reactions		3
	aim				4
	move			4
	aggression		5
	evasion			1
	intelligence	4
	rank			lt
	scale			100
	width			22
	height			84
	crouchheight	84
	yawspeed		70
	walkSpeed		50
	runSpeed		130
	headPitchRangeUp	25
	headPitchRangeDown	25
	torsoPitchRangeUp	25
	torsoPitchRangeDown	25
	dismemberProbHead	0
	dismemberProbArms	0
	dismemberProbHands	0
	dismemberProbLegs	0
	dismemberProbWaist	0
}
""" % dict(n=NAME)

def files(game_dir):
    """{pk3 path: bytes} for everything the droid needs. Cached in tools/build/ until this file changes."""
    cache = os.path.join(HERE, "tools", "build", "droid")
    stamp = os.path.getmtime(__file__)
    paths = ["%s/model.glm" % DIR, "%s/model_default.skin" % DIR, "%s/droid.tga" % DIR, "%s/droid_glow.tga" % DIR,
             "%s/animsounds.cfg" % DIR, "shaders/battledroid.shader", "ext_data/battledroid.npc"]
    if all(os.path.exists(os.path.join(cache, p)) and os.path.getmtime(os.path.join(cache, p)) > stamp for p in paths):
        return {p: open(os.path.join(cache, p), "rb").read() for p in paths}
    import io
    out = {}
    glm = make_glm(game_dir)
    out["%s/model.glm" % DIR] = glm
    tpl = Template(read_asset(game_dir, TEMPLATE))
    parts = build_parts()
    out["%s/model_default.skin" % DIR] = make_skin([n for n in (h["name"] for h in tpl.hier) if n in parts]).encode()
    diff, glow = paint_textures()
    for nm, im in (("droid", diff), ("droid_glow", glow)):
        buf = io.BytesIO()
        im.save(buf, "TGA")
        out["%s/%s.tga" % (DIR, nm)] = buf.getvalue()
    snd = read_asset(game_dir, "models/players/stormtrooper/animsounds.cfg").decode("latin1")
    snd = snd.replace("sound/player/footsteps/clank%d.wav", "sound/weapons/galak/footstep%d.wav")
    snd = "\n".join(l for l in snd.splitlines() if "chars/st1/misc" not in l) + "\n"   # no trooper death cries
    out["%s/animsounds.cfg" % DIR] = snd.encode("latin1")
    out["shaders/battledroid.shader"] = SHADER_TXT.encode()
    out["ext_data/battledroid.npc"] = NPC_TXT.encode()
    for p, data in out.items():
        fp = os.path.join(cache, p)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "wb") as f:
            f.write(data)
    return out

if __name__ == "__main__":
    import sys
    g = os.path.expanduser("~/.steam/steam/steamapps/common/Jedi Outcast/GameData/base")
    for p, d in files(g).items():
        print(p, len(d))
