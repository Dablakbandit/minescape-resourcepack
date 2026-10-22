"""Boots as OSRS draws them, on the boots' leg boxes of layer 1 (armour_looks.py numbers them).

A boot fills each side of the leg box from `TOP` texels down (mid-shin) to the sole. Families that
share a shape and differ only by colour (metal, leather, mystic and the like) are greyscale for the
item's dye, details in their own colours on top; one-of-a-kind boots are painted in their colours.
"""
import numpy as np

from armour_art import TINTED, OWN, LIGHT, BONE, BONE_DARK
from armour_detail import LEG, LIMB_SIDES, faces

TOP = 26
H = 48
SOLE = 3


def shoe(c, colour, code=OWN, top=TOP, folds=5, seed=1, sole=(46, 40, 36), ragged=0):
    """The boot: one colour (or grey to dye), soft folds, lit from above, a dark sole; its top edge
    torn up to `ragged` texels deep."""
    def paint(f, side):
        f.clear(0, 0, f.w, f.h)
        f.alpha[top:] = True
        if ragged:
            cuts = np.random.default_rng(seed + len(side)).integers(0, ragged + 1, f.w)
            for x in range(f.w):
                f.alpha[top:top + cuts[x], x] = False
        f.base(colour if code == OWN else (colour,) * 3, 0.05, seed)
        if folds:
            f.folds(folds, 0.15)
        f.light(1.12, 0.85)
        f.rect(0, H - SOLE, f.w, H, sole if code == OWN else (60,) * 3)
    faces(c, LEG, LIMB_SIDES, paint, code)
    faces(c, LEG, ("bottom",), lambda f, n: f.base(sole if code == OWN else (60,) * 3), code)


def over(c, paint, sides=LIMB_SIDES, code=OWN):
    """Details on top of the boot: paint(face, side) sets the texels it draws."""
    def wrap(f, side):
        f.alpha[:] = False
        paint(f, side)
    faces(c, LEG, sides, wrap, code, overlay=True)


def rows(f, y0, y1, colour, shade=True):
    """A band across the face, rows y0..y1, lit at its top and shaded at its bottom."""
    f.alpha[y0:y1] = True
    c = np.array(colour, float)
    f.rgb[y0:y1] = c
    if shade and y1 - y0 > 1:
        f.rgb[y0] = c * 1.25
        f.rgb[y1 - 1] = c * 0.65


def block(f, x0, y0, x1, y1, colour):
    f.alpha[y0:y1, x0:x1] = True
    c = np.array(colour, float)
    f.rgb[y0:y1, x0:x1] = c
    f.rgb[y0, x0:x1] = c * 1.25
    f.rgb[y1 - 1, x0:x1] = c * 0.65


def triangle(f, x, y, w, h, colour, point="up"):
    """A spike or claw: `point` up, down, left or right, w by h texels from (x, y), lit on one side."""
    c, lit, dark = np.array(colour, float), np.array(colour, float) * 1.2, np.array(colour, float) * 0.6
    for k in range(h):
        frac = (k + 1) / h
        if point in ("up", "down"):
            span = max(1, int(round(w * frac)))
            yy = y + (k if point == "up" else h - 1 - k)
            x0 = x + (w - span) // 2
            for xx in range(x0, x0 + span):
                if 0 <= xx < f.w and 0 <= yy < f.h:
                    f.alpha[yy, xx] = True
                    f.rgb[yy, xx] = lit if xx == x0 else (dark if xx == x0 + span - 1 and span > 2 else c)
    if point in ("left", "right"):
        for k in range(w):
            frac = (k + 1) / w
            span = max(1, int(round(h * frac)))
            xx = x + (k if point == "left" else w - 1 - k)
            y0 = y + (h - span) // 2
            for yy in range(y0, y0 + span):
                if 0 <= xx < f.w and 0 <= yy < f.h:
                    f.alpha[yy, xx] = True
                    f.rgb[yy, xx] = lit if yy == y0 else (dark if yy == y0 + span - 1 and span > 2 else c)


def cuff(c, colour, height=5, code=OWN):
    over(c, lambda f, s: rows(f, TOP, TOP + height, colour), code=code)


def toe(c, colour, height=6, code=OWN):
    """A toe cap over the front of the foot."""
    over(c, lambda f, s: block(f, 1, H - SOLE - height, f.w - 1, H - SOLE, colour) if s == "front" else None, code=code)


def claws(c, colour, count=3, length=6):
    """Claws over the front of the foot, pointing down."""
    def paint(f, s):
        if s != "front":
            return
        step = f.w // count
        for i in range(count):
            triangle(f, i * step + 1, H - length, step - 1, length, colour, point="down")
    over(c, paint)


# --- the boots ---------------------------------------------------------------------------------------

def armour(c):
    """Metal boots: a brown leather cuff over a plated foot the dye colours (bronze to rune)."""
    def plates(f, side):
        f.clear(0, 0, f.w, f.h)
        f.alpha[TOP:] = True
        f.base((205,) * 3, 0.04, 121).light(1.15, 0.8)
        f.bevel(TOP + 6, TOP + 13, hi=1.3, lo=0.6)
        f.bevel(TOP + 13, H - SOLE, hi=1.25, lo=0.55)
        f.rect(0, H - SOLE, f.w, H, (70,) * 3)
    faces(c, LEG, LIMB_SIDES, plates, TINTED)
    faces(c, LEG, ("bottom",), lambda f, n: f.base((70,) * 3), TINTED)
    cuff(c, (112, 80, 46), 6)
    toe(c, (225,) * 3, 5, LIGHT)


def leather(c):
    """Leather boots (and the plain coloured ones): a folded-over cuff, the rest dyed."""
    shoe(c, 200, TINTED, seed=122)
    cuff(c, 228, 4, LIGHT)


def mystic(c):
    shoe(c, 205, TINTED, seed=123, folds=4)
    cuff(c, (36, 26, 58), 3)


def snakeskin(c):
    shoe(c, 190, TINTED, seed=125, folds=0)

    def scale(f, s):
        d = (np.abs((f.xx % 6) - 3) + np.abs((f.yy % 6) - 3)) < 3
        sel = d & (f.yy >= TOP + 5) & (f.yy < H - SOLE)
        f.alpha[sel] = True
        f.rgb[sel] = (220,) * 3
    over(c, scale, code=LIGHT)
    cuff(c, 225, 5, LIGHT)


def gardening(c):
    shoe(c, 180, TINTED, top=TOP - 4, seed=124, folds=0)

    def shine(f, s):
        f.alpha[TOP - 2:H - SOLE - 1, 3:5] = True
        f.rgb[TOP - 2:H - SOLE - 1, 3:5] = (240,) * 3
    over(c, shine, code=LIGHT)


def builders(c):
    shoe(c, 185, TINTED, seed=126)
    cuff(c, (70, 46, 26), 3)

    def laces(f, s):
        if s == "front":
            for y in range(TOP + 4, H - SOLE - 3, 3):
                f.alpha[y, 4:12] = True
                f.rgb[y, 4:12] = (232, 190, 40)
    over(c, laces)


def graceful(c):
    shoe(c, 230, TINTED, seed=127, folds=4)

    def wing(f, s):
        if s == "outer":
            for j, row in enumerate(["w.......", "ww......", "www.....", "wwww....", ".wwwww..", "..wwwww.", "...wwwww"]):
                for i, ch in enumerate(row):
                    if ch == "w":
                        f.alpha[TOP + 1 + j, 6 + i] = True
                        f.rgb[TOP + 1 + j, 6 + i] = (250, 248, 240) if j % 2 == 0 else (200, 196, 210)
    over(c, wing)


def lightness(c):
    shoe(c, 215, TINTED, seed=128, folds=4)
    cuff(c, 235, 3, LIGHT)


def fighting(c):
    shoe(c, (124, 92, 56), seed=131)
    cuff(c, (82, 58, 34), 4)
    over(c, lambda f, s: rows(f, TOP + 6, TOP + 8, (160, 30, 24)))

    def spike(f, s):
        if s == "outer":
            triangle(f, 1, H - SOLE - 6, 9, 5, BONE, point="right")
        if s == "front":
            triangle(f, 5, H - SOLE - 7, 6, 6, BONE, point="up")
    over(c, spike)


def fancy(c):
    shoe(c, (60, 160, 240), seed=132, folds=0)
    over(c, lambda f, s: (rows(f, TOP, TOP + 6, (240, 222, 50)), rows(f, TOP + 6, TOP + 11, (240, 70, 180)),
                          rows(f, H - SOLE - 5, H - SOLE, (70, 220, 90))))


def ranger(c):
    shoe(c, (98, 150, 40), seed=133)
    cuff(c, (118, 172, 54), 4)


def rogue(c):
    shoe(c, (54, 56, 46), seed=134)
    cuff(c, (128, 112, 82), 5)


def spiked(c):
    shoe(c, (132, 128, 126), seed=135)
    claws(c, BONE, 3, 7)

    def side_claws(f, s):
        if s == "outer":
            triangle(f, 2, H - 7, 4, 7, BONE, point="down")
    over(c, side_claws)


def climbing(c, gilded=False):
    shoe(c, (124, 122, 122), seed=136)
    cuff(c, (96, 94, 94) if not gilded else (236, 184, 34), 4)
    if gilded:
        def straps(f, s):
            for y in (TOP + 8, TOP + 12):
                f.alpha[y:y + 1, 2:f.w - 2] = True
                f.rgb[y:y + 1, 2:f.w - 2] = (236, 184, 34)
        over(c, straps)
    claws(c, (200, 200, 200), 4, 3)


def decorative(upper):
    def paint(c):
        lower = {"gold": (40, 42, 92), "red": (30, 40, 170), "white": (110, 110, 210)}[upper]
        top_colour = {"gold": (204, 192, 60), "red": (184, 24, 24), "white": (210, 210, 220)}[upper]
        shoe(c, lower, seed=137)
        over(c, lambda f, s: rows(f, TOP, TOP + 10, top_colour))
    return paint


def holy_sandals(c):
    shoe(c, (34, 40, 76), seed=138)

    def straps(f, s):
        for y in (TOP + 2, TOP + 7, TOP + 12):
            f.alpha[y:y + 2] = True
            f.rgb[y:y + 2] = (236, 236, 240)
        if s == "front":
            for j, row in enumerate(["..y..", ".yyy.", "yyyyy", ".yyy.", "..y.."]):
                for i, ch in enumerate(row):
                    if ch == "y":
                        f.alpha[TOP + 15 + j, 5 + i] = True
                        f.rgb[TOP + 15 + j, 5 + i] = (240, 210, 60)
    over(c, straps)


def insulated(c):
    shoe(c, (30, 30, 32), seed=139)
    cuff(c, (226, 226, 40), 5)


def mime(c):
    shoe(c, (28, 28, 30), seed=140)
    cuff(c, (60, 60, 64), 3)


def skeleton(c):
    shoe(c, (26, 26, 28), seed=141, folds=0)

    def bones(f, s):
        for y in range(TOP + 3, H - SOLE - 2, 4):
            f.alpha[y:y + 2, 2:f.w - 2] = True
            f.rgb[y:y + 2, 2:f.w - 2] = (236, 232, 222)
            f.rgb[y + 1, 2:f.w - 2] = (180, 176, 166)
    over(c, bones)


def zombie(c):
    shoe(c, (118, 118, 116), seed=142, ragged=5)
    claws(c, (90, 90, 88), 2, 4)


def bark(colour, tip):
    def paint(c):
        shoe(c, colour, seed=144)
        cuff(c, tuple(int(v * 0.7) for v in colour), 4)
        toe(c, tip, 7)
        over(c, lambda f, s: rows(f, TOP + 10, TOP + 11, tuple(int(v * 0.6) for v in colour), False))
    return paint


def zealots(c):
    shoe(c, (152, 140, 42), seed=145)
    cuff(c, (74, 64, 30), 5)
    over(c, lambda f, s: rows(f, TOP + 5, TOP + 7, (200, 190, 120)))


def wizard(c):
    shoe(c, (28, 112, 192), seed=146)
    cuff(c, (40, 128, 210), 3)


def stone(c):
    shoe(c, (46, 46, 62), seed=147, folds=0)

    def facets(f, s):
        sel = ((f.xx // 4 + f.yy // 5) % 3 == 0) & (f.yy >= TOP) & (f.yy < H - SOLE)
        f.alpha[sel] = True
        f.rgb[sel] = (78, 78, 98)
    over(c, facets)


def santa(c):
    shoe(c, (128, 108, 40), seed=148)
    cuff(c, (244, 242, 232), 7)


def chicken(c):
    shoe(c, (242, 188, 40), seed=149, folds=0, sole=(220, 150, 30))
    claws(c, (246, 246, 240), 3, 8)


BOOTS = {
    "armour": armour, "leather": leather, "mystic": mystic, "snakeskin": snakeskin, "gardening": gardening,
    "builders": builders, "graceful": graceful, "lightness": lightness,
    "fighting": fighting, "fancy": fancy, "ranger": ranger, "rogue": rogue, "spiked": spiked,
    "climbing": climbing, "climbing_gilded": lambda c: climbing(c, True),
    "decorative_gold": decorative("gold"), "decorative_red": decorative("red"), "decorative_white": decorative("white"),
    "holy_sandals": holy_sandals, "insulated": insulated, "mime": mime, "skeleton": skeleton, "zombie": zombie,
    "splitbark": bark((112, 84, 50), (184, 152, 112)), "swampbark": bark((62, 60, 32), (120, 152, 60)),
    "bloodbark": bark((92, 46, 40), (170, 40, 40)), "zealots": zealots, "wizard": wizard, "stone": stone,
    "santa": santa, "chicken": chicken,
}
