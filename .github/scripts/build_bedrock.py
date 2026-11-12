"""MineScape's Bedrock pack and Geyser's item mappings, built from this Java pack.

    python .github/scripts/build_bedrock.py            build/bedrock/ (below)
    python .github/scripts/build_bedrock.py --jobs 4   icon renders on 4 processes (default: the CPUs, at most 8)
    python .github/scripts/build_bedrock.py --no-zip   the pack tree and mappings only

Bedrock players join through Geyser, which turns each Java item into a Bedrock one. Every custom item
here is told apart the Java way, so the mappings say the same thing in Geyser's terms:

  * custom model data (leather horse armour, the noted icons below zero, worn leather armour at
    10000 + its tile, and the older materials' looks): a "legacy" definition on the material, matched as
    Java 1.18.2 matches an override, custom model data at least its number, the highest number first;
  * damage (tools and the older looks, scenery in item frames): a "definition" on the material's own
    item model with a range_dispatch damage predicate, the threshold the item's damage (not normalised:
    the Java pack's fraction of the material's durability, back to a whole damage value).

Overrides next to each other that pick the same model share one Bedrock item (the Java pack picks the
same for every number between them too), which keeps the Bedrock item count well under the client's
limit (MAX_ITEMS). The mob models (custom model data from MOBS_FROM, build_mobs.py) are not items here:
the Bedrock entities are (bedrock_entities.py).

Each Bedrock item has an icon: a flat model's layers, or a 3D model drawn as the Java inventory draws it
(its gui transform), by the small software renderer below, cached in cache/bedrock/icons/. Every 1.18.2 item gets
one too, from the Java pack's model of it with the client jar's models and textures where the pack has none (block
items rendered, builtin ones such as chests from their block entity's boxes). Each distinct picture is written once,
textures/ms/i/<its sha1>.png; item_texture.json names it for each Bedrock item by a key that only follows the
item's identifier (ms.<identifier's name>, the mapping's icon), and bedrock_icons.json gives the plugin every
picture's path by item (bedrock/ICONS.md). carrot.json and feather.json are left out (SKIP_MATERIALS).

A 3D model also gets an attachable, so it's drawn as a model in the hand, on the head (armour stands) and
in first person: its elements as Bedrock geometry, one geometry per texture (one render controller each),
posed by its Java display transforms the way java2bedrock does it. Worn leather armour (armour/<piece>.json)
gets an attachable per item: its look's Blockbench model, the textures baked in the item's colour as
build_armour.py bakes them.

Item frames: every 3D look is also a frame entity (bedrock_entities.json's frames), its attachable's geometry and
textures posed by the frame's facing and rotation (entity properties the Geyser extension sets) and the model's fixed
display, as Java's ItemFrameRenderer draws the item.

A flat item gets an attachable too, but only for armour stands (an attachable's item condition on the owner):
Bedrock draws nothing a stand wears or holds without one, and ground items, hint markers and props are stands.
A player's hand keeps Bedrock's own picture of the item.

The world: the Java pack's retextures of vanilla blocks go to Bedrock's own texture paths by
bedrock_block_textures.json (made once by gen_block_map.py from the game's terrain_texture.json), with the armour
stand cleared (a mob is only the model on its head), the item frame cleared (Java's frame model is empty), and the
grass and foliage colours and the sun and moon. Java block models and blockstate variants (furniture made of
slabs and stairs, flat leaves, random stone variants) have no Bedrock equivalent for vanilla blocks; those blocks
show the retexture on their own shape.

Furniture: the blockstates that draw a vanilla block as another model (a table from a top purpur slab, chairs and
loot chests from stairs, cabinets, torches, rails without fence posts) as Geyser custom block state overrides
(geyser_block_mappings.json), the model as Bedrock block geometry with its textures in the pack's terrain atlas.
A state picking among models at random takes the likeliest.

Sounds: the minecraft, mob and skill namespaces' sound events as sounds/sound_definitions.json, named as Geyser
plays a Java custom sound (its id without "minecraft:"), with their .ogg files. The music player's MIDI notes
(osrsmidi, 81 MB) are a second pack, minescape-music.mcpack, offered beside the main one.

Glyphs: the plain icon glyphs (the emoji font's pages, skill icons and badges among them) as Bedrock
glyph pages, font/glyph_<page>.png; the offset, hud, menu and sidebar fonts are never sent to Bedrock.

JSON UI: generated into the pack by bedrock_hud_ui.py and bedrock_hud_textures.py (the hud) and
bedrock_chest_ui.py (the item-grid windows); ui/_ui_defs.json lists the files in ui/'s
folders (those in ui/ itself are vanilla's screens, merged by name). bedrock_entities.py builds the mobs and props and
writes bedrock_entities.json with the frames.

Written (build/ is git-ignored). CI publishes the packs, the mappings and the contracts, each with a .sha1, to the
patreon release (test) and the resourcepack release (live), where MineScape's Geyser extension fetches them: the
mappings into Geyser's custom_mappings/ as Geyser starts, the packs per player (live on joining, test after /urp test).

    build/bedrock/pack/                  the pack tree
    build/bedrock/minescape.mcpack       the pack
    build/bedrock/minescape-music.mcpack the music player's instruments, a second pack beside it
    build/bedrock/geyser_mappings.json   Geyser's custom item mappings (format 2)
    build/bedrock/geyser_block_mappings.json  Geyser's custom block state overrides (format 1)
    build/bedrock/bedrock_entities.json  the entities' contract (bedrock_entities.py)
    build/bedrock/bedrock_icons.json     every item's icon in the pack, for the plugin's forms (bedrock/ICONS.md)
"""
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
import zipfile
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(SCRIPTS, "..", ".."))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
ASSETS = os.path.join(ROOT, "assets")
ITEM_MODELS = os.path.join(ASSETS, "minecraft", "models", "item")
CACHE = os.path.join(ROOT, "cache")
ICON_CACHE = os.path.join(CACHE, "bedrock", "icons")
ARMOUR_SOURCE = os.path.join(ROOT, "armour")
OUT = os.path.join(ROOT, "build", "bedrock")
PACK = os.path.join(OUT, "pack")

NAMESPACE = "minescape"
PACK_NAME = "MineScape"
# Stable across builds, so a client replaces the pack it has; the version below tells it that it changed.
PACK_UUID = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://minescape.me/bedrock/resource-pack"))
MODULE_UUID = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://minescape.me/bedrock/resource-pack/resources"))
MIN_ENGINE = [1, 21, 0]
# Bedrock item ids are 16-bit and vanilla takes ~1,700 of them
MAX_ITEMS = 30000

ICON = 32           # icon size, pixels (the pack's icons are 32x32)
RENDER = 64         # 3D icons are drawn at this size, then halved
RENDER_VERSION = 3  # bump to throw away the cached icons
MOBS_FROM = 100001  # build_mobs.py's custom model data on leather horse armour
ITEM = "leather_horse_armor"
NOTED = "feather"
ARMOUR = {"chest": "leather_chestplate", "legs": "leather_leggings", "boots": "leather_boots"}
# Lists that aren't items: feather.json is the noted icons' source (a noted item is leather horse armour
# below zero), carrot.json the same list again from before that. 7,600 Bedrock items and 6 MB saved.
SKIP_MATERIALS = {"carrot", "feather"}
ICON_DIR = "textures/ms/i"      # icons, each picture once, named by its content
MODEL_TEXTURE_DIR = "textures/ms/m"
# Bedrock clients can fail to load a file whose path in the pack is this long or longer
MAX_PATH = 80
# Bedrock aborts the whole game while loading a pack with a texture over 16,384 pixels on a side (Direct3D's
# limit), and phones commonly take no more than 4,096: every texture is kept within this. A Java animated
# texture is its frames stacked in one strip (one was 288 x 19,584), so only its first frame is copied.
MAX_TEXTURE = 4096
ARMOUR_TEXTURE_DIR = "textures/ms/armour"
ITEM_MATERIAL = "entity_alphatest_one_sided"
BLEND_MATERIAL = "entity_alphablend"

WARNINGS = []


def warn(message):
    WARNINGS.append(message)


# --- files -------------------------------------------------------------------------------------------

def read_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path, data, pretty=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        if pretty:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        else:
            json.dump(data, f, separators=(",", ":"), ensure_ascii=False)


# Item and armour geometries are collected and written at the end, GEOMETRIES_PER_FILE to a file: one file per model
# was 1,995 files, and a Bedrock client unpacks a pack a file at a time (tens of thousands took it minutes).
GEOMETRIES = []
GEOMETRIES_PER_FILE = 150


def add_geometries(geometries):
    GEOMETRIES.extend(geometries)


def write_geometries():
    """The collected geometries, GEOMETRIES_PER_FILE to a file; returns how many files."""
    files = 0
    for n in range(0, len(GEOMETRIES), GEOMETRIES_PER_FILE):
        write_json(os.path.join(PACK, "models", "entity", "ms", "g%03d.geo.json" % files),
                   {"format_version": "1.21.0", "minecraft:geometry": GEOMETRIES[n:n + GEOMETRIES_PER_FILE]})
        files += 1
    return files


def write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def full(ref):
    return ref if ":" in ref else "minecraft:" + ref


def split(ref):
    ns, path = full(ref).split(":", 1)
    return ns, path


def model_path(ref, assets=None):
    ns, path = split(ref)
    return os.path.join(assets or ASSETS, ns, "models", *path.split("/")) + ".json"


def texture_path(ref, assets=None):
    ns, path = split(ref)
    return os.path.join(assets or ASSETS, ns, "textures", *path.split("/")) + ".png"


def slug(text):
    return re.sub(r"[^a-z0-9_]+", "_", text.lower()).strip("_")


_SHA = {}


def file_sha(path):
    if path not in _SHA:
        with open(path, "rb") as f:
            _SHA[path] = hashlib.sha1(f.read()).hexdigest()
    return _SHA[path]


def png_bytes(image):
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()


# --- which item is which: the Java overrides ---------------------------------------------------------

def pristine(name):
    """models/item/<name>.json as committed: count_icons.py rewrites leather_* in place (CI, and a local
    checkout that ran it) and keeps the committed copy in cache/."""
    path = os.path.join(ITEM_MODELS, name + ".json")
    model = read_json(path)
    if any(str(o.get("model", "")).startswith("ms:count/") for o in model.get("overrides", [])):
        copy = os.path.join(CACHE, name + ".source.json")
        if not os.path.exists(copy):
            raise SystemExit("%s is count_icons.py's rewrite and cache/%s.source.json is missing: run "
                             "count_icons.py --restore" % (path, name))
        model = read_json(copy)
    return model


def cmd_numbers(model):
    numbers = {}
    for override in model.get("overrides", []):
        predicate = override.get("predicate", {})
        if set(predicate) == {"custom_model_data"}:
            numbers[int(predicate["custom_model_data"])] = full(override["model"])
    return numbers


def armour_items(piece):
    """custom model data -> the armour item (armour_looks.items) with its line in armour/<piece>.json."""
    import armour_looks
    lines = {e["custom_model_data"]: e for e in read_json(os.path.join(ARMOUR_SOURCE, piece + ".json"))["items"]}
    out = {}
    for tile, item in armour_looks.items(piece).items():
        out[item["custom_model_data"]] = dict(item, line=lines[item["custom_model_data"]], piece=piece)
    return out


def overrides():
    """material -> [(predicate kind, threshold, model ref, extra)] in the order the Java pack lists them
    (the order a 1.18.2 client reads them in, the last match winning). extra is None or the armour item."""
    import count_icons
    found = {}
    for file in sorted(os.listdir(ITEM_MODELS)):
        if not file.endswith(".json"):
            continue
        material = file[:-5]
        if material in SKIP_MATERIALS:
            continue
        model = pristine(material)
        listed = []
        if material == ITEM:
            # as count_icons.py lists them: the items by number, the noted icons below zero, ascending
            numbers = cmd_numbers(model)
            for number, ref in cmd_numbers(read_json(os.path.join(ITEM_MODELS, NOTED + ".json"))).items():
                if number > 0:
                    numbers[-number] = ref
            listed = [("cmd", n, numbers[n], None) for n in sorted(numbers) if n < MOBS_FROM]
        else:
            most = count_icons.durability(material)
            for override in model.get("overrides", []):
                predicate = override.get("predicate", {})
                ref = full(override["model"])
                keys = set(predicate)
                if keys == {"custom_model_data"}:
                    listed.append(("cmd", int(predicate["custom_model_data"]), ref, None))
                elif "damage" in keys and keys <= {"damage", "damaged"}:
                    if predicate.get("damaged", 0) > 0:
                        continue  # the plugin's items are unbreakable: never damaged
                    if not most:
                        warn("%s: damage overrides, but its durability is unknown" % material)
                        break
                    # the lowest damage whose fraction of the durability reaches the threshold
                    threshold = float(predicate["damage"])
                    damage = max(0, math.ceil(threshold * most - 1e-6))
                    listed.append(("damage", damage, ref, None))
                else:
                    warn("%s: override %s isn't by custom model data or damage alone; left out" % (material, predicate))
            piece = next((p for p, m in ARMOUR.items() if m == material), None)
            if piece:
                for number, item in sorted(armour_items(piece).items()):
                    listed.append(("cmd", number, full(item["icon"]), item))
        if listed:
            found[material] = listed
    return found


def live(listed):
    """The overrides of one predicate kind that can still be picked, ascending: a 1.18.2 client takes
    the last override whose threshold the item reaches, so one with a later one at or below its own
    threshold is never picked."""
    picked, lowest = [], None
    for entry in reversed(listed):
        if lowest is None or entry[1] < lowest:
            picked.append(entry)
            lowest = entry[1]
    return sorted(picked, key=lambda e: e[1])


# --- models --------------------------------------------------------------------------------------------

class Model:
    """A Java item model, its parents applied: kind is "flat" (layers), "3d" (elements) or "empty". A vanilla model
    (vanilla=True) reads models and textures the pack hasn't got from the 1.18.2 client jar, as the game does."""

    def __init__(self, ref, chain, root, vanilla=False, names=()):
        self.ref = ref
        self.vanilla = vanilla
        textures, display = {}, {}
        for model in reversed(chain):
            textures.update(model.get("textures", {}))
            display.update(model.get("display", {}))
        self.display = display
        self.gui_light = next((m["gui_light"] for m in chain if "gui_light" in m), None)
        self.root = split(root)[1] if root else None
        self.handheld = any(split(n)[1] in ("item/handheld", "item/handheld_rod") for n in list(names) + [root or ""])

        def resolve(value, depth=0):
            while isinstance(value, str) and value.startswith("#") and depth < 16:
                value = textures.get(value[1:])
                depth += 1
            return full(value) if isinstance(value, str) and not value.startswith("#") else None
        self.textures = {name: resolve(value) for name, value in textures.items()}
        elements = next((m["elements"] for m in chain if "elements" in m), None)
        self.elements = elements
        if elements:
            self.kind = "3d"
        elif elements is None and any(("layer%d" % i) in self.textures for i in range(5)):
            self.kind = "flat"
        else:
            self.kind = "empty"
        self.layers = [self.textures.get("layer%d" % i) for i in range(5) if ("layer%d" % i) in self.textures]

    def face_texture(self, face):
        value = face.get("texture")
        if not isinstance(value, str):
            return None
        if value.startswith("#"):
            return self.textures.get(value[1:])
        return full(value)


_MODELS = {}


def load_model(ref, vanilla=False):
    """The model, its parents read from the pack (and, for a vanilla model, from the client jar where the pack hasn't
    got them; vanilla="jar": from the jar alone), or None. A pack model's chain stops at the first parent the pack
    hasn't got (its root)."""
    if (ref, vanilla) in _MODELS:
        return _MODELS[(ref, vanilla)]
    chain, names, cur, seen, root = [], [], ref, set(), None
    while cur and cur not in seen:
        seen.add(cur)
        path = model_path(cur, vanilla_assets() if vanilla == "jar" else None)
        if not os.path.exists(path) and vanilla:
            path = model_path(cur, vanilla_assets())
        if not os.path.exists(path):
            root = cur
            break
        model = read_json(path)
        chain.append(model)
        names.append(cur)
        cur = full(model["parent"]) if "parent" in model else None
    model = Model(ref, chain, root, vanilla, names) if chain else None
    _MODELS[(ref, vanilla)] = model
    return model


def texture_info(ref, vanilla=False):
    """(path, frames) of a texture in the pack, else in the client jar (as the game finds a texture the pack hasn't
    got: block/white_concrete for a white chair), or None: frames is how many animation frames tall it is.
    vanilla="jar": the jar's alone."""
    if not ref:
        return None
    path = texture_path(ref, vanilla_assets() if vanilla == "jar" else None)
    if not os.path.exists(path):
        path = texture_path(ref, vanilla_assets())
    if not os.path.exists(path):
        return None
    frames = 1
    meta = path + ".mcmeta"
    if os.path.exists(meta):
        try:
            animation = read_json(meta).get("animation", {})
        except ValueError:
            animation = {}
        with Image.open(path) as image:
            w, h = image.size
        # a frame is as the mcmeta says, else a square as wide as the texture
        fh = animation.get("height") or (h if animation.get("width") else min(w, h))
        frames = max(1, h // max(1, int(fh)))
    return path, frames


# --- icons ---------------------------------------------------------------------------------------------

# a face's corners (top left, top right, bottom right, bottom left, seen from outside) by which end of
# each axis they take, as armour_models.py has them
FACE_CORNERS = {
    "north": ((1, 1, 0), (0, 1, 0), (0, 0, 0), (1, 0, 0)),
    "south": ((0, 1, 1), (1, 1, 1), (1, 0, 1), (0, 0, 1)),
    "east": ((1, 1, 1), (1, 1, 0), (1, 0, 0), (1, 0, 1)),
    "west": ((0, 1, 0), (0, 1, 1), (0, 0, 1), (0, 0, 0)),
    "up": ((0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)),
    "down": ((0, 0, 1), (1, 0, 1), (1, 0, 0), (0, 0, 0)),
}
SHADE = {"up": 1.0, "down": 0.5, "north": 0.8, "south": 0.8, "east": 0.6, "west": 0.6}


def default_uv(face, lo, hi):
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    return {"north": [16 - x1, 16 - y1, 16 - x0, 16 - y0], "south": [x0, 16 - y1, x1, 16 - y0],
            "east": [16 - z1, 16 - y1, 16 - z0, 16 - y0], "west": [z0, 16 - y1, z1, 16 - y0],
            "up": [x0, z0, x1, z1], "down": [x0, 16 - z1, x1, 16 - z0]}[face]


def axis_matrix(axis, degrees):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def first_frame(path, frames):
    image = Image.open(path).convert("RGBA")
    if frames > 1:
        image = image.crop((0, 0, image.width, image.height // frames))
    return image


def fit_texture(image):
    """The image within MAX_TEXTURE on each side. Geometry gives UVs in its own texture_width/height, not
    in pixels, so a texture scaled down still lines up; nearest-neighbour keeps pixel art sharp."""
    scale = MAX_TEXTURE / max(image.size)
    if scale >= 1:
        return image
    return image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.NEAREST)


def tinted(image, tint):
    if not tint:
        return image
    px = np.array(image, np.float32)
    px[..., :3] *= np.array(tint, np.float32) / 255.0
    return Image.fromarray(np.clip(np.round(px), 0, 255).astype(np.uint8))


def fit(image):
    """The image on an ICON x ICON canvas: whole-number scaling for pixel art, centred."""
    w, h = image.size
    if (w, h) == (ICON, ICON):
        return image
    big = max(w, h)
    if big < ICON:
        k = ICON // big
        image = image.resize((w * k, h * k), Image.NEAREST)
    elif big > ICON:
        k = ICON / big
        image = image.convert("RGBa").resize((max(1, round(w * k)), max(1, round(h * k))), Image.BOX).convert("RGBA")
    canvas = Image.new("RGBA", (ICON, ICON))
    canvas.paste(image, ((ICON - image.width) // 2, (ICON - image.height) // 2))
    return canvas


def flat_icon(layers):
    """layers: [(path, frames, tint)] -> the icon."""
    images = [tinted(first_frame(p, f), t) for p, f, t in layers]
    if not images:
        return Image.new("RGBA", (ICON, ICON))
    w = max(i.width for i in images)
    h = max(i.height for i in images)
    out = Image.new("RGBA", (w, h))
    for image in images:
        if image.size != (w, h):
            image = image.resize((w, h), Image.NEAREST)
        out = Image.alpha_composite(out, image)
    return fit(out)


def display_matrix(display):
    rotation = display.get("rotation", [0, 0, 0])
    translation = display.get("translation", [0, 0, 0])
    scale = display.get("scale", [1, 1, 1])
    r = axis_matrix("x", rotation[0]) @ axis_matrix("y", rotation[1]) @ axis_matrix("z", rotation[2])
    m = r @ np.diag([float(s) for s in scale])
    t = np.array([max(-80, min(80, float(v))) / 16.0 for v in translation])
    return m, t


def element_points(element):
    """{face: 4 corners in model units (0-16), the element's rotation applied}."""
    lo = [float(v) for v in element["from"]]
    hi = [float(v) for v in element["to"]]
    rotation = element.get("rotation")
    out = {}
    for face, spec in (element.get("faces") or {}).items():
        if face not in FACE_CORNERS or not isinstance(spec, dict):
            continue
        pts = np.array([[hi[i] if ends[i] else lo[i] for i in range(3)] for ends in FACE_CORNERS[face]], np.float64)
        if rotation and rotation.get("angle"):
            origin = np.array(rotation.get("origin", [8, 8, 8]), np.float64)
            axis = rotation.get("axis", "y")
            m = axis_matrix(axis, float(rotation["angle"]))
            pts = (pts - origin) @ m.T
            if rotation.get("rescale"):
                k = 1.0 / math.cos(math.radians(abs(float(rotation["angle"]))))
                pts *= np.array([1.0 if a == axis else k for a in "xyz"])
            pts += origin
        out[face] = pts
    return out


def render_icon(job):
    """A 3D model as the Java inventory draws it: job = {elements, textures {ref: (path, frames)},
    tints {ref: rgb}, gui display, light}. Returns PNG bytes, ICON x ICON."""
    images = {}
    for ref, (path, frames) in job["textures"].items():
        images[ref] = np.array(tinted(first_frame(path, frames), job["tints"].get(ref)), np.uint8)
    m, t = display_matrix(job["gui"])
    flat_light = job["light"] == "front"
    R = RENDER
    colour = np.zeros((R, R, 4), np.float32)
    depth = np.full((R, R), -np.inf, np.float32)
    for element in job["elements"]:
        shade_on = element.get("shade", True) and not flat_light
        points = element_points(element)
        lo = [float(v) for v in element["from"]]
        hi = [float(v) for v in element["to"]]
        for face, pts in points.items():
            spec = element["faces"][face]
            ref = spec.get("_texture")
            image = images.get(ref)
            if image is None:
                continue
            q = (pts / 16.0 - 0.5) @ m.T + t
            normal = np.cross(q[3] - q[0], q[1] - q[0])
            if normal[2] <= 1e-9:
                continue
            u1, v1, u2, v2 = spec.get("uv") or default_uv(face, lo, hi)
            uvs = [(u1, v1), (u2, v1), (u2, v2), (u1, v2)]
            turns = int(spec.get("rotation", 0)) // 90 % 4
            if turns:
                uvs = uvs[-turns:] + uvs[:-turns]
            th, tw = image.shape[:2]
            uv = np.array([(u * tw / 16.0, v * th / 16.0) for u, v in uvs], np.float64)
            sx = (q[:, 0] * 16 + 8) * R / 16.0
            sy = (8 - q[:, 1] * 16) * R / 16.0
            sz = q[:, 2]
            shade = SHADE[face] if shade_on else 1.0
            for a, b, c in ((0, 1, 2), (0, 2, 3)):
                x0, x1, x2 = sx[a], sx[b], sx[c]
                y0, y1, y2 = sy[a], sy[b], sy[c]
                den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
                if abs(den) < 1e-12:
                    continue
                xa = max(0, int(math.floor(min(x0, x1, x2))))
                xb = min(R, int(math.ceil(max(x0, x1, x2))))
                ya = max(0, int(math.floor(min(y0, y1, y2))))
                yb = min(R, int(math.ceil(max(y0, y1, y2))))
                if xa >= xb or ya >= yb:
                    continue
                X, Y = np.meshgrid(np.arange(xa, xb) + 0.5, np.arange(ya, yb) + 0.5)
                w0 = ((y1 - y2) * (X - x2) + (x2 - x1) * (Y - y2)) / den
                w1 = ((y2 - y0) * (X - x2) + (x0 - x2) * (Y - y2)) / den
                w2 = 1.0 - w0 - w1
                inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
                if not inside.any():
                    continue
                z = w0 * sz[a] + w1 * sz[b] + w2 * sz[c]
                region = depth[ya:yb, xa:xb]
                mask = inside & (z > region)
                if not mask.any():
                    continue
                u = w0 * uv[a, 0] + w1 * uv[b, 0] + w2 * uv[c, 0]
                v = w0 * uv[a, 1] + w1 * uv[b, 1] + w2 * uv[c, 1]
                tu = np.clip(np.floor(u).astype(np.int64), 0, tw - 1)
                tv = np.clip(np.floor(v).astype(np.int64), 0, th - 1)
                texel = image[tv, tu].astype(np.float32)
                mask &= texel[..., 3] >= 26
                if not mask.any():
                    continue
                texel[..., :3] *= shade
                target = colour[ya:yb, xa:xb]
                target[mask] = texel[mask]
                region[mask] = z[mask]
    out = Image.fromarray(np.clip(np.round(colour), 0, 255).astype(np.uint8))
    out = out.convert("RGBa").resize((ICON, ICON), Image.BOX).convert("RGBA")
    return png_bytes(out)


def render_cached(task):
    """task = (key, job, cache folder): the cache is passed, as a worker process has the module's defaults."""
    key, job, cache = task
    path = os.path.join(cache, key[:2], key + ".png")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return key, f.read()
    data = render_icon(job)
    write_bytes(path, data)
    return key, data


def icon_task(model, tints=None):
    """What an icon of a model is drawn from, and its key (the same model and textures, the same key):
    ("flat", key, layers), ("3d", key, render job), ("image", key, PNG bytes) or ("empty", "empty", None).
    tints: {tintindex: rgb} (a flat model's layer index is its tintindex)."""
    tints = tints or {}
    if model.kind == "flat":
        layers = []
        for i, ref in enumerate(model.layers):
            info = texture_info(ref, model.vanilla)
            if info:
                layers.append((info[0], info[1], tints.get(i)))
            elif ref and not model.vanilla:
                warn("%s: no texture %s" % (model.ref, ref))
        key = hashlib.sha1(json.dumps(["flat", RENDER_VERSION, [(file_sha(p), f, t) for p, f, t in layers]]).encode()).hexdigest()
        return "flat", key, layers
    elements = model.elements if model.kind == "3d" else None
    if elements is None and model.vanilla:
        proxy = builtin_proxy(model)
        if isinstance(proxy, bytes):
            return "image", hashlib.sha1(proxy).hexdigest(), proxy
        elements = proxy
    if not elements:
        return "empty", "empty", None
    textures, by_ref = {}, {}
    out = []
    for element in elements:
        if "from" not in element or "to" not in element:
            continue
        e = dict(element, faces={})
        for face, spec in (element.get("faces") or {}).items():
            if not isinstance(spec, dict):
                continue
            ref = spec.get("_texture") or model.face_texture(spec)
            info = texture_info(ref, model.vanilla)
            if not info:
                continue
            textures[ref] = info
            if spec.get("tintindex") in tints:
                by_ref[ref] = tints[spec["tintindex"]]
            e["faces"][face] = dict(spec, _texture=ref)
        out.append(e)
    job = {"elements": out, "textures": textures, "tints": by_ref, "gui": model.display.get("gui", {}), "light": model.gui_light}
    key = hashlib.sha1(json.dumps(["3d", RENDER_VERSION, out, {r: (file_sha(p), f) for r, (p, f) in textures.items()},
                                   by_ref, job["gui"], job["light"]], sort_keys=True, default=str).encode()).hexdigest()
    return "3d", key, job


def render_icons(tasks, jobs):
    """{key: PNG bytes} for icon_task results: flat ones drawn here, 3D ones on `jobs` processes (or from the cache)."""
    icons = {"empty": png_bytes(Image.new("RGBA", (ICON, ICON)))}
    renders = {}
    for kind, key, what in tasks:
        if key in icons or key in renders:
            continue
        if kind == "flat":
            icons[key] = png_bytes(flat_icon(what))
        elif kind == "image":
            icons[key] = what
        elif kind == "3d":
            renders[key] = what
    work = [(key, job, ICON_CACHE) for key, job in sorted(renders.items())]
    if jobs > 1 and len(work) > 50:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            for key, data in pool.map(render_cached, work, chunksize=16):
                icons[key] = data
    else:
        for task in work:
            key, data = render_cached(task)
            icons[key] = data
    return icons, len(renders)


# --- vanilla items: the 1.18.2 client jar ------------------------------------------------------------------

# Every 1.18.2 item gets an icon in the pack (bedrock_icons.json "vanilla"), drawn from the Java pack's model of it,
# with the client jar's models and textures where the pack hasn't got them, so the plugin can show any item in a form.
JAVA_VERSION = "1.18.2"
MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
VANILLA = os.path.join(CACHE, "bedrock", "vanilla-" + JAVA_VERSION)
# item models that are only parents of others, or picked by an override or by the game's code, not items
TEMPLATES = {"generated", "handheld", "handheld_rod", "amethyst_bud"}
CODE_MODELS = {"air", "trident_in_hand", "spyglass_in_hand"}
GRASS, FOLIAGE, WATER = (145, 189, 89), (72, 181, 24), (56, 93, 198)
# an item's default colours by tintindex, as ItemColors gives them with no tag (spawn eggs keep their plain texture)
VANILLA_TINTS = dict(
    {name: {0: GRASS} for name in ("grass_block", "grass", "tall_grass", "fern", "large_fern")},
    **{name: {0: FOLIAGE} for name in ("oak_leaves", "jungle_leaves", "acacia_leaves", "dark_oak_leaves", "vine")},
    **{name: {0: (160, 101, 64)} for name in ("leather_helmet", "leather_chestplate", "leather_leggings", "leather_boots",
                                               "leather_horse_armor")},
    **{name: {0: WATER} for name in ("potion", "splash_potion", "lingering_potion", "tipped_arrow")},
    spruce_leaves={0: (97, 153, 97)}, birch_leaves={0: (128, 167, 85)}, lily_pad={0: (113, 195, 92)},
    filled_map={1: (70, 64, 46)}, firework_star={1: (138, 138, 138)})
# DyeColor's colours, for banners
DYES = {"white": 0xF9FFFE, "orange": 0xF9801D, "magenta": 0xC74EBD, "light_blue": 0x3AB3DA, "yellow": 0xFED83D,
        "lime": 0x80C71F, "pink": 0xF38BAA, "gray": 0x474F52, "light_gray": 0x9D9D97, "cyan": 0x169C9C,
        "purple": 0x8932B8, "blue": 0x3C44AA, "brown": 0x835432, "green": 0x5E7C16, "red": 0xB02E26, "black": 0x1D1D21}


def vanilla_jar():
    """The 1.18.2 client jar: MINECRAFT_JAR, the launcher's, or downloaded once into cache/."""
    candidates = [os.environ.get("MINECRAFT_JAR"),
                  os.path.join(os.environ.get("APPDATA", ""), ".minecraft", "versions", JAVA_VERSION, JAVA_VERSION + ".jar"),
                  os.path.expanduser("~/.minecraft/versions/%s/%s.jar" % (JAVA_VERSION, JAVA_VERSION)),
                  os.path.join(CACHE, "minecraft-%s.jar" % JAVA_VERSION)]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    import urllib.request
    path = candidates[-1]
    print("downloading the Minecraft %s client jar into cache/" % JAVA_VERSION)
    with urllib.request.urlopen(MANIFEST, timeout=60) as r:
        manifest = json.load(r)
    url = next(v["url"] for v in manifest["versions"] if v["id"] == JAVA_VERSION)
    with urllib.request.urlopen(url, timeout=60) as r:
        client = json.load(r)["downloads"]["client"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with urllib.request.urlopen(client["url"], timeout=300) as r:
        data = r.read()
    # the jar as Mojang's version file says it is, or nothing is read from it
    if hashlib.sha1(data).hexdigest() != client["sha1"]:
        sys.exit("the downloaded Minecraft %s client jar doesn't match Mojang's SHA-1" % JAVA_VERSION)
    with open(path + ".part", "wb") as f:
        f.write(data)
    os.replace(path + ".part", path)
    return path


_VANILLA_ASSETS = {}


def vanilla_assets():
    """The client jar's assets/minecraft models and textures, extracted once into cache/bedrock/ (which CI caches)."""
    if VANILLA not in _VANILLA_ASSETS:
        done = os.path.join(VANILLA, "extracted")
        if not os.path.exists(done):
            with zipfile.ZipFile(vanilla_jar()) as jar:
                for name in jar.namelist():
                    if name.startswith(("assets/minecraft/models/", "assets/minecraft/textures/")) and not name.endswith("/"):
                        write_bytes(os.path.join(VANILLA, *name.split("/")), jar.read(name))
            write_bytes(done, JAVA_VERSION.encode())
        _VANILLA_ASSETS[VANILLA] = os.path.join(VANILLA, "assets")
    return _VANILLA_ASSETS[VANILLA]


def vanilla_items():
    """Every 1.18.2 item, by its id's name (its item model's): the jar's item models less the templates and the
    models only an override (bow_pulling_0, compass_00) or the game's code (trident_in_hand) picks."""
    folder = os.path.join(vanilla_assets(), "minecraft", "models", "item")
    models = {f[:-5]: read_json(os.path.join(folder, f)) for f in os.listdir(folder) if f.endswith(".json")}
    picked = set()
    for name, model in models.items():
        for override in model.get("overrides", []):
            target = split(full(override["model"]))[1].split("/", 1)[-1]
            if target != name:
                picked.add(target)
    return sorted(n for n in models if n not in picked and n not in CODE_MODELS and n not in TEMPLATES
                  and not n.startswith("template_"))


def vanilla_icon_task(name):
    """The icon of a 1.18.2 item as the Java pack draws it; as the game alone does where the pack's model of it draws
    nothing (a model whose texture the pack hasn't got)."""
    task = ("empty", "empty", None)
    for source in (True, "jar"):
        model = load_model("minecraft:item/" + name, vanilla=source)
        if model is not None:
            task = icon_task(model, VANILLA_TINTS.get(name))
            if task[0] != "empty" and not (task[0] == "flat" and not task[2]):
                return task
    return task


def part_box(lo, hi, uv, size, ref, texture_size, place):
    """An entity model's cube (ModelPart: corners lo, hi in its own space, texOffs uv, size w h d) as an item model
    element in block space, its faces' UVs where ModelPart puts them; place maps a point of the model's space to the
    block's (the renderer's turns and flips)."""
    w, h, d = size
    u, v = uv
    l, m, n, o, p, q = u, u + d, u + d + w, u + d + 2 * w, u + 2 * d + w, u + 2 * d + 2 * w
    r, s, t = v, v + d, v + d + h
    corner = {1: (0, 0, 0), 2: (1, 0, 0), 3: (1, 1, 0), 4: (0, 1, 0), 5: (0, 0, 1), 6: (1, 0, 1), 7: (1, 1, 1), 8: (0, 1, 1)}
    points = {k: np.array(place(tuple(hi[i] if e[i] else lo[i] for i in range(3))), float) for k, e in corner.items()}
    low = np.min(list(points.values()), axis=0)
    high = np.max(list(points.values()), axis=0)
    ends = {k: tuple(int(abs(pt[i] - high[i]) < 1e-6) for i in range(3)) for k, pt in points.items()}
    tw, th = texture_size
    faces = {}
    for verts, (u1, v1, u2, v2) in (((6, 5, 1, 2), (m, r, n, s)), ((3, 4, 8, 7), (n, s, o, r)), ((1, 5, 8, 4), (l, s, m, t)),
                                    ((2, 1, 4, 3), (m, s, n, t)), ((6, 2, 3, 7), (n, s, p, t)), ((5, 6, 7, 8), (p, s, q, t))):
        at = {ends[k]: (cu * 16.0 / tw, cv * 16.0 / th) for k, (cu, cv) in zip(verts, ((u2, v1), (u1, v1), (u1, v2), (u2, v2)))}
        face = next((f for f, c in FACE_CORNERS.items() if set(c) == set(at)), None)
        if face is None:
            continue
        want = [at[c] for c in FACE_CORNERS[face]]
        for turn in range(4):
            base = [want[(k + turn) % 4] for k in range(4)]
            if base[1][1] == base[0][1] and base[3][0] == base[0][0] and base[2] == (base[1][0], base[3][1]):
                faces[face] = {"uv": [base[0][0], base[0][1], base[2][0], base[2][1]], "rotation": turn * 90, "_texture": ref}
                break
    return {"from": [float(x) for x in low], "to": [float(x) for x in high], "faces": faces}


def crop_icon(ref, box, tint=None):
    info = texture_info(ref, True)
    if not info:
        return None
    return png_bytes(fit(tinted(first_frame(*info).crop(box), tint)))


def builtin_proxy(model):
    """A builtin/entity item (chests, shulker boxes, beds, heads, banners, the shield, the conduit), which Java draws
    with its block entity's renderer: that renderer's boxes as item model elements, or a picture (PNG bytes)."""
    name = split(model.ref)[1].rsplit("/", 1)[-1]
    colour = next((c for c in sorted(DYES, key=len, reverse=True) if name.startswith(c + "_")), None)

    def boxes(ref, size, parts, place):
        if not texture_info(ref, True):
            return None
        return [part_box(lo, hi, uv, dims, ref, size, place) for lo, hi, uv, dims in parts]

    if name in ("chest", "trapped_chest", "ender_chest"):
        ref = "minecraft:entity/chest/" + {"chest": "normal", "trapped_chest": "trapped", "ender_chest": "ender"}[name]
        # ChestRenderer: the chest faces north, the model turned half round
        return boxes(ref, (64, 64), [((1, 0, 1), (15, 10, 15), (0, 19), (14, 10, 14)), ((1, 9, 1), (15, 14, 15), (0, 0), (14, 5, 14)),
                                     ((7, 7, 15), (9, 11, 16), (0, 0), (2, 4, 1))], lambda p: (16 - p[0], p[1], 16 - p[2]))
    if name.endswith("shulker_box"):
        ref = "minecraft:entity/shulker/shulker" + ("_" + colour if colour else "")
        return boxes(ref, (64, 64), [((-8, 16, -8), (8, 24, 8), (0, 28), (16, 8, 16)), ((-8, 8, -8), (8, 20, 8), (0, 0), (16, 12, 16))],
                     lambda p: (p[0] + 8, 24 - p[1], 8 - p[2]))
    if name.endswith("_bed") and colour:
        ref = "minecraft:entity/bed/" + colour
        head = boxes(ref, (64, 64), [((0, 0, 0), (16, 16, 6), (0, 0), (16, 16, 6))], lambda p: (16 - p[0], 9 - p[2], 16 - p[1]))
        foot = boxes(ref, (64, 64), [((0, 0, 0), (16, 16, 6), (0, 22), (16, 16, 6))], lambda p: (16 - p[0], 9 - p[2], -p[1]))
        return (head or []) + (foot or []) or None
    skulls = {"skeleton_skull": ("skeleton/skeleton", (64, 32), False), "wither_skeleton_skull": ("skeleton/wither_skeleton", (64, 32), False),
              "zombie_head": ("zombie/zombie", (64, 64), True), "creeper_head": ("creeper/creeper", (64, 32), False),
              "player_head": ("steve", (64, 64), True)}
    if name in skulls:
        path, size, hat = skulls[name]
        parts = [((-4, -8, -4), (4, 0, 4), (0, 0), (8, 8, 8))]
        if hat:
            parts.append(((-4.25, -8.25, -4.25), (4.25, 0.25, 4.25), (32, 0), (8, 8, 8)))
        # SkullBlockRenderer: on the floor, the model flipped (y down)
        return boxes("minecraft:entity/" + path, size, parts, lambda p: (8 - p[0], -p[1], p[2] + 8))
    if name == "dragon_head":
        return boxes("minecraft:entity/enderdragon/dragon", (256, 256),
                     [((-8, -8, -10), (8, 8, 6), (112, 30), (16, 16, 16)), ((-6, -1, -24), (6, 4, -8), (176, 44), (12, 5, 16)),
                      ((-6, 4, -24), (6, 8, -8), (176, 65), (12, 4, 16))], lambda p: (8 - p[0], 8 - p[1], p[2] + 8))
    if name == "conduit":
        return boxes("minecraft:entity/conduit/base", (32, 16), [((-3, -3, -3), (3, 3, 3), (0, 0), (6, 6, 6))],
                     lambda p: (p[0] + 8, p[1] + 8, p[2] + 8))
    if name.endswith("_banner") and colour:
        rgb = DYES[colour]
        return crop_icon("minecraft:entity/banner_base", (1, 1, 21, 41), ((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255))
    if name == "shield":
        return crop_icon("minecraft:entity/shield_base_nopattern", (1, 1, 13, 23))
    return None


# --- 3D models as Bedrock geometry ------------------------------------------------------------------

def r4(v):
    v = round(float(v), 4)
    return 0.0 if v == 0 else v


def bedrock_cube(element, faces):
    """A Java element as a Bedrock cube with only the given faces ({face: (uv, rotation)} in 0-16 units),
    as java2bedrock and Blockbench convert it: x mirrored, the model's centre at x = z = 0."""
    lo = [float(v) for v in element["from"]]
    hi = [float(v) for v in element["to"]]
    cube = {"origin": [r4(-hi[0] + 8), r4(lo[1]), r4(lo[2] - 8)],
            "size": [r4(hi[0] - lo[0]), r4(hi[1] - lo[1]), r4(hi[2] - lo[2])]}
    rotation = element.get("rotation")
    if rotation and rotation.get("angle"):
        angle = float(rotation["angle"])
        origin = rotation.get("origin", [8, 8, 8])
        cube["pivot"] = [r4(-float(origin[0]) + 8), r4(origin[1]), r4(float(origin[2]) - 8)]
        cube["rotation"] = {"x": [-angle, 0, 0], "y": [0, -angle, 0], "z": [0, 0, angle]}[rotation.get("axis", "y")]
    uv = {}
    inset = 0.008
    for face, (box, turn) in faces.items():
        u1, v1, u2, v2 = [float(v) for v in box]
        su = 1 if u2 >= u1 else -1
        sv = 1 if v2 >= v1 else -1
        if face in ("up", "down"):
            entry = {"uv": [r4(u2 - inset * su), r4(v2 - inset * sv)],
                     "uv_size": [r4(u1 - u2 + 2 * inset * su), r4(v1 - v2 + 2 * inset * sv)]}
        else:
            entry = {"uv": [r4(u1 + inset * su), r4(v1 + inset * sv)],
                     "uv_size": [r4(u2 - u1 - 2 * inset * su), r4(v2 - v1 - 2 * inset * sv)]}
        if turn:
            entry["uv_rotation"] = turn
        uv[face] = entry
    cube["uv"] = uv
    return cube


ITEM_BONES = [
    {"name": "ms_root", "binding": "c.item_slot == 'head' ? 'head' : q.item_slot_to_bone_name(c.item_slot)", "pivot": [0, 8, 0]},
    {"name": "ms_x", "parent": "ms_root", "pivot": [0, 8, 0]},
    {"name": "ms_y", "parent": "ms_x", "pivot": [0, 8, 0]},
]


def display_growth(display):
    """How much bigger than its own box a model is drawn at most: its largest display scale (a head's at 0.625)."""
    grow = 1.0
    for key, spec in (display or {}).items():
        scale = (spec or {}).get("scale") if isinstance(spec, dict) else None
        if scale:
            grow = max(grow, max(abs(float(v)) for v in scale) * (0.625 if key == "head" else 1.0))
    return grow


def item_geometries(model, name):
    """[(geometry json, texture ref, frames, blends)] for a 3D model, one per texture its faces use."""
    by_texture = {}
    order = []
    lowest, highest = [0.0, 0.0, 0.0], [16.0, 16.0, 16.0]
    for element in model.elements:
        if "from" not in element or "to" not in element:
            continue
        for i in range(3):
            lowest[i] = min(lowest[i], float(element["from"][i]), float(element["to"][i]))
            highest[i] = max(highest[i], float(element["from"][i]), float(element["to"][i]))
        lo = [float(v) for v in element["from"]]
        hi = [float(v) for v in element["to"]]
        faces = {}
        for face, spec in (element.get("faces") or {}).items():
            if face not in FACE_CORNERS or not isinstance(spec, dict):
                continue
            ref = model.face_texture(spec)
            if not ref or not texture_info(ref, model.vanilla):
                continue
            box = spec.get("uv") or default_uv(face, lo, hi)
            faces.setdefault(ref, {})[face] = (box, int(spec.get("rotation", 0)) % 360)
        for ref, chosen in faces.items():
            if ref not in by_texture:
                by_texture[ref] = []
                order.append(ref)
            by_texture[ref].append(bedrock_cube(element, chosen))
    # culling bounds hold the model at its largest display scale, lifted onto a stand's head (19.9 px)
    extent = max(max(abs(v - 8) for v in lowest + highest), 8) / 16.0 * display_growth(model.display)
    out = []
    for i, ref in enumerate(order):
        path, frames = texture_info(ref, model.vanilla)
        geometry = {
            # one frame of an animated texture is copied (first_frame), and the UVs only ever cover it
            "description": {"identifier": "geometry.ms.%s.t%d" % (name, i), "texture_width": 16,
                            "texture_height": 16, "visible_bounds_width": r4(extent * 2 + 1),
                            "visible_bounds_height": r4(extent * 2 + 2.75), "visible_bounds_offset": [0, 1.4, 0]},
            "bones": ITEM_BONES + [{"name": "ms_z", "parent": "ms_y", "pivot": [0, 8, 0], "cubes": by_texture[ref]}],
        }
        out.append((geometry, ref, frames, blends(path)))
    return out


_BLENDS = {}


def blends(path):
    """Whether a texture has see-through texels (not just cut-outs), so needs a blending material."""
    if path not in _BLENDS:
        a = np.array(Image.open(path).convert("RGBA"))[..., 3]
        _BLENDS[path] = bool(((a > 25) & (a < 230)).sum() > max(4, a.size // 200))
    return _BLENDS[path]


def display_animations(display, key):
    """The Java display transforms as Bedrock animations on the item bones (java2bedrock's mapping)."""
    def part(name):
        # Java draws a hand without its own transform with the other hand's (mirrored as it draws a left hand)
        if not display.get(name) and name.endswith("lefthand"):
            return display.get(name.replace("lefthand", "righthand")) or {}
        return display.get(name) or {}

    def bones(d, mirror_x, flip_z=False, base=None, head=False):
        rot = d.get("rotation")
        tr = d.get("translation")
        sc = d.get("scale")
        out = {}
        x = {}
        if rot:
            x["rotation"] = [-rot[0], 0, 0]
        if tr:
            k = 0.625 if head else 1.0
            x["position"] = [(-tr[0] if mirror_x else tr[0]) * k, tr[1] * k, (-tr[2] if flip_z else tr[2]) * k]
        if head:
            x["scale"] = [v * 0.625 for v in sc] if sc else 0.625
        elif sc:
            x["scale"] = sc
        if x:
            out["ms_x"] = x
        if rot:
            out["ms_y"] = {"rotation": [0, -rot[1], 0]}
            out["ms_z"] = {"rotation": [0, 0, rot[2]]}
        if base:
            out["ms_root"] = base
        return out

    third = {"rotation": [90, 0, 0], "position": [0, 13, -3]}
    first = {"rotation": [90, 60, -40], "position": [4, 10, 4], "scale": 1.5}
    prefix = "animation.ms.item.%s." % key
    return {
        prefix + "thirdperson_main_hand": {"loop": True, "bones": bones(part("thirdperson_righthand"), True, base=third)},
        prefix + "thirdperson_off_hand": {"loop": True, "bones": bones(part("thirdperson_lefthand"), False, base=third)},
        prefix + "head": {"loop": True, "bones": bones(part("head"), True, base={"position": [0, 19.9, 0]}, head=True)},
        prefix + "firstperson_main_hand": {"loop": True, "bones": bones(part("firstperson_righthand"), True, True, base=first)},
        prefix + "firstperson_off_hand": {"loop": True, "bones": bones(part("firstperson_lefthand"), False, True, base=first)},
    }


def item_attachable(identifier, geometries, textures, anim_key):
    prefix = "animation.ms.item.%s." % anim_key
    desc = {
        "identifier": identifier,
        "materials": {"default": ITEM_MATERIAL, "blend": BLEND_MATERIAL, "enchanted": ITEM_MATERIAL},
        "textures": dict(textures, enchanted="textures/misc/enchanted_item_glint"),
        "geometry": geometries,
        "scripts": {
            "pre_animation": ["v.main_hand = c.item_slot == 'main_hand';", "v.off_hand = c.item_slot == 'off_hand';",
                              "v.head = c.item_slot == 'head';"],
            "animate": [{"thirdperson_main_hand": "v.main_hand && !c.is_first_person"},
                        {"thirdperson_off_hand": "v.off_hand && !c.is_first_person"},
                        {"thirdperson_head": "v.head && !c.is_first_person"},
                        {"firstperson_main_hand": "v.main_hand && c.is_first_person"},
                        {"firstperson_off_hand": "v.off_hand && c.is_first_person"},
                        {"firstperson_head": "c.is_first_person && v.head"}],
        },
        "animations": {"thirdperson_main_hand": prefix + "thirdperson_main_hand",
                       "thirdperson_off_hand": prefix + "thirdperson_off_hand",
                       "thirdperson_head": prefix + "head",
                       "firstperson_main_hand": prefix + "firstperson_main_hand",
                       "firstperson_off_hand": prefix + "firstperson_off_hand",
                       "firstperson_head": "animation.ms.item.disable"},
        "render_controllers": [],
    }
    return desc


# A flat item as item/generated draws it: one pixel thick, the picture on both sides
FLAT_GEOMETRY = "geometry.ms.flat"
FLAT_DISPLAY = {"head": {"rotation": [0, 180, 0], "translation": [0, 13, 7], "scale": [1, 1, 1]},
                "thirdperson_righthand": {"rotation": [0, -90, 55], "translation": [0, 4, 0.5], "scale": [0.85, 0.85, 0.85]},
                "firstperson_righthand": {"rotation": [0, -90, 25], "translation": [1.13, 3.2, 1.13], "scale": [0.68, 0.68, 0.68]}}


def flat_geometry():
    edge = {"north": ([16, 0, 0, 16], 0), "south": ([0, 0, 16, 16], 0), "east": ([0, 0, 1, 16], 0),
            "west": ([15, 0, 16, 16], 0), "up": ([0, 0, 16, 1], 0), "down": ([0, 15, 16, 16], 0)}
    cube = bedrock_cube({"from": [0, 0, 7.5], "to": [16, 16, 8.5]}, edge)
    return {"description": {"identifier": FLAT_GEOMETRY, "texture_width": 16, "texture_height": 16, "visible_bounds_width": 3,
                            "visible_bounds_height": 4, "visible_bounds_offset": [0, 1.4, 0]},
            "bones": ITEM_BONES + [{"name": "ms_z", "parent": "ms_y", "pivot": [0, 8, 0], "cubes": [cube]}]}


def flat_stand_attachable(item_identifier, texture, anim_key):
    """A flat item worn or held by an armour stand - a ground item, a hint, a prop - which Bedrock draws only through an
    attachable. Only for stands: a player's hand keeps Bedrock's own picture of the item."""
    desc = item_attachable(item_identifier + ".stand", {"default": FLAT_GEOMETRY}, {"default": texture}, anim_key)
    desc["item"] = {item_identifier: "q.owner_identifier == 'minecraft:armor_stand'"}
    desc["materials"] = {"default": "entity_alphatest", "enchanted": "entity_alphatest"}
    desc["render_controllers"] = ["controller.render.ms.flat"]
    return desc


# --- worn armour ---------------------------------------------------------------------------------------

BONES = {"body": "body", "right_arm": "rightArm", "left_arm": "leftArm", "right_leg": "rightLeg", "left_leg": "leftLeg"}
PIECE_GROUP = {"chest": "chestplate", "legs": "leggings", "boots": "boots"}
LAYER_HIDDEN = {"chest": "variable.chest_layer_visible = 0.0;", "legs": "variable.leg_layer_visible = 0.0;",
                "boots": "variable.boot_layer_visible = 0.0;"}
PIVOTS = {"body": [0, 24, 0], "rightArm": [-5, 22, 0], "leftArm": [5, 22, 0], "rightLeg": [-1.9, 12, 0], "leftLeg": [1.9, 12, 0]}


def bake_codes(image, colour):
    """A look's texture in the item's colour, as build_armour.py bakes the sheets: exact greys dyed (unless
    alpha 254), alpha 253 a light shade of the colour, anything else its own colour, alpha under 128 clear."""
    px = np.array(image.convert("RGBA")).astype(np.float32)
    a = px[..., 3]
    grey = (px[..., 0] == px[..., 1]) & (px[..., 1] == px[..., 2])
    tint = np.array(colour, np.float32) / 255.0
    light = tint + (1.0 - tint) * 0.55
    rgb = px[..., :3]
    dyed = grey & (a != 254) & (a != 253) & (a >= 128)
    rgb[dyed] *= tint
    rgb[a == 253] *= light
    out = np.zeros(px.shape, np.uint8)
    out[..., :3] = np.clip(np.round(rgb), 0, 255).astype(np.uint8)
    out[..., 3] = np.where(a >= 128, 255, 0)
    out[a < 128] = 0
    return Image.fromarray(out)


def bbmodel_look(path, piece, swaps):
    """A look's Blockbench model as Bedrock bones on the humanoid's, and its textures stacked into one
    atlas: (bones, [(image, y offset, scale x, scale y)] in model order (None where unused), atlas size)."""
    import base64
    model = read_json(path)
    res = model.get("resolution", {"width": 16, "height": 16})
    raw = []
    for t in model.get("textures", []):
        source = t.get("source", "")
        image = None
        if t.get("name") in swaps:
            image = Image.open(swaps[t["name"]]).convert("RGBA")
        elif source.startswith("data:image/png;base64,"):
            image = Image.open(io.BytesIO(base64.b64decode(source.split(",", 1)[1]))).convert("RGBA")
        uw, uh = t.get("uv_width", res["width"]), t.get("uv_height", res["height"])
        if image is not None:
            frame = max(1, round(image.width * uh / uw))
            if image.height >= 2 * frame:
                image = image.crop((0, 0, image.width, frame))
        raw.append((image, uw, uh))
    cubes = {e["uuid"]: e for e in model.get("elements", []) if e.get("type", "cube") == "cube"}
    groups = {g["uuid"]: g for g in model.get("groups", []) if "uuid" in g}
    bones, used = [], set()
    names = set()

    def unique(name):
        base, n = name, 1
        while name in names:
            n += 1
            name = "%s_%d" % (base, n)
        names.add(name)
        return name

    def walk(node, inside, bone):
        if isinstance(node, str):
            cube = cubes.get(node)
            if cube is None or cube.get("export") is False or not inside or bone is None:
                return
            bone["cubes"].append(cube)
            for spec in (cube.get("faces") or {}).values():
                if spec and spec.get("texture") is not None:
                    used.add(spec["texture"])
            return
        if "name" not in node and node.get("uuid") in groups:
            node = dict(groups[node["uuid"]], children=node.get("children", []))
        if node.get("export") is False:
            return
        name = node.get("name", "")
        here = bone
        if name == PIECE_GROUP[piece]:
            inside = True
        elif inside and name in BONES and bone is None:
            here = {"name": unique(BONES[name]), "pivot": PIVOTS[BONES[name]], "cubes": [], "raw": node}
            bones.append(here)
        elif inside and bone is not None:
            origin = node.get("origin", [0, 0, 0])
            rotation = node.get("rotation", [0, 0, 0])
            here = {"name": unique(slug("%s_%s" % (bone["name"], name)) or "part"), "parent": bone["name"],
                    "pivot": [r4(-origin[0]), r4(origin[1]), r4(origin[2])], "cubes": []}
            if any(rotation):
                here["rotation"] = [r4(-rotation[0]), r4(-rotation[1]), r4(rotation[2])]
            bones.append(here)
        for child in node.get("children", []):
            walk(child, inside, here)

    for node in model.get("outliner", []):
        walk(node, False, None)
    # the atlas: the used textures one under another, each at its own pixels
    layout, y, width = [], 0, 1
    for i, (image, uw, uh) in enumerate(raw):
        if i not in used or image is None:
            layout.append(None)
            continue
        layout.append((image, y, image.width / uw, image.height / uh))
        y += image.height
        width = max(width, image.width)
    height = max(1, y)
    out = []
    for bone in bones:
        cubes_out = []
        for cube in bone["cubes"]:
            g = float(cube.get("inflate", 0) or 0)
            lo = [float(v) for v in cube["from"]]
            hi = [float(v) for v in cube["to"]]
            entry = {"origin": [r4(-hi[0]), r4(lo[1]), r4(lo[2])], "size": [r4(hi[i] - lo[i]) for i in range(3)]}
            if g:
                entry["inflate"] = r4(g)
            if any(cube.get("rotation", [0, 0, 0])):
                o = cube.get("origin", [0, 0, 0])
                r = cube["rotation"]
                entry["pivot"] = [r4(-o[0]), r4(o[1]), r4(o[2])]
                entry["rotation"] = [r4(-r[0]), r4(-r[1]), r4(r[2])]
            uv = {}
            for face, spec in (cube.get("faces") or {}).items():
                if not spec or spec.get("texture") is None or face not in FACE_CORNERS:
                    continue
                place = layout[spec["texture"]] if spec["texture"] < len(layout) else None
                if place is None:
                    continue
                _, oy, kx, ky = place
                u1, v1, u2, v2 = [float(v) for v in spec["uv"]]
                u1, u2, v1, v2 = u1 * kx, u2 * kx, v1 * ky + oy, v2 * ky + oy
                face_uv = {"uv": [r4(u1), r4(v1)], "uv_size": [r4(u2 - u1), r4(v2 - v1)]}
                if face in ("up", "down"):
                    face_uv = {"uv": [r4(u2), r4(v2)], "uv_size": [r4(u1 - u2), r4(v1 - v2)]}
                if spec.get("rotation"):
                    face_uv["uv_rotation"] = int(spec["rotation"])
                uv[face] = face_uv
            if uv:
                entry["uv"] = uv
                cubes_out.append(entry)
        b = {k: v for k, v in bone.items() if k not in ("cubes", "raw")}
        if cubes_out:
            b["cubes"] = cubes_out
        out.append(b)
    return out, layout, (width, height)


def atlas_for(layout, size, colour):
    atlas = Image.new("RGBA", size)
    for place in layout:
        if place is None:
            continue
        image, oy, _, _ = place
        atlas.paste(bake_codes(image, colour), (0, oy))
    return atlas


# --- glyphs --------------------------------------------------------------------------------------------

# The fonts whose glyphs are plain icons in the text (no offsets), by font: Bedrock has one font, so only
# these, and only providers sitting on the line (ascent > 0, not far above it).
GLYPH_FONTS = ("emoji",)


def glyph_pages():
    pages = {}
    count = 0
    for font in GLYPH_FONTS:
        path = os.path.join(ASSETS, font, "font", "default.json")
        if not os.path.exists(path):
            continue
        for provider in read_json(path).get("providers", []):
            if provider.get("type") != "bitmap":
                continue
            height = provider.get("height", 8)
            ascent = provider.get("ascent", 0)
            if ascent <= 0 or ascent > height + 2:
                continue
            source = texture_path(re.sub(r"\.png$", "", provider["file"]))
            if not os.path.exists(source):
                warn("glyphs: %s has no %s" % (font, provider["file"]))
                continue
            image = Image.open(source).convert("RGBA")
            rows = provider["chars"]
            ch = image.height // len(rows)
            for r, row in enumerate(rows):
                cw = image.width // len(row)
                for c, char in enumerate(row):
                    code = ord(char)
                    if char in ("\x00", " ") or code > 0xFFFF:
                        continue
                    glyph = image.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))
                    page = pages.setdefault(code >> 8, Image.new("RGBA", (256, 256)))
                    k = 16 / max(cw, ch)
                    g = glyph.resize((max(1, round(cw * k)), max(1, round(ch * k))),
                                     Image.NEAREST if k >= 1 else Image.BOX)
                    cell = code & 0xFF
                    x, y = (cell % 16) * 16, (cell // 16) * 16
                    page.paste(g, (x + (16 - g.width) // 2, y + 16 - g.height))
                    count += 1
    for page, image in sorted(pages.items()):
        write_bytes(os.path.join(PACK, "font", "glyph_%02X.png" % page), png_bytes(image))
    return len(pages), count


# --- sounds ------------------------------------------------------------------------------------------

# Java sound namespaces the main Bedrock pack carries; osrsmidi (the music player's instrument notes, 81 MB) is
# the music pack's (music_pack()).
SOUND_NAMESPACES = ("minecraft", "mob", "skill")
SOUND_CATEGORIES = {"master": "player", "music": "music", "record": "record", "records": "record", "weather": "weather",
                    "block": "block", "blocks": "block", "hostile": "hostile", "neutral": "neutral", "player": "player",
                    "players": "player", "ambient": "ambient", "voice": "player"}


def sounds(namespaces=SOUND_NAMESPACES, pack=None):
    """The Java pack's own sound events as Bedrock sound definitions, with their .ogg files. Geyser plays a Java
    custom sound by its id with "minecraft:" taken off ("levelup.combat", "skill:fishing", "mob:goblin.attack"),
    so those are the event names."""
    pack = pack or PACK
    definitions, files = {}, set()

    def file_of(name, namespace):
        ns, _, path = name.partition(":") if ":" in name else ("minecraft", "", name)
        return ns, path

    for namespace in namespaces:
        path = os.path.join(ASSETS, namespace, "sounds.json")
        if not os.path.exists(path):
            continue
        events = read_json(path)
        for event, spec in events.items():
            entries = []
            pending = list(spec.get("sounds", []))
            depth = 0
            while pending and depth < 200:
                depth += 1
                entry = pending.pop(0)
                if isinstance(entry, str):
                    entry = {"name": entry}
                if entry.get("type") == "event":  # another event's sounds, as Java allows
                    other = events.get(entry["name"].split(":")[-1], {})
                    pending.extend(other.get("sounds", []))
                    continue
                ns, rel = file_of(entry["name"], namespace)
                source = os.path.join(ASSETS, ns, "sounds", *rel.split("/")) + ".ogg"
                if not os.path.exists(source):
                    warn("sound %s:%s plays %s:%s, which isn't in the pack" % (namespace, event, ns, rel))
                    continue
                target = "sounds/ms/%s/%s" % (ns, rel)
                files.add((source, target))
                sound = {"name": target}
                for key in ("volume", "pitch", "stream"):
                    if key in entry:
                        sound[key] = entry[key]
                for _ in range(max(1, min(10, int(entry.get("weight", 1))))):
                    entries.append(sound)
            if not entries:
                continue
            key = event if namespace == "minecraft" else namespace + ":" + event
            definitions[key] = {"category": SOUND_CATEGORIES.get(spec.get("category", "master"), "player"), "sounds": entries}
    for source, target in files:
        os.makedirs(os.path.dirname(os.path.join(pack, *target.split("/"))), exist_ok=True)
        shutil.copyfile(source, os.path.join(pack, *target.split("/")) + ".ogg")
    if definitions:
        write_json(os.path.join(pack, "sounds", "sound_definitions.json"),
                   {"format_version": "1.20.20", "sound_definitions": dict(sorted(definitions.items()))}, pretty=True)
    return len(definitions), len(files)


GUI = os.path.join(ASSETS, "minecraft", "textures", "gui")
# Bedrock's own hud icons the Java pack draws nothing for (its hearts, hunger and armour are blank: the orbs do that)
BLANK_WHEN_JAVA_IS = {
    "sprites/hud/heart/full.png": ["heart", "heart_half", "heart_background", "heart_blink", "heart_flash", "heart_flash_half",
                                   "heart_new", "absorption_heart", "absorption_heart_half", "poison_heart", "poison_heart_half",
                                   "poison_heart_flash", "poison_heart_flash_half", "wither_heart", "wither_heart_half",
                                   "wither_heart_flash", "wither_heart_flash_half", "horse_heart", "horse_heart_half",
                                   "horse_heart_flash", "horse_heart_flash_half"],
    "sprites/hud/food_full.png": ["hunger_background", "hunger_blink", "hunger_effect", "hunger_effect_background",
                                  "hunger_effect_flash_full", "hunger_effect_flash_half", "hunger_effect_full", "hunger_effect_half",
                                  "hunger_flash_full", "hunger_flash_half", "hunger_full", "hunger_half"],
    "sprites/hud/armor_full.png": ["armor_empty", "armor_full", "armor_half"],
}


def gui_image(rel):
    path = os.path.join(GUI, *rel.split("/"))
    return Image.open(path).convert("RGBA") if os.path.exists(path) else None


def blank(image):
    return image is not None and image.getbbox() is None


def ui_texture(name, image, nineslice=None):
    """A Bedrock textures/ui image, with its nine-slice description when it's drawn stretched."""
    write_bytes(os.path.join(PACK, "textures", "ui", name + ".png"), png_bytes(image))
    if nineslice:
        write_json(os.path.join(PACK, "textures", "ui", name + ".json"), nineslice)


def half(image):
    """A Java gui texture drawn at twice the pixels, at Bedrock's own size."""
    return image.resize((max(1, image.width // 2), max(1, image.height // 2)), Image.NEAREST)


def gui_skin():
    """The Java pack's gui look on Bedrock's own screens, from the same textures: its hotbar, selection, XP bar, slots,
    panels, air bubbles and crosshair, and blanks where the Java pack draws nothing (hearts, hunger, armour, the map's
    paper, which would frame the off-hand minimap). Bedrock's screens keep their own layouts. Sizes and nine-slices
    follow the game's own (textures/ui in its vanilla archive)."""
    written = 0
    for source, names in BLANK_WHEN_JAVA_IS.items():
        if blank(gui_image(source)):
            for name in names:
                ui_texture(name, Image.new("RGBA", (9, 9)))
                written += 1
    # the off-hand minimap is a held map: no paper round it, as the Java minimap has none
    write_bytes(os.path.join(PACK, "textures", "map", "map_background.png"), png_bytes(Image.new("RGBA", (16, 16))))
    written += 1
    hotbar = gui_image("sprites/hud/hotbar.png")
    if hotbar is not None:
        bar = half(hotbar)  # 182 x 22: a pixel's edge, then nine 20-pixel slots
        for i in range(9):
            ui_texture("hotbar_%d" % i, hotbar.crop((2 + 40 * i, 0, 42 + 40 * i, 44)))
        ui_texture("hotbar_start_cap", bar.crop((0, 0, 1, 22)))
        ui_texture("hotbar_end_cap", bar.crop((181, 0, 182, 22)))
        written += 11
    selection = gui_image("sprites/hud/hotbar_selection.png")
    if selection is not None:
        ui_texture("selected_hotbar_slot", selection)
        written += 1
    for java, bedrock, middle in (("experience_bar_background", "experiencebarempty", [6, 1, 6, 1]),
                                  ("experience_bar_progress", "experiencebarfull", [1, 0, 1, 0])):
        bar = gui_image("sprites/hud/%s.png" % java)
        if bar is not None:
            bar = half(bar)  # 182 x 5
            piece = Image.new("RGBA", (13, 5))
            piece.paste(bar.crop((0, 0, 6, 5)), (0, 0))
            piece.paste(bar.crop((91, 0, 92, 5)), (6, 0))
            piece.paste(bar.crop((176, 0, 182, 5)), (7, 0))
            ui_texture(bedrock, piece, {"nineslice_size": middle, "base_size": [13, 5]})
            written += 1
    ui_texture("experiencenub", Image.new("RGBA", (11, 5)))
    inventory = gui_image("container/inventory.png")
    if inventory is not None:
        # one of the Java inventory's stone slots, its notched corners kept by the slice
        ui_texture("cell_image", half(inventory.crop((15, 15, 49, 49))), {"nineslice_size": 3, "base_size": [17, 17]})
        written += 1
    panel = gui_image("container/generic_54.png")
    if panel is not None:
        # the Java container's stone frame round its dark inside: its top corners and edges, mirrored for the bottom
        # (the Java panel runs on into the inventory below), round a middle of its inside
        frame = half(panel.crop((3, 8, 349, 263)))  # 173 x 127
        w = frame.width
        top_left, top_right = frame.crop((0, 0, 5, 5)), frame.crop((w - 5, 0, w, 5))
        top = frame.crop((20, 0, 26, 5))
        flip = lambda im: im.transpose(Image.FLIP_TOP_BOTTOM)
        tile = Image.new("RGBA", (16, 16))
        for image, xy in ((top_left, (0, 0)), (top_right, (11, 0)), (flip(top_left), (0, 11)), (flip(top_right), (11, 11)),
                          (top, (5, 0)), (flip(top), (5, 11)), (frame.crop((0, 40, 5, 46)), (0, 5)),
                          (frame.crop((w - 5, 40, w, 46)), (11, 5)), (frame.crop((40, 40, 46, 46)), (5, 5))):
            tile.paste(image, xy)
        ui_texture("dialog_background_opaque", tile, {"nineslice_size": 5, "base_size": [16, 16]})
        written += 1
    for java, bedrock in (("sprites/hud/air.png", "bubble"), ("sprites/hud/air_bursting.png", "bubble_pop")):
        image = gui_image(java)
        if image is not None:
            ui_texture(bedrock, half(image) if image.width > 9 else image)
            written += 1
    # a page of blank glyphs: U+F8FF marks a boss bar to be drawn without its bar (BedrockBossBarListener)
    write_bytes(os.path.join(PACK, "font", "glyph_F8.png"), png_bytes(Image.new("RGBA", (256, 256))))
    # boss bars: the Java pack's white bar, which the hud tints by each bar's colour (bedrock_hud_ui.py)
    for java, name in (("background", "boss_background"), ("progress", "boss_progress")):
        bar = gui_image("sprites/boss_bar/white_%s.png" % java)
        if bar is not None:
            write_bytes(os.path.join(PACK, "textures", "ms", "ui", name + ".png"), png_bytes(bar.resize((182, 5), Image.NEAREST)))
            written += 1
    # titles on the dark panels in OSRS's orange, as the Java pack's window titles are (#FF981F)
    write_json(os.path.join(PACK, "ui", "_global_variables.json"),
               {"$title_text_color": [1.0, 0.596, 0.122], "$pocket_title_text_color": [1.0, 0.596, 0.122]}, pretty=True)
    crosshair = gui_image("sprites/hud/crosshair.png")
    if crosshair is not None:
        ui_texture("cross_hair", crosshair)
        written += 1
    return written


MUSIC_PACK = os.path.join(OUT, "music_pack")
MUSIC_UUID = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://minescape.me/bedrock/music-pack"))
MUSIC_MODULE_UUID = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://minescape.me/bedrock/music-pack/resources"))


def music_pack(version, make_zip):
    """The music player's instrument notes (osrsmidi) as a pack of their own, which Geyser sends beside the main
    one: 81 MB a Bedrock player downloads once, kept out of the main pack so that one stays quick to update."""
    if os.path.isdir(MUSIC_PACK):
        shutil.rmtree(MUSIC_PACK)
    os.makedirs(MUSIC_PACK)
    events, files = sounds(("osrsmidi",), MUSIC_PACK)
    # The server plays each note where the player stands; on Bedrock a held note would stay there as they walk on,
    # so the notes are heard as music is, not from a place (is3D off), on the jukebox slider as Java's RECORDS are.
    definitions_path = os.path.join(MUSIC_PACK, "sounds", "sound_definitions.json")
    if os.path.exists(definitions_path):
        definitions = read_json(definitions_path)
        for definition in definitions["sound_definitions"].values():
            definition["category"] = "record"
            for sound in definition["sounds"]:
                sound["is3D"] = False
        write_json(definitions_path, definitions, pretty=True)
    write_json(os.path.join(MUSIC_PACK, "manifest.json"), {
        "format_version": 2,
        "header": {"name": PACK_NAME + " Music", "description": "MineScape's music player instruments",
                   "uuid": MUSIC_UUID, "version": [1, 0, version], "min_engine_version": MIN_ENGINE},
        "modules": [{"type": "resources", "uuid": MUSIC_MODULE_UUID, "version": [1, 0, version]}],
    }, pretty=True)
    shutil.copyfile(os.path.join(PACK, "pack_icon.png"), os.path.join(MUSIC_PACK, "pack_icon.png"))
    size = zip_pack(os.path.join(OUT, "minescape-music.mcpack"), MUSIC_PACK) if make_zip else 0
    return events, files, size


BLOCK_TABLE = os.path.join(SCRIPTS, "bedrock_block_textures.json")
# Java pack texture -> the Bedrock vanilla texture it stands for, where both games use the same picture layout
VANILLA_TEXTURES = {
    "entity/armorstand/wood.png": ["textures/entity/armor_stand"],  # clear: a mob is only the model on the stand's head
    "entity/sign.png": ["textures/entity/sign"],
    "colormap/grass.png": ["textures/colormap/grass"],
    "colormap/foliage.png": ["textures/colormap/foliage"],
    "environment/sun.png": ["textures/environment/sun"],
    "environment/moon_phases.png": ["textures/environment/moon_phases"],
}


# Bedrock textures of things the Java pack draws nothing for
CLEAR_TEXTURES = ["textures/blocks/itemframe_background", "textures/blocks/glow_item_frame"]


def frame_count(path, image):
    """How many frames an animated Java texture holds: a strip of squares, with a .mcmeta beside it."""
    if not os.path.exists(path + ".mcmeta") or image.height <= image.width or image.height % image.width:
        return 1
    return image.height // image.width


def vanilla_textures():
    """The Java pack's retextures of vanilla blocks and a few entities, at Bedrock's own texture paths, so the world
    looks the same on Bedrock. Blocks go by bedrock_block_textures.json (gen_block_map.py, from the game's
    terrain_texture.json); an animated texture keeps its frames only where Bedrock animates that texture too
    (a flipbook), and is its first frame elsewhere. Java block models and blockstate variants have no Bedrock
    equivalent for vanilla blocks: those blocks get the retexture on Bedrock's own shape."""
    textures = os.path.join(ASSETS, "minecraft", "textures")
    jobs = []
    try:
        table = read_json(BLOCK_TABLE)
    except (OSError, ValueError) as e:
        warn("no block texture table (%s): Bedrock keeps vanilla block textures" % e)
        table = {"textures": {}, "flipbook": []}
    flipbook = set(table.get("flipbook", []))
    for name, targets in table["textures"].items():
        jobs.append((os.path.join(textures, "block", name + ".png"), targets))
    for rel, targets in VANILLA_TEXTURES.items():
        jobs.append((os.path.join(textures, *rel.split("/")), targets))
    written = 0
    # Java's item frame model is empty: frames don't show, only what they hold (a model frame is a custom entity)
    for target in CLEAR_TEXTURES:
        write_bytes(os.path.join(PACK, *target.split("/")) + ".png", png_bytes(Image.new("RGBA", (16, 16))))
        written += 1
    for source, targets in jobs:
        if not os.path.exists(source):
            continue
        image = Image.open(source).convert("RGBA")
        frames = frame_count(source, image)
        for target in targets:
            picture = image if frames > 1 and target in flipbook else first_frame(source, frames)
            write_bytes(os.path.join(PACK, *target.split("/")) + ".png", png_bytes(fit_texture(picture)))
            written += 1
    written += grass_side(textures)
    return written


# Bedrock's tint for a grass block in the inventory (its terrain_texture.json's grass_carried)
GRASS_CARRIED = (0x79, 0xC0, 0x5A)


def grass_side(textures):
    """A grass block's side, which Java draws as two layers - grass_block_side, then grass_block_side_overlay tinted
    by the biome - and Bedrock as one texture, textures/blocks/grass_side, drawn opaque, whose alpha is how much of
    the biome's overlay_color each pixel takes: 255 fully tinted, 0 not at all (checked in the 26.63 client: alpha 0
    stayed grey, 128 half green, 255 full). So the overlay's pixels go in with the overlay's own alpha, the side's
    with alpha 0; the top for a grass block held in the hand (grass_carried) is the top already tinted, as Bedrock's
    own is."""
    side_path = os.path.join(textures, "block", "grass_block_side.png")
    overlay_path = os.path.join(textures, "block", "grass_block_side_overlay.png")
    if not (os.path.exists(side_path) and os.path.exists(overlay_path)):
        return 0
    side = Image.open(side_path).convert("RGBA")
    overlay = Image.open(overlay_path).convert("RGBA").resize(side.size, Image.NEAREST)
    out = Image.new("RGBA", side.size)
    sp, op, px = side.load(), overlay.load(), out.load()
    for y in range(side.height):
        for x in range(side.width):
            r, g, b, a = op[x, y]
            if a:
                px[x, y] = (r, g, b, a)
            else:
                px[x, y] = sp[x, y][:3] + (0,)
    write_bytes(os.path.join(PACK, "textures", "blocks", "grass_side.png"), png_bytes(fit_texture(out)))
    written = 1
    top_path = os.path.join(textures, "block", "grass_block_top.png")
    if os.path.exists(top_path):
        top = Image.open(top_path).convert("RGBA")
        tinted = Image.new("RGBA", top.size)
        tp, cp = top.load(), tinted.load()
        for y in range(top.height):
            for x in range(top.width):
                r, g, b, a = tp[x, y]
                cp[x, y] = (r * GRASS_CARRIED[0] // 255, g * GRASS_CARRIED[1] // 255, b * GRASS_CARRIED[2] // 255, a)
        write_bytes(os.path.join(PACK, "textures", "blocks", "grass_carried.png"), png_bytes(fit_texture(tinted)))
        written += 1
    return written


# --- blocks drawn as other models ------------------------------------------------------------------------

BLOCKSTATES = os.path.join(ASSETS, "minecraft", "blockstates")
BLOCK_TEXTURE_DIR = "textures/ms/b"
# blockstates left to Bedrock: its fire is its own
BLOCK_SKIP = {"fire"}
FULL = {"origin": [-8, 0, -8], "size": [16, 16, 16]}
NO_BOX = {"origin": [0, 0, 0], "size": [0, 0, 0]}
EMPTY_GEOMETRY = "minecraft:geometry.full_block"   # drawn with the clear texture: a block Java shows nothing of


WATERLOGGABLE = ("_fence", "_slab", "_stairs", "_wall", "_coral", "_coral_fan", "_wall_fan")


def full_states(block, overrides):
    """Geyser matches whole Java states: a blockstate file's keys with the properties it leaves out (waterlogged)
    filled in both ways, each key's properties in Minecraft's order (alphabetical)."""
    out = {}
    for state, override in overrides.items():
        props = dict(p.split("=", 1) for p in state.split(",") if "=" in p)
        options = [props]
        if block.endswith(WATERLOGGABLE) and "waterlogged" not in props:
            options = [dict(props, waterlogged=w) for w in ("false", "true")]
        for option in options:
            out[",".join("%s=%s" % (k, option[k]) for k in sorted(option))] = override
    return out


def block_collision(block, state):
    """The vanilla block's collision as Bedrock takes it (a box, or a stair's two), so a Bedrock player walks where a
    Java one does."""
    props = dict(p.split("=", 1) for p in state.split(",") if "=" in p)
    if block.endswith("_slab"):
        kind = props.get("type", "bottom")
        return FULL if kind == "double" else {"origin": [-8, 8 if kind == "top" else 0, -8], "size": [16, 8, 16]}
    if block.endswith("_stairs"):
        top = props.get("half") == "top"
        slab = {"origin": [-8, 8 if top else 0, -8], "size": [16, 8, 16]}
        corner, size = {"east": ([0, -8], [8, 16]), "west": ([-8, -8], [8, 16]), "south": ([-8, 0], [16, 8]),
                        "north": ([-8, -8], [16, 8])}.get(props.get("facing", "north"))
        return [slab, {"origin": [corner[0], 0 if top else 8, corner[1]], "size": [size[0], 8, size[1]]}]
    if block.endswith(("_pressure_plate", "torch", "_coral", "lily_pad", "end_rod", "beetroots")):
        return NO_BOX
    return FULL


BLOCK_SPAN = 29.5   # pixels a block's geometry may span on an axis (Bedrock allows 1 14/16 blocks)


def fit_block(cubes):
    """Cubes shrunk about the block's foot (x = z = 0, y = 0) as far as Bedrock needs: a block's geometry may span
    under 30 pixels on each axis and must reach into the block. Rotated cubes count at their diagonal."""
    lo, hi = [1e9] * 3, [-1e9] * 3
    for cube in cubes:
        o, size = cube["origin"], cube["size"]
        grow = 0.21 * max(size) if cube.get("rotation") else 0.0
        for i in range(3):
            lo[i] = min(lo[i], o[i] - grow)
            hi[i] = max(hi[i], o[i] + size[i] + grow)
    if not cubes:
        return cubes
    if lo[1] < 0:
        # a model dipping under the block's floor is lifted onto it (Bedrock's block starts at y = 0)
        for cube in cubes:
            cube["origin"][1] = r4(cube["origin"][1] - lo[1])
            if "pivot" in cube:
                cube["pivot"][1] = r4(cube["pivot"][1] - lo[1])
        hi[1] -= lo[1]
        lo[1] = 0.0
    scale = 1.0
    for i in range(3):
        if hi[i] - lo[i] > BLOCK_SPAN:
            scale = min(scale, BLOCK_SPAN / (hi[i] - lo[i]))
    # the span also has to sit where Bedrock looks for it: x and z within 15 of the middle, y from 0 to 30
    for i, (least, most) in ((0, (-15, 15)), (1, (0, 30)), (2, (-15, 15))):
        if lo[i] * scale < least and lo[i] < 0:
            scale = min(scale, least / lo[i]) if least else scale
        if hi[i] * scale > most:
            scale = min(scale, most / hi[i])
    if scale >= 0.999:
        return cubes
    for cube in cubes:
        cube["origin"] = [r4(v * scale) for v in cube["origin"]]
        cube["size"] = [r4(v * scale) for v in cube["size"]]
        if "pivot" in cube:
            cube["pivot"] = [r4(v * scale) for v in cube["pivot"]]
    return cubes


def model_cubes(model, name_texture):
    """A Java block model's elements as Bedrock block cubes, each face naming its texture's material instance,
    shrunk to Bedrock's block size where the model is bigger (furniture over two blocks)."""
    cubes = []
    for element in model.elements or []:
        if "from" not in element or "to" not in element:
            continue
        lo, hi = element["from"], element["to"]
        if max(hi[i] - lo[i] for i in range(3)) < 0.01:
            continue  # a point: nothing to draw
        faces, names = {}, {}
        for face, spec in (element.get("faces") or {}).items():
            if face not in FACE_CORNERS or not isinstance(spec, dict):
                continue
            ref = model.face_texture(spec)
            if not ref or not texture_info(ref):
                continue
            box = spec.get("uv") or default_uv(face, [float(v) for v in lo], [float(v) for v in hi])
            faces[face] = (box, int(spec.get("rotation", 0)) % 360)
            names[face] = name_texture(ref)
        if not faces:
            continue
        cube = bedrock_cube(element, faces)
        for face, instance in names.items():
            cube["uv"][face]["material_instance"] = instance
        cubes.append(cube)
    return fit_block(cubes)


def build_blocks():
    """Vanilla blocks the Java pack draws as other models (tables from slabs, chairs from stairs, cabinets, its own
    torches) as Geyser custom block state overrides: the model as Bedrock block geometry, its textures in the pack's
    terrain atlas, the blockstate's turn, and the vanilla block's collision. A state picking among models at random
    takes the likeliest; states whose model is only vanilla's shape retextured are left to the retexture.
    Written to geyser_block_mappings.json for Geyser's custom_mappings folder."""
    if not os.path.isdir(BLOCKSTATES):
        return 0, {}
    terrain, geometries, mappings, instance_of, done = {}, [], {}, {}, set()

    def instance(ref):
        if ref not in instance_of:
            key = "ms_b_" + hashlib.sha1(ref.encode()).hexdigest()[:10]
            path, frames = texture_info(ref)
            target = "%s/%s" % (BLOCK_TEXTURE_DIR, key[5:])
            write_bytes(os.path.join(PACK, *target.split("/")) + ".png", png_bytes(fit_texture(first_frame(path, frames))))
            terrain[key] = {"textures": target}
            instance_of[ref] = key
        return instance_of[ref]

    def materials_for(used):
        out = {key: {"texture": key, "render_method": "alpha_test", "ambient_occlusion": False} for key in sorted(used)}
        out["*"] = dict(out[min(used)]) if used else {"texture": "ms_b_clear", "render_method": "alpha_test"}
        return out

    def geometry_of(model_ref):
        model = load_model(full(model_ref))
        if model is None or model.kind != "3d":
            return None, None
        used = set()

        def named(ref):
            key = instance(ref)
            used.add(key)
            return key
        cubes = model_cubes(model, named)
        if not cubes:
            return EMPTY_GEOMETRY, materials_for(used)
        name = "geometry.ms.block." + slug(split(full(model_ref))[1].replace("/", "_"))
        if name not in done:
            done.add(name)
            geometries.append({"description": {"identifier": name, "texture_width": 16, "texture_height": 16},
                               "bones": [{"name": "root", "pivot": [0, 0, 0], "cubes": cubes}]})
        return name, materials_for(used)

    states = 0
    for file in sorted(os.listdir(BLOCKSTATES)):
        block = file[:-5]
        if not file.endswith(".json") or block in BLOCK_SKIP:
            continue
        spec = read_json(os.path.join(BLOCKSTATES, file))
        overrides = {}
        if "variants" in spec:
            for state, variants in spec["variants"].items():
                options = variants if isinstance(variants, list) else [variants]
                pick = max(options, key=lambda v: v.get("weight", 1))
                geometry, materials = geometry_of(pick["model"])
                if geometry is None:
                    continue  # vanilla's own shape: the retexture does it
                collision = block_collision(block, state)
                selection = FULL if isinstance(collision, list) or collision is NO_BOX else collision
                override = {"geometry": geometry, "material_instances": materials, "collision_box": collision,
                            "selection_box": selection}
                turn = [int(pick.get("x", 0)) % 360, (360 - int(pick.get("y", 0))) % 360, 0]
                if any(turn):
                    override["transformation"] = {"rotation": turn}
                overrides["" if state in ("", "normal") else state] = override
        elif "multipart" in spec:
            # fences drawn without posts: each combination of sides, the parts that apply merged into one geometry
            sides = sorted({k for part in spec["multipart"] for k in (part.get("when") or {})})
            if not sides or len(sides) > 4:
                continue
            for bits in range(1 << len(sides)):
                values = {side: "true" if bits >> i & 1 else "false" for i, side in enumerate(sides)}
                cubes, used = [], set()

                def named(ref):
                    key = instance(ref)
                    used.add(key)
                    return key
                for part in spec["multipart"]:
                    when = part.get("when") or {}
                    if any(values.get(k) != str(v) for k, v in when.items()):
                        continue
                    applies = part["apply"] if isinstance(part["apply"], list) else [part["apply"]]
                    model = load_model(full(applies[0]["model"]))
                    if model is None or model.kind != "3d":
                        continue
                    turn = int(applies[0].get("y", 0)) % 360
                    for cube in model_cubes(model, named):
                        if turn:
                            cube["pivot"], cube["rotation"] = [0, 8, 0], [0, -turn, 0]
                        cubes.append(cube)
                state = ",".join("%s=%s" % (k, values[k]) for k in sides)
                name = "geometry.ms.block.%s_%d" % (block, bits)
                if cubes:
                    geometries.append({"description": {"identifier": name, "texture_width": 16, "texture_height": 16},
                                       "bones": [{"name": "root", "pivot": [0, 0, 0], "cubes": cubes}]})
                overrides[state] = {"geometry": name if cubes else EMPTY_GEOMETRY, "material_instances": materials_for(used),
                                    "collision_box": FULL, "selection_box": FULL}
        if overrides:
            states += len(overrides)
            entry = {"name": "ms_" + block, "only_override_states": True, "included_in_creative_inventory": False}
            if "" in overrides:
                entry.update(overrides.pop(""))
                entry["only_override_states"] = False
            if overrides:
                entry["state_overrides"] = full_states(block, overrides)
            mappings["minecraft:" + block] = entry
    if not mappings:
        return 0, {}
    write_bytes(os.path.join(PACK, *BLOCK_TEXTURE_DIR.split("/"), "clear.png"), png_bytes(Image.new("RGBA", (16, 16))))
    terrain["ms_b_clear"] = {"textures": BLOCK_TEXTURE_DIR + "/clear"}
    write_json(os.path.join(PACK, "models", "blocks", "ms_blocks.geo.json"), {"format_version": "1.16.0", "minecraft:geometry": geometries})
    write_json(os.path.join(PACK, "textures", "terrain_texture.json"),
               {"resource_pack_name": NAMESPACE, "texture_name": "atlas.terrain", "padding": 8, "num_mip_levels": 4,
                "texture_data": terrain}, pretty=True)
    write_json(os.path.join(OUT, "geyser_block_mappings.json"), {"format_version": 1, "blocks": mappings}, pretty=True)
    return states, mappings


# --- item frames: every 3D item as a frame entity ------------------------------------------------------------

# On Java a frame model is an item in a (pack-invisible) item frame; the plugin sends Bedrock viewers such a frame as a
# tagged armour stand, which MineScape's Geyser extension swaps for the item's frame entity (bedrock_entities.json).
# A frame entity is the item's own geometry (its attachable's) and textures, posed by two animations: the frame's
# turns from the entity's properties (FRAME_POSE, shared by all), and the model's fixed display (one per display).
FRAME_POSE = "animation.%s.frame.pose" % NAMESPACE
FRAME_DEPTH, INVISIBLE_DEPTH = 7, 8   # pixels toward the wall an item sits from the block's middle (ItemFrameRenderer)
FRAME_HITBOX = [-0.5, 0, -0.5, 0.5, 1, 0.5]


def euler_zyx(m):
    """Angles (x, y, z) in degrees with m = Rz Ry Rx, the order a Bedrock (Blockbench) rotation turns in."""
    sy = -m[2, 0]
    if abs(sy) < 0.999999:
        y = math.asin(max(-1.0, min(1.0, sy)))
        x = math.atan2(m[2, 1], m[2, 2])
        z = math.atan2(m[1, 0], m[0, 0])
    else:
        y = math.copysign(math.pi / 2, sy)
        x = 0.0
        z = math.atan2(-m[0, 1], m[1, 1])
    return [math.degrees(x), math.degrees(y), math.degrees(z)]


def frame_pose():
    """The frame's turns on the item geometry's bones, all pivoting at the block's middle: Java turns the item x by the
    frame's pitch, then y by 180 minus its yaw, under the entity's half turn (a Bedrock model faces -z), which comes to
    one axis at a time, so one bone (ms_root); then (ms_x) moves it toward the wall, turns it z by its rotation (45
    degrees a step) and halves it. Values are Bedrock rotations (x and y negated, as Blockbench writes them)."""
    facing = "q.property('%s:facing')" % NAMESPACE
    pitch = "%s == 0 ? 90 : (%s == 1 ? -90 : 0)" % (facing, facing)
    yaw = "%s <= 1 ? 0 : (%s == 2 ? -180 : (%s == 4 ? 90 : (%s == 5 ? -90 : 0)))" % (facing, facing, facing, facing)
    depth = "q.property('%s:invisible') ? %d : %d" % (NAMESPACE, INVISIBLE_DEPTH, FRAME_DEPTH)
    spin = "q.property('%s:rotation') * 45" % NAMESPACE
    return {"loop": True, "bones": {"ms_root": {"rotation": [pitch, yaw, 0]},
                                    "ms_x": {"position": [0, 0, depth], "rotation": [0, 0, spin], "scale": 0.5}}}


def frame_display(fixed):
    """A model's fixed display (how Java draws it in a frame) on ms_y: its translation (x mirrored, as the geometry is),
    its x, y, z turns as one Bedrock rotation, and its scale, as Java clamps them. None when it changes nothing."""
    rotation = [float(v) for v in fixed.get("rotation") or (0, 0, 0)]
    translation = [max(-80.0, min(80.0, float(v))) for v in fixed.get("translation") or (0, 0, 0)]
    scale = [max(-4.0, min(4.0, float(v))) for v in fixed.get("scale") or (1, 1, 1)]
    bone = {}
    if any(translation):
        bone["position"] = [r4(-translation[0]), r4(translation[1]), r4(translation[2])]
    if any(rotation):
        x, y, z = euler_zyx(axis_matrix("x", rotation[0]) @ axis_matrix("y", rotation[1]) @ axis_matrix("z", rotation[2]))
        bone["rotation"] = [r4(-x), r4(-y), r4(z)]
    if scale != [1.0, 1.0, 1.0]:
        bone["scale"] = [r4(v) for v in scale]
    return bone or None


# One client entity draws every frame model: the extension sets its model (MODEL_PROPERTY, the frame's index) and the
# model's fixed display (DISPLAY_PROPERTIES), and a render controller per part picks that model's geometry, texture and
# material from arrays. An entity per model was 3,361 files and as many entities registered with Geyser.
FRAME_ENTITY = "%s:frame" % NAMESPACE
MODEL_PROPERTY = "%s:model" % NAMESPACE
FRAME_FIXED = "animation.%s.frame.fixed" % NAMESPACE
EMPTY_GEOMETRY = "geometry.%s.empty" % NAMESPACE
# the fixed display's translation (x, y, z), rotation and scale, as frame_display gives them and Java clamps them
DISPLAY_PROPERTIES = {"px": (-80, 80, 0), "py": (-80, 80, 0), "pz": (-80, 80, 0),
                      "rx": (-180, 180, 0), "ry": (-180, 180, 0), "rz": (-180, 180, 0),
                      "sx": (-4, 4, 1), "sy": (-4, 4, 1), "sz": (-4, 4, 1)}


def frame_fixed():
    """The model's fixed display on ms_y, from the properties the extension sets."""
    q = lambda name: "q.property('%s:%s')" % (NAMESPACE, name)
    return {"loop": True, "bones": {"ms_y": {"position": [q("px"), q("py"), q("pz")],
                                             "rotation": [q("rx"), q("ry"), q("rz")],
                                             "scale": [q("sx"), q("sy"), q("sz")]}}}


def frame_display_values(display):
    """The DISPLAY_PROPERTIES for a frame_display bone (None: none)."""
    display = display or {}
    position = display.get("position", [0, 0, 0])
    rotation = display.get("rotation", [0, 0, 0])
    scale = display.get("scale", [1, 1, 1])
    if not isinstance(scale, list):
        scale = [scale] * 3
    return dict(zip(DISPLAY_PROPERTIES, [r4(v) for v in list(position) + list(rotation) + list(scale)]))


def write_frames(frames):
    """The frame entity, its render controllers and animations; the frames' entries in bedrock_entities.json."""
    ordered = sorted(frames.values(), key=lambda f: f["index"])
    assert [f["index"] for f in ordered] == list(range(len(ordered))), "frame indexes must run 0, 1, 2, ..."
    slots = max([len(f["parts"]) for f in ordered] or [1])
    geometries, textures = {EMPTY_GEOMETRY: "empty"}, {}
    for f in ordered:
        for g, t, _ in f["parts"]:
            geometries.setdefault(g, "g%d" % len(geometries))
            textures.setdefault(t, "t%d" % len(textures))
    placeholder = next(iter(textures.values()), None)
    model = "q.property('%s')" % MODEL_PROPERTY
    controllers = {}
    for i in range(slots):
        g_arr, t_arr, m_arr = [], [], []
        for f in ordered:
            if i < len(f["parts"]):
                g, t, blend = f["parts"][i]
                g_arr.append("Geometry." + geometries[g])
                t_arr.append("Texture." + textures[t])
                m_arr.append("Material.blend" if blend else "Material.default")
            else:
                g_arr.append("Geometry.empty")
                t_arr.append("Texture." + placeholder)
                m_arr.append("Material.default")
        controllers["controller.render.%s.frame_%d" % (NAMESPACE, i)] = {
            "arrays": {"geometries": {"Array.g": g_arr}, "textures": {"Array.t": t_arr}, "materials": {"Array.m": m_arr}},
            "geometry": "Array.g[%s]" % model, "textures": ["Array.t[%s]" % model],
            "materials": [{"*": "Array.m[%s]" % model}]}
    write_json(os.path.join(PACK, "render_controllers", "ms_frames.render_controllers.json"),
               {"format_version": "1.8.0", "render_controllers": controllers})
    add_geometries([{"description": {"identifier": EMPTY_GEOMETRY, "texture_width": 16, "texture_height": 16},
                     "bones": [{"name": "ms_root", "pivot": [0, 0, 0]}]}])
    write_json(os.path.join(PACK, "entity", "ms", "frame.entity.json"), {"format_version": "1.10.0", "minecraft:client_entity": {
        "description": {
            "identifier": FRAME_ENTITY,
            "materials": {"default": ITEM_MATERIAL, "blend": BLEND_MATERIAL},
            "textures": {name: path for path, name in textures.items()},
            "geometry": {name: g for g, name in geometries.items()},
            "render_controllers": list(controllers),
            "animations": {"pose": FRAME_POSE, "fixed": FRAME_FIXED},
            "scripts": {"animate": ["pose", "fixed"]}}}})
    write_json(os.path.join(PACK, "animations", "ms_frames.animation.json"),
               {"format_version": "1.8.0", "animations": {FRAME_POSE: frame_pose(), FRAME_FIXED: frame_fixed()}})
    entries = []
    for f in ordered:
        entries.append({"identifier": FRAME_ENTITY, "kind": "frame", "index": f["index"], "model": f["model"],
                        "match": {"items": sorted(f["items"])}, "hitbox": FRAME_HITBOX, "scale": 1.0,
                        "display": frame_display_values(f["display"])})
    print("  frame entity: %d models, %d parts at most, %d geometries, %d textures"
          % (len(ordered), slots, len(geometries) - 1, len(textures)))
    return entries


# --- the json ui -------------------------------------------------------------------------------------------

def ui_files():
    """The JSON UI, from its generators: the hud (bedrock_hud_ui.py, its textures bedrock_hud_textures.py) and the
    item-grid windows (bedrock_chest_ui.py). A file in ui/
    itself is one of vanilla's screens, merged by name; ours are in folders and listed in ui/_ui_defs.json."""
    import bedrock_chest_ui
    import bedrock_hud_textures
    import bedrock_hud_ui
    written = bedrock_hud_ui.write_all(PACK) + bedrock_chest_ui.write_all(PACK)
    textures = bedrock_hud_textures.write_all(PACK)
    listed = sorted(rel for rel in written if rel.count("/") > 1)
    write_json(os.path.join(PACK, "ui", "_ui_defs.json"), {"ui_defs": listed}, pretty=True)
    return written, textures, listed


# --- the build -----------------------------------------------------------------------------------------

def pack_version():
    for name in ("BEDROCK_PACK_VERSION", "GITHUB_RUN_NUMBER"):
        if os.environ.get(name, "").isdigit():
            return int(os.environ[name])
    try:
        return int(subprocess.check_output(["git", "rev-list", "--count", "HEAD"], cwd=ROOT, text=True).strip())
    except (OSError, subprocess.CalledProcessError, ValueError):
        return 0


def pretty_name(ref):
    name = split(ref)[1].rsplit("/", 1)[-1]
    return re.sub(r"\s+", " ", name.replace("_", " ")).strip().title() or ref


def identifier(material, kind, value):
    if kind == "damage":
        return "%s:%s_d%d" % (NAMESPACE, material, value)
    return "%s:%s_%s" % (NAMESPACE, material, ("n%d" % -value) if value < 0 else value)


BY = {"cmd": "custom_model_data", "damage": "damage"}


def threshold_index(bands, value_of):
    """material -> {"by", <what>: [[threshold, value], ...] ascending, maybe "fallback": the same by the other
    predicate}: an item takes the value of the highest threshold at or under its custom model data (or damage). Custom
    model data first where a material has both, as Geyser's priority does; neighbours with the same value are one."""
    out = {}
    for material, kinds in sorted(bands.items()):
        rules = []
        for kind in [k for k in ("cmd", "damage") if k in kinds]:
            listed = []
            for value, d in sorted(kinds[kind], key=lambda e: e[0]):
                picked = value_of(material, d)
                if not listed or listed[-1][1] != picked:
                    listed.append([value, picked])
            rules.append((kind, listed))
        yield_rule = None
        for kind, listed in reversed(rules):
            rule = {"by": BY[kind], "rules": listed}
            if yield_rule:
                rule["fallback"] = yield_rule
            yield_rule = rule
        out[material] = yield_rule
    return out


def renamed(index, name):
    """threshold_index's rules under the name a file gives them ("icons", "entities")."""
    out = {}
    for material, rule in index.items():
        r = {"by": rule["by"], name: rule["rules"]}
        if "fallback" in rule:
            r["fallback"] = {"by": rule["fallback"]["by"], name: rule["fallback"]["rules"]}
        out[material] = r
    return out


def build(jobs, make_zip):
    started = time.time()
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(PACK)
    os.makedirs(ICON_CACHE, exist_ok=True)

    # 1. the Bedrock items: runs of live overrides that pick the same look; every live override, for the indexes
    definitions = []  # dicts: material, kind, values, ref, armour, priority
    per_material = {}
    bands = {}        # material -> kind -> [(threshold, its definition, or None for the material's own look)]
    for material, listed in overrides().items():
        kinds = {k for k, _, _, _ in listed}
        for kind in ("cmd", "damage"):
            picked = live([e for e in listed if e[0] == kind])
            run = None
            for _, value, ref, armour in picked:
                band = bands.setdefault(material, {}).setdefault(kind, [])
                if ref == "minecraft:item/" + material:
                    run = None  # the material's own look: Bedrock's own item
                    band.append((value, None))
                    continue
                same = run is not None and run["ref"] == ref and armour is None and run["armour"] is None
                if same:
                    run["values"].append(value)
                else:
                    run = {"material": material, "kind": kind, "values": [value], "ref": ref, "armour": armour,
                           "priority": 1 if kind == "cmd" and len(kinds) > 1 else 0}
                    definitions.append(run)
                    per_material[material] = per_material.get(material, 0) + 1
                band.append((value, run))

    # 2. icons: each item's model (a vanilla item model the pack hasn't got, such as item/book, from the client jar),
    # and every 1.18.2 item's, drawn (3D ones in parallel, or from the cache)
    tasks = {}  # (ref, tint) -> icon task
    missing_models = set()
    for d in definitions:
        tint = tuple(d["armour"]["icon_colour"]) if d["armour"] else None
        model = load_model(d["ref"]) or load_model(d["ref"], vanilla=True)
        d["model"] = model
        if model is None:
            missing_models.add(d["ref"])
        elif (d["ref"], tint) not in tasks:
            tasks[(d["ref"], tint)] = icon_task(model, {0: tint} if tint else None)
    for ref in sorted(missing_models):
        warn("no model %s; its items are left to Geyser's default" % ref)
    definitions = [d for d in definitions if d["model"] is not None]
    vanilla_tasks = {name: vanilla_icon_task(name) for name in vanilla_items()}
    icons, rendered = render_icons(list(tasks.values()) + list(vanilla_tasks.values()), jobs)

    # each distinct picture once, named by its content; every Bedrock item's icon key (ms.<its identifier's name>) names
    # its picture in item_texture.json
    icon_files = {}

    def icon_file(data):
        digest = hashlib.sha1(data).hexdigest()[:16]
        if digest not in icon_files:
            icon_files[digest] = "%s/%s" % (ICON_DIR, digest)
            write_bytes(os.path.join(PACK, *ICON_DIR.split("/"), digest + ".png"), data)
        return icon_files[digest]

    vanilla_icons = {name: icon_file(icons[task[1]]) for name, task in vanilla_tasks.items()}
    texture_data = {}
    mappings = {}
    for d in definitions:
        tint = tuple(d["armour"]["icon_colour"]) if d["armour"] else None
        d["identifier"] = identifier(d["material"], d["kind"], d["values"][0])
        d["icon"] = "ms." + d["identifier"].split(":", 1)[1]
        d["icon_path"] = icon_file(icons[tasks[(d["ref"], tint)][1]])
        texture_data[d["icon"]] = {"textures": d["icon_path"]}
        entry = {"bedrock_identifier": d["identifier"],
                 "display_name": d["armour"]["name"].replace("_", " ").title() if d["armour"] else pretty_name(d["ref"])}
        if d["kind"] == "cmd":
            entry = dict(type="legacy", custom_model_data=d["values"][0], **entry)
        else:
            entry = dict(type="definition", model="minecraft:" + d["material"], **entry)
            entry["predicate"] = {"type": "range_dispatch", "property": "damage", "threshold": d["values"][0]}
        if d["priority"]:
            entry["priority"] = d["priority"]
        entry["bedrock_options"] = {"icon": d["icon"], "allow_offhand": True, "display_handheld": bool(d["model"].handheld)}
        if d["armour"]:
            entry["bedrock_options"]["creative_category"] = "equipment"
        mappings.setdefault("minecraft:" + d["material"], []).append(entry)
    write_json(os.path.join(PACK, "textures", "item_texture.json"),
               {"resource_pack_name": NAMESPACE, "texture_name": "atlas.items", "texture_data": texture_data})

    # the plugin's icon index (bedrock/ICONS.md): every vanilla item's icon, and each material's custom ones by threshold
    def icon_of(material, d):
        if d is not None and d.get("icon_path"):
            return d["icon_path"]
        return vanilla_icons.get(material) or warn("%s has overrides but isn't a 1.18.2 item" % material)
    items_index = renamed(threshold_index(bands, icon_of), "icons")
    signature = json.dumps({"vanilla": vanilla_icons, "items": items_index}, sort_keys=True)
    icon_index = {"build": hashlib.sha1(signature.encode()).hexdigest()[:12], "vanilla": vanilla_icons, "items": items_index}
    write_json(os.path.join(OUT, "bedrock_icons.json"), icon_index)

    # 3. attachables: 3D models in the hand and on the head, the same geometry their frame entities draw; models with
    # the same cubes share a geometry
    geometry_done = {}   # model ref -> [(geometry id, texture path in pack, blends)]
    geometry_names = {}  # geometry name -> model ref
    geometry_ids = {}    # a geometry's content -> its identifier
    geometries_written = 0
    frames = {}          # (parts, fixed display) -> frame: index, parts, display, model, items
    animations = {"animation.ms.item.disable": {"loop": True, "bones": {"ms_root": {"scale": 0}}}}
    anim_keys = {}
    copied_textures = set()
    attachables = 0
    max_layers = 0
    flat_attachables = 0
    for d in definitions:
        model = d["model"]
        if d["armour"]:
            continue
        if model.kind == "flat":
            display = dict(FLAT_DISPLAY, **{k: v for k, v in model.display.items() if v})
            display = {k: display.get(k) for k in ("thirdperson_righthand", "thirdperson_lefthand", "head",
                                                   "firstperson_righthand", "firstperson_lefthand")}
            dkey = hashlib.sha1(json.dumps(display, sort_keys=True).encode()).hexdigest()[:12]
            if dkey not in anim_keys:
                anim_keys[dkey] = True
                animations.update(display_animations(display, dkey))
            write_json(os.path.join(PACK, "attachables", "ms", "flat", d["identifier"].split(":", 1)[1] + ".json"),
                       {"format_version": "1.10.0", "minecraft:attachable": {"description": flat_stand_attachable(d["identifier"], d["icon_path"], dkey)}})
            flat_attachables += 1
            continue
        if model.kind != "3d":
            continue
        if d["ref"] not in geometry_done:
            ns, path = split(d["ref"])
            name = slug("%s_%s" % (ns, path.replace("/", "_")))
            if geometry_names.get(name, d["ref"]) != d["ref"]:
                name += "_" + hashlib.sha1(d["ref"].encode()).hexdigest()[:8]
            geometry_names[name] = d["ref"]
            parts, new = [], []
            for geometry, ref, frame_count_, blend in item_geometries(model, name):
                description = geometry["description"]
                content = json.dumps([{k: v for k, v in description.items() if k != "identifier"}, geometry["bones"]], sort_keys=True)
                gid = geometry_ids.setdefault(hashlib.sha1(content.encode()).hexdigest(), description["identifier"])
                if gid == description["identifier"]:
                    new.append(geometry)
                target = "%s/%s" % (MODEL_TEXTURE_DIR, hashlib.sha1(ref.encode()).hexdigest()[:12])
                if target not in copied_textures:
                    src = texture_info(ref, model.vanilla)[0]
                    dst = os.path.join(PACK, *target.split("/")) + ".png"
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    if frame_count_ > 1 or max(Image.open(src).size) > MAX_TEXTURE:
                        fit_texture(first_frame(src, frame_count_)).save(dst, optimize=True)
                    else:
                        shutil.copyfile(src, dst)
                    copied_textures.add(target)
                parts.append((gid, target, blend))
            if new:
                add_geometries(new)
                geometries_written += len(new)
            geometry_done[d["ref"]] = parts
            display = {k: model.display.get(k) for k in ("thirdperson_righthand", "thirdperson_lefthand", "head",
                                                         "firstperson_righthand", "firstperson_lefthand")}
            dkey = hashlib.sha1(json.dumps(display, sort_keys=True).encode()).hexdigest()[:12]
            if dkey not in anim_keys:
                anim_keys[dkey] = True
                animations.update(display_animations(display, dkey))
            model._anim = dkey
        parts = geometry_done[d["ref"]]
        if not parts:
            continue
        max_layers = max(max_layers, len(parts))
        desc = item_attachable(d["identifier"], {"t%d" % i: g for i, (g, _, _) in enumerate(parts)},
                               {"t%d" % i: t for i, (_, t, _) in enumerate(parts)}, model._anim)
        desc["render_controllers"] = ["controller.render.ms.item_%s%d" % ("b" if b else "t", i)
                                      for i, (_, _, b) in enumerate(parts)]
        write_json(os.path.join(PACK, "attachables", "ms", "items", d["identifier"].split(":", 1)[1] + ".json"),
                   {"format_version": "1.10.0", "minecraft:attachable": {"description": desc}})
        attachables += 1
        # its frame entity: one per look, the items that show it listed as the plugin matches them
        fixed = frame_display(model.display.get("fixed") or {})
        frame = frames.setdefault((tuple(parts), json.dumps(fixed, sort_keys=True)),
                                  {"index": len(frames), "parts": parts, "display": fixed, "model": d["ref"], "items": []})
        for value in d["values"]:
            frame["items"].append(["minecraft:" + d["material"], value if d["kind"] == "cmd" else 0,
                                   value if d["kind"] == "damage" else 0, False])
        d["frame"] = frame["index"]
    write_json(os.path.join(PACK, "animations", "ms_items.animation.json"),
               {"format_version": "1.8.0", "animations": animations})
    write_json(os.path.join(PACK, "models", "entity", "ms", "flat.geo.json"), {"format_version": "1.21.0", "minecraft:geometry": [flat_geometry()]})
    controllers = {"controller.render.ms.flat": {"geometry": "Geometry.default", "materials": [{"*": "Material.default"}],
                                                 "textures": ["Texture.default"]}}
    for i in range(max(1, max_layers)):
        for kind, material in (("t", "Material.default"), ("b", "Material.blend")):
            controllers["controller.render.ms.item_%s%d" % (kind, i)] = {
                "geometry": "Geometry.t%d" % i, "materials": [{"*": material}], "textures": ["Texture.t%d" % i]}
    write_json(os.path.join(PACK, "render_controllers", "ms_items.render_controllers.json"),
               {"format_version": "1.8.0", "render_controllers": controllers}, pretty=True)
    frame_entries = write_frames(frames)
    frame_items = renamed(threshold_index(bands, lambda material, d: d.get("frame", -1) if d is not None else -1), "entities")

    # 4. worn armour: an attachable per armour item, from its look's Blockbench model
    armour_count = 0
    looks_done = {}
    for d in definitions:
        armour = d["armour"]
        if not armour:
            continue
        piece = armour["piece"]
        line = armour["line"]
        look = line["look"]
        bb = os.path.join(ARMOUR_SOURCE, "models", piece, look + ".bbmodel")
        if not os.path.exists(bb):
            warn("%s: no look model armour/models/%s/%s.bbmodel; not drawn when worn" % (armour["name"], piece, look))
            continue
        number = armour["custom_model_data"]
        texture_ref = "%s/%s/%d" % (ARMOUR_TEXTURE_DIR, piece, number)
        texture_file = os.path.join(PACK, *texture_ref.split("/")) + ".png"
        import armour_looks
        swaps = armour_looks.replaced(piece, line, "%s.json %s" % (piece, armour["name"]))
        gkey = (piece, look)
        if gkey not in looks_done:
            bones, layout, size = bbmodel_look(bb, piece, {})
            gid = "geometry.ms.armour.%s.%s" % (piece, slug(look))
            add_geometries([{
                "description": {"identifier": gid, "texture_width": size[0], "texture_height": size[1],
                                "visible_bounds_width": 3, "visible_bounds_height": 3,
                                "visible_bounds_offset": [0, 1, 0]},
                "bones": bones}])
            looks_done[gkey] = (gid, size)
        gid, size = looks_done[gkey]
        _, layout, size2 = bbmodel_look(bb, piece, swaps) if swaps else (None, None, None)
        if layout is None:
            _, layout, size2 = bbmodel_look(bb, piece, {})
        if size2 != size:
            warn("%s: its swapped textures change the look's atlas size; drawn without them" % armour["name"])
            _, layout, size2 = bbmodel_look(bb, piece, {})
        write_bytes(texture_file, png_bytes(atlas_for(layout, size, armour["colour"])))
        write_json(os.path.join(PACK, "attachables", "ms", "armour", d["identifier"].split(":", 1)[1] + ".json"), {
            "format_version": "1.10.0", "minecraft:attachable": {"description": {
                "identifier": d["identifier"],
                "materials": {"default": "armor", "enchanted": "armor_enchanted"},
                "textures": {"default": texture_ref, "enchanted": "textures/misc/enchanted_actor_glint"},
                "geometry": {"default": gid},
                "scripts": {"parent_setup": LAYER_HIDDEN[piece]},
                "render_controllers": ["controller.render.armor"]}}})
        armour_count += 1

    # 5. glyphs, the JSON UI, the world, sounds, the entities (mobs and props from bedrock_entities.py, the frames above)
    glyph_page_count, glyph_count = glyph_pages()
    ui_written, hud_textures, ui_defs = ui_files()
    retextured = vanilla_textures()
    skinned = gui_skin()
    block_states, block_mappings = build_blocks()
    sound_events, sound_files = sounds()
    import bedrock_entities
    print("  %d geometries in %d files" % (len(GEOMETRIES), write_geometries()))
    contract = bedrock_entities.build(PACK, OUT, frame_entries, frame_items)

    # 6. manifest, icon, mappings, zip
    version = pack_version()
    write_json(os.path.join(PACK, "manifest.json"), {
        "format_version": 2,
        "header": {"name": PACK_NAME, "description": "MineScape for Bedrock: items, armour, glyphs, menus and mobs",
                   "uuid": PACK_UUID, "version": [1, 0, version], "min_engine_version": MIN_ENGINE},
        "modules": [{"type": "resources", "uuid": MODULE_UUID, "version": [1, 0, version]}],
    }, pretty=True)
    icon = Image.open(os.path.join(ROOT, "pack.png")).convert("RGBA")
    if icon.width > 256:
        icon = icon.resize((256, 256), Image.LANCZOS)
    write_bytes(os.path.join(PACK, "pack_icon.png"), png_bytes(icon))
    for material in mappings:
        mappings[material].sort(key=lambda e: (-e.get("priority", 0), e.get("custom_model_data", e.get("predicate", {}).get("threshold", 0))))
    write_json(os.path.join(OUT, "geyser_mappings.json"), {"format_version": 2, "items": dict(sorted(mappings.items()))})

    problems = validate(mappings, texture_data, icon_index)
    size = 0
    if make_zip:
        size = zip_pack(os.path.join(OUT, "minescape.mcpack"))
    music_events, music_files, music_size = music_pack(version, make_zip)

    # summary
    total = sum(len(v) for v in mappings.values())
    print("Bedrock pack built in %.0fs: %s" % (time.time() - started, os.path.relpath(OUT, ROOT)))
    print("  items:      %d Bedrock items (%d legacy custom model data, %d damage) over %d materials"
          % (total, sum(1 for d in definitions if d["kind"] == "cmd"), sum(1 for d in definitions if d["kind"] == "damage"), len(mappings)))
    for material, count in sorted(per_material.items(), key=lambda kv: -kv[1]):
        print("              %-22s %d" % (material, count))
    print("  icons:      %d pictures (%d rendered 3D) for %d item icon keys and %d vanilla items (bedrock_icons.json)"
          % (len(icon_files), rendered, len(texture_data), len(vanilla_icons)))
    print("  3D:         %d attachables over %d models, %d geometries, %d model textures, up to %d textures a model"
          % (attachables, sum(1 for v in geometry_done.values() if v), geometries_written, len(copied_textures), max_layers))
    print("  frames:     %d frame entities for the 3D items (%d fixed displays)"
          % (len(frame_entries), len({json.dumps(f["display"], sort_keys=True) for f in frames.values()})))
    print("  flat:       %d attachables for flat items worn or held by armour stands" % flat_attachables)
    print("  armour:     %d worn attachables over %d looks" % (armour_count, len(looks_done)))
    print("  glyphs:     %d glyphs on %d pages" % (glyph_count, glyph_page_count))
    print("  ui:         %s; %d hud textures; ui_defs %d" % (", ".join(ui_written), hud_textures, len(ui_defs)))
    print("  vanilla:    %d Bedrock textures replaced by the Java pack's (blocks, armour stand, colours, sky)" % retextured)
    print("  gui:        %d Bedrock ui textures from the Java pack's gui (hotbar, slots, panels, XP bar; blank hearts and hunger)" % skinned)
    print("  blocks:     %d block states drawn as their Java models over %d blocks (geyser_block_mappings.json)"
          % (block_states, len(block_mappings)))
    print("  sounds:     %d sound events over %d .ogg files" % (sound_events, sound_files))
    print("  music:      %d instrument notes over %d .ogg files, a pack of their own%s"
          % (music_events, music_files, ", minescape-music.mcpack %.1f MB" % (music_size / 1e6) if make_zip else ""))
    print("  entities:   %d (tag %04x) in bedrock_entities.json" % (len(contract["entities"]), contract["tag"]))
    if make_zip:
        print("  pack:       minescape.mcpack, %.1f MB, version 1.0.%d" % (size / 1e6, version))
    if total > MAX_ITEMS:
        problems.append("%d Bedrock items is more than %d" % (total, MAX_ITEMS))
    if WARNINGS:
        print("  %d warnings:" % len(WARNINGS))
        for w in WARNINGS[:60]:
            print("    " + w)
        if len(WARNINGS) > 60:
            print("    ... and %d more" % (len(WARNINGS) - 60))
    if problems:
        print("  %d problems:" % len(problems))
        for p in problems[:40]:
            print("    " + p)
        raise SystemExit(1)


def short_name(name, most=40):
    """A file name short enough for MAX_PATH, still unique: cut, with a hash of the whole name."""
    if len(name) <= most:
        return name
    return name[:most - 9] + "_" + hashlib.sha1(name.encode()).hexdigest()[:8]


def validate(mappings, texture_data, icon_index):
    """Every mapping's icon listed and its picture on disk, every icon index path in the pack, identifiers unique,
    textures within MAX_TEXTURE, every JSON file in the pack valid."""
    problems = []
    for folder, _, files in os.walk(PACK):
        for file in files:
            rel = os.path.relpath(os.path.join(folder, file), PACK).replace(os.sep, "/")
            if len(rel) >= MAX_PATH:
                problems.append("path of %d characters (Bedrock's limit is under %d): %s" % (len(rel), MAX_PATH, rel))
            if file.endswith(".png"):
                with Image.open(os.path.join(folder, file)) as image:
                    if max(image.size) > MAX_TEXTURE:
                        problems.append("texture %dx%d over %d pixels on a side (crashes Bedrock past 16,384): %s"
                                        % (image.width, image.height, MAX_TEXTURE, rel))
            elif file.endswith(".json"):
                try:
                    read_json(os.path.join(folder, file))
                except ValueError as e:
                    problems.append("%s: %s" % (rel, e))

    def in_pack(path):
        return os.path.exists(os.path.join(PACK, *path.split("/")) + ".png")

    for key, entry in texture_data.items():
        if not in_pack(entry["textures"]):
            problems.append("item_texture.json %s: no %s.png" % (key, entry["textures"]))
    seen = set()
    for material, entries in mappings.items():
        for e in entries:
            ident = e["bedrock_identifier"]
            if ident in seen:
                problems.append("duplicate identifier %s" % ident)
            seen.add(ident)
            if not re.fullmatch(r"[a-z0-9_.]+:[a-z0-9_.]+", ident):
                problems.append("identifier %s has characters Bedrock doesn't take" % ident)
            if e["bedrock_options"]["icon"] not in texture_data:
                problems.append("%s: icon %s isn't in item_texture.json" % (ident, e["bedrock_options"]["icon"]))
    paths = list(icon_index["vanilla"].values())

    def rule_paths(rule):
        return [p for _, p in rule["icons"]] + (rule_paths(rule["fallback"]) if "fallback" in rule else [])
    for rule in icon_index["items"].values():
        paths += rule_paths(rule)
    for path in sorted(set(paths)):
        if not path or not in_pack(path):
            problems.append("bedrock_icons.json: no %s.png in the pack" % path)
    return problems


def zip_pack(target, tree=None):
    """The pack tree as an .mcpack, in a fixed order with fixed times, so the same pack zips the same."""
    tree = tree or PACK
    entries = []
    for folder, _, files in os.walk(tree):
        for file in files:
            path = os.path.join(folder, file)
            entries.append((os.path.relpath(path, tree).replace(os.sep, "/"), path))
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, path in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if name.endswith((".png", ".ogg")) else zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(path, "rb") as f:
                z.writestr(info, f.read())
    return os.path.getsize(target)


if __name__ == "__main__":
    args = sys.argv[1:]
    jobs = min(8, os.cpu_count() or 1)
    if "--jobs" in args:
        jobs = max(1, int(args[args.index("--jobs") + 1]))
    build(jobs, "--no-zip" not in args)
