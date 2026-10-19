"""Which look each leather armour item wears, for the armour shader (see build_shaders.py).

The server tells clients an item's look in the low three bits of each channel of its dye colour:
nine bits, 0b10 then the look's number, which is the item's LeatherArmourType model value
(LeatherArmourType.java in the plugin). The shader reads it, draws that look's tile of the armour
sheet (build_armour.py paints them, from armour_art.py) and, for skirts and robes, hangs the
leggings from the waist.

Numbers are per armour layer. Layer 1 draws chestplates and boots: a number's tile holds the chest
look of that number on the body and arms, and the boots look of it on the legs. Layer 2 draws
leggings, each with a shape. A number not listed is the plain look: the current platebody,
platelegs or armour boots.

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

LOOKS = 128
# Tiles across a sheet; each tile is one armour texture at the pack's 256x128.
COLUMNS = 8
TILE = (256, 128)


def layer_1(number):
    """(chest look, boots look) of a layer 1 number."""
    return CHEST.get(number, "plain"), BOOTS.get(number, "plain")


def layer_2(number):
    """(legs look, shape) of a layer 2 number."""
    return LEGGINGS.get(number, ("plain", LEGS))


def tiles(layer):
    """The layer's distinct tiles in sheet order, the plain one first."""
    looks = layer_1 if layer == 1 else (lambda n: layer_2(n)[0])
    names = [looks(-1)]
    for number in range(LOOKS):
        if looks(number) not in names:
            names.append(looks(number))
    return names


def glsl():
    """The tables as GLSL: each number's tile, and each layer's shape."""
    def array(name, values):
        return "const int %s[%d] = int[](%s);\n" % (name, LOOKS, ", ".join(str(v) for v in values))
    one, two = tiles(1), tiles(2)
    return (array("MS_TILE_1", [one.index(layer_1(n)) for n in range(LOOKS)])
            + array("MS_TILE_2", [two.index(layer_2(n)[0]) for n in range(LOOKS)])
            + array("MS_SHAPE_1", [TORSO.get(n, TORSO_NONE) for n in range(LOOKS)])
            + array("MS_SHAPE_2", [layer_2(n)[1] for n in range(LOOKS)]))
