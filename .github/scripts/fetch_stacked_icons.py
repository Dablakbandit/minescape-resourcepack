"""
fetch_stacked_icons.py

Writes the quantity icons for stackable items straight out of the local
osrsreboxed-db dumps that already sit next to this script:

    items-cache-data.json     id -> name / "stacked" (which quantity the id draws)
    icons-items-complete.json id -> base64 PNG of the inventory sprite

Unlike fetch_icons_osrsdb.py, which pulls a single sprite off the wiki by name,
this resolves the hidden stack-variant item IDs the cache keeps, so a stack
renders the way it does in OSRS. Most items change at 2, 3, 4 and 5, but not
all: coins and blood money go on to 25, 100, 250, 1000 and 10000, trading sticks
change at 10, 100, 1000 and 10000, an ecto-token only at 2 and 3. Every quantity
the cache has a variant for is written, as <slug>_<quantity>.

A model already at <slug>_<quantity> that draws something other than this
script's texture is left alone (some items' own icon is named after the stack
it shows, e.g. weapon/ranging/adamant_arrow_p_5): that quantity keeps it.

Usage (from resourcepack root):
    python .github/scripts/fetch_stacked_icons.py --set enchanted_bolts
    python .github/scripts/fetch_stacked_icons.py --set enchanted_bolts --dry-run
    python .github/scripts/fetch_stacked_icons.py --item "Ruby bolts (e)" --slug weapon/ranging/ruby_bolts_e
    python .github/scripts/fetch_stacked_icons.py --set seeds --from-quantity 2
    python .github/scripts/fetch_stacked_icons.py --set stacked_singles --quantity 1
    python .github/scripts/fetch_stacked_icons.py --set plain_q5 --quantity 5 --beside
    python .github/scripts/fetch_stacked_icons.py --poison
"""

import argparse
import base64
import json
import os
from io import BytesIO

from PIL import Image

# -- paths --------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ITEMS_JSON = "items-cache-data.json"
ICONS_JSON = "icons-items-complete.json"
TEXTURE_DIR = os.path.join("assets", "minecraft", "textures", "item", "ms")
MODEL_DIR = os.path.join("assets", "ms", "models")
TARGET_SIZE = (32, 32)

# -- named sets ---------------------------------------------------------------

# The 14 enchanted crossbow bolts that hold flint custom_model_data 448-461.
# Slugs follow the weapon/ranging convention the other _1.._5 bolt sets use.
ENCHANTED_BOLTS = [
    ("Opal bolts (e)",         "weapon/ranging/opal_bolts_e"),
    ("Opal dragon bolts (e)",  "weapon/ranging/opal_dragon_bolts_e"),
    ("Jade bolts (e)",         "weapon/ranging/jade_bolts_e"),
    ("Jade dragon bolts (e)",  "weapon/ranging/jade_dragon_bolts_e"),
    ("Pearl bolts (e)",        "weapon/ranging/pearl_bolts_e"),
    ("Topaz bolts (e)",        "weapon/ranging/topaz_bolts_e"),
    ("Topaz dragon bolts (e)", "weapon/ranging/topaz_dragon_bolts_e"),
    ("Sapphire bolts (e)",     "weapon/ranging/sapphire_bolts_e"),
    ("Emerald bolts (e)",      "weapon/ranging/emerald_bolts_e"),
    ("Ruby bolts (e)",         "weapon/ranging/ruby_bolts_e"),
    ("Diamond bolts (e)",      "weapon/ranging/diamond_bolts_e"),
    ("Dragonstone bolts (e)",  "weapon/ranging/dragonstone_bolts_e"),
    ("Onyx bolts (e)",         "weapon/ranging/onyx_bolts_e"),
    ("Onyx dragon bolts (e)",  "weapon/ranging/onyx_dragon_bolts_e"),
]

# Plain ammunition that OSRS draws differently as the stack grows but the pack
# only had a single icon for. Quantity 1 keeps whatever model data it already
# had; only 2-5 are written here.
PLAIN_AMMO = [(f.replace("_", " ").capitalize(), "weapon/ranging/" + f.lower()) for f in [
    "ADAMANT_ARROW", "ADAMANT_BOLTS", "AMETHYST_ARROW", "AMETHYST_BROAD_BOLTS", "BLURITE_BOLTS",
    "BOLT_RACK", "BROAD_ARROWS", "BROAD_BOLTS", "BRONZE_ARROW", "BRONZE_BOLTS", "IRON_ARROW",
    "IRON_BOLTS", "JADE_BOLTS", "MITHRIL_ARROW", "MITHRIL_BOLTS", "ONYX_BOLTS",
    "ONYX_DRAGON_BOLTS", "OPAL_BOLTS", "RUNE_ARROW", "RUNITE_BOLTS", "SILVER_BOLTS",
    "STEEL_ARROW", "STEEL_BOLTS", "TOPAZ_BOLTS", "TRAINING_ARROWS",
]]

# The stackable items below kept a single icon although OSRS draws their stack
# growing. Each was matched to its MineScape item (Items.java, MembersItems.java)
# by name; quantity 1 keeps the item's own icon, so these are run with
# --from-quantity 2. The names are as items-cache-data.json has them (the cache
# still calls javelin tips "javelin heads").

# Poisoned arrows and bolts, the dragon arrows and bolts, and the dragon bolts
# beside the enchanted ones. Their own icon is often named _5 for the stack it
# shows: that quantity keeps it (see the module docstring).
MORE_AMMO = [
    ("Adamant arrow(p)",    "weapon/ranging/adamant_arrow_p"),
    ("Adamant bolts (p)",   "weapon/ranging/adamant_bolts_p"),
    ("Amethyst arrow(p)",   "weapon/ranging/amethyst_arrow_p"),
    ("Blurite bolts (p)",   "weapon/ranging/blurite_bolts_p"),
    ("Bronze arrow(p)",     "weapon/ranging/bronze_arrow_p"),
    ("Bronze bolts (p)",    "weapon/ranging/bronze_bolts_p"),
    ("Dragon arrow",        "weapon/ranging/dragon_arrow"),
    ("Dragon bolts",        "weapon/ranging/dragon_bolts"),
    ("Dragon bolts (p)",    "weapon/ranging/dragon_bolts_p"),
    ("Iron arrow(p)",       "weapon/ranging/iron_arrow_p"),
    ("Jade dragon bolts",   "weapon/ranging/jade_dragon_bolts"),
    ("Mithril arrow(p)",    "weapon/ranging/mithril_arrow_p"),
    ("Mithril bolts (p)",   "weapon/ranging/mithril_bolts_p"),
    ("Opal dragon bolts",   "weapon/ranging/opal_dragon_bolts"),
    ("Rune arrow(p)",       "weapon/ranging/rune_arrow_p"),
    ("Runite bolts (p)",    "weapon/ranging/runite_bolts_p"),
    ("Silver bolts (p)",    "weapon/ranging/silver_bolts_p"),
    ("Steel arrow(p)",      "weapon/ranging/steel_arrow_p"),
    ("Steel bolts (p)",     "weapon/ranging/steel_bolts_p"),
    ("Topaz dragon bolts",  "weapon/ranging/topaz_dragon_bolts"),
]

# What ammunition is fletched from: unfinished bolts, bolt and javelin tips,
# shafts, headless arrows, broad arrowheads. Beside the gem tips already in fletching/.
FLETCHING_PARTS = [
    ("Adamant bolts(unf)",      "fletching/adamant_bolts_unf"),
    ("Amethyst bolt tips",      "fletching/amethyst_bolt_tips"),
    ("Amethyst javelin heads",  "fletching/amethyst_javelin_heads"),
    ("Arrow shaft",             "fletching/arrow_shaft"),
    ("Blurite bolts (unf)",     "fletching/blurite_bolts_unf"),
    ("Broad arrowheads",        "fletching/broad_arrowheads"),
    ("Bronze bolts (unf)",      "fletching/bronze_bolts_unf"),
    ("Dragon bolts (unf)",      "fletching/dragon_bolts_unf"),
    ("Dragon javelin heads",    "fletching/dragon_javelin_heads"),
    ("Dragonstone bolt tips",   "fletching/dragonstone_bolt_tips"),
    ("Headless arrow",          "fletching/headless_arrow"),
    ("Iron bolts (unf)",        "fletching/iron_bolts_unf"),
    ("Jade bolt tips",          "fletching/jade_bolt_tips"),
    ("Mithril bolts (unf)",     "fletching/mithril_bolts_unf"),
    ("Onyx bolt tips",          "fletching/onyx_bolt_tips"),
    ("Opal bolt tips",          "fletching/opal_bolt_tips"),
    ("Runite bolts (unf)",      "fletching/runite_bolts_unf"),
    ("Silver bolts (unf)",      "fletching/silver_bolts_unf"),
    ("Steel bolts (unf)",       "fletching/steel_bolts_unf"),
    ("Topaz bolt tips",         "fletching/topaz_bolt_tips"),
    ("Unfinished broad bolts",  "fletching/unfinished_broad_bolts"),
]

# Seeds and spores, beside each one's own icon in farming/seed/.
SEEDS = [(name, "farming/seed/" + slug) for name, slug in [
    ("Acorn",                  "acorn_seed"),
    ("Apple tree seed",        "apple_tree_seed"),
    ("Asgarnian seed",         "asgarnian_seed"),
    ("Attas seed",             "attas_seed"),
    ("Banana tree seed",       "banana_tree_seed"),
    ("Barley seed",            "barley_seed"),
    ("Belladonna seed",        "belladonna_seed"),
    ("Buchu seed",             "buchu_seed"),
    ("Cabbage seed",           "cabbage_seed"),
    ("Cactus seed",            "cactus_seed"),
    ("Cadavaberry seed",       "cadavaberry_seed"),
    ("Calquat tree seed",      "calquat_tree_seed"),
    ("Celastrus seed",         "celastrus_seed"),
    ("Curry tree seed",        "curry_tree_seed"),
    ("Delphinium seed",        "delphinium_seed"),
    ("Dragonfruit tree seed",  "dragonfruit_tree_seed"),
    ("Dwellberry seed",        "dwellberry_seed"),
    ("Golpar seed",            "golpar_seed"),
    ("Grape seed",             "grape_seed"),
    ("Guam seed",              "guam_seed"),
    ("Hammerstone seed",       "hammerstone_seed"),
    ("Hespori seed",           "hespori_seed"),
    ("Iasor seed",             "iasor_seed"),
    ("Jangerberry seed",       "jangerberry_seed"),
    ("Jute seed",              "jute_seed"),
    ("Kelda seed",             "kelda_seed"),
    ("Krandorian seed",        "krandorian_seed"),
    ("Kronos seed",            "kronos_seed"),
    ("Limpwurt seed",          "limpwurt_seed"),
    ("Magic seed",             "magic_seed"),
    ("Mahogany seed",          "mahogany_seed"),
    ("Maple seed",             "maple_seed"),
    ("Marigold seed",          "marigold_seed"),
    ("Mushroom spore",         "mushroom_spore"),
    ("Nasturtium seed",        "nasturtium_seed"),
    ("Noxifer seed",           "noxifer_seed"),
    ("Onion seed",             "onion_seed"),
    ("Orange tree seed",       "orange_tree_seed"),
    ("Palm tree seed",         "palm_tree_seed"),
    ("Papaya tree seed",       "papaya_tree_seed"),
    ("Pineapple seed",         "pineapple_seed"),
    ("Pink rose seed",         "pink_rose_seed"),
    ("Potato cactus seed",     "potato_cactus_seed"),
    ("Potato seed",            "potato_seed"),
    ("Red rose seed",          "red_rose_seed"),
    ("Redberry seed",          "redberry_seed"),
    ("Redwood tree seed",      "redwood_tree_seed"),
    ("Rosemary seed",          "rosemary_seed"),
    ("Seaweed spore",          "seaweed_spore"),
    ("Snape grass seed",       "snape_grass_seed"),
    ("Snowdrop seed",          "snowdrop_seed"),
    ("Spirit seed",            "spirit_seed"),
    ("Strawberry seed",        "strawberry_seed"),
    ("Sweetcorn seed",         "sweetcorn_seed"),
    ("Teak seed",              "teak_seed"),
    ("Tomato seed",            "tomato_seed"),
    ("Vine seed",              "vine_seed"),
    ("Watermelon seed",        "watermelon_seed"),
    ("White lily seed",        "white_lily_seed"),
    ("White rose seed",        "white_rose_seed"),
    ("Whiteberry seed",        "whiteberry_seed"),
    ("Wildblood seed",         "wildblood_seed"),
    ("Willow seed",            "willow_seed"),
    ("Woad seed",              "woad_seed"),
    ("Yanillian seed",         "yanillian_seed"),
    ("Yew seed",               "yew_seed"),
]]

# Everything else: tokens, herblore secondaries, sweets, trading sticks, rivets.
# Beside each one's own icon, or in misc/ where that sits in an old material folder.
STACK_MISC = [
    ("Purple sweets",        "clues/purple_sweets"),
    ("Amylase crystal",      "herblore/amylase_crystal"),
    ("Lava scale shard",     "herblore/lava_scale_shard"),
    ("Zulrah's scales",      "herblore/zulrahs_scales"),
    ("Ecto-token",           "misc/ecto_token"),
    ("Warrior guild token",  "misc/warrior_guild_token"),
    ("Woad leaf",            "misc/woad_leaf"),
    ("Trading sticks",       "other/trading_sticks"),
    ("Rivets",               "quest/tower_of_life/rivets"),
]

# The (p+) and (p++) arrows and bolts: the cache has no stack variants for them, and their sprite is their (p)
# item's pixel for pixel, so nothing is written for them (the dragon arrows' (p) item is POISONED's "head" kind). Their numbers in leather_horse_armor.json point at
# their (p) item's models (<slug>_1 .. _4, and the (p) item's own old _5 picture for 5).
SHARED_LOOKS = [
    ('Adamant arrow(p+)',    'weapon/ranging/adamant_arrow_p'),
    ('Adamant arrow(p++)',   'weapon/ranging/adamant_arrow_p'),
    ('Adamant bolts (p+)',   'weapon/ranging/adamant_bolts_p'),
    ('Adamant bolts (p++)',  'weapon/ranging/adamant_bolts_p'),
    ('Amethyst arrow(p+)',   'weapon/ranging/amethyst_arrow_p'),
    ('Amethyst arrow(p++)',  'weapon/ranging/amethyst_arrow_p'),
    ('Blurite bolts (p+)',   'weapon/ranging/blurite_bolts_p'),
    ('Blurite bolts (p++)',  'weapon/ranging/blurite_bolts_p'),
    ('Bronze arrow(p+)',     'weapon/ranging/bronze_arrow_p'),
    ('Bronze arrow(p++)',    'weapon/ranging/bronze_arrow_p'),
    ('Bronze bolts (p+)',    'weapon/ranging/bronze_bolts_p'),
    ('Bronze bolts (p++)',   'weapon/ranging/bronze_bolts_p'),
    ('Dragon bolts (p+)',    'weapon/ranging/dragon_bolts_p'),
    ('Dragon bolts (p++)',   'weapon/ranging/dragon_bolts_p'),
    ('Iron arrow(p+)',       'weapon/ranging/iron_arrow_p'),
    ('Iron arrow(p++)',      'weapon/ranging/iron_arrow_p'),
    ('Mithril arrow(p+)',    'weapon/ranging/mithril_arrow_p'),
    ('Mithril arrow(p++)',   'weapon/ranging/mithril_arrow_p'),
    ('Mithril bolts (p+)',   'weapon/ranging/mithril_bolts_p'),
    ('Mithril bolts (p++)',  'weapon/ranging/mithril_bolts_p'),
    ('Rune arrow(p+)',       'weapon/ranging/rune_arrow_p'),
    ('Rune arrow(p++)',      'weapon/ranging/rune_arrow_p'),
    ('Runite bolts (p+)',    'weapon/ranging/runite_bolts_p'),
    ('Runite bolts (p++)',   'weapon/ranging/runite_bolts_p'),
    ('Silver bolts (p+)',    'weapon/ranging/silver_bolts_p'),
    ('Silver bolts (p++)',   'weapon/ranging/silver_bolts_p'),
    ('Steel arrow(p+)',      'weapon/ranging/steel_arrow_p'),
    ('Steel arrow(p++)',     'weapon/ranging/steel_arrow_p'),
    ('Steel bolts (p+)',     'weapon/ranging/steel_bolts_p'),
    ('Steel bolts (p++)',    'weapon/ranging/steel_bolts_p'),
    ("Dragon arrow(p+)",     "weapon/ranging/dragon_arrow_p"),
    ("Dragon arrow(p++)",    "weapon/ranging/dragon_arrow_p"),
]

# Items whose own icon is a picture of the whole stack (often the wiki's image), so with the looks
# above a stack of one drew bigger than a stack of two. Their single icon is written from the cache
# as <slug>_1 (or <slug>_single where _1 is taken) with --quantity 1, and the item's own number in
# leather_horse_armor.json points at it; the old picture's files stay, as other numbers use them.
STACKED_SINGLES = [
    ('Purple sweets',           'clues/purple_sweets'),
    ('Spirit seed',             'farming/seed/spirit_seed'),
    ('Adamant bolts(unf)',      'fletching/adamant_bolts_unf'),
    ('Amethyst bolt tips',      'fletching/amethyst_bolt_tips'),
    ('Amethyst javelin heads',  'fletching/amethyst_javelin_heads'),
    ('Blurite bolts (unf)',     'fletching/blurite_bolts_unf'),
    ('Broad arrowheads',        'fletching/broad_arrowheads'),
    ('Dragon bolts (unf)',      'fletching/dragon_bolts_unf'),
    ('Dragon javelin heads',    'fletching/dragon_javelin_heads'),
    ('Dragonstone bolt tips',   'fletching/dragonstone_bolt_tips'),
    ('Jade bolt tips',          'fletching/jade_bolt_tips'),
    ('Onyx bolt tips',          'fletching/onyx_bolt_tips'),
    ('Opal bolt tips',          'fletching/opal_bolt_tips'),
    ('Topaz bolt tips',         'fletching/topaz_bolt_tips'),
    ('Unfinished broad bolts',  'fletching/unfinished_broad_bolts'),
    ('Amylase crystal',         'herblore/amylase_crystal'),
    ('Lava scale shard',        'herblore/lava_scale_shard'),
    ("Zulrah's scales",         'herblore/zulrahs_scales'),
    ('Warrior guild token',     'misc/warrior_guild_token'),
    ('Trading sticks',          'other/trading_sticks'),
    ('Rivets',                  'quest/tower_of_life/rivets'),
    ('Adamant arrow(p)',        'weapon/ranging/adamant_arrow_p'),
    ('Adamant bolts (p)',       'weapon/ranging/adamant_bolts_p'),
    ('Amethyst arrow(p)',       'weapon/ranging/amethyst_arrow_p'),
    ('Amethyst broad bolts',    'weapon/ranging/amethyst_broad_bolts'),
    ('Blurite bolts',           'weapon/ranging/blurite_bolts'),
    ('Blurite bolts (p)',       'weapon/ranging/blurite_bolts_p'),
    ('Bolt rack',               'weapon/ranging/bolt_rack'),
    ('Broad arrows',            'weapon/ranging/broad_arrows'),
    ('Broad bolts',             'weapon/ranging/broad_bolts'),
    ('Bronze arrow(p)',         'weapon/ranging/bronze_arrow_p'),
    ('Bronze bolts (p)',        'weapon/ranging/bronze_bolts_p'),
    ('Dragon arrow',            'weapon/ranging/dragon_arrow'),
    ('Dragon bolts',            'weapon/ranging/dragon_bolts'),
    ('Dragon bolts (p)',        'weapon/ranging/dragon_bolts_p'),
    ('Iron arrow(p)',           'weapon/ranging/iron_arrow_p'),
    ('Jade bolts',              'weapon/ranging/jade_bolts'),
    ('Jade dragon bolts',       'weapon/ranging/jade_dragon_bolts'),
    ('Mithril arrow(p)',        'weapon/ranging/mithril_arrow_p'),
    ('Mithril bolts (p)',       'weapon/ranging/mithril_bolts_p'),
    ('Onyx bolts',              'weapon/ranging/onyx_bolts'),
    ('Onyx dragon bolts',       'weapon/ranging/onyx_dragon_bolts'),
    ('Opal bolts',              'weapon/ranging/opal_bolts'),
    ('Opal dragon bolts',       'weapon/ranging/opal_dragon_bolts'),
    ('Rune arrow(p)',           'weapon/ranging/rune_arrow_p'),
    ('Runite bolts (p)',        'weapon/ranging/runite_bolts_p'),
    ('Silver bolts (p)',        'weapon/ranging/silver_bolts_p'),
    ('Steel arrow(p)',          'weapon/ranging/steel_arrow_p'),
    ('Steel bolts (p)',         'weapon/ranging/steel_bolts_p'),
    ('Topaz bolts',             'weapon/ranging/topaz_bolts'),
    ('Topaz dragon bolts',      'weapon/ranging/topaz_dragon_bolts'),
]
# Plain items whose quantity-5 look was the old brighter art at <slug>_5: their cache sprite goes beside it as
# <slug>_q5 (--set plain_q5 --quantity 5 --beside).
PLAIN_Q5 = [
    ("Dragon arrow",  "weapon/ranging/dragon_arrow"),
    ("Dragon bolts",  "weapon/ranging/dragon_bolts"),
]

SETS = {
    "enchanted_bolts": ENCHANTED_BOLTS,
    "plain_ammo": PLAIN_AMMO,
    "more_ammo": MORE_AMMO,
    "fletching_parts": FLETCHING_PARTS,
    "seeds": SEEDS,
    "stack_misc": STACK_MISC,
    "stacked_singles": STACKED_SINGLES,
    "plain_q5": PLAIN_Q5,
}


# -- lookup -------------------------------------------------------------------

def resolve_stack_ids(items: dict, name: str) -> dict:
    """
    Return {quantity: item_id}: 1 and every quantity the item has a variant for.

    Quantity 1 is the base item (no "stacked", not a placeholder or note); the
    rest come from the hidden variants whose "stacked" field names the quantity
    at which the game swaps to them (mostly 2-5; see the module docstring).
    Those ids are not always in ascending order, and for some items are
    scattered far from the base - the "stacked" field is what decides, never
    the numbering.
    """
    matches = [v for v in items.values() if v["name"] == name]
    if not matches:
        raise SystemExit("no item named %r in items-cache-data.json" % name)

    base = [
        v for v in matches
        if v.get("stacked") is None and not v.get("placeholder") and not v.get("noted")
    ]
    if not base:
        raise SystemExit("%r has no base (unstacked) item" % name)

    # Some names belong to more than one item (Broad arrows 4150 and 4160, Purple sweets 4561 and
    # 10476): the one that stacks is the one with stack variants. Then the lowest id (Dragon arrow
    # 11212 before 20389, the minigame copy).
    base.sort(key=lambda v: (not v.get("stackable"), v["id"]))
    ids = {1: str(base[0]["id"])}
    for v in matches:
        q = v.get("stacked")
        if q is None or v.get("placeholder"):
            continue
        if q in ids and ids[q] != str(v["id"]):
            # two items share the name (Coins, Orchid seed): which set is meant isn't ours to guess
            raise SystemExit("%r has two variants for %d (%s, %s)" % (name, q, ids[q], v["id"]))
        ids[q] = str(v["id"])

    if len(ids) == 1:
        raise SystemExit("%r has no stack variants" % name)
    return dict(sorted(ids.items()))


# -- output -------------------------------------------------------------------

def decode(raw_b64: str) -> Image.Image:
    return Image.open(BytesIO(base64.b64decode(raw_b64))).convert("RGBA")


def to_texture(raw_b64, crop_to=None) -> Image.Image:
    """
    Decode a cache sprite (or take a decoded one) and centre it on a 32x32 transparent canvas.

    Cropped to its content first, and deliberately not resampled. The sprites
    sit on a 36x32 canvas but the artwork inside fits well within 32x32, so
    scaling only softens every edge into partial alpha, which reads as a blurry,
    washed out icon beside the pack's hand drawn art. Anything genuinely
    oversized is scaled with NEAREST to keep the pixel edges hard.
    """
    image = decode(raw_b64) if isinstance(raw_b64, str) else raw_b64

    bbox = crop_to or image.getbbox()
    if bbox:
        image = image.crop(bbox)
    if image.size[0] > TARGET_SIZE[0] or image.size[1] > TARGET_SIZE[1]:
        image.thumbnail(TARGET_SIZE, Image.NEAREST)

    canvas = Image.new("RGBA", TARGET_SIZE, (0, 0, 0, 0))
    canvas.paste(image, ((TARGET_SIZE[0] - image.width) // 2,
                         (TARGET_SIZE[1] - image.height) // 2))
    return canvas


# -- poison -------------------------------------------------------------------

# The cache draws a poisoned arrow's head a dull olive and a poisoned bolt with one green pixel at its tip:
# beside the plain item, at slot size, a stack of 1-4 poisoned bolts reads as plain ones. The pack's old
# poisoned art (the item's own icon, <slug>_5, now only kept for the old materials that name it) has clearly
# green tips. So the poisoned looks keep the cache's shapes at every quantity and repaint the poison: the
# pixels where the poisoned sprite differs from the plain one of the same quantity, grown down a bolt's tip,
# in the green of the old art's tips, by the plain sprite's shading, the dark outline and the shadow left alone.
# One green for every item, the old poisoned bolts' (the old arrows' is an olive that reads as a bronze head at
# slot size), lifted by two lighter tones so a tip of a few pixels still reads as green on the dark slot.
POISON_GREEN_FROM = "weapon/ranging/bronze_bolts_p"
POISON_LIFT = (1.3, 1.6)
OUTLINE = (0, 0, 1)
SHADOW = (48, 32, 32)          # 0x302020, the cache's drop shadow
BOLT_TIP = [(0, 1), (-1, 2), (0, 2), (-2, 3), (-1, 3)]   # a bolt's tip below its one green pixel (bolts point up and right)
BOLT_BRIGHT = 0.4      # a bolt's tip is a few pixels: its shading uses the lighter part of the green only
# Dragon arrow(p) has no sprites of its own in the cache, so it is the plain dragon arrow's at each quantity with
# its head painted (kind "head"): the head is the arrow's pale metal, every pixel whose green is at least
# HEAD_GREEN of its red (the shaft and fletching are red).
HEAD_GREEN = 0.75
# An arrow's heads: the cache marks only part of some heads as poisoned (a dot on a single arrow, nothing on the
# rear arrows of a stack), so every arrow (p) paints its whole heads: the pixels where the plain arrows of these
# metals, which share their shapes, differ from each other at that quantity.
ARROW_METALS = ["Bronze arrow", "Iron arrow", "Steel arrow", "Mithril arrow", "Adamant arrow", "Rune arrow",
                "Amethyst arrow"]
# Adamant's own heads and tips are green, so its poison is the old poisoned arrows' yellow-green, lifted, and only
# its brighter half: a lime that differs from adamant in hue and in brightness.
GREEN_BODIED = ("Adamant",)
LIME_FROM = "weapon/ranging/bronze_arrow_p"
LIME_BRIGHT = 0.5

POISONED = [(name, name.replace(" (p)", "").replace("(p)", ""), "weapon/ranging/" + slug, kind)
            for name, slug, kind in [
                ("Adamant arrow(p)",   "adamant_arrow_p",   "arrow"),
                ("Amethyst arrow(p)",  "amethyst_arrow_p",  "arrow"),
                ("Bronze arrow(p)",    "bronze_arrow_p",    "arrow"),
                ("Iron arrow(p)",      "iron_arrow_p",      "arrow"),
                ("Mithril arrow(p)",   "mithril_arrow_p",   "arrow"),
                ("Rune arrow(p)",      "rune_arrow_p",      "arrow"),
                ("Steel arrow(p)",     "steel_arrow_p",     "arrow"),
                ("Adamant bolts (p)",  "adamant_bolts_p",   "bolt"),
                ("Blurite bolts (p)",  "blurite_bolts_p",   "bolt"),
                ("Bronze bolts (p)",   "bronze_bolts_p",    "bolt"),
                ("Dragon bolts (p)",   "dragon_bolts_p",    "bolt"),
                ("Mithril bolts (p)",  "mithril_bolts_p",   "bolt"),
                ("Runite bolts (p)",   "runite_bolts_p",    "bolt"),
                ("Silver bolts (p)",   "silver_bolts_p",    "bolt"),
                ("Steel bolts (p)",    "steel_bolts_p",     "bolt"),
                ("Dragon arrow(p)",    "dragon_arrow_p",    "head"),
            ]]


def luminance(c) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def poison_ramp(slug: str = POISON_GREEN_FROM) -> list:
    """The poison greens of the old art at <slug>_5, darkest first (green, with little blue: not adamant),
    and the brightest lifted by POISON_LIFT."""
    with open(os.path.join(MODEL_DIR, slug + "_5.json"), encoding="utf-8") as fh:
        ref = json.load(fh)["textures"]["layer0"]
    namespace, path = ref.split(":", 1) if ":" in ref else ("minecraft", ref)
    image = Image.open(os.path.join("assets", namespace, "textures", path + ".png")).convert("RGBA")
    greens = {p[:3] for p in image.getdata()
              if p[3] and p[1] > p[0] + 8 and p[1] > p[2] + 8 and p[2] < p[1] * 0.5}
    if len(greens) < 3:
        raise SystemExit("%s_5 has no poison green to sample" % slug)
    ramp = sorted(greens, key=luminance)
    top = ramp[-1]
    return ramp + [tuple(min(255, round(c * f)) for c in top) for f in POISON_LIFT]


def arrow_heads(items: dict, icons: dict, quantity: int) -> set:
    """The arrowhead pixels of ARROW_METALS' plain sprites at this quantity (where they differ from each other)."""
    images = [decode(icons[resolve_stack_ids(items, metal)[quantity]]) for metal in ARROW_METALS]
    alpha = {tuple(p[3] > 0 for p in image.getdata()) for image in images}
    if len(alpha) != 1:
        raise SystemExit("the plain arrows' shapes differ at %d" % quantity)
    w, h = images[0].size
    loaded = [image.load() for image in images]
    return {(x, y) for x in range(w) for y in range(h) if len({px[x, y] for px in loaded}) > 1}


def poison_texture(poisoned_b64: str, plain_b64: str, ramp: list, kind: str, heads=frozenset(),
                   bright: float = 0.0) -> Image.Image:
    poisoned, plain = decode(poisoned_b64), decode(plain_b64)
    if poisoned.size != plain.size:
        raise SystemExit("poisoned and plain sprites differ in size")
    w, h = poisoned.size
    pp, pl = poisoned.load(), plain.load()

    def paintable(x, y):
        if not (0 <= x < w and 0 <= y < h):
            return False
        c = pp[x, y]
        return c[3] and c[:3] != OUTLINE and c[:3] != SHADOW

    if kind == "head":
        mask = {(x, y) for x in range(w) for y in range(h)
                if paintable(x, y) and pl[x, y][1] >= HEAD_GREEN * pl[x, y][0]}
    else:
        mask = {(x, y) for x in range(w) for y in range(h) if pp[x, y] != pl[x, y] and paintable(x, y)}
    if kind == "arrow":
        mask |= {xy for xy in heads if paintable(*xy)}
    if kind == "bolt":
        mask |= {(x + dx, y + dy) for x, y in mask for dx, dy in BOLT_TIP if paintable(x + dx, y + dy)}
    if not mask:
        raise SystemExit("no poison found")
    shade = {xy: luminance(pl[xy]) for xy in mask}
    low, high = min(shade.values()), max(shade.values())
    out = poisoned.copy()
    po = out.load()
    for xy, l in shade.items():
        t = (l - low) / (high - low) if high > low else 0.75
        if kind == "bolt":
            t = BOLT_BRIGHT + (1 - BOLT_BRIGHT) * t
        t = bright + (1 - bright) * t
        po[xy] = ramp[round(t * (len(ramp) - 1))] + (255,)
    return to_texture(out, crop_to=poisoned.getbbox())


def draws_own_texture(path: str, slug: str) -> bool:
    """True if there is no model at path yet, or it is one this script wrote for slug."""
    if not os.path.exists(path):
        return True
    with open(path, encoding="utf-8") as fh:
        layer0 = json.load(fh).get("textures", {}).get("layer0")
    return layer0 == "item/ms/%s" % slug


def write_model(slug: str, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n") as fh:
        json.dump(
            {"parent": "item/handheld", "textures": {"layer0": "item/ms/%s" % slug}},
            fh,
            indent=4,
        )
        fh.write("\n")


# -- main ---------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", choices=sorted(SETS), help="A named set of items to write.")
    parser.add_argument("--item", help="A single OSRS item name (needs --slug).")
    parser.add_argument("--slug", help="Model path under ms:, e.g. weapon/ranging/ruby_bolts_e")
    parser.add_argument("--from-quantity", type=int, default=1, choices=[1, 2],
                        help="Lowest quantity to write. Pass 2 to leave the single-item icon alone.")
    parser.add_argument("--quantity", type=int,
                        help="Write only this quantity, e.g. 1 for --set stacked_singles.")
    parser.add_argument("--beside", action="store_true",
                        help="Where <slug>_<quantity> draws something else, write <slug>_q<quantity> beside it.")
    parser.add_argument("--poison", action="store_true",
                        help="The poisoned arrows and bolts (POISONED), quantities 1-5, their poison repainted.")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing.")
    parser.add_argument("--data-dir", default=SCRIPT_DIR,
                        help="Where the two dumps are (default: beside this script; they aren't committed).")
    args = parser.parse_args()

    if args.poison:
        targets = []
    elif args.set:
        targets = SETS[args.set]
    elif args.item and args.slug:
        targets = [(args.item, args.slug)]
    else:
        parser.error("pass --set, or both --item and --slug")

    items = json.load(open(os.path.join(args.data_dir, ITEMS_JSON), encoding="utf-8"))
    icons = json.load(open(os.path.join(args.data_dir, ICONS_JSON), encoding="utf-8"))

    written = 0
    for name, slug in targets:
        stack_ids = resolve_stack_ids(items, name)
        print("%s  ->  %s  %s" % (name, slug, stack_ids))

        for quantity, item_id in stack_ids.items():
            if quantity < args.from_quantity or (args.quantity is not None and quantity != args.quantity):
                continue
            out = "%s_%d" % (slug, quantity)
            if quantity == 1 and not draws_own_texture(os.path.join(MODEL_DIR, out + ".json"), out):
                # a single icon of the item's own already holds _1: the cache's goes beside it
                out = "%s_single" % slug
            elif args.beside and not draws_own_texture(os.path.join(MODEL_DIR, out + ".json"), out):
                out = "%s_q%d" % (slug, quantity)
            texture_path = os.path.join(TEXTURE_DIR, out + ".png")
            model_path = os.path.join(MODEL_DIR, out + ".json")

            if not draws_own_texture(model_path, out):
                print("  kept %s: it draws something else already" % model_path)
                continue

            if args.dry_run:
                print("  DRY  would write %s (id %s) and %s" % (texture_path, item_id, model_path))
                continue

            os.makedirs(os.path.dirname(texture_path), exist_ok=True)
            to_texture(icons[item_id]).save(texture_path)
            write_model(out, model_path)
            written += 1

        print()

    for name, plain_name, slug, kind in (POISONED if args.poison else []):
        plain_ids = resolve_stack_ids(items, plain_name)
        poisoned_ids = plain_ids if kind == "head" else resolve_stack_ids(items, name)
        lime = name.startswith(GREEN_BODIED)
        ramp = poison_ramp(LIME_FROM) if lime else poison_ramp()
        print("%s  ->  %s  (%s; %d greens)" % (name, slug, kind, len(ramp)))
        for quantity in range(1, 6):
            out = "%s_%d" % (slug, quantity)
            if not draws_own_texture(os.path.join(MODEL_DIR, out + ".json"), out):
                # the old picture keeps its name for what still uses it: this goes beside it
                out = "%s_q%d" % (slug, quantity)
            texture_path = os.path.join(TEXTURE_DIR, out + ".png")
            model_path = os.path.join(MODEL_DIR, out + ".json")
            if args.dry_run:
                print("  DRY  would write %s and %s" % (texture_path, model_path))
                continue
            os.makedirs(os.path.dirname(texture_path), exist_ok=True)
            heads = arrow_heads(items, icons, quantity) if kind == "arrow" else frozenset()
            poison_texture(icons[poisoned_ids[quantity]], icons[plain_ids[quantity]], ramp, kind, heads,
                           LIME_BRIGHT if lime else 0.0).save(texture_path)
            write_model(out, model_path)
            written += 1

    print("Done. %d icon(s) written." % written)


if __name__ == "__main__":
    main()
