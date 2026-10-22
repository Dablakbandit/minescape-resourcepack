"""MineScape's armour models (armour/models/<piece>/<look>.bbmodel, see its README) for Minecraft 1.21.2
and newer, where leather's equipment asset can list more layers than its own two.

Each model face is drawn by one face of one of the armour's boxes, in one of the extra layers: a box has
six faces, so a body part with up to 6 * N model faces needs N layers. Every extra layer has its own
texture (textures/entity/equipment/<humanoid|humanoid_leggings>/minescape_model_<k>.png), so the armour
stitch knows which layer it is drawing from the texture's mark:

    the top right texel   (255, k, 255, alpha 4) a humanoid model layer, alpha 5 a leggings one
    rows 0 to 3           by item tile (x): its chest (row 0) or boots (row 1) model's row + 1 in
                          red and green, 0 none; its chest (row 2) or boots (row 3) colour. The
                          leggings' texture uses rows 0 and 2.
    rows 4 on             a row a model: ten texels a box face, (slot * 6 + face) * 10: four corners,
                          the normal, four texture positions, used (green: its texels have clear
                          ones, so its back can be seen)
    below                 the texels this layer's faces draw, packed

A corner is a byte an axis, a quarter of a pixel from its body part's pivot (32 pixels either side); a
texture position is two 12-bit texel coordinates in one texel's red, green and blue. Every texel is
all but clear, so a shader that doesn't know the layers (a shader pack without the Stitch mod) cuts
them all out: the data at alpha 1, the models' texels by colour code, alpha 1 dyed in the item's
colour, 2 its own colour, 3 a light shade, 0 clear.

The sheet the armour already draws (entity/equipment/.../leather.png) is marked as having models (its
mark's green has bit 32), so its own layer hides a modelled item where the models can be drawn.

Writes, from build_armour.py:
    assets/minecraft/textures/entity/equipment/humanoid*/minescape_model_<k>.png
    the overlays armour_models_* with leather's equipment asset, one for each form it takes
    MODELLED, for the armour stitch's table
"""
import base64
import io
import json
import math
import os

import numpy as np
from PIL import Image

import armour_looks as looks

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODELS = os.path.join(ROOT, "armour", "models")
TEXTURES = os.path.join(ROOT, "assets", "minecraft", "textures", "entity", "equipment")
W = 2048
RECORD = 10
TABLE_ROWS = 4
# the alpha of every data texel: under the 0.1 any shader cuts out at
QUIET = 1
# the models' colour codes, in alpha
DYED, OWN, LIGHT = 1, 2, 3
# each body part's pivot, in Minecraft's model space (pixels; y down, front -z)
PIVOT = {"head": (0, 0, 0), "body": (0, 0, 0), "right_arm": (-5, 2, 0), "left_arm": (5, 2, 0),
         "right_leg": (-1.9, 12, 0), "left_leg": (1.9, 12, 0)}
# the armour's boxes, by slot: head, hat, body, right arm, left arm, right leg, left leg
SLOT = {"body": 2, "right_arm": 3, "left_arm": 4, "right_leg": 5, "left_leg": 6}
PIECE = {"chest": "chestplate", "boots": "boots", "legs": "leggings"}
UNDYED = -6265536
# A model layer's texture. OptiFine's CIT gives every leather layer but the overlay an item's own tile
# (build_armour.cit), these too, so under OptiFine (from 1.21.2) an item's look is flat.
MODEL_TEXTURE = "minecraft:minescape_model_%d"
# leather's equipment asset, as each overlay (armour_looks.MODEL_OVERLAYS) has it: (path, form)
FORMS = dict(zip([o[0] for o in looks.MODEL_OVERLAYS], [
    ("models/equipment/leather.json", "plain"),
    ("equipment/leather.json", "plain"),
    ("equipment/leather.json", "horse_overlay"),
    ("equipment/leather.json", "baby"),
]))


# --- reading a model ----------------------------------------------------------------------------------

def rotation(degrees):
    """Blockbench's rotation: Euler angles in order ZYX (x applied first)."""
    x, y, z = (math.radians(a) for a in degrees)
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    rx = ((1, 0, 0), (0, cx, -sx), (0, sx, cx))
    ry = ((cy, 0, sy), (0, 1, 0), (-sy, 0, cy))
    rz = ((cz, -sz, 0), (sz, cz, 0), (0, 0, 1))

    def mul(a, b):
        return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))
    return mul(mul(rz, ry), rx)


def turn(p, origin, degrees):
    if not any(degrees):
        return p
    r = rotation(degrees)
    d = [p[i] - origin[i] for i in range(3)]
    return tuple(origin[i] + sum(r[i][k] * d[k] for k in range(3)) for i in range(3))


# a face's corners (top left, top right, bottom right, bottom left, seen from outside) by which end of
# each axis they take: 0 the cube's low end, 1 its high end
FACE_CORNERS = {
    "north": ((1, 1, 0), (0, 1, 0), (0, 0, 0), (1, 0, 0)),
    "south": ((0, 1, 1), (1, 1, 1), (1, 0, 1), (0, 0, 1)),
    "east": ((1, 1, 1), (1, 1, 0), (1, 0, 0), (1, 0, 1)),
    "west": ((0, 1, 0), (0, 1, 1), (0, 0, 1), (0, 0, 0)),
    "up": ((0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)),
    "down": ((0, 0, 1), (1, 0, 1), (1, 0, 0), (0, 0, 0)),
}


def codes(image):
    """A model texture in the models' colour codes: a clear texel 0; alpha 253 in the drawing a light
    shade; an exact grey dyed (unless its alpha is 254); anything else its own colour."""
    px = np.array(image.convert("RGBA"))
    a = px[..., 3]
    grey = (px[..., 0] == px[..., 1]) & (px[..., 1] == px[..., 2])
    out = px.copy()
    out[..., 3] = np.where(a < 128, 0, np.where(a == 253, LIGHT, np.where(grey & (a != 254), DYED, OWN)))
    out[a < 128] = 0
    return Image.fromarray(out)


def load(path, piece):
    """The piece's faces by body part, as (corners in the part's own space, (texture, x, y) a corner); its
    cubes by body part (cube()); and its textures in colour codes."""
    model = json.load(open(path, encoding="utf-8"))
    res = model.get("resolution", {"width": 16, "height": 16})
    textures = []
    for t in model.get("textures", []):
        source = t.get("source", "")
        if not source.startswith("data:image/png;base64,"):
            raise SystemExit("%s: texture %s isn't embedded in the project" % (path, t.get("name")))
        image = Image.open(io.BytesIO(base64.b64decode(source.split(",", 1)[1])))
        textures.append((codes(image), t.get("uv_width", res["width"]), t.get("uv_height", res["height"])))
    cubes = {e["uuid"]: e for e in model["elements"] if e.get("type", "cube") == "cube"}
    faces = {part: [] for part in SLOT}
    whole = {part: [] for part in SLOT}

    def walk(node, inside, part, groups):
        if isinstance(node, str):
            cube = cubes.get(node)
            if cube is None or cube.get("export") is False or not inside:
                return
            if part is None:
                raise SystemExit("%s: cube %s is outside a body part's group" % (path, cube.get("name")))
            faces[part].extend(cube_faces(cube, groups, part, textures))
            whole[part].append(cube_of(cube, groups, part, textures))
            return
        if node.get("export") is False:
            return
        name = node.get("name", "")
        if name == piece:
            inside = True
        elif inside and name in SLOT:
            part = name
        for child in node.get("children", []):
            walk(child, inside, part, groups + [(node.get("origin", [0, 0, 0]), node.get("rotation", [0, 0, 0]))])

    for node in model["outliner"]:
        walk(node, False, None, [])
    return faces, whole, [t[0] for t in textures]


def to_part(p, cube, groups, part):
    """A point of a cube's (Blockbench's coordinates, before the cube's and its groups' rotations) in its
    body part's own space."""
    p = turn(p, cube.get("origin", [0, 0, 0]), cube.get("rotation", [0, 0, 0]))
    for origin, degrees in reversed(groups):
        p = turn(p, origin, degrees)
    # Blockbench's space to Minecraft's model space, then to the body part's own
    m = (-p[0], 24 - p[1], p[2])
    return tuple(m[i] - PIVOT[part][i] for i in range(3))


def face_uvs(spec, textures):
    """A face's texture positions at its corners (top left, top right, bottom right, bottom left), as
    (texture, x, y) in the texture's pixels."""
    image, uw, uh = textures[spec["texture"]]
    u1, v1, u2, v2 = spec["uv"]
    uvs = [(u1, v1), (u2, v1), (u2, v2), (u1, v2)]
    turns = int(spec.get("rotation", 0)) // 90 % 4
    uvs = uvs[-turns:] + uvs[:-turns] if turns else uvs
    return [(spec["texture"], u * image.width / uw, v * image.height / uh) for u, v in uvs]


def cube_bounds(cube):
    g = cube.get("inflate", 0)
    return [cube["from"][i] - g for i in range(3)], [cube["to"][i] + g for i in range(3)]


def cube_faces(cube, groups, part, textures):
    lo, hi = cube_bounds(cube)
    out = []
    for face, spec in cube.get("faces", {}).items():
        if spec is None or spec.get("texture") is None or face not in FACE_CORNERS:
            continue
        corners = [to_part(tuple(hi[i] if ends[i] else lo[i] for i in range(3)), cube, groups, part)
                   for ends in FACE_CORNERS[face]]
        out.append((corners, face_uvs(spec, textures)))
    return out


def cube_of(cube, groups, part, textures):
    """A cube whole, for the tracer: its corners in the part's space; whether it's turned; the map from
    its own coordinates to the part's space, x -> m x + v (m's columns); its bounds; its faces' texture
    positions by name."""
    lo, hi = cube_bounds(cube)
    v = to_part((0.0, 0.0, 0.0), cube, groups, part)
    m = [[to_part(tuple(1.0 if j == i else 0.0 for j in range(3)), cube, groups, part)[k] - v[k] for k in range(3)]
         for i in range(3)]
    turned = any(cube.get("rotation", [0, 0, 0])) or any(any(d) for _, d in groups)
    corners = [to_part(tuple(hi[i] if (k >> i) & 1 else lo[i] for i in range(3)), cube, groups, part) for k in range(8)]
    faces = {face: face_uvs(spec, textures) for face, spec in cube.get("faces", {}).items()
             if spec is not None and spec.get("texture") is not None and face in FACE_CORNERS}
    return {"corners": corners, "turned": turned, "m": m, "v": v, "lo": lo, "hi": hi, "faces": faces}


# --- encoding -----------------------------------------------------------------------------------------

def enc(v, what):
    b = round(v * 4) + 128
    if not 0 <= b <= 255:
        raise SystemExit("%s is %.1f pixels from its body part's pivot; the limit is 32" % (what, abs(v)))
    return b


def normal(c):
    e1 = [c[1][i] - c[0][i] for i in range(3)]
    e2 = [c[3][i] - c[0][i] for i in range(3)]
    n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
    length = math.sqrt(sum(x * x for x in n)) or 1.0
    return tuple(round((x / length * 0.5 + 0.5) * 255) for x in n) + (QUIET,)


def u24(n):
    return ((n >> 16) & 255, (n >> 8) & 255, n & 255, QUIET)


class Shelf:
    """Packs rectangles left to right in rows, from a top row down."""

    def __init__(self, top, width=W):
        self.x, self.y, self.h = 0, top, 0
        self.width = width
        self.bottom = top

    def place(self, w, h):
        if self.x + w > self.width:
            self.x, self.y, self.h = 0, self.y + self.h + 1, 0
        at = (self.x, self.y)
        self.x += w + 1
        self.h = max(self.h, h)
        self.bottom = max(self.bottom, self.y + h)
        return at


# --- building ------------------------------------------------------------------------------------------

def models_of(kind):
    """{look: path} for the piece's looks that have a model."""
    folder = os.path.join(MODELS, kind)
    if not os.path.isdir(folder):
        return {}
    return {f[:-8]: os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.endswith(".bbmodel")}


def look_name(item):
    """The item's look, by file name (the items give its path)."""
    return os.path.splitext(os.path.basename(item["look"]))[0]


def colour(item):
    c = item.get("colour")
    if not c:
        return 0xA06540
    if isinstance(c, str):
        return int(c.lstrip("#"), 16)
    return c[0] << 16 | c[1] << 8 | c[2]


def layer_texture(models, k, kinds, tiles, leggings):
    """The k-th extra layer's texture: tables, records and the texels its faces draw."""
    rows = TABLE_ROWS + len(models)
    shelf = Shelf(rows)
    pieces = []
    placed = {}
    records = []
    for r, (kind, look, faces, textures) in enumerate(models):
        for part, quads in faces.items():
            for f, (corners, uvs) in enumerate(quads[k * 6:(k + 1) * 6]):
                tex = uvs[0][0]
                xs = [u[1] for u in uvs]
                ys = [u[2] for u in uvs]
                x0, y0 = math.floor(min(xs) + 1e-6), math.floor(min(ys) + 1e-6)
                x1, y1 = math.ceil(max(xs) - 1e-6), math.ceil(max(ys) - 1e-6)
                key = (r, tex, x0, y0, x1, y1)
                if key not in placed:
                    w, h = max(1, x1 - x0), max(1, y1 - y0)
                    at = shelf.place(w, h)
                    placed[key] = at
                    pieces.append((textures[tex].crop((x0, y0, x0 + w, y0 + h)), at))
                ax, ay = placed[key]
                tuvs = [(round(u[1] - x0 + ax), round(u[2] - y0 + ay)) for u in uvs]
                records.append((r, SLOT[part], f, corners, tuvs, "%s %s" % (look, part), clear(textures[tex], uvs)))
    height = shelf.bottom + 1
    if height > 4095:
        raise SystemExit("model layer %d needs %d rows; 4095 is the most a texture position can reach" % (k, height))
    img = Image.new("RGBA", (W, height), (0, 0, 0, 0))
    for image, at in pieces:
        img.paste(image, at)
    px = img.load()
    # the tables: each item tile's model rows and colours
    for t in range(looks.TILES):
        for i, kind in enumerate(kinds):
            item = tiles[kind].get(t)
            if item is None:
                continue
            row = next((r for r, m in enumerate(models) if m[0] == kind and m[1] == look_name(item)), None)
            if row is not None:
                px[t, i] = ((row + 1) >> 8, (row + 1) & 255, 0, QUIET)
            c = colour(item)
            px[t, 2 + i] = ((c >> 16) & 255, (c >> 8) & 255, c & 255, QUIET)
    for r, slot, f, corners, tuvs, what, see_through in records:
        x, y = (slot * 6 + f) * RECORD, TABLE_ROWS + r
        for c in range(4):
            px[x + c, y] = tuple(enc(v, what) for v in corners[c]) + (QUIET,)
            u, v = tuvs[c]
            assert 0 <= u < 4096 and 0 <= v < 4096
            px[x + 5 + c, y] = u24(u << 12 | v)
        px[x + 4, y] = normal(corners)
        # used; green where its texels have clear ones, to see its back through
        px[x + 9, y] = (255, 255 if see_through else 0, 255, QUIET)
    px[W - 1, 0] = (255, k, 255, 5 if leggings else 4)
    return img


def equipment(form, humanoid, leggings):
    """Leather's equipment asset in one of its forms, with the model layers after leather's own."""
    leather = {"dyeable": {"color_when_undyed": UNDYED}, "texture": "minecraft:leather"}
    pair = [leather, {"texture": "minecraft:leather_overlay"}]
    layers = {"horse_body": [leather] if form == "plain" else pair,
              "humanoid": pair + [{"dyeable": {"color_when_undyed": UNDYED}, "texture": MODEL_TEXTURE % k}
                                  for k in range(humanoid)],
              "humanoid_leggings": pair + [{"dyeable": {"color_when_undyed": UNDYED}, "texture": MODEL_TEXTURE % k}
                                           for k in range(leggings)]}
    if form == "baby":
        layers["humanoid_baby"] = pair
    return {"layers": dict(sorted(layers.items()))}


def item_equipment(kind, layers):
    """One armour item's own equipment asset (minescape:<piece>_<tile>, which the plugin gives the item
    on 1.21.2+ clients): leather's own layers, then only as many model layers as its look needs, so
    the item draws only those."""
    leather = {"dyeable": {"color_when_undyed": UNDYED}, "texture": "minecraft:leather"}
    model = [{"dyeable": {"color_when_undyed": UNDYED}, "texture": MODEL_TEXTURE % k} for k in range(layers)]
    return {"layers": {"humanoid_leggings" if kind == "legs" else "humanoid": [leather, {"texture": "minecraft:leather_overlay"}] + model}}


def build():
    """Writes the model layers and overlays; returns {kind: set of item tiles with a model}."""
    import shutil
    chest, boots, legs = looks.items("chest"), looks.items("boots"), looks.items("legs")
    tiles = {"chest": chest, "boots": boots, "legs": legs}
    sets = {}
    layers_of = {}
    for layer, kinds, folder in ((1, ("chest", "boots"), "humanoid"), (2, ("legs",), "humanoid_leggings")):
        models = []
        for kind in kinds:
            for look, path in models_of(kind).items():
                faces, _, textures = load(path, PIECE[kind])
                models.append((kind, look, faces, textures))
                # the layers this look needs: six faces of each of its body parts a layer
                layers_of[(kind, look)] = max([0] + [math.ceil(len(q) / 6) for q in faces.values()])
        need = max([1] + [math.ceil(len(q) / 6) for m in models for q in m[2].values()]) if models else 0
        out = os.path.join(TEXTURES, folder)
        for old in [f for f in os.listdir(out) if f.startswith("minescape_model_")] if os.path.isdir(out) else []:
            os.remove(os.path.join(out, old))
        for k in range(need):
            layer_texture(models, k, kinds, tiles, layer == 2).save(os.path.join(out, MODEL_TEXTURE.split(":")[1] % k + ".png"))
        sets[folder] = need
        for kind in kinds:
            modelled = {m[1] for m in models if m[0] == kind}
            sets[kind] = {t for t, item in tiles[kind].items() if look_name(item) in modelled}
        print("models %s: %d looks, %d layers" % (folder, len(models), need))
    for directory, (path, form) in FORMS.items():
        shutil.rmtree(os.path.join(ROOT, directory), ignore_errors=True)
        target = os.path.join(ROOT, directory, "assets", "minecraft", path)
        os.makedirs(os.path.dirname(target))
        with open(target, "w", newline="\n") as f:
            json.dump(equipment(form, sets["humanoid"], sets["humanoid_leggings"]), f, indent=2)
            f.write("\n")
        # every armour item's own asset, beside leather's (the same folder, in MineScape's namespace)
        folder = os.path.join(ROOT, directory, "assets", "minescape", os.path.dirname(path))
        os.makedirs(folder)
        for kind, items in tiles.items():
            for tile, item in items.items():
                with open(os.path.join(folder, "%s_%d.json" % (kind, tile)), "w", newline="\n") as f:
                    json.dump(item_equipment(kind, layers_of.get((kind, look_name(item)), 0)), f, separators=(",", ":"))
                    f.write("\n")
    return sets


# --- the tracer, for releases without the extra layers (to 1.21.1) ----------------------------------------
#
# Below a sheet's looks (the sheet the armour already draws), from row `top`:
#     rows top, top + 1     by item tile (x): its chest (or leggings) model's, then its boots model's,
#                           first header row, 0 none
#     rows top + 2, + 3     their colours
#     header rows           five a model, one a body part (body, right arm, left arm, right leg, left
#                           leg): its cube count; the sphere round it, centre and radius; its box; at
#                           x 8 its first cube; from x HEADER_CUBES each cube's first three texels
#                           (below), so a ray finds the cubes it meets in one row
#     cubes                 from row `cubes`, CUBE texels each (a cube's never cross a row):
#                               0       red 1 if it's turned; green its faces, blue those with clear
#                                       texels, a bit each in FACE_ORDER
#                               1, 2    its box in the part's space (round a turned cube)
#                               3 on    each face's texture positions at its top left, top right and
#                                       bottom left corners, three texels a face in FACE_ORDER
#                               21 on   a turned cube: the map from the part's space to its own, x ->
#                                       a x + b with its corner at 0: a's nine numbers in 12 bits
#                                       two a texel, then b and the cube's size in fixed point
#     texels                what the faces draw, packed
# The sheet's (width - 2, 0) holds top, (width - 3, 0) cubes, as 24-bit numbers. OptiFine's own tile for
# an item (build_armour.cit) carries its models the same way, its tables in column 0 alone.

TRACE_SLOTS = ("body", "right_arm", "left_arm", "right_leg", "left_leg")
CUBE = 32
# the most cubes a body part's model has (the stitch tests them all)
MAX_CUBES = 32
# where a header row lists its cubes' first three texels (flags and box), side by side
HEADER_CUBES = 16
# a cube's faces, by its own axes' ends: x low and high, y low and high, z low and high
FACE_ORDER = ("west", "east", "down", "up", "north", "south")


def enc_lo(v):
    return max(0, math.floor(v * 4) + 128)


def enc_hi(v):
    return min(255, math.ceil(v * 4) + 128)


def fixed(v):
    """A number in 24-bit fixed point, 1/1024 of a pixel."""
    n = int(round(v * 1024)) + (1 << 23)
    if not 0 <= n < 1 << 24:
        raise SystemExit("%.1f pixels is out of the tracer's reach" % v)
    return u24(n)


def unit_pair(a, b):
    """Two numbers from -1 to 1 in 12 bits each."""
    q = lambda x: max(0, min(4095, int(round((x * 0.5 + 0.5) * 4095))))
    return u24(q(a) << 12 | q(b))


_loaded = {}


def most_cubes():
    """The most cubes any traced body part has: the tracer tests that many, at most."""
    return max([1] + [len(cubes.get(slot, [])) for kinds in (("chest", "boots"), ("legs",))
                      for _, _, cubes, _ in models_for(kinds) for slot in TRACE_SLOTS])


def models_for(kinds):
    out = []
    for kind in kinds:
        for look, path in models_of(kind).items():
            if path not in _loaded:
                _loaded[path] = load(path, PIECE[kind])
            _, cubes, textures = _loaded[path]
            out.append((kind, look, cubes, textures))
    return out


def clear(texture, uvs):
    """Whether any texel a face's texture positions span is clear."""
    xs = [u[1] for u in uvs]
    ys = [u[2] for u in uvs]
    box = (math.floor(min(xs) + 1e-6), math.floor(min(ys) + 1e-6), math.ceil(max(xs) - 1e-6), math.ceil(max(ys) - 1e-6))
    alpha = np.array(texture.crop((box[0], box[1], max(box[2], box[0] + 1), max(box[3], box[1] + 1))).getchannel("A"))
    return bool((alpha == 0).any())


def traced(layer, sheet, entries=None):
    """The sheet with the tracer's data for its pieces' models below its looks. entries, {column: {kind:
    item}}, are the tables' columns, by default every item tile; with them only their models go in."""
    kinds = ("chest", "boots") if layer == 1 else ("legs",)
    if entries is None:
        tiles = {kind: looks.items(kind) for kind in kinds}
        entries = {t: {kind: tiles[kind][t] for kind in kinds if t in tiles[kind]} for t in range(looks.TILES)}
        models = models_for(kinds)
    else:
        wanted = {(kind, look_name(item)) for columns in entries.values() for kind, item in columns.items()}
        models = [m for m in models_for(kinds) if (m[0], m[1]) in wanted]
        if not models:
            return sheet
    width = sheet.width
    # a cube's texels share a row, found with a shift (the stitch reads them by width)
    assert width & (width - 1) == 0 and width % CUBE == 0, width
    top = sheet.height
    header = top + 4
    cubes_row = header + 5 * len(models)
    count = 0
    for kind, look, cubes, textures in models:
        for slot in TRACE_SLOTS:
            if len(cubes.get(slot, [])) > MAX_CUBES:
                raise SystemExit("%s %s %s: %d cubes; a body part's model can have %d" % (kind, look, slot, len(cubes[slot]), MAX_CUBES))
            count += len(cubes.get(slot, []))
    rows = -(-count * CUBE // width)
    shelf = Shelf(cubes_row + rows + 1, width)
    placed = {}
    pieces = []

    def place(r, uvs):
        tex = uvs[0][0]
        xs = [u[1] for u in uvs]
        ys = [u[2] for u in uvs]
        x0, y0 = math.floor(min(xs) + 1e-6), math.floor(min(ys) + 1e-6)
        x1, y1 = math.ceil(max(xs) - 1e-6), math.ceil(max(ys) - 1e-6)
        key = (r, tex, x0, y0, x1, y1)
        if key not in placed:
            w, h = max(1, x1 - x0), max(1, y1 - y0)
            placed[key] = shelf.place(w, h)
            pieces.append((models[r][3][tex].crop((x0, y0, x0 + w, y0 + h)), placed[key]))
        ax, ay = placed[key]
        return [(round(u[1] - x0 + ax), round(u[2] - y0 + ay)) for u in uvs]

    texel_rows = {}
    c = 0
    for r, (kind, look, cubes, textures) in enumerate(models):
        for s, slot in enumerate(TRACE_SLOTS):
            row = header + 5 * r + s
            line = texel_rows.setdefault(row, {})
            # the biggest first: their hits come early, and a ray stops testing cubes it meets beyond one
            mine = sorted(cubes.get(slot, []), key=lambda cube: -math.prod(
                max(p[i] for p in cube["corners"]) - min(p[i] for p in cube["corners"]) for i in range(3)))
            if not mine:
                line[0] = (0, 0, 0, QUIET)
                continue
            pts = [p for cube in mine for p in cube["corners"]]
            lo = [min(p[i] for p in pts) for i in range(3)]
            hi = [max(p[i] for p in pts) for i in range(3)]
            centre = [(lo[i] + hi[i]) / 2 for i in range(3)]
            what = "%s %s" % (look, slot)
            line[0] = (len(mine), 0, 0, QUIET)
            line[1] = tuple(enc(x, what) for x in centre) + (QUIET,)
            line[2] = (min(255, math.ceil(max(math.dist(centre, p) for p in pts) * 4)), 0, 0, QUIET)
            line[3] = tuple(enc_lo(x) for x in lo) + (QUIET,)
            line[4] = tuple(enc_hi(x) for x in hi) + (QUIET,)
            line[8] = u24(c)
            for n, cube in enumerate(mine):
                texels = {}
                clo = [min(p[i] for p in cube["corners"]) for i in range(3)]
                chi = [max(p[i] for p in cube["corners"]) for i in range(3)]
                faces, cut = 0, 0
                for f, name in enumerate(FACE_ORDER):
                    uvs = cube["faces"].get(name)
                    if uvs is None:
                        continue
                    faces |= 1 << f
                    if clear(textures[uvs[0][0]], uvs):
                        cut |= 1 << f
                    tuvs = place(r, uvs)
                    for k, corner in enumerate((0, 1, 3)):
                        u, v = tuvs[corner]
                        assert 0 <= u < 4096 and 0 <= v < 4096
                        texels[3 + 3 * f + k] = u24(u << 12 | v)
                texels[0] = (1 if cube["turned"] else 0, faces, cut, QUIET)
                if cube["turned"]:
                    texels[1] = tuple(enc_lo(x) for x in clo) + (QUIET,)
                    texels[2] = tuple(enc_hi(x) for x in chi) + (QUIET,)
                    # the part's space to the cube's own: m is a turn (and the mirror into Minecraft's
                    # space), so its inverse is its transpose
                    a = [[cube["m"][i][j] for j in range(3)] for i in range(3)]
                    av = [sum(a[i][j] * cube["v"][j] for j in range(3)) for i in range(3)]
                    b = [-(av[i] + cube["lo"][i]) for i in range(3)]
                    flat = [a[i][j] for i in range(3) for j in range(3)] + [0.0]
                    for k in range(5):
                        texels[21 + k] = unit_pair(flat[2 * k], flat[2 * k + 1])
                    for k in range(3):
                        texels[26 + k] = fixed(b[k])
                        texels[29 + k] = fixed(cube["hi"][k] - cube["lo"][k])
                else:
                    texels[1] = tuple(enc(x, what) for x in clo) + (QUIET,)
                    texels[2] = tuple(enc(x, what) for x in chi) + (QUIET,)
                for k, px in texels.items():
                    at = c * CUBE + k
                    texel_rows.setdefault(cubes_row + at // width, {})[at % width] = px
                # its first three texels again in the part's header row, beside the other cubes'
                for k in range(3):
                    line[HEADER_CUBES + 3 * n + k] = texels[k]
                c += 1
    height = shelf.bottom + 1
    if height > 4095:
        raise SystemExit("the layer %d sheet with its traced models needs %d rows; 4095 is the most" % (layer, height))
    out = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    out.paste(sheet, (0, 0))
    for image, at in pieces:
        out.paste(image, at)
    px = out.load()
    for y, line in texel_rows.items():
        for x, value in line.items():
            px[x, y] = value
    for x, columns in entries.items():
        for i, kind in enumerate(kinds):
            item = columns.get(kind)
            if item is None:
                continue
            r = next((r for r, m in enumerate(models) if m[0] == kind and m[1] == look_name(item)), None)
            if r is not None:
                px[x, top + i] = u24(header + 5 * r)
            col = colour(item)
            px[x, top + 2 + i] = ((col >> 16) & 255, (col >> 8) & 255, col & 255, QUIET)
    px[width - 2, 0] = u24(top)
    px[width - 3, 0] = u24(cubes_row)
    return out


def glsl(sets):
    """MS_MODELLED: each item tile's modelled pieces, bit 1 chest, 2 boots, 4 legs."""
    bits = [(1 if t in sets["chest"] else 0) | (2 if t in sets["boots"] else 0) | (4 if t in sets["legs"] else 0)
            for t in range(looks.TILES)]
    return "const int MS_MODELLED[%d] = int[](%s);\n" % (looks.TILES, ", ".join(map(str, bits)))
