"""Painting armour a face at a time, for the Barrows sets (armour_barrows.py) and boots
(armour_boots.py): in texels from a face's top left corner, through small material functions (plate,
chain, cloth, leather, each shaded by its bevels and folds) and details on top (rivets, straps,
frayed edges). Coordinates passed in are model pixels, as in armour_art.py.
"""
import numpy as np
from PIL import Image

from armour_art import SCALE, TINTED, OWN, LIGHT, BONE, BONE_DARK

# Faces as (u, v, width, height) in model pixels.
BODY = {"right": (16, 20, 4, 12), "front": (20, 20, 8, 12), "left": (28, 20, 4, 12), "back": (32, 20, 8, 12),
        "top": (20, 16, 8, 4), "bottom": (28, 16, 8, 4)}
ARM = {"outer": (40, 20, 4, 12), "front": (44, 20, 4, 12), "inner": (48, 20, 4, 12), "back": (52, 20, 4, 12),
       "top": (44, 16, 4, 4), "bottom": (48, 16, 4, 4)}
LEG = {"outer": (0, 20, 4, 12), "front": (4, 20, 4, 12), "inner": (8, 20, 4, 12), "back": (12, 20, 4, 12),
       "top": (4, 16, 4, 4), "bottom": (8, 16, 4, 4)}
SIDES = ("right", "front", "left", "back")
LIMB_SIDES = ("outer", "front", "inner", "back")


def texels(face):
    u, v, w, h = face
    return int(u * SCALE), int(v * SCALE), int(w * SCALE), int(h * SCALE)


def smooth_noise(w, h, cells, seed):
    """Soft blobs in 0..1, for rust and stains."""
    r = np.random.default_rng(seed)
    small = Image.fromarray((r.random((max(2, h // cells), max(2, w // cells))) * 255).astype(np.uint8))
    return np.array(small.resize((w, h), Image.BILINEAR), float) / 255


class Face:
    """A face being painted in full colour (or greyscale to dye), texel by texel."""

    def __init__(self, canvas, face, code=OWN, overlay=False):
        self.c, self.code, self.overlay = canvas, code, overlay
        self.x, self.y, self.w, self.h = texels(face)
        self.rgb = np.zeros((self.h, self.w, 3), float)
        self.alpha = np.ones((self.h, self.w), bool)
        self.yy, self.xx = np.mgrid[0:self.h, 0:self.w]

    def base(self, colour, grain=0.06, seed=0):
        r = np.random.default_rng(seed)
        self.rgb[:] = np.array(colour, float)
        self.rgb *= 1 + r.uniform(-grain, grain, (self.h, self.w))[..., None]
        return self

    def light(self, top=1.12, bottom=0.82):
        """Lit from above: brighter at the top of the face."""
        t = np.linspace(top, bottom, self.h)[:, None, None]
        self.rgb *= t
        return self

    def bevel(self, y0, y1, x0=0, x1=None, hi=1.3, lo=0.6, width=1):
        """A raised plate in rows y0..y1 (texels): a lit top and left edge, a shaded bottom and right."""
        x1 = self.w if x1 is None else x1
        region = self.rgb[y0:y1, x0:x1]
        region[:width] *= hi
        region[:, :width] *= (hi + 1) / 2
        region[-width:] *= lo
        region[:, -width:] *= (lo + 1) / 2
        return self

    def lames(self, height, hi=1.4, lo=0.45, y0=0, y1=None):
        """Overlapping plates down rows y0..y1, each `height` texels, each shadowed by the one above."""
        y1 = self.h if y1 is None else y1
        for y in range(y0, y1, height):
            self.bevel(y, min(y1, y + height), hi=hi, lo=lo)
            if y > y0:
                self.rgb[y + 1:y + 3] *= 0.72
        return self

    def chain(self, colour, cell=3):
        """Mail: rings lit on their upper rims."""
        row = self.yy // cell
        xx = (self.xx + (cell // 2) * (row % 2)) % cell
        yy = self.yy % cell
        ring = ((xx == 0) | (yy == 0))
        rim = (yy == 0) & (xx != 0)
        c = np.array(colour, float)
        self.rgb[:] = c * 0.45
        self.rgb[ring] = c * 1.0
        self.rgb[rim] = c * 1.35
        return self

    def folds(self, spacing, depth=0.25, phase=0):
        """Vertical cloth folds."""
        wave = 1 - depth * (0.5 + 0.5 * np.cos((self.xx + phase) / spacing * 2 * np.pi))
        self.rgb *= wave[..., None]
        return self

    def chevrons(self, colour, cell=8, width=2):
        xx = np.abs(((self.xx % cell) - cell / 2 + 0.5))
        band = ((self.yy - xx.astype(int)) % cell) < width
        self.rgb[band] = np.array(colour, float)
        edge = ((self.yy - xx.astype(int)) % cell) == width
        self.rgb[edge] *= 1.25
        return self

    def stain(self, colour, amount, cells=6, seed=1):
        """Rust, dirt or blood in soft blobs over `amount` of the face."""
        n = smooth_noise(self.w, self.h, cells, seed)
        mask = np.clip((n - (1 - amount)) / 0.15, 0, 1)[..., None]
        self.rgb = self.rgb * (1 - mask) + np.array(colour, float) * mask * (0.85 + 0.3 * n[..., None])
        return self

    def scratches(self, count, seed=2, hi=1.45):
        r = np.random.default_rng(seed)
        for _ in range(count):
            x, y = r.integers(0, self.w), r.integers(0, self.h)
            for k in range(r.integers(2, 5)):
                xx, yy = x + k, y + k // 2
                if 0 <= xx < self.w and 0 <= yy < self.h:
                    self.rgb[yy, xx] *= hi
        return self

    def rect(self, x0, y0, x1, y1, colour, shade=True):
        """A solid block in texels, lit at its top and shaded at its bottom."""
        c = np.array(colour, float)
        self.rgb[y0:y1, x0:x1] = c
        if shade and y1 - y0 > 1:
            self.rgb[y0:y0 + 1, x0:x1] = c * 1.3
            self.rgb[y1 - 1:y1, x0:x1] = c * 0.6
        return self

    def rivet(self, x, y, colour):
        c = np.array(colour, float)
        for dx, dy in ((1, 2), (2, 1), (2, 2)):
            if 0 <= x + dx < self.w and 0 <= y + dy < self.h:
                self.rgb[y + dy, x + dx] *= 0.55
        for dx, dy, f in ((0, 0, 1.6), (1, 0, 1.1), (0, 1, 1.0), (1, 1, 0.6)):
            if 0 <= x + dx < self.w and 0 <= y + dy < self.h:
                self.rgb[y + dy, x + dx] = c * f
        return self

    def rivets(self, y, colour, step=4, x0=1):
        for x in range(x0, self.w - 1, step):
            self.rivet(x, y, colour)
        return self

    def line(self, points, colour, width=1):
        c = np.array(colour, float)
        # its shadow first, a texel down
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            steps = int(max(abs(x1 - x0), abs(y1 - y0)) * 2) + 1
            for t in np.linspace(0, 1, steps):
                x, y = int(round(x0 + (x1 - x0) * t)), int(round(y0 + (y1 - y0) * t)) + width
                if 0 <= x < self.w and 0 <= y < self.h:
                    self.rgb[y, x] *= 0.6
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            steps = int(max(abs(x1 - x0), abs(y1 - y0)) * 2) + 1
            for t in np.linspace(0, 1, steps):
                x, y = int(round(x0 + (x1 - x0) * t)), int(round(y0 + (y1 - y0) * t))
                for k in range(width):
                    if 0 <= x < self.w and 0 <= y + k < self.h:
                        self.rgb[y + k, x] = c * (1.25 if k == 0 else 0.8)
        return self

    def sprite(self, x, y, rows, palette, shadow=True):
        """Pixel art, casting a shadow one texel down and right onto what is under it."""
        if shadow:
            for j, row in enumerate(rows):
                for i, ch in enumerate(row):
                    yy, xx = y + j + 1, x + i + 1
                    if ch != "." and 0 <= xx < self.w and 0 <= yy < self.h:
                        below = rows[j + 1][i + 1] if j + 1 < len(rows) and i + 1 < len(row) else "."
                        if below == ".":
                            self.rgb[yy, xx] *= 0.5
        for j, row in enumerate(rows):
            for i, ch in enumerate(row):
                if ch != "." and 0 <= x + i < self.w and 0 <= y + j < self.h:
                    self.rgb[y + j, x + i] = palette[ch]
        return self

    def fray(self, depth=4, seed=3, bottom=True):
        """A ragged edge: texels cut away up to `depth` from the bottom (or top)."""
        r = np.random.default_rng(seed)
        cuts = r.integers(0, depth + 1, self.w)
        for x in range(self.w):
            for k in range(cuts[x]):
                y = self.h - 1 - k if bottom else k
                self.alpha[y, x] = False
        return self

    def clear(self, x0, y0, x1, y1):
        self.alpha[y0:y1, x0:x1] = False
        return self

    def occlude(self, width=4, strength=0.3):
        """Soft shadow into each edge of the face, so a box reads as a solid."""
        d = np.minimum(np.minimum(self.xx, self.w - 1 - self.xx), np.minimum(self.yy, self.h - 1 - self.yy))
        self.rgb *= (1 - strength * np.clip(1 - d / width, 0, 1))[..., None]
        return self

    def done(self):
        if not self.overlay:
            self.occlude(4, 0.15)
        px = self.c.px[self.y:self.y + self.h, self.x:self.x + self.w]
        rgb = np.clip(self.rgb, 0, 255).astype(np.uint8)
        if self.code == TINTED:
            grey = rgb.mean(axis=2).astype(np.uint8)
            rgb = np.stack([grey] * 3, axis=2)
        if self.overlay:
            # only what was painted; the rest keeps what is under it
            px[self.alpha, :3] = rgb[self.alpha]
            px[self.alpha, 3] = self.code
            return
        px[..., :3] = np.where(self.alpha[..., None], rgb, 0)
        px[..., 3] = np.where(self.alpha, self.code, 0)


def faces(canvas, group, names, fn, code=OWN, overlay=False):
    """Paint each named face of a group with fn(face, name); an overlay only where it paints."""
    for name in names:
        f = Face(canvas, group[name], code, overlay)
        fn(f, name)
        f.done()
