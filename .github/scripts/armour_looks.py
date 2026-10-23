"""How each leather armour item looks worn, for the armour shader (see build_shaders.py).

armour/chest.json, armour/legs.json and armour/boots.json at the pack's root define every armour item
of that piece: its custom model data (10000 + its tile, 1 to 511), the look it wears (a Blockbench model
armour/models/<piece>/<name>.bbmodel, whose texture <name>.png is the flat look, or plain), the colour
that look is dyed where it is grey, its inventory icon (count_icons.py colours it the same) and its
shape. build_armour.py bakes each item's look in its colour into a tile of the armour sheets, and the
tables here tell the shader which sheet tile each item's tile is, and its shape; items that look the
same share a sheet tile.

The plugin puts an item's tile in its dye, (dye >> 13) & 511 (ItemCount); the shader draws that tile
as it is, coloured already, and for skirts and robes hangs the leggings from the waist. Tile 0 is the
plain look dyed by the dye itself: leather the plugin doesn't define.

Layer 1 draws chestplates and boots: its tile n holds chest item n's look on the body and arms and
boots item n's on the legs, each piece showing only its own boxes. Layer 2 draws leggings.

Pure Python: CI's shader build imports it.
"""
import base64, hashlib, json, os, re

# The shapes a piece has unless its item says otherwise: leggings' own legs, a body with nothing below
# the waist.
LEGS = 0
TORSO_NONE = 0

# An item's tile, 0 to 511 (the dye's nine bits); its custom model data is 10000 + it.
TILES = 512
CUSTOM_MODEL_DATA = 10000
# Tiles across a sheet; each tile is one armour texture at the pack's 256x128.
COLUMNS = 8
TILE = (256, 128)
PIECES = ("chest", "legs", "boots")
SHAPES = {"chest": ("none", "fauld", "jerkin", "tunic"), "legs": ("legs", "skirt", "robe", "skirt_over_legs"),
          "boots": ("none",)}


# The looks' sources, at the pack's root: the models, and the plain looks (which have none).
SOURCE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "armour"))
MODELS = os.path.join(SOURCE, "models")
# where each model's flat look is written out for the build to read (gitignored)
EXTRACTED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "cache", "armour_looks"))
LAYER_PARTS = {1: ("chest", "boots"), 2: ("legs",)}


def plain_file(part):
    return os.path.join(SOURCE, "plain", part + ".png")


def look_file(part, name):
    """The flat look <name>.png embedded in armour/models/<part>/<name>.bbmodel, written out to a file
    (rewritten only when it changed); None if there is no such model."""
    model = os.path.join(MODELS, part, name + ".bbmodel")
    if not os.path.exists(model):
        return None
    textures = json.load(open(model, encoding="utf-8")).get("textures", [])
    texture = next((t for t in textures if t.get("name") == name + ".png"), None)
    source = (texture or {}).get("source", "")
    if not source.startswith("data:image/png;base64,"):
        raise ValueError("armour/models/%s/%s.bbmodel has no embedded texture %s.png, its flat look" % (part, name, name))
    data = base64.b64decode(source.split(",", 1)[1])
    path = os.path.join(EXTRACTED, part, name + ".png")
    if not os.path.exists(path) or open(path, "rb").read() != data:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
    return path


def items(piece):
    """tile -> the piece's item: {look (its file's path), colour (r, g, b), shape (a number), icon, name},
    from armour/<piece>.json, checked."""
    path = os.path.join(SOURCE, piece + ".json")
    found = {}
    for entry in json.load(open(path, encoding="utf-8"))["items"]:
        where = "%s.json %s" % (piece, entry.get("name", entry.get("custom_model_data")))
        tile = entry["custom_model_data"] - CUSTOM_MODEL_DATA
        if not 1 <= tile < TILES:
            raise ValueError("%s: custom model data is %d to %d" % (where, CUSTOM_MODEL_DATA + 1, CUSTOM_MODEL_DATA + TILES - 1))
        if tile in found:
            raise ValueError("%s: custom model data %d is %s's already" % (where, entry["custom_model_data"], found[tile]["name"]))
        look = plain_file(piece) if entry["look"] == "plain" else look_file(piece, entry["look"])
        if look is None:
            raise ValueError("%s: no look armour/models/%s/%s.bbmodel" % (where, piece, entry["look"]))
        colour = entry["colour"].lstrip("#")
        if not re.fullmatch(r"[0-9a-fA-F]{6}", colour):
            raise ValueError("%s: colour %r is not #rrggbb" % (where, entry["colour"]))
        shape = entry.get("shape", SHAPES[piece][0])
        if shape not in SHAPES[piece]:
            raise ValueError("%s: shape %r is none of %s" % (where, shape, ", ".join(SHAPES[piece])))
        found[tile] = {"look": look, "colour": tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4)),
                       "shape": SHAPES[piece].index(shape), "icon": entry["icon"], "name": entry.get("name", str(tile)),
                       "custom_model_data": entry["custom_model_data"]}
    return found


def tiles(layer):
    """(the layer's distinct sheet tiles in order, each a (look file, colour) per part of the layer, the
    colour None for the plain tile dyed by the shader; each item tile's sheet tile). Tile 0 is plain."""
    parts = LAYER_PARTS[layer]
    defined = [items(part) for part in parts]
    digests = {}

    def digest(path):
        if path not in digests:
            digests[path] = hashlib.sha1(open(path, "rb").read()).hexdigest()
        return digests[path]

    plain = tuple((plain_file(part), None) for part in parts)
    keys = [tuple((digest(f), c) for f, c in plain)]
    order, index = [plain], [0]
    for tile in range(1, TILES):
        spec = tuple((d[tile]["look"], d[tile]["colour"]) if tile in d else (plain_file(part), None)
                     for d, part in zip(defined, parts))
        if all(c is None for _, c in spec):
            index.append(0)
            continue
        key = tuple((digest(f), c) for f, c in spec)
        if key not in keys:
            keys.append(key)
            order.append(spec)
        index.append(keys.index(key))
    return order, index


# OptiFine's armour rules (build_armour.py), matching an item's custom model data: by NBT before 1.20.5
# (the base folder's, for every client reading no overlays), its component from 1.20.5 (pack format
# 32), as floats from 1.21.4 (46). From 1.21.2 (42) OptiFine gives an item's tile to every leather layer,
# the models' too, so there it is the tile without the models.
# (overlay directory, first format, last format or None, rule)
CIT_MATCH = [(None, None, None, "nbt.CustomModelData=%d"),
             ("cit_1_20_5", 32, 41, "components.custom_model_data=%d"),
             ("cit_1_21_2", 42, 45, "components.custom_model_data=%d"),
             ("cit_1_21_4", 46, None, "components.custom_model_data.floats.0=regex:%d([.]0+)?[fF]?")]
CIT_FLAT_FROM = 42

# The armour models' overlays (armour_models.py), leather's equipment asset as each range of releases
# has it: (overlay directory, first format, last format or None)
MODEL_OVERLAYS = [("armour_models_1_21_2", 42, 45), ("armour_models_1_21_4", 46, 74),
                  ("armour_models_1_21_11", 75, 83), ("armour_models_26_1", 84, None)]


def glsl():
    """The tables as GLSL: each item tile's sheet tile, and its shape."""
    def array(name, values):
        return "const int %s[%d] = int[](%s);\n" % (name, TILES, ", ".join(str(v) for v in values))
    chest, legs = items("chest"), items("legs")
    return (array("MS_TILE_1", tiles(1)[1])
            + array("MS_TILE_2", tiles(2)[1])
            + array("MS_SHAPE_1", [chest[t]["shape"] if t in chest else TORSO_NONE for t in range(TILES)])
            + array("MS_SHAPE_2", [legs[t]["shape"] if t in legs else LEGS for t in range(TILES)])
            # the sheets' rows of looks (the traced models' data comes below them)
            + "const int MS_SHEET_ROWS_1 = %d;\nconst int MS_SHEET_ROWS_2 = %d;\n"
            % (-(-len(tiles(1)[0]) // COLUMNS), -(-len(tiles(2)[0]) // COLUMNS)))
