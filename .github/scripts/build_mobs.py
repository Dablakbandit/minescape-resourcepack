"""Animated mobs: mobs/animated.json's Blockbench models baked into item models whose texture carries their
animations, for the mobs stitch (assets/minescape/stitches/mobs.*) to play.

    python .github/scripts/build_mobs.py     in CI, before count_icons.py, which adds each to leather horse
                                             armour's overrides by its custom model data

A mob is an item on an armour stand's head. Its model's cubes become one item model (Java has no bones), shrunk
into -16 to 32 and grown back by its head display; every face gets its own copy of its texels, from whichever of the
model's textures it reads, in one S x S sprite (256, 512 or 1024; the atlas may put it anywhere):

  from the top          the faces, packed edge to edge, each at least 4 x 4 texels; the 2 x 2 block in from each of a
                        face's corners carries in the low 3 bits of its red, green and blue (9 bits a texel: the corner
                        texel's lowest, then the one beside it, the one under or over it, the one across) the face's
                        number (12 bits), the sprite's size (2: 256, 512, 1024) and that corner texel's own place in
                        the sprite (10 bits across, 10 down), so one vertex finds the sprite from its own uv
  the bottom row        header: magic at x 0 and x S - 1, then where the clips and keyframes start, the bone count, the
                        head display's scale (in 4096ths)
  up from the header    records, row-major from the row above it: faces (20 texels), clips (2), keyframes (5 a bone
                        a frame), alpha 254

A face record: bone and whether its corners wind against its outward normal; its uv rect in the sprite (u0 v0 u1 v1);
where the model rests at each rect corner (min-min, max-min, max-max, min-max); where 26.3's tilted model draws each. A keyframe: the bone's model-space transform there, a rotation (quaternion), an offset
and a uniform scale: posed = scale * rotate(q, rest) + offset. A clip: its first frame, its frames, how it ends
(0 hold the last frame, 1 loop, 2 back to rest) and how many ticks the clip before it fades into it over. A looping
clip plays on the game's clock (its phase the game time mod its length), any other from the tick the dye says.

Each animation is sampled once a game tick as Blockbench poses it: a bone turns about its pivot by its rest rotation
plus the keyframe's (Z then Y then X, right-handed), moves by the keyframe's position and scales by its scale,
inside its parent; Blockbench 5.2.2's own poses of the mithril dragon match these to 0.001 units. A face hidden
inside another cube of its own bone is left out, with its texels (the two never move apart).

Every face's uv is inset an eighth of a texel from its edges (INSET), which nothing else in the atlas has: the side of
its texel a vertex's uv sits says which corner of its face it is, and that it is a mob's.

How a model is turned where it is drawn: where the stitch can share a quad's corners (subgroup shuffles), from two of
its face's edges. 26.3 can't (its OpenGL backend turns shaders back into GLSL 330, which takes no shuffles), so from
26.3 on (TILTED_OVERLAY) every model is drawn with each cube tilted by TILT, and a vertex takes the turn from its face's
normal, which Minecraft snaps to the nearest axis and the tilt keeps level, and the world's up, at the head display's
scale; the stitch then puts it where the untilted model, posed, has it. That holds for a mob as MineScape stands one: an
upright, full-size armour stand turned only about the vertical.

Each model is checked first (check()) against what the conversion and old Minecraft versions can take, every
problem listed by cube, bone and animation name, and the build stops on any.

A prop ("origin": true, such as a skillcape emote's) keeps its model's origin over the stand instead of its middle, and
is drawn a block a 16 of its units (it takes no scale): it reaches at most 60 units from its origin and stands at most
117 tall.

A mob may take its model's textures from other PNGs ("textures": {"<texture name in the model>": "<png in
mobs/textures/>"}), so one model and its animations can be several mobs in different colours.

Written (git-ignored): assets/ms/textures/item/mobs/<name>.png, assets/ms/models/mobs/animated/<name>.json and the
tilted copy in mobs_26_3/ (an overlay build_shaders.py lists in pack.mcmeta), and
run/mobs.json, which the release publishes for the plugin: each mob's custom model data, its clips (id and ticks
played) and a hitbox fitted to the model, in blocks about the stand's feet.
"""
import base64
import io
import json
import math
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFINITIONS = os.path.join(ROOT, "mobs", "animated.json")
SOURCES = os.path.join(ROOT, "mobs", "models")
RECOLOURS = os.path.join(ROOT, "mobs", "textures")
PUBLISHED = os.path.join(ROOT, "run", "mobs.json")
TEXTURES = os.path.join(ROOT, "assets", "ms", "textures", "item", "mobs")
MODELS = os.path.join(ROOT, "assets", "ms", "models", "mobs", "animated")
FIRST_NUMBER = 100001

MARK = 254
MAGIC = (0x4D, 0x42, 0x33)
FACE_TEXELS = 20
KEY_TEXELS = 5
HOLD, LOOP, ONCE = 0, 1, 2
SIZES = (256, 512, 1024)
END = {"loop": LOOP, "hold": HOLD, "once": ONCE}
BLEND = 4
# where a mob's feet are under an armour stand's head: a model point at y g shows at the head's
# translation + scale * (g - 8) units, which is this for the ground
GROUND = -38.8
# an armour stand draws its head item at 0.625 of a block per 16 units, times the head display's scale
HEAD_ITEM = 0.625 / 16
# how far in from a face's edges its uv sits, in texels: a mob's mark (see the top)
INSET = 0.125
# the cube angles every Minecraft version takes (from 1.21.6 any angle, but not before)
CUBE_ANGLES = (-45.0, -22.5, 0.0, 22.5, 45.0)
MAX_FRAMES = 255
# a face's texels are at least this many across and down, so the 2 x 2 blocks at its four corners never overlap
MIN_FACE = 4
# 26.3 draws a mob's model with every cube turned by this (x y z degrees, as Minecraft applies them: z, then y, then
# x): each of its axes 54.7 degrees from upright and 15 degrees round from the diagonals, so every face's normal, which
# Minecraft snaps to the nearest axis, snaps to a level one (by 0.13 at least) and a vertex's normal tells how the
# model is turned; the mobs stitch puts every vertex back where the untilted model has it
TILT = (-26.5650, 24.0956, 39.2316)
TILTED_OVERLAY = "mobs_26_3"
TILTED = os.path.join(ROOT, TILTED_OVERLAY, "assets", "ms", "models", "mobs", "animated")
# the overlays this writes, for build_shaders.py to list: directory, first pack format, last (None: the newest)
OVERLAYS = [(TILTED_OVERLAY, 97, None)]
MAX_CLIPS = 30


class ModelError(Exception):
    """A model the conversion can't take: every problem found, one a line."""


def definitions():
    with open(DEFINITIONS, encoding="utf-8") as f:
        mobs = json.load(f)["mobs"]
    numbers = [m["custom_model_data"] for m in mobs]
    assert len(set(numbers)) == len(numbers), "two mobs with one custom model data"
    assert all(n >= FIRST_NUMBER for n in numbers), "a mob's custom model data is from %d, above the items'" % FIRST_NUMBER
    return mobs


def overrides():
    """Each mob's model by its custom model data, for count_icons.py."""
    return {m["custom_model_data"]: "ms:mobs/animated/" + m["name"] for m in definitions()}


# ---- the sprite ----------------------------------------------------------------------------------------------

def quaternion(m):
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        q = ((m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s)
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = (0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s)
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = ((m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s)
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = ((m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s)
    q = np.array(q)
    return q / np.linalg.norm(q) * (1 if q[3] >= 0 else -1)


def split(m):
    """A 3x3 rotation times a uniform scale, as (rotation, scale)."""
    s = float(np.cbrt(abs(np.linalg.det(m))))
    return m / s, s


class Sprite:
    def __init__(self, size, bones):
        self.size = size
        self.img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        self.faces = []    # (bone, (u0, v0, u1, v1), corners at min-min, max-min, max-max, min-max)
        self.clips = []    # (first, frames, end, blend)
        self.keys = []     # per frame: per bone (3x3 rotation*scale, offset)
        self.bones = bones
        self.bottom = 0    # the lowest row a face uses, which the records must stay under
        self.display_scale = 1.0

    def visible(self, x, y, rgba):
        self.img.putpixel((x, y), rgba)
        self.bottom = max(self.bottom, y + 1)

    def face(self, bone, rect, corners, tilted, flip):
        """A face whose texels are already in place. The 2 x 2 block of texels in from each of its corners carries, in
        the low 3 bits of red, green and blue (9 bits a texel: the corner's own lowest, then the one beside it, the one
        under or over it, the one across), its number (12 bits), the sprite's size (2) and that corner texel's own
        place in the sprite (10 across, 10 down): one vertex finds the sprite from its own uv, wherever the atlas put
        it. tilted: its corners as 26.3's tilted model has them; flip: its corners wind against its outward normal."""
        index = len(self.faces)
        assert index < 4096, "a sprite's faces are numbered in 12 bits"
        u0, v0, u1, v1 = rect
        assert u1 - u0 >= MIN_FACE and v1 - v0 >= MIN_FACE, "a face's corner blocks would overlap"
        code = SIZES.index(self.size)
        for (x, y), (dx, dy) in (((u0, v0), (1, 1)), ((u1 - 1, v0), (-1, 1)), ((u1 - 1, v1 - 1), (-1, -1)), ((u0, v1 - 1), (1, -1))):
            word = index | code << 12 | x << 14 | y << 24
            for k, (ox, oy) in enumerate(((0, 0), (dx, 0), (0, dy), (dx, dy))):
                r, g, b, a = self.img.getpixel((x + ox, y + oy))
                bits = (word >> (9 * k)) & 511
                # opaque, to carry the number (a clear texel of the model's own is drawn as black)
                self.img.putpixel((x + ox, y + oy), ((r & ~7) | (bits & 7), (g & ~7) | ((bits >> 3) & 7), (b & ~7) | (bits >> 6), 255))
        self.faces.append((bone, rect, corners, tilted, flip))
        return index

    def clip(self, frames, end, blend=BLEND):
        """A clip of frames (each a list of per-bone (matrix, offset)), ending as end says, faded into from the
        clip before it over blend ticks; its id, from 1 (30 at most: the dye has 5 bits, and 31 is no clip)."""
        first = len(self.keys)
        self.keys.extend(frames)
        self.clips.append((first, len(frames), end, blend))
        assert len(self.clips) <= 30
        return len(self.clips)

    def _put(self, i, rgb):
        y = self.size - 2 - i // self.size
        assert y >= self.bottom, "the records reach the faces"
        self.img.putpixel((i % self.size, y), (*rgb, MARK))

    @staticmethod
    def _position(v):
        e = int(round((v + 32) * 512))
        assert 0 <= e < 65536, v
        return e

    def write(self):
        put = self._put
        k = 0
        for bone, (u0, v0, u1, v1), corners, tilted, flip in self.faces:
            put(k, (bone, 1 if flip else 0, 0))
            put(k + 1, (u0 >> 8, u0 & 255, v0 >> 8))
            put(k + 2, (v0 & 255, u1 >> 8, u1 & 255))
            put(k + 3, (v1 >> 8, v1 & 255, 0))
            for i, c in enumerate(corners):
                x, y, z = (self._position(a) for a in c)
                put(k + 4 + 2 * i, (x >> 8, x & 255, y >> 8))
                put(k + 5 + 2 * i, (y & 255, z >> 8, z & 255))
            for i, c in enumerate(tilted):
                x, y, z = (self._position(a) for a in c)
                put(k + 12 + 2 * i, (x >> 8, x & 255, y >> 8))
                put(k + 13 + 2 * i, (y & 255, z >> 8, z & 255))
            k += FACE_TEXELS
        clips_at = k
        for c, (first, frames, end, blend) in enumerate(self.clips):
            assert frames < 256 and first < 65536
            put(clips_at + 2 * (c + 1), (first >> 8, first & 255, frames))
            put(clips_at + 2 * (c + 1) + 1, (end, blend, 0))
        keys_at = clips_at + 2 * (len(self.clips) + 1)
        for fi, frame in enumerate(self.keys):
            for bi, (m, t) in enumerate(frame):
                r, s = split(m)
                q = quaternion(r)
                qe = [int(round((c + 1) / 2 * 4095)) for c in q]
                te = [int(round((c + 64) * 512)) for c in t]
                assert all(0 <= v < 65536 for v in te), t
                se = int(round(s * 16384))
                at = keys_at + (fi * self.bones + bi) * KEY_TEXELS
                put(at, (qe[0] >> 4, ((qe[0] & 15) << 4) | (qe[1] >> 8), qe[1] & 255))
                put(at + 1, (qe[2] >> 4, ((qe[2] & 15) << 4) | (qe[3] >> 8), qe[3] & 255))
                put(at + 2, (te[0] >> 8, te[0] & 255, te[1] >> 8))
                put(at + 3, (te[1] & 255, te[2] >> 8, te[2] & 255))
                put(at + 4, (se >> 8, se & 255, 0))
        h = self.size - 1
        self.img.putpixel((0, h), (*MAGIC, MARK))
        self.img.putpixel((1, h), (clips_at >> 16, (clips_at >> 8) & 255, clips_at & 255, MARK))
        self.img.putpixel((2, h), (keys_at >> 16, (keys_at >> 8) & 255, keys_at & 255, MARK))
        self.img.putpixel((3, h), (self.bones, 0, 0, MARK))
        # the head display's scale (in 4096ths), for a vertex that can't measure its face as drawn
        se = int(round(self.display_scale * 4096))
        self.img.putpixel((4, h), (se >> 16, (se >> 8) & 255, se & 255, MARK))
        self.img.putpixel((self.size - 1, h), (*MAGIC, MARK))
        return self.img

    @staticmethod
    def records_needed(faces, frames, bones, clips):
        return faces * FACE_TEXELS + 2 * (clips + 1) + frames * bones * KEY_TEXELS


def face_corners(face, f, t):
    """Minecraft's face corners in FaceInfo's vertex order (top left, bottom left, bottom right, top right, as
    seen from outside the face), which uv corners 0 (u0 v0), 1 (u0 v1), 2 (u1 v1), 3 (u1 v0) land on, turned by
    the face's rotation."""
    x0, y0, z0 = f
    x1, y1, z1 = t
    tl, tr, br, bl = {
        "north": [(x1, y1, z0), (x0, y1, z0), (x0, y0, z0), (x1, y0, z0)],
        "south": [(x0, y1, z1), (x1, y1, z1), (x1, y0, z1), (x0, y0, z1)],
        "east": [(x1, y1, z1), (x1, y1, z0), (x1, y0, z0), (x1, y0, z1)],
        "west": [(x0, y1, z0), (x0, y1, z1), (x0, y0, z1), (x0, y0, z0)],
        "up": [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)],
        "down": [(x0, y0, z1), (x1, y0, z1), (x1, y0, z0), (x0, y0, z0)],
    }[face]
    return [tl, bl, br, tr]


def rect_corners(face, f, t, uv, rotation, transform=None):
    """Where the model rests at the face's uv rect corners (min-min, max-min, max-max, min-max), as Minecraft maps
    a face's uv (possibly flipped) and rotation onto its vertices; transform turns the cube's corners first."""
    verts = face_corners(face, f, t)
    if transform is not None:
        verts = [transform(np.array(v, float)) for v in verts]
    u0, v0, u1, v1 = uv
    uv_of = {0: (u0, v0), 1: (u0, v1), 2: (u1, v1), 3: (u1, v0)}
    at = {}
    for k in range(4):  # vertex k takes uv corner (k + rotation / 90) % 4
        at[uv_of[(k + rotation // 90) % 4]] = verts[k]
    lo_u, hi_u, lo_v, hi_v = min(u0, u1), max(u0, u1), min(v0, v1), max(v0, v1)
    return [tuple(at[(lo_u, lo_v)]), tuple(at[(hi_u, lo_v)]), tuple(at[(hi_u, hi_v)]), tuple(at[(lo_u, hi_v)])]


# ---- how the model shows as an item -----------------------------------------------------------------------------

# Each place an item is drawn, but on the stand's head: its turn (degrees, x y z as Minecraft applies them), how many
# pixels its whole model fits in, and where its middle goes (pixels). A screen's icon three-quarters on, as the old
# models' were; side on in an item frame.
DISPLAYS = {
    "gui": ([30, 45, 0], 15.0, [0, 0, 0]),
    "fixed": ([0, 90, 0], 14.0, [0, 0, 0]),
    "ground": ([0, 0, 0], 8.0, [0, 4, 0]),
    "thirdperson_righthand": ([0, 90, 0], 9.0, [0, 3, 1]),
    "thirdperson_lefthand": ([0, 90, 0], 9.0, [0, 3, 1]),
    "firstperson_righthand": ([0, 90, 0], 10.0, [1, 3, 0]),
    "firstperson_lefthand": ([0, 90, 0], 10.0, [1, 3, 0]),
}


def turn_xyz(deg):
    """Minecraft's display rotation: x, then y, then z, about the item's middle (JOML's rotationXYZ)."""
    x, y, z = (math.radians(a) for a in deg)
    rx = np.array([[1, 0, 0], [0, math.cos(x), -math.sin(x)], [0, math.sin(x), math.cos(x)]])
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rz = np.array([[math.cos(z), -math.sin(z), 0], [math.sin(z), math.cos(z), 0], [0, 0, 1]])
    return rx @ ry @ rz


def fitted(lo, hi, rotation, size, middle):
    """A display that turns the model as asked and fits its box, as seen face on, in size pixels, centred on
    middle: a point p of the model shows at translation + turn * scale * (p - 8)."""
    r = turn_xyz(rotation)
    corners = np.array([[a, b, c] for a in (lo[0], hi[0]) for b in (lo[1], hi[1]) for c in (lo[2], hi[2])], float) - 8
    seen = corners @ r.T
    extent = max(np.ptp(seen[:, 0]), np.ptp(seen[:, 1]))
    scale = min(4.0, size / extent)
    centre = (seen.min(axis=0) + seen.max(axis=0)) / 2 * scale
    translation = [max(-80.0, min(80.0, round(float(m - c), 2))) for m, c in zip(middle, centre)]
    translation[2] = round(float(middle[2]), 2)
    return {"rotation": rotation, "translation": translation, "scale": [round(scale, 4)] * 3}


# ---- the Blockbench model --------------------------------------------------------------------------------------

def euler_zyx(deg):
    x, y, z = (math.radians(a) for a in deg)
    rx = np.array([[1, 0, 0], [0, math.cos(x), -math.sin(x)], [0, math.sin(x), math.cos(x)]])
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rz = np.array([[math.cos(z), -math.sin(z), 0], [math.sin(z), math.cos(z), 0], [0, 0, 1]])
    return rz @ ry @ rx


TILT_M = None


def affine(m, t):
    a = np.eye(4)
    a[:3, :3] = m
    a[:3, 3] = t
    return a


def number(v):
    return float(str(v).strip()) if str(v).strip() else 0.0


def sample(keyframes, channel, t, default):
    keys = sorted((k for k in keyframes if k["channel"] == channel), key=lambda k: float(k["time"]))
    if not keys:
        return default
    vals = [(float(k["time"]), np.array([number(k["data_points"][0][a]) for a in "xyz"])) for k in keys]
    if t <= vals[0][0]:
        return vals[0][1]
    for (t0, v0), (t1, v1) in zip(vals, vals[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * ((t - t0) / (t1 - t0) if t1 > t0 else 1.0)
    return vals[-1][1]


def texture_image(texture, mob):
    """A texture's pixels: the mob's own PNG for it if it swaps it (mobs/textures/), else saved inside the .bbmodel
    (Blockbench's default), else a PNG of the texture's name beside it in mobs/models/."""
    name = os.path.basename(texture.get("name") or "")
    if not name.lower().endswith(".png"):
        name += ".png"
    swaps = mob.get("textures", {})
    swap = swaps.get(name, swaps.get(name[:-4]))
    if swap is not None:
        path = os.path.join(RECOLOURS, swap)
        if not os.path.exists(path):
            raise ModelError("%s: swaps %s for %s, which isn't in mobs/textures/" % (mob["name"], name, swap))
        return Image.open(path).convert("RGBA")
    source = texture.get("source") or ""
    if source.startswith("data:") and "," in source:
        return Image.open(io.BytesIO(base64.b64decode(source.split(",", 1)[1]))).convert("RGBA")
    path = os.path.join(SOURCES, name)
    if not os.path.exists(path):
        raise ModelError("%s: texture %s isn't saved in the model, and there's no %s beside it in mobs/models/" % (mob["name"], name, name))
    return Image.open(path).convert("RGBA")


def check(d, mob):
    """What in the model the conversion, or an older Minecraft, can't take (errors), and what it plays other than as
    drawn in Blockbench (warnings)."""
    errors, warnings = [], []
    elements = {e["uuid"]: e for e in d.get("elements", [])}
    owner, bones = {}, [0]
    names = {g["uuid"]: g.get("name") or g["uuid"] for g in d.get("groups", [])}

    def walk(nodes, bone):
        for n in nodes:
            uid = n if isinstance(n, str) else n.get("uuid")
            if uid in elements:
                owner[uid] = bone
                continue
            bones[0] += 1
            walk(n.get("children", []) if isinstance(n, dict) else [], names.get(uid, uid))
    walk(d.get("outliner", []), None)

    def cube(e):
        # cubes are often all called "cube": its bone and where it starts say which
        return "cube %s%s at %s" % (e.get("name"), " in bone %s" % owner[e["uuid"]] if owner.get(e["uuid"]) else "",
                                    "/".join("%g" % c for c in e.get("from", [])))
    for e in elements.values():
        turned = [(axis, a) for axis, a in zip("xyz", e.get("rotation", [0, 0, 0])) if abs(a) > 1e-6]
        if len(turned) > 1:
            errors.append("%s is rotated about %s; a cube may turn about one axis only" % (cube(e), " and ".join(t[0] for t in turned)))
        for axis, a in turned:
            if not any(abs(a - ok) < 1e-4 for ok in CUBE_ANGLES):
                errors.append("%s is rotated %g degrees about %s; use -45, -22.5, 22.5 or 45" % (cube(e), a, axis))
        if not owner.get(e["uuid"]):
            errors.append("%s isn't in a bone (group)" % cube(e))
    if bones[0] > 255:
        errors.append("%d bones; at most 255" % bones[0])
    for g in d.get("groups", []):
        if any(abs(a) > 1e-6 for a in g.get("rotation", [0, 0, 0])):
            warnings.append("bone %s has its own rest rotation, which shows only while an animation plays" % g.get("name"))
    animations = {a["name"]: a for a in d.get("animations", [])}
    if len(mob["clips"]) > MAX_CLIPS:
        errors.append("%d clips; at most %d" % (len(mob["clips"]), MAX_CLIPS))
    for clip in mob["clips"]:
        if clip not in animations:
            errors.append("mobs/animated.json plays %s, which the model has no animation called" % clip)
    for a in animations.values():
        if a["name"] not in mob["clips"]:
            continue
        if round(float(a.get("length", 0)) * 20) > MAX_FRAMES - 1:
            errors.append("animation %s is %.2f s long; at most %.2f s" % (a["name"], float(a["length"]), (MAX_FRAMES - 1) / 20))
        clip = mob["clips"][a["name"]]
        end = (clip.get("end") if isinstance(clip, dict) else None) or a.get("loop")
        if end != "loop" and round(float(a.get("length", 0)) * 20) >= 240:
            # a played clip's start is the game time mod 240 ticks: by 240 ticks in it would start again
            errors.append("animation %s is %.2f s long and doesn't loop; at most 11.95 s" % (a["name"], float(a["length"])))
        for an in a.get("animators", {}).values():
            if an.get("type") != "bone":
                if an.get("keyframes"):
                    warnings.append("animation %s has %s keyframes, which are left out" % (a["name"], an.get("type", "effect")))
                continue
            for k in an.get("keyframes", []):
                if k.get("channel") not in ("rotation", "position", "scale"):
                    continue
                where = "animation %s, bone %s, %s at %ss" % (a["name"], an.get("name"), k.get("channel"), k.get("time"))
                values = []
                for point in k.get("data_points", []):
                    for axis in "xyz":
                        v = point.get(axis, 0)
                        try:
                            values.append(number(v))
                        except ValueError:
                            errors.append("%s: %s is %r; keyframes must be plain numbers, not Molang" % (where, axis, v))
                if k.get("interpolation", "linear") != "linear":
                    warnings.append("%s is %s, which plays as linear" % (where, k.get("interpolation")))
                if k.get("channel") == "scale" and len(values) >= 3 and max(values[:3]) - min(values[:3]) > 1e-4:
                    warnings.append("%s scales %s unevenly; it plays as an even scale" % (where, "/".join("%g" % v for v in values[:3])))
    return errors, warnings


def clip_list(mob, animations):
    """The mob's clips in id order: (id, animation, end)."""
    out = []
    for name, c in mob["clips"].items():
        c = c if isinstance(c, dict) else {"id": c}
        assert name in animations, "%s: the model has no animation %s" % (mob["name"], name)
        end = c.get("end", animations[name]["loop"])
        out.append((c["id"], name, END[end]))
    out.sort()
    assert [c[0] for c in out] == list(range(1, len(out) + 1)), "%s: clip ids run from 1 with none missed" % mob["name"]
    return out


def build(mob):
    """The mob's texture and model, and what the plugin needs of it (for run/mobs.json)."""
    name = mob["name"]
    path = os.path.join(SOURCES, mob["model"])
    if not os.path.exists(path):
        raise ModelError("%s: no %s in mobs/models/" % (name, mob["model"]))
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    errors, warnings = check(d, mob)
    for w in warnings:
        print("  warning: %s: %s" % (name, w))
    if errors:
        raise ModelError("\n".join("%s: %s" % (name, e) for e in errors))
    groups = {g["uuid"]: g for g in d["groups"]}
    elements = {e["uuid"]: e for e in d["elements"]}
    animations = {a["name"]: a for a in d["animations"]}
    clips = clip_list(mob, animations)
    bones, parent, owner = [], {}, {}

    def walk(nodes, up):
        for n in nodes:
            uid = n if isinstance(n, str) else n["uuid"]
            if uid in elements:
                owner[uid] = up
                continue
            parent[uid] = up
            bones.append(uid)
            walk(n.get("children", []) if isinstance(n, dict) else [], uid)
    walk(d["outliner"], None)
    assert all(owner.get(u) is not None for u in elements), "%s: a cube outside every bone" % name
    assert len(bones) < 256
    index = {u: i for i, u in enumerate(bones)}

    # the cubes fitted into Java's -16 to 32, ground (y 0) kept level: a mob's middle over the stand, as big as it
    # fits; a prop's ("origin": true) own origin over the stand, which its display grows back to a block a 16 units
    lo = np.min([e["from"] for e in d["elements"]] + [e["to"] for e in d["elements"]], axis=0)
    hi = np.max([e["from"] for e in d["elements"]] + [e["to"] for e in d["elements"]], axis=0)
    anchored = bool(mob.get("origin", False))
    if anchored:
        reach = max(abs(float(v)) for v in (lo[0], hi[0], lo[2], hi[2]))
        f = min(24.0 / max(reach, 1e-6), 47.0 / float(hi[1] - lo[1]))
        shift = np.array([8.0, -15.5 - f * lo[1], 8.0])
    else:
        f = 47.0 / float(max(hi - lo))
        shift = np.array([8 - f * (lo[0] + hi[0]) / 2, -15.5 - f * lo[1], 8 - f * (lo[2] + hi[2]) / 2])
    A = affine(np.eye(3) * f, shift)
    A_inv = np.linalg.inv(A)

    def java(p):
        return f * np.array(p, float) + shift

    # the textures the faces read, loaded as a face first needs each: its pixels, and its pixels per uv unit
    images = {}

    def texture_of(ref):
        if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
            index = int(ref)
        else:
            index = next((i for i, t in enumerate(d["textures"]) if ref in (t.get("uuid"), t.get("id"))), None)
        if index is None or not 0 <= index < len(d["textures"]):
            raise ModelError("%s: a face reads a texture the model hasn't got" % name)
        if index not in images:
            texture = d["textures"][index]
            image = texture_image(texture, mob)
            images[index] = (image, image.width / texture.get("uv_width", image.width))
        return images[index]

    normals = {"north": (0, 0, -1), "south": (0, 0, 1), "east": (1, 0, 0), "west": (-1, 0, 0), "up": (0, 1, 0), "down": (0, -1, 0)}
    turns = {}
    for uid, e in elements.items():
        r = e.get("rotation", [0, 0, 0])
        turns[uid] = euler_zyx(r) if any(abs(a) > 1e-6 for a in r) else np.eye(3)

    def inside(p, other):
        e = elements[other]
        o = np.array(e["origin"], float)
        q = turns[other].T @ (p - o) + o
        return all(min(e["from"][i], e["to"][i]) - 1e-4 <= q[i] <= max(e["from"][i], e["to"][i]) + 1e-4 for i in range(3))

    def hidden(uid, face):
        e = elements[uid]
        others = [u for u in elements if u != uid and owner[u] == owner[uid]]
        if not others:
            return False
        o = np.array(e["origin"], float)
        corners = [turns[uid] @ (np.array(c, float) - o) + o for c in face_corners(face, e["from"], e["to"])]
        out = turns[uid] @ np.array(normals[face], float) * 0.02
        for a in np.linspace(0.02, 0.98, 7):
            for b in np.linspace(0.02, 0.98, 7):
                p = (corners[0] * (1 - a) + corners[3] * a) * (1 - b) + (corners[1] * (1 - a) + corners[2] * a) * b + out
                if not any(inside(p, other) for other in others):
                    return False
        return True

    faces, culled = [], 0
    for uid, e in elements.items():
        for face, fd in e["faces"].items():
            if fd.get("texture") is None or not fd.get("uv"):
                continue
            src, per = texture_of(fd["texture"])
            u0, v0, u1, v1 = (round(c * per) for c in fd["uv"])
            if u0 == u1 or v0 == v1:
                continue
            if hidden(uid, face):
                culled += 1
                continue
            faces.append((uid, face, fd, (u0, v0, u1, v1), src))

    # each face's own copy of its texels (at least 2 x 2, for its four corners to carry its number), edge to edge
    # on shelves, tallest first, in the smallest sprite they and the records fit
    sizes = [(max(MIN_FACE, abs(u1 - u0)), max(MIN_FACE, abs(v1 - v0))) for _, _, _, (u0, v0, u1, v1), _ in faces]
    lengths = {}
    for _, anim, end in clips:
        lengths[anim] = max(1, round(float(animations[anim]["length"]) * 20)) + (0 if end == LOOP else 1)
    records = Sprite.records_needed(len(faces), sum(lengths.values()), len(bones), len(clips))
    order = sorted(range(len(faces)), key=lambda i: -sizes[i][1])
    for size in SIZES:
        place, x, y, row = {}, 0, 0, 0
        for i in order:
            w, h = sizes[i]
            if x + w > size:
                x, y, row = 0, y + row, 0
            place[i] = (x, y)
            x += w
            row = max(row, h)
        if y + row + -(-records // size) + 1 <= size:
            break
    else:
        raise ModelError("%s: its %d faces' pixels and %d animation frames don't fit 1024 x 1024; use fewer or lower-resolution"
                         " faces, or shorter animations" % (name, len(faces), sum(lengths.values())))
    sprite = Sprite(size, len(bones))

    by_element = {}
    for i, (uid, face, fd, (u0, v0, u1, v1), src) in enumerate(faces):
        e = elements[uid]
        px, py = place[i]
        w, h = sizes[i]
        su, sv = min(u0, u1), min(v0, v1)
        sw, sh = abs(u1 - u0), abs(v1 - v0)
        for yy in range(h):
            for xx in range(w):
                sprite.visible(px + xx, py + yy, src.getpixel((su + xx * sw // w, sv + yy * sh // h)))
        # the same corners of the copy, flipped as the face was
        nu0, nu1 = (px, px + w) if u0 < u1 else (px + w, px)
        nv0, nv1 = (py, py + h) if v0 < v1 else (py + h, py)
        rotation = int(fd.get("rotation", 0)) % 360
        turn = None
        r = e.get("rotation", [0, 0, 0])
        if any(abs(a) > 1e-6 for a in r):
            origin = java(e["origin"])
            m = euler_zyx(r)
            turn = lambda p, m=m, o=origin: m @ (p - o) + o
        corners = rect_corners(face, java(e["from"]), java(e["to"]), (nu0, nv0, nu1, nv1), rotation, turn)
        middle = (java(e["from"]) + java(e["to"])) / 2
        tilted = rect_corners(face, java(e["from"]), java(e["to"]), (nu0, nv0, nu1, nv1), rotation,
                              lambda p, o=middle: TILT_M @ (p - o) + o)
        outward = (euler_zyx(r) if any(abs(a) > 1e-6 for a in r) else np.eye(3)) @ np.array(normals[face], float)
        c = [np.array(v) for v in corners]
        flip = float(np.cross(c[1] - c[0], c[3] - c[0]) @ outward) < 0
        sprite.face(index[owner[uid]], (px, py, px + w, py + h), corners, tilted, flip)
        s = 16 / size
        # each edge an eighth of a texel in, towards the face's middle: the mob's mark (INSET)
        iu0, iu1 = (nu0 + INSET, nu1 - INSET) if nu0 < nu1 else (nu0 - INSET, nu1 + INSET)
        iv0, iv1 = (nv0 + INSET, nv1 - INSET) if nv0 < nv1 else (nv0 - INSET, nv1 + INSET)
        out = {"uv": [round(c * s, 6) for c in (iu0, iv0, iu1, iv1)], "texture": "#skin", "tintindex": 0}
        if rotation:
            out["rotation"] = rotation
        by_element.setdefault(uid, {})[face] = out
    model_elements = []
    for uid, fs in by_element.items():
        e = elements[uid]
        el = {"from": [round(v, 4) for v in java(e["from"])], "to": [round(v, 4) for v in java(e["to"])], "faces": fs}
        r = e.get("rotation", [0, 0, 0])
        nz = [(a, v) for a, v in zip("xyz", r) if abs(v) > 1e-6]
        if nz:
            assert len(nz) == 1, "%s: a cube turned about two axes, which Java models can't" % name
            el["rotation"] = {"angle": nz[0][1], "axis": nz[0][0], "origin": [round(v, 4) for v in java(e["origin"])]}
        model_elements.append(el)

    # the clips, a frame a tick
    for cid, anim, end in clips:
        a = animations[anim]
        animators = {an.get("name"): an.get("keyframes", []) for an in a.get("animators", {}).values() if an.get("type") == "bone"}
        length = float(a["length"])
        frames = []
        for fi in range(lengths[anim]):
            t = min(fi / 20.0, length)
            world = {}
            for uid in bones:
                g = groups[uid]
                keys = animators.get(g["name"], [])
                rot = np.array(g.get("rotation", [0, 0, 0]), float) + sample(keys, "rotation", t, np.zeros(3))
                pos = sample(keys, "position", t, np.zeros(3))
                scl = sample(keys, "scale", t, np.ones(3))
                pivot = np.array(g["origin"], float)
                local = affine(np.eye(3), pivot + pos) @ affine(euler_zyx(rot) @ np.diag(scl), np.zeros(3)) @ affine(np.eye(3), -pivot)
                world[uid] = (world[parent[uid]] @ local) if parent[uid] else local
            frames.append([((A @ world[uid] @ A_inv)[:3, :3], (A @ world[uid] @ A_inv)[:3, 3]) for uid in bones])
            # a keyframe's offset is kept to within 64 Java units of where the bone rests (the sprite's encoding)
            for uid, (_, offset) in zip(bones, frames[-1]):
                if np.max(np.abs(offset)) >= 63.9:
                    raise ModelError("%s: animation %s at %.2f s takes bone %s %.0f units from where it rests; at most %.0f here"
                                     % (name, anim, t, groups[uid]["name"], np.max(np.abs(offset)) / f, 63.9 / f))
        assert sprite.clip(frames, end) == cid

    tilted_elements = []
    for el, uid in zip(model_elements, by_element):
        e = elements[uid]
        middle = (java(e["from"]) + java(e["to"])) / 2
        t = dict(el)
        t["rotation"] = {"origin": [round(float(v), 4) for v in middle], "x": TILT[0], "y": TILT[1], "z": TILT[2]}
        tilted_elements.append(t)
    box_lo = np.min([e["from"] for e in model_elements] + [e["to"] for e in model_elements], axis=0)
    box_hi = np.max([e["from"] for e in model_elements] + [e["to"] for e in model_elements], axis=0)
    ground = float(java([0, 0, 0])[1])
    if anchored:
        # sixteen of the model's units a block: f Java units each, HEAD_ITEM blocks a Java unit at display scale 1
        assert "scale" not in mob, "%s: a prop (origin) is drawn a block a 16 units; it takes no scale" % name
        scale = 1.0 / (f * HEAD_ITEM * 16)
        if scale > 4:
            raise ModelError("%s: reaches %.1f units from its origin and stands %.1f tall; a prop reaches at most %.0f and stands at most %.0f"
                             % (name, reach, float(hi[1] - lo[1]), 24 * 4 * HEAD_ITEM * 16, 47 * 4 * HEAD_ITEM * 16))
        scale = round(scale, 4)
    else:
        scale = float(mob.get("scale", 1))
    assert 0 < scale <= 4, "%s: a display scale is at most 4" % name
    sprite.display_scale = scale
    os.makedirs(TEXTURES, exist_ok=True)
    sprite.write().save(os.path.join(TEXTURES, name + ".png"))
    model = {"textures": {"skin": "ms:item/mobs/" + name, "particle": "ms:item/mobs/" + name},
             "elements": model_elements,
             # on the stand's head, facing its front (the model faces +z), feet on the ground; anywhere else fitted
             "display": dict({place: fitted(box_lo, box_hi, *d) for place, d in DISPLAYS.items()},
                             head={"rotation": [0, 180, 0], "translation": [0, round(GROUND - scale * (ground - 8), 2), 0],
                                   "scale": [scale] * 3})}
    os.makedirs(MODELS, exist_ok=True)
    with open(os.path.join(MODELS, name + ".json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(model, fh, separators=(",", ":"))
    os.makedirs(TILTED, exist_ok=True)
    with open(os.path.join(TILTED, name + ".json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(dict(model, elements=tilted_elements), fh, separators=(",", ":"))
    # a hitbox about the stand's feet, in blocks, which the plugin turns with the mob: the model's height, and most
    # of its width and length at rest (players click its body more than the tips of its wings and tail)
    block = HEAD_ITEM * scale
    half_x = 0.4 * (box_hi[0] - box_lo[0]) * block
    half_z = 0.4 * (box_hi[2] - box_lo[2]) * block
    height = (box_hi[1] - ground) * block
    hitbox = [round(float(v), 2) for v in (-half_x, 0, -half_z, half_x, height, half_z)]
    print("%s (%d): %d bones, %d faces (%d inside their own bone left out), %d x %d sprite, hitbox %s"
          % (name, mob["custom_model_data"], len(bones), len(faces), culled, size, size, hitbox))
    played = {}
    for cid, anim, end in clips:
        # how long it plays: a loop's frames, any other's last frame
        played[anim] = {"clip": cid, "ticks": lengths[anim] - (0 if end == LOOP else 1)}
        print("  clip %2d %-14s %3d ticks, %s" % (cid, anim, played[anim]["ticks"], {v: k for k, v in END.items()}[end]))
    return {"custom_model_data": mob["custom_model_data"], "clips": played, "hitbox": hitbox}


def main():
    global TILT_M
    TILT_M = euler_zyx(TILT)
    published, failed = {}, []
    for mob in definitions():
        try:
            published[mob["name"]] = build(mob)
        except ModelError as e:
            failed.append(str(e))
    if failed:
        raise SystemExit("These models can't be built:\n  " + "\n  ".join("\n".join(failed).split("\n")))
    os.makedirs(os.path.dirname(PUBLISHED), exist_ok=True)
    with open(PUBLISHED, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(published, fh, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
