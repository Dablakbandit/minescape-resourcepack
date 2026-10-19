"""Paints the armour sheets: every look in armour_looks.py as a tile (art from armour_art.py, over the
plain armour in .github/armour), for the armour shader (build_shaders.py) to pick between. Run it after
changing the art or the looks, and commit what it writes:

    python .github/scripts/build_armour.py

The top right texel of a sheet marks it as one: (255, 0, 255, alpha 1), green 128 on the leggings'.
"""
import os, sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
import armour_art as art
import armour_looks as looks

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SOURCE = os.path.join(ROOT, ".github", "armour")
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


def plain(layer):
    """The plain armour as a canvas, every texel it draws dyed."""
    px = np.array(Image.open(os.path.join(SOURCE, "layer_%d.png" % layer)).convert("RGBA"))
    px[..., 3] = (px[..., 3] > 25) * art.TINTED
    return art.Canvas(px)


def tile(layer, look, base):
    if layer == 1:
        chest_look, boots_look = look
        c = art.chest(chest_look, base)
        art.neckline(c)
        c.copy(art.boots(boots_look, base), art.BOOTS_AREA)
        art.rims(c, 1)
        return c.px
    c = art.legs(look, base)
    art.rims(c, 2)
    return c.px


def sheet(layer):
    base = plain(layer)
    names = looks.tiles(layer)
    w, h = looks.TILE
    rows = -(-len(names) // looks.COLUMNS)
    out = np.zeros((h * rows, w * looks.COLUMNS, 4), np.uint8)
    for i, look in enumerate(names):
        x, y = (i % looks.COLUMNS) * w, (i // looks.COLUMNS) * h
        out[y:y + h, x:x + w] = tile(layer, look, base)
    out[0, -1] = (255, 0 if layer == 1 else 128, 255, 1)
    return Image.fromarray(out), names


def main():
    for layer in (1, 2):
        image, names = sheet(layer)
        for rel in OUTPUTS[layer]:
            path = os.path.join(TEXTURES, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            image.save(path)
        overlay = Image.open(os.path.join(SOURCE, "layer_%d_overlay.png" % layer))
        for rel in OVERLAYS[layer]:
            path = os.path.join(TEXTURES, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            overlay.save(path)
        print("layer %d: %s, %d tiles" % (layer, image.size, len(names)))


if __name__ == "__main__":
    main()
