"""The armour looks' texture conventions and a canvas over them, for build_armour.py. (The looks were
once painted here in code; they are the armour models' textures now, armour/models/.)

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

BONE, BONE_DARK = (228, 214, 170), (150, 132, 92)
STUD, STUD_DARK = (205, 205, 200), (110, 110, 108)


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
