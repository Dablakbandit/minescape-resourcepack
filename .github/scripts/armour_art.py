"""Art for the armour looks (armour_looks.py), painted in code so a look is a few lines.

A tile is 256x128 RGBA: Minecraft's 64x32 armour layout at four texels a model pixel. Greyscale
texels the item's dye tints carry alpha 255 (TINTED); 254 (OWN) keeps a texel's own colour (gold,
bone, studs, an emblem); 253 (LIGHT) dyes a greyscale texel a light shade of the dye ((t) trims,
mantles). Coordinates below are model pixels, fractions in quarters.
"""
import numpy as np
from PIL import Image, ImageDraw

SCALE = 4
TINTED, OWN, LIGHT = 255, 254, 253

# Faces as (u, v, width, height), and the strips that wrap round a box: right side, front, left
# side, back. Arms and legs share one texture between left and right, mirrored.
BODY_STRIP, BODY_FRONT, BODY_BACK = (16, 20, 24, 12), (20, 20, 8, 12), (32, 20, 8, 12)
BODY_TOP, BODY_BOTTOM = (20, 16, 8, 4), (28, 16, 8, 4)
ARM_STRIP, ARM_TOP, ARM_OUTER, ARM_FRONT = (40, 20, 16, 12), (44, 16, 4, 4), (40, 20, 4, 12), (44, 20, 4, 12)
LEG_STRIP, LEG_TOP, LEG_BOTTOM, LEG_FRONT, LEG_OUTER = (0, 20, 16, 12), (4, 16, 4, 4), (8, 16, 4, 4), (4, 20, 4, 12), (0, 20, 4, 12)
CHEST_AREA = [(16, 16, 56, 32)]
BOOTS_AREA = [(0, 16, 16, 32)]

GOLD, GOLD_DARK = (236, 184, 34), (150, 104, 14)
BONE, BONE_DARK = (228, 214, 170), (150, 132, 92)
STUD, STUD_DARK = (205, 205, 200), (110, 110, 108)
LEATHER_STRAP, RED_BELT = (96, 60, 30), (150, 30, 24)
GODS = {
    "zamorak": ((196, 36, 30), (110, 14, 10)),
    "saradomin": ((236, 232, 214), (150, 140, 110)),
    "guthix": ((70, 170, 60), (24, 90, 22)),
    "ancient": ((156, 64, 156), (80, 22, 80)),
    "armadyl": ((214, 214, 206), (120, 120, 112)),
    "bandos": ((196, 150, 60), (110, 76, 20)),
}


def rng(seed):
    return np.random.default_rng(seed)


class Canvas:
    def __init__(self, px=None):
        self.px = np.zeros((128, 256, 4), np.uint8) if px is None else px.copy()

    def _box(self, u, v, w, h):
        return (slice(int(round(v * SCALE)), int(round((v + h) * SCALE))),
                slice(int(round(u * SCALE)), int(round((u + w) * SCALE))))

    def fill(self, u, v, w, h, grey, code=TINTED):
        r = self.px[self._box(u, v, w, h)]
        r[..., :3] = grey
        r[..., 3] = code

    def own(self, u, v, w, h, rgb, only_opaque=False):
        r = self.px[self._box(u, v, w, h)]
        mask = r[..., 3] > 0 if only_opaque else np.ones(r.shape[:2], bool)
        r[mask, :3] = rgb
        r[mask, 3] = OWN

    def light(self, u, v, w, h, grey=235, only_opaque=False):
        r = self.px[self._box(u, v, w, h)]
        mask = r[..., 3] > 0 if only_opaque else np.ones(r.shape[:2], bool)
        r[mask, :3] = grey
        r[mask, 3] = LIGHT

    def clear(self, u, v, w, h):
        self.px[self._box(u, v, w, h)] = 0

    def pattern(self, u, v, w, h, fn, code=TINTED):
        """fn(x, y) -> grey, or None for clear, over the area's texels (x, y from its corner)."""
        r = self.px[self._box(u, v, w, h)]
        for y in range(r.shape[0]):
            for x in range(r.shape[1]):
                g = fn(x, y)
                if g is None:
                    r[y, x] = 0
                else:
                    r[y, x, :3] = g
                    r[y, x, 3] = code

    def shade(self, u, v, w, h, factor):
        """Darken (or lighten, factor > 1) the dyed texels of an area."""
        r = self.px[self._box(u, v, w, h)]
        mask = r[..., 3] == TINTED
        r[mask, :3] = np.clip(r[mask, :3].astype(float) * factor, 0, 255).astype(np.uint8)

    def noise(self, amount=6, seed=1):
        mask = self.px[..., 3] == TINTED
        n = rng(seed).integers(-amount, amount + 1, size=self.px.shape[:2])
        for c in range(3):
            ch = self.px[..., c].astype(int) + n
            self.px[..., c] = np.where(mask, np.clip(ch, 0, 255), self.px[..., c])

    def edges(self, faces, factor=0.75):
        """A darker rim of one texel round each face, so boxes read as shapes."""
        for u, v, w, h in faces:
            x0, y0, x1, y1 = int(u * SCALE), int(v * SCALE), int((u + w) * SCALE) - 1, int((v + h) * SCALE) - 1
            for sl in ((slice(y0, y0 + 1), slice(x0, x1 + 1)), (slice(y1, y1 + 1), slice(x0, x1 + 1)),
                       (slice(y0, y1 + 1), slice(x0, x0 + 1)), (slice(y0, y1 + 1), slice(x1, x1 + 1))):
                r = self.px[sl]
                mask = r[..., 3] == TINTED
                r[mask, :3] = (r[mask, :3].astype(float) * factor).astype(np.uint8)

    def line(self, points, rgb, width=2, code=OWN, only_opaque=True):
        layer = Image.new("L", (256, 128), 0)
        ImageDraw.Draw(layer).line([(x * SCALE, y * SCALE) for x, y in points], fill=255, width=width)
        mask = np.array(layer) > 0
        if only_opaque:
            mask &= self.px[..., 3] > 0
        self.px[mask, :3] = rgb if code != LIGHT else (rgb[0],) * 3
        self.px[mask, 3] = code

    def sprite(self, u, v, rows, palette):
        x0, y0 = int(round(u * SCALE)), int(round(v * SCALE))
        for j, row in enumerate(rows):
            for i, ch in enumerate(row):
                if ch != ".":
                    self.px[y0 + j, x0 + i, :3] = palette[ch]
                    self.px[y0 + j, x0 + i, 3] = OWN

    def stud(self, u, v, rgb=STUD, dark=STUD_DARK):
        """A round rivet three texels across."""
        self.sprite(u, v, [".a.", "abd", ".d."], {"a": rgb, "b": tuple(min(255, c + 30) for c in rgb), "d": dark})

    def spike(self, u, v, up=True, big=False):
        """A bone spike: four texels wide and five tall, or twice that."""
        rows = ["..a.", "..a.", ".aab", ".abb", "aabb"]
        if big:
            rows = ["...ab...", "...ab...", "..aabb..", "..aabb..", ".aaabbb.", ".aaabbb.", "aaaabbbb", "aaaabbbb"]
        if not up:
            rows = rows[::-1]
        self.sprite(u, v, rows, {"a": BONE, "b": BONE_DARK})

    def copy(self, other, areas):
        for u0, v0, u1, v1 in areas:
            sl = self._box(u0, v0, u1 - u0, v1 - v0)
            self.px[sl] = other.px[sl]


# How far in from vanilla's the armour shader draws each layer's sides (build_shaders.py, MS_NARROW).
# The top and bottom faces stay where they were, so their rims are cleared to match.
NARROW = {1: 0.5, 2: 0.15}


def rims(c, layer):
    """Clear the top and bottom faces' rims across (and the body box's front and back) by as much as
    the shader pulls the sides in. Under a texel, as the leggings' is, it is left: a lip too thin to
    see."""
    k = NARROW[layer]
    if k * SCALE < 1:
        return
    boxes = [(0, 4), (16, 8)] + ([(40, 4)] if layer == 1 else [])
    for u0, w in boxes:
        for u in (u0 + 4, u0 + 4 + w):
            c.clear(u, 16, k, 4)
            c.clear(u + w - k, 16, k, 4)
            if w == 8:
                c.clear(u, 16, w, k)
                c.clear(u, 20 - k, w, k)


def neckline(c):
    """Clear where the chest box would sit in the jaw: the middle of its top face and of the top
    row of its front and back."""
    c.clear(21, 16, 6, 4)
    c.clear(21.5, 20, 5, 0.75)
    c.clear(33.5, 20, 5, 0.75)


def trim_colours(kind):
    if kind == "gold":
        return GOLD, GOLD_DARK, OWN
    if kind == "light":
        return (235,), (150,), LIGHT
    colour, edge = GODS[kind]
    return colour, edge, OWN


def band(c, u, v, w, h, kind):
    colour, edge, code = trim_colours(kind)
    if code == LIGHT:
        c.light(u, v, w, h, colour[0], only_opaque=True)
    else:
        c.own(u, v, w, h, colour, only_opaque=True)


# --- textures ----------------------------------------------------------------------------------------

def folds(width, shades):
    return lambda x, y: shades[x % width]


def scales(cell=8, light=224, dark=188):
    """Overlapping scales, each lit at its top and shaded to its rim."""
    def fn(x, y):
        row = y // cell
        xx = (x + (cell // 2 if row % 2 else 0)) % cell
        yy = y % cell
        d = abs(xx - cell / 2 + 0.5) / (cell / 2) + yy / cell
        if d > 1.15:
            return dark - 6
        return int(light - (light - dark) * min(1.0, d))
    return fn


RING = [".aaaaaa.",
        "b......b",
        "b......b",
        "b......b",
        ".cccccc.",
        "........"]


def chain(light=228, mid=204, dark=172, fill=190):
    """Mail: rings two pixels across, lit on their upper rim and shaded on the lower, each row
    offset half a ring from the last."""
    tones = {"a": light, "b": mid, "c": dark, ".": fill}

    def fn(x, y):
        row = y // len(RING)
        return tones[RING[y % len(RING)][(x + 4 * (row % 2)) % len(RING[0])]]
    return fn


def diamonds(cell=8, light=210, dark=140):
    def fn(x, y):
        xx, yy = x % cell - cell / 2, y % cell - cell / 2
        return light if abs(xx) + abs(yy) < cell / 2 - 1 else dark
    return fn


def chevrons(cell=8, light=200, dark=150):
    """Ahrim's V pattern."""
    def fn(x, y):
        xx = abs(x % cell - cell / 2)
        return dark if (y - int(xx)) % cell in (0, 1) else light
    return fn


def checks(cell=4, a=(120, 70, 170), b=(80, 40, 120)):
    return lambda x, y: a if ((x // cell) + (y // cell)) % 2 == 0 else b


# --- chest ---------------------------------------------------------------------------------------------

def vest(c, fn, sleeves=0):
    """A sleeveless (or short sleeved) body: the torso in a pattern, the arms bare below `sleeves`."""
    c.pattern(*BODY_STRIP, fn)
    c.pattern(*BODY_TOP, fn)
    c.clear(40, 16, 16, 16)
    if sleeves:
        c.pattern(40, 20, 16, sleeves, fn)
        c.pattern(*ARM_TOP, fn)
    # a round neck at the top of the front
    c.clear(22.5, 20, 3, 1)


def platebody_trim(c, kind):
    colour, edge, code = trim_colours(kind)
    put = (lambda u, v, w, h, rgb: c.light(u, v, w, h, rgb[0], True)) if code == LIGHT else (lambda u, v, w, h, rgb: c.own(u, v, w, h, rgb, True))
    put(16, 31.25, 24, 0.75, colour)
    put(16, 31, 24, 0.25, edge)
    put(20, 16, 8, 0.5, colour)
    put(20, 19.5, 8, 0.5, colour)
    put(20, 16, 0.5, 4, colour)
    put(27.5, 16, 0.5, 4, colour)
    put(16, 20, 24, 0.5, colour)
    c.line([(20.4, 20.4), (24, 24.2), (27.6, 20.4)], colour, 2, code)
    c.line([(20.4, 21.1), (24, 24.9), (27.6, 21.1)], edge, 1, code)
    put(44, 16, 4, 0.5, colour)
    put(44, 19.5, 4, 0.5, colour)
    put(44, 16, 0.5, 4, colour)
    put(47.5, 16, 0.5, 4, colour)
    put(40, 22.75, 16, 0.75, colour)
    put(40, 23.5, 16, 0.25, edge)


def vest_trim(c, kind):
    """Edges of a vest: hem, the armholes, the neck."""
    band(c, 16, 31.25, 24, 0.75, kind)
    band(c, 16, 20, 24, 0.5, kind)
    band(c, 20, 16, 8, 0.5, kind)
    band(c, 20, 19.5, 8, 0.5, kind)


def robe_top(c, cuffs=True):
    c.pattern(*BODY_STRIP, folds(12, (220, 222, 222, 220, 216, 212, 208, 206, 206, 208, 212, 216)))
    c.fill(*BODY_TOP, 214)
    c.pattern(*ARM_STRIP, folds(8, (220, 222, 220, 214, 208, 206, 208, 214)))
    c.fill(*ARM_TOP, 216)
    if cuffs:
        # the arm and body boxes overlap at the sides, face to face: cuff and hem on the same row
        c.shade(40, 31, 16, 1, 0.9)
        c.shade(16, 31, 24, 1, 0.9)


def robe_top_trim(c, kind):
    band(c, 16, 31, 24, 1, kind)
    band(c, 40, 31, 16, 1, kind)
    band(c, 23.5, 21, 1, 10, kind)


EMBLEMS = {
    "zamorak": ([
        "....rrrrrrrr....", "..rr........rr..", ".r...dddddd...r.", ".r..........d.r.", "r..........d...r",
        "r.........d....r", "r........d.....r", "r.......d......r", "r......d.......r", "r.....d........r",
        "r....d.........r", ".r..d..........r", ".r...dddddd...r.", "..rr........rr..", "....rrrrrrrr....",
    ], {"r": (196, 36, 30), "d": (120, 16, 12)}),
    "saradomin": ([
        ".......w........", ".......w........", "......www.......", "......wyw.......", ".....wwyww......",
        "..wwwwyyywwww...", "wwwwyyyyyyywwwww", "..wwwwyyywwww...", ".....wwyww......", "......wyw.......",
        "......www.......", ".......w........", ".......w........",
    ], {"w": (240, 236, 220), "y": (226, 190, 70)}),
    "guthix": ([
        "....gggggggg....", "..gg........g...", ".g...........g..", "g...gggggg......", "g..g......g.....",
        "g..g...gggggg...", "g..g......g.g...", "g...g....g..g...", ".g...gggg...g...", "..gg.......g....",
        "....ggggggg.....",
    ], {"g": (70, 170, 60)}),
    "ancient": ([
        ".....pppppp.....", "...pp......pp...", "..p....dd....p..", ".p....dddd....p.", ".p...dd..dd...p.",
        "p...dd....dd...p", "p..dd......dd..p", "p...dd....dd...p", ".p...dd..dd...p.", ".p....dddd....p.",
        "..p....dd....p..", "...pp......pp...", ".....pppppp.....",
    ], {"p": (156, 64, 156), "d": (90, 24, 90)}),
    "armadyl": ([
        "w..............w", "ww............ww", "www..........www", ".www...gg...www.", ".wwww.gggg.wwww.",
        "..wwwwggggwwww..", "...wwwggggwww...", "....ww.gg.ww....", "......wggw......", ".......ww.......",
    ], {"w": (226, 226, 220), "g": (150, 150, 150)}),
    "bandos": ([
        "..b..........b..", "..bb........bb..", "...bbbbbbbbbb...", "...bkkkkkkkkb...", "..bbk.bbbb.kbb..",
        ".bb.kbb..bbk.bb.", "bb..kb....bk..bb", "....kbb..bbk....", ".....kbbbbk.....", "......kbbk......",
        ".......kk.......",
    ], {"b": (196, 150, 60), "k": (100, 70, 20)}),
}


def emblem(c, god):
    rows, palette = EMBLEMS[god]
    c.sprite(24 - len(rows[0]) / 2 / SCALE, 26.75 - len(rows) / 2 / SCALE, rows, palette)


def chest(name, plain):
    """The chest look `name` on a canvas, `plain` the current platebody art."""
    kind, _, trim = name.partition("_")
    c = Canvas()
    import armour_barrows
    if kind in armour_barrows.CHESTS:
        armour_barrows.CHESTS[kind](c)
        return c
    if kind in ("plain", "body"):
        c.copy(plain, CHEST_AREA)
        if trim:
            platebody_trim(c, trim)
            if trim in GODS:
                emblem(c, trim)
        return c
    if kind == "chain":
        vest(c, chain())
        c.noise(2, 3)
        c.edges([BODY_FRONT, BODY_BACK], 0.8)
        if trim:
            vest_trim(c, trim)
    elif kind == "dhide":
        vest(c, scales())
        c.shade(16, 31, 24, 1, 0.8)
        if trim:
            vest_trim(c, trim)
    elif kind == "leather":
        vest(c, folds(12, (205, 210, 212, 208, 200, 196, 192, 196, 202, 206, 208, 206)))
        # seams, and lacing up the front
        c.shade(16, 25.5, 24, 0.25, 0.75)
        for v in (21.5, 23, 24.5):
            c.own(23.75, v, 0.5, 0.75, LEATHER_STRAP)
        c.noise(7, 5)
        if trim:
            vest_trim(c, trim)
    elif kind == "hardleather":
        vest(c, folds(8, (170, 178, 182, 178, 168, 160, 156, 162)))
        c.line([(21, 22), (24, 21.25), (27, 22), (27, 27), (24, 28.5), (21, 27), (21, 22)], (200,), 2, TINTED)
        c.noise(6, 6)
    elif kind == "studded":
        vest(c, folds(12, (200, 206, 210, 206, 196, 190, 186, 190, 198, 202, 206, 204)))
        for u in range(16, 40, 2):
            for v in (22, 24.5, 27, 29.5):
                c.stud(u + (0.75 if int(v * 2) % 2 else 0.25), v)
        c.noise(6, 7)
        if trim:
            vest_trim(c, trim)
    elif kind == "snakeskin":
        vest(c, diamonds(8, 205, 140), sleeves=3)
        c.noise(5, 8)
    elif kind in ("robe", "gown"):
        robe_top(c)
        if kind == "gown":
            c.light(20, 20, 8, 1.5, 230)
        if trim:
            robe_top_trim(c, trim)
    elif kind == "mystic":
        robe_top(c)
        # the white mantle over the shoulders, and a light panel down the front
        c.light(16, 20, 24, 2.5, 238)
        c.light(*BODY_TOP, grey=238)
        c.light(40, 20, 16, 3, 238)
        c.light(*ARM_TOP, grey=238)
        c.light(22.5, 22.5, 3, 9.5, 225)
    elif kind == "builders":
        c.pattern(*ARM_STRIP, checks(), OWN)
        c.pattern(*ARM_TOP, checks(), OWN)
        c.pattern(*BODY_STRIP, checks(), OWN)
        c.pattern(*BODY_TOP, checks(), OWN)
        # the apron over it, dyed
        c.fill(20.5, 22, 7, 10, 200)
        c.fill(32.5, 22, 7, 10, 190)
        c.fill(21.5, 20, 1, 2, 160)
        c.fill(25.5, 20, 1, 2, 160)
        c.fill(22.5, 25, 3, 2, 170)
        c.clear(40, 26, 16, 6)
        c.noise(4, 11)
    elif kind == "graceful":
        c.pattern(*BODY_STRIP, folds(10, (232, 236, 238, 236, 228, 220, 214, 210, 216, 226)))
        c.fill(*BODY_TOP, 230)
        c.pattern(40, 20, 16, 6, folds(8, (230, 236, 230, 220, 210, 206, 212, 224)))
        c.fill(*ARM_TOP, 232)
        c.line([(20.5, 20.5), (24, 25), (27.5, 20.5)], (30, 30, 30), 2)
        c.line([(21, 31.5), (24, 27), (27, 31.5)], (170, 40, 40), 3)
        c.own(23.5, 24.75, 1, 1.5, (60, 160, 150))
        c.noise(3, 12)
    else:
        raise ValueError(name)
    c.edges([BODY_FRONT, BODY_BACK, (16, 20, 4, 12), (28, 20, 4, 12)], 0.85)
    return c


# --- boots ---------------------------------------------------------------------------------------------

def boots(name, plain):
    """Boots on the leg box of layer 1, from `top` down to the foot."""
    c = Canvas()
    if name == "plain":
        c.copy(plain, BOOTS_AREA)
        return c
    import armour_boots
    armour_boots.BOOTS[name](c)
    return c


# --- legs ----------------------------------------------------------------------------------------------

SIDES = ((16, 4), (20, 8), (28, 4), (32, 8))


# A plateskirt's length down the leg from the hip, in pixels: to the knee.
KNEE = 6.5


def hung(c, fn, waist=210, length=12):
    """A skirt or robe on the leg boxes, each leg one half of it, `length` pixels down from the hip and
    the rest of the leg clear; the shader flares them at the foot so the halves open in a V between
    the legs. The waist band sits on the body box."""
    c.pattern(0, 20, 16, length, fn)
    c.fill(0, 20, 16, 0.75, waist)
    c.fill(0, 20 + length - 0.5, 16, 0.5, 170)
    c.fill(16, 29.5, 24, 2.5, waist)
    c.fill(16, 29.25, 24, 0.25, 170)


def platelegs_trim(c, kind):
    band(c, 4.5, 23.5, 3, 2, kind)
    band(c, 16, 30.5, 24, 0.5, kind)


def plateskirt_trim(c, kind):
    band(c, 0, 21, 16, 0.75, kind)
    band(c, 16, 30, 24, 0.5, kind)
    for k in range(0, 16 * SCALE, 12):
        band(c, k / SCALE, 20 + KNEE - 1, 0.75, 1, kind)


def robe_trim(c, kind):
    band(c, 0, 31, 16, 1, kind)
    # down the inner edge of each leg's front: one seam down the middle
    band(c, 7.25, 21, 0.75, 10, kind)


def trousers(c, fn, belt=170):
    c.pattern(*LEG_STRIP, fn)
    c.fill(*LEG_TOP, 180)
    c.fill(*LEG_BOTTOM, 120)
    c.fill(16, 29.5, 24, 2.5, belt)
    c.fill(16, 31.5, 24, 0.5, 120)


def legs(name, plain):
    kind, _, trim = name.partition("_")
    c = Canvas()
    import armour_barrows
    if kind in armour_barrows.LEGGINGS:
        armour_barrows.LEGGINGS[kind](c)
        return c
    if kind in ("plain", "legs"):
        c.px = plain.px.copy()
        if trim:
            platelegs_trim(c, trim)
        return c
    if kind == "skirt":
        hung(c, lambda x, y: 196 if x % 8 == 0 else (int(228 - y / 26 * 22) + (6 if x % 8 == 1 else 0)), waist=214, length=KNEE)
        if trim:
            plateskirt_trim(c, trim)
    elif kind == "robe":
        hung(c, folds(12, (220, 222, 222, 220, 216, 212, 208, 206, 206, 208, 212, 216)), waist=214)
        if trim:
            robe_trim(c, trim)
    elif kind == "mystic":
        hung(c, folds(12, (220, 222, 222, 220, 216, 212, 208, 206, 206, 208, 212, 216)), waist=214)
        c.light(6, 21.5, 2, 10.5, 225)
        c.pattern(0, 31.25, 16, 0.75, lambda x, y: (245,) * 3 if (x + y) % 4 < 2 else None, OWN)
    elif kind == "chaps":
        trousers(c, folds(8, (196, 204, 208, 204, 194, 186, 182, 188)))
        c.shade(8, 20, 4, 12, 0.8)
        if trim:
            band(c, 0, 20, 16, 0.5, trim)
            band(c, 16, 29.5, 24, 0.5, trim)
    elif kind == "dhide":
        trousers(c, scales())
        if trim:
            band(c, 16, 29.5, 24, 0.5, trim)
            band(c, 4.5, 23.5, 3, 1, trim)
    elif kind == "studded":
        trousers(c, folds(8, (200, 206, 210, 206, 196, 190, 186, 190)))
        for u in range(0, 16, 2):
            for v in (21, 24, 27, 30):
                c.stud(u + 0.25, v)
        if trim:
            band(c, 16, 29.5, 24, 0.5, trim)
    elif kind == "snakeskin":
        trousers(c, diamonds(8, 205, 140))
    elif kind == "builders":
        trousers(c, folds(8, (205, 210, 214, 210, 200, 194, 190, 196)))
        c.fill(4.5, 25, 3, 2.5, 150)
        c.shade(4.5, 25, 3, 2.5, 0.9)
    elif kind == "graceful":
        trousers(c, folds(8, (230, 236, 232, 222, 212, 208, 214, 226)))
        c.line([(0.5, 21), (6, 27), (10, 31.5)], (170, 40, 40), 4, OWN)
        c.line([(8, 21), (12, 25)], (60, 160, 150), 3, OWN)
    else:
        raise ValueError(name)
    c.noise(2, 30)
    return c
