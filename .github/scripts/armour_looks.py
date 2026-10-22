"""How each leather armour item looks worn, for the armour shader (see build_shaders.py).

armour/chest.json, armour/legs.json and armour/boots.json at the pack's root define every armour item
of that piece: its custom model data (10000 + its tile, 1 to 511), the look it wears (a file
armour/<piece>/<name>.png, or plain), the colour that look is dyed where it is grey, its inventory icon
(count_icons.py colours it the same) and its shape. build_armour.py bakes each item's look in its
colour into a tile of the armour sheets, and the tables here tell the shader which sheet tile each
item's tile is, and its shape; items that look the same share a sheet tile.

The plugin puts an item's tile in its dye, (dye >> 13) & 511 (ItemCount); the shader draws that tile
as it is, coloured already, and for skirts and robes hangs the leggings from the waist. Tile 0 is the
plain look dyed by the dye itself: leather the plugin doesn't define.

Layer 1 draws chestplates and boots: its tile n holds chest item n's look on the body and arms and
boots item n's on the legs, each piece showing only its own boxes. Layer 2 draws leggings.

The look files are named by the old LeatherArmourType numbers, and the tables below map those numbers
to looks for build_armour.py --split, which painted them from code (armour_art.py).

Pure Python: CI's shader build imports it.
"""

GODS = ("guthix", "saradomin", "zamorak", "armadyl", "ancient", "bandos")

# Shapes the leggings can take: their own legs; a plateskirt to below the knee, legs hidden; a robe
# to the ankle; a plateskirt over legs still worn (Guthan's wraps, Karil's leggings).
LEGS, SKIRT, ROBE, SKIRT_OVER_LEGS = 0, 1, 2, 3

# layer 1, chestplates: number -> chest look
CHEST = {
    40: "graceful", 48: "studded", 49: "builders", 50: "snakeskin", 51: "studded_light", 52: "studded_gold",
    53: "verac", 54: "torag", 55: "karil", 56: "guthan", 57: "dharok", 58: "ahrim",
    59: "mystic", 60: "mystic", 61: "mystic", 62: "mystic",
    63: "robe_light", 64: "leather_gold", 65: "dhide_light", 66: "robe", 67: "hardleather", 68: "leather",
    69: "robe_gold", 70: "robe", 71: "gown_gold", 72: "gown", 73: "dhide_gold", 74: "dhide",
    75: "chain_light", 76: "chain_gold", 77: "chain", 78: "body_light", 79: "body_gold",
}
# GUTHIX .. BANDOS _PLATEBODY are 5 .. 0
CHEST.update({5 - i: "body_" + god for i, god in enumerate(GODS)})

# Shapes a chestplate's body can take below the waist: none, a plate fauld, a jerkin, a tunic.
TORSO_NONE, FAULD, JERKIN, TUNIC = 0, 1, 2, 3
# layer 1, chestplates: number -> torso shape
TORSO = {57: FAULD, 54: FAULD, 56: FAULD, 55: JERKIN, 58: TUNIC}

# layer 1, boots: number -> boots look
BOOTS = {58: "lightness", 59: "graceful", 60: "builders", 61: "snakeskin", 62: "gardening", 63: "mystic",
         64: "armour", 65: "leather",
         30: "fighting", 31: "fancy", 32: "ranger", 33: "rogue", 34: "spiked", 35: "climbing", 36: "climbing_gilded",
         37: "decorative_gold", 38: "decorative_red", 39: "decorative_white", 40: "holy_sandals", 41: "insulated",
         42: "mime", 43: "skeleton", 44: "zombie", 45: "splitbark", 46: "swampbark", 47: "bloodbark", 48: "zealots",
         49: "wizard", 50: "stone", 51: "santa", 52: "chicken"}

# layer 2, leggings: number -> (legs look, shape)
LEGGINGS = {
    43: ("graceful", LEGS), 44: ("studded", LEGS), 45: ("builders", LEGS), 46: ("snakeskin", LEGS),
    47: ("studded_light", LEGS), 48: ("studded_gold", LEGS),
    49: ("verac", SKIRT), 50: ("torag", LEGS), 51: ("karil", SKIRT_OVER_LEGS), 52: ("guthan", SKIRT_OVER_LEGS),
    53: ("dharok", LEGS), 54: ("ahrim", ROBE),
    55: ("mystic", ROBE), 56: ("mystic", ROBE), 57: ("mystic", ROBE), 58: ("mystic", ROBE),
    59: ("robe_light", ROBE), 60: ("dhide_light", LEGS), 61: ("dhide_gold", LEGS), 62: ("dhide", LEGS),
    63: ("robe", ROBE), 64: ("robe_gold", ROBE), 65: ("robe", ROBE), 66: ("robe_gold", ROBE), 67: ("robe", ROBE),
    68: ("chaps_gold", LEGS), 69: ("chaps", LEGS),
    70: ("skirt_light", SKIRT), 71: ("skirt_gold", SKIRT), 72: ("skirt", SKIRT),
    73: ("legs_light", LEGS), 74: ("legs_gold", LEGS),
}
# GUTHIX .. BANDOS _PLATESKIRT are 11 .. 6, _PLATELEGS 5 .. 0
LEGGINGS.update({11 - i: ("skirt_" + god, SKIRT) for i, god in enumerate(GODS)})
LEGGINGS.update({5 - i: ("legs_" + god, LEGS) for i, god in enumerate(GODS)})

import hashlib, json, os, re

LOOKS = 128
# An item's tile, 0 to 511 (the dye's nine bits); its custom model data is 10000 + it.
TILES = 512
CUSTOM_MODEL_DATA = 10000
# Tiles across a sheet; each tile is one armour texture at the pack's 256x128.
COLUMNS = 8
TILE = (256, 128)
PIECES = ("chest", "legs", "boots")
SHAPES = {"chest": ("none", "fauld", "jerkin", "tunic"), "legs": ("legs", "skirt", "robe", "skirt_over_legs"),
          "boots": ("none",)}


def layer_1(number):
    """(chest look, boots look) of a layer 1 number."""
    return CHEST.get(number, "plain"), BOOTS.get(number, "plain")


def layer_2(number):
    """(legs look, shape) of a layer 2 number."""
    return LEGGINGS.get(number, ("plain", LEGS))


# The look files, at the pack's root.
SOURCE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "armour"))
LAYER_PARTS = {1: ("chest", "boots"), 2: ("legs",)}
FILE = re.compile(r"(\d+)_[A-Za-z0-9_]+\.png$")


def files(part):
    """number -> the look file of that number for the part."""
    found = {}
    folder = os.path.join(SOURCE, part)
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        match = FILE.match(name)
        if not match:
            continue
        number = int(match.group(1))
        if number >= LOOKS:
            raise ValueError("%s/%s: looks are numbered 0 to %d" % (part, name, LOOKS - 1))
        if number in found:
            raise ValueError("%s: two files for %d, %s and %s" % (part, number, os.path.basename(found[number]), name))
        found[number] = os.path.join(folder, name)
    return found


def plain_file(part):
    return os.path.join(SOURCE, part, "plain.png")


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
        look = plain_file(piece) if entry["look"] == "plain" else os.path.join(SOURCE, piece, entry["look"] + ".png")
        if not os.path.exists(look):
            raise ValueError("%s: no look armour/%s/%s.png" % (where, piece, entry["look"]))
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
