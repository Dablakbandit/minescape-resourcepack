"""Builds the armour sheets from the look files in armour/ (see armour_looks.py), for the armour shader
(build_shaders.py) to pick between. The pack's build runs it; run it yourself to see a change in game:

    python .github/scripts/build_armour.py

A look file is a whole 256x128 armour texture (Minecraft's 64x32 layout, four texels a pixel), of
which only its part's boxes are read: the body and arms for chest, the legs for boots, the legs and
body for legs. Exact greys are dyed by the item's colour, any other colour keeps its own, alpha 253
dyes a grey a light shade of the dye, and alpha under 128 is clear.

The looks were first painted in code (armour_art.py, armour_barrows.py, armour_boots.py, over the
plain armour in .github/armour). --split paints any look that has no file yet, named after the
plugin's LeatherArmourType:

    python .github/scripts/build_armour.py --split ../minescape.me/modules/minescape-items/src/main/java/me/minescape/gameplay/items/LeatherArmourType.java

The top right texel of a sheet marks it as one: (255, 0, 255, alpha 1), green 128 on the leggings'.
"""
import os, re, sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
import armour_art as art
import armour_looks as looks

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PAINT_SOURCE = os.path.join(ROOT, ".github", "armour")
TEXTURES = os.path.join(ROOT, "assets", "minecraft", "textures")
# up to 1.21.1, and the equipment assets' own from 1.21.2
OUTPUTS = {
    1: ["models/armor/leather_layer_1.png", "entity/equipment/humanoid/leather.png"],
    2: ["models/armor/leather_layer_2.png", "entity/equipment/humanoid_leggings/leather.png"],
}
OVERLAYS = {
    1: ["entity/equipment/humanoid/leather_overlay.png"],
    2: ["entity/equipment/humanoid_leggings/leather_overlay.png"],
}
# Each part's boxes on the texture, as (u0, v0, u1, v1) in model pixels.
AREAS = {"chest": art.CHEST_AREA, "boots": art.BOOTS_AREA, "legs": [(0, 16, 40, 32)]}


def read(path, part):
    """A look file as a canvas in the sheets' alpha codes, only its part's boxes kept."""
    px = np.array(Image.open(path).convert("RGBA"))
    if px.shape[:2] != (looks.TILE[1], looks.TILE[0]):
        raise ValueError("%s is %dx%d, not %dx%d" % (path, px.shape[1], px.shape[0], looks.TILE[0], looks.TILE[1]))
    alpha = px[..., 3]
    grey = (px[..., 0] == px[..., 1]) & (px[..., 1] == px[..., 2])
    code = np.where(alpha == art.LIGHT, art.LIGHT, np.where(grey & (alpha != art.OWN), art.TINTED, art.OWN))
    out = px.copy()
    out[..., 3] = np.where(alpha >= 128, code, 0)
    out[alpha < 128] = 0
    c = art.Canvas()
    c.copy(art.Canvas(out), AREAS[part])
    return c


def tile(layer, paths):
    if layer == 1:
        chest, boots = paths
        c = read(chest, "chest")
        art.neckline(c)
        c.copy(read(boots, "boots"), art.BOOTS_AREA)
        art.rims(c, 1)
        return c.px
    c = read(paths[0], "legs")
    art.rims(c, 2)
    return c.px


def sheet(layer):
    order, _ = looks.tiles(layer)
    w, h = looks.TILE
    rows = -(-len(order) // looks.COLUMNS)
    out = np.zeros((h * rows, w * looks.COLUMNS, 4), np.uint8)
    for i, paths in enumerate(order):
        x, y = (i % looks.COLUMNS) * w, (i // looks.COLUMNS) * h
        out[y:y + h, x:x + w] = tile(layer, paths)
    out[0, -1] = (255, 0 if layer == 1 else 128, 255, 1)
    return Image.fromarray(out), len(order)


def build():
    for layer in (1, 2):
        image, count = sheet(layer)
        for rel in OUTPUTS[layer]:
            path = os.path.join(TEXTURES, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            image.save(path)
        overlay = Image.open(os.path.join(looks.SOURCE, "layer_%d_overlay.png" % layer))
        for rel in OVERLAYS[layer]:
            path = os.path.join(TEXTURES, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            overlay.save(path)
        print("layer %d: %s, %d tiles" % (layer, image.size, count))


# --- painting the looks from code, once ----------------------------------------------------------------

def painted(part, number):
    """The part's look of that number as the code paints it, in the files' convention."""
    plain = np.array(Image.open(os.path.join(PAINT_SOURCE, "layer_%d.png" % (2 if part == "legs" else 1))).convert("RGBA"))
    plain[..., 3] = (plain[..., 3] > 25) * art.TINTED
    base = art.Canvas(plain)
    if part == "chest":
        canvas = art.chest(looks.layer_1(number)[0] if number >= 0 else "plain", base)
    elif part == "boots":
        canvas = art.boots(looks.layer_1(number)[1] if number >= 0 else "plain", base)
    else:
        canvas = art.legs(looks.layer_2(number)[0] if number >= 0 else "plain", base)
    c = art.Canvas()
    c.copy(canvas, AREAS[part])
    px = c.px.copy()
    own = px[..., 3] == art.OWN
    # an own colour that happens to be an exact grey would read back as dyed
    same = own & (px[..., 0] == px[..., 1]) & (px[..., 1] == px[..., 2])
    px[same, 2] = np.where(px[same, 2] < 255, px[same, 2] + 1, 254)
    px[..., 3] = np.where(px[..., 3] == art.LIGHT, art.LIGHT, np.where(px[..., 3] > 0, 255, 0))
    return Image.fromarray(px)


def leather_types(java):
    """(part, number, name) of each LeatherArmourType: the chest block, then the legs from
    PLATELEGS_NORMAL, the boots from BOOTS, then the god pieces by their names."""
    part, found = "chest", []
    for name, number in re.findall(r"^\s*([A-Z0-9_]+)\(\(short\)\s*(\d+)\)", open(java, encoding="utf-8").read(), re.M):
        if name == "PLATELEGS_NORMAL":
            part = "legs"
        elif name == "BOOTS":
            part = "boots"
        elif name.endswith("_PLATEBODY"):
            part = "chest"
        elif name.endswith(("_PLATELEGS", "_PLATESKIRT")):
            part = "legs"
        found.append((part, int(number), name.lower()))
    return found


def split(java):
    """Writes every look without a file yet as its own file, and each part's plain look."""
    wrote = 0
    for part in ("chest", "boots", "legs"):
        os.makedirs(os.path.join(looks.SOURCE, part), exist_ok=True)
        if not os.path.exists(looks.plain_file(part)):
            painted(part, -1).save(looks.plain_file(part))
            wrote += 1
    for part, number, name in leather_types(java):
        if number in looks.files(part):
            continue
        painted(part, number).save(os.path.join(looks.SOURCE, part, "%d_%s.png" % (number, name)))
        wrote += 1
    for layer in (1, 2):
        overlay = os.path.join(looks.SOURCE, "layer_%d_overlay.png" % layer)
        if not os.path.exists(overlay):
            Image.open(os.path.join(PAINT_SOURCE, "layer_%d_overlay.png" % layer)).save(overlay)
            wrote += 1
    print("wrote %d files to %s" % (wrote, os.path.relpath(looks.SOURCE, ROOT)))


if __name__ == "__main__":
    if "--split" in sys.argv:
        split(sys.argv[sys.argv.index("--split") + 1])
    else:
        build()
