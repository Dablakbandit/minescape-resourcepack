"""Animated mobs: mobs/animated.json's Blockbench models baked into item models whose texture carries their
animations, for the mobs stitch (assets/minescape/stitches/mobs.*) to play.

    python .github/scripts/build_mobs.py     in CI, before count_icons.py, which adds each to leather horse
                                             armour's overrides by its custom model data

A mob is an item on an armour stand's head. Its model's cubes become one item model (Java has no bones), shrunk
into -16 to 32 and grown back by its head display; every face gets its own copy of its texels in one S x S sprite
(256, 512 or 1024; the atlas may put it anywhere):

  from the top          the faces, packed edge to edge; each carries in the low 3 bits of the red, green and blue
                        of its four corner texels (top left, top right, bottom right, bottom left; 9 bits each, the
                        first corner's lowest) its number (12 bits), the sprite's size (2: 256, 512, 1024) and its
                        own top left in the sprite (10 bits across, 10 down), which a vertex reads from its quad's
                        corners to find the sprite
  the bottom row        header: magic at x 0 and x S - 1, then where the clips and keyframes start, the bone count
  up from the header    records, row-major from the row above it: faces (12 texels), clips (2), keyframes (5 a bone
                        a frame), alpha 254

A face record: bone; its uv rect in the sprite (u0 v0 u1 v1); where the model rests at each rect corner (min-min,
max-min, max-max, min-max). A keyframe: the bone's model-space transform there, a rotation (quaternion), an offset
and a uniform scale: posed = scale * rotate(q, rest) + offset. A clip: its first frame, its frames, how it ends
(0 hold the last frame, 1 loop, 2 back to rest) and how many ticks the clip before it fades into it over. A looping
clip plays on the game's clock (its phase the game time mod its length), any other from the tick the dye says.

Each animation is sampled once a game tick as Blockbench poses it: a bone turns about its pivot by its rest rotation
plus the keyframe's (Z then Y then X, right-handed), moves by the keyframe's position and scales by its scale,
inside its parent; Blockbench 5.2.2's own poses of the mithril dragon match these to 0.001 units. A face hidden
inside another cube of its own bone is left out, with its texels (the two never move apart).

Written (git-ignored): assets/ms/textures/item/mobs/<name>.png, assets/ms/models/mobs/animated/<name>.json
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
TEXTURES = os.path.join(ROOT, "assets", "ms", "textures", "item", "mobs")
MODELS = os.path.join(ROOT, "assets", "ms", "models", "mobs", "animated")
FIRST_NUMBER = 100001

MARK = 254
MAGIC = (0x4D, 0x42, 0x33)
FACE_TEXELS = 12
KEY_TEXELS = 5
HOLD, LOOP, ONCE = 0, 1, 2
SIZES = (256, 512, 1024)
END = {"loop": LOOP, "hold": HOLD, "once": ONCE}
BLEND = 4
# where a mob's feet are under an armour stand's head: a model point at y g shows at the head's
# translation + scale * (g - 8) units, which is this for the ground
GROUND = -38.8


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

    def visible(self, x, y, rgba):
        self.img.putpixel((x, y), rgba)
        self.bottom = max(self.bottom, y + 1)

    def face(self, bone, rect, corners):
        """A face whose texels are already in place: its number, the sprite's size and where the face is in it go
        into its corners' low bits (CORNER_BITS), so a vertex finds the sprite from its own face wherever the
        atlas put it."""
        index = len(self.faces)
        assert index < 4096, "a sprite's faces are numbered in 12 bits"
        u0, v0, u1, v1 = rect
        assert u1 - u0 >= 2 and v1 - v0 >= 2, "a face needs four distinct corner texels"
        word = index | SIZES.index(self.size) << 12 | u0 << 14 | v0 << 24
        for k, (x, y) in enumerate(((u0, v0), (u1 - 1, v0), (u1 - 1, v1 - 1), (u0, v1 - 1))):
            r, g, b, a = self.img.getpixel((x, y))
            bits = (word >> (9 * k)) & 511
            # opaque, to carry the number (a clear texel of the model's own is drawn as black)
            self.img.putpixel((x, y), ((r & ~7) | (bits & 7), (g & ~7) | ((bits >> 3) & 7), (b & ~7) | (bits >> 6), 255))
        self.faces.append((bone, rect, corners))
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
        for bone, (u0, v0, u1, v1), corners in self.faces:
            put(k, (bone, 0, 0))
            put(k + 1, (u0 >> 8, u0 & 255, v0 >> 8))
            put(k + 2, (v0 & 255, u1 >> 8, u1 & 255))
            put(k + 3, (v1 >> 8, v1 & 255, 0))
            for i, c in enumerate(corners):
                x, y, z = (self._position(a) for a in c)
                put(k + 4 + 2 * i, (x >> 8, x & 255, y >> 8))
                put(k + 5 + 2 * i, (y & 255, z >> 8, z & 255))
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
    with open(os.path.join(SOURCES, mob["model"]), encoding="utf-8") as f:
        d = json.load(f)
    name = mob["name"]
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

    # the cubes fitted into Java's -16 to 32, ground (y 0) kept level
    lo = np.min([e["from"] for e in d["elements"]] + [e["to"] for e in d["elements"]], axis=0)
    hi = np.max([e["from"] for e in d["elements"]] + [e["to"] for e in d["elements"]], axis=0)
    f = 47.0 / float(max(hi - lo))
    shift = np.array([8 - f * (lo[0] + hi[0]) / 2, -15.5 - f * lo[1], 8 - f * (lo[2] + hi[2]) / 2])
    A = affine(np.eye(3) * f, shift)
    A_inv = np.linalg.inv(A)

    def java(p):
        return f * np.array(p, float) + shift

    texture = d["textures"][0]
    src = Image.open(io.BytesIO(base64.b64decode(texture["source"].split(",", 1)[1]))).convert("RGBA")
    per = texture["width"] / texture["uv_width"]

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
            assert fd["texture"] == 0, "%s: a face reads a texture other than the first" % name
            u0, v0, u1, v1 = (round(c * per) for c in fd["uv"])
            if u0 == u1 or v0 == v1:
                continue
            if hidden(uid, face):
                culled += 1
                continue
            faces.append((uid, face, fd, (u0, v0, u1, v1)))

    # each face's own copy of its texels (at least 2 x 2, for its four corners to carry its number), edge to edge
    # on shelves, tallest first, in the smallest sprite they and the records fit
    sizes = [(max(2, abs(u1 - u0)), max(2, abs(v1 - v0))) for _, _, _, (u0, v0, u1, v1) in faces]
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
        raise SystemExit("%s: the faces and records don't fit a 1024 sprite" % name)
    sprite = Sprite(size, len(bones))

    by_element = {}
    for i, (uid, face, fd, (u0, v0, u1, v1)) in enumerate(faces):
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
        sprite.face(index[owner[uid]], (px, py, px + w, py + h), corners)
        s = 16 / size
        out = {"uv": [nu0 * s, nv0 * s, nu1 * s, nv1 * s], "texture": "#skin", "tintindex": 0}
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
        assert sprite.clip(frames, end) == cid

    box_lo = np.min([e["from"] for e in model_elements] + [e["to"] for e in model_elements], axis=0)
    box_hi = np.max([e["from"] for e in model_elements] + [e["to"] for e in model_elements], axis=0)
    os.makedirs(TEXTURES, exist_ok=True)
    sprite.write().save(os.path.join(TEXTURES, name + ".png"))
    ground = float(java([0, 0, 0])[1])
    scale = float(mob.get("scale", 1))
    assert 0 < scale <= 4, "%s: a display scale is at most 4" % name
    model = {"textures": {"skin": "ms:item/mobs/" + name, "particle": "ms:item/mobs/" + name},
             "elements": model_elements,
             # on the stand's head, facing its front (the model faces +z), feet on the ground; anywhere else fitted
             "display": dict({place: fitted(box_lo, box_hi, *d) for place, d in DISPLAYS.items()},
                             head={"rotation": [0, 180, 0], "translation": [0, round(GROUND - scale * (ground - 8), 2), 0],
                                   "scale": [scale] * 3})}
    os.makedirs(MODELS, exist_ok=True)
    with open(os.path.join(MODELS, name + ".json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(model, fh, separators=(",", ":"))
    print("%s (%d): %d bones, %d faces (%d inside their own bone left out), %d x %d sprite"
          % (name, mob["custom_model_data"], len(bones), len(faces), culled, size, size))
    for cid, anim, end in clips:
        # how long it plays: a loop's frames, any other's last frame
        print("  clip %2d %-14s %3d ticks, %s" % (cid, anim, lengths[anim] - (0 if end == LOOP else 1), {v: k for k, v in END.items()}[end]))


def main():
    for mob in definitions():
        build(mob)


if __name__ == "__main__":
    main()
