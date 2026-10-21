"""Builds the armour sheets from armour/<piece>.json and the look files in armour/ (see
armour_looks.py), for the armour shader (build_shaders.py) to pick between. The pack's build runs it;
run it yourself to see a change in game:

    python .github/scripts/build_armour.py

A look file is a whole 256x128 armour texture (Minecraft's 64x32 layout, four texels a pixel), of
which only its part's boxes are read: the body and arms for chest, the legs for boots, the legs and
body for legs. Exact greys are dyed by the item's colour, any other colour keeps its own, alpha 253
dyes a grey a light shade of the colour, and alpha under 128 is clear. Each item's tile is baked in its
colour; tile 0, the plain look, keeps those codes for the shader to dye.

The looks were first painted in code (armour_art.py, armour_barrows.py, armour_boots.py, over the
plain armour in .github/armour). --split paints any look that has no file yet, named after the
plugin's LeatherArmourType:

    python .github/scripts/build_armour.py --split ../minescape.me/modules/minescape-items/src/main/java/me/minescape/gameplay/items/LeatherArmourType.java

The top right texel of a sheet marks it as one: (255, 0, 255, alpha 1), green 128 on the leggings'.

It also writes OptiFine's per-item armour textures for shader packs (see CIT below): each item's tile
under assets/minecraft/optifine/cit/minescape/, and its rules there and in the cit_* overlays; and the
armour as a stitch for the Stitch mod (armour_stitch.py), in assets/minescape/stitches/.
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

# Shader packs draw armour without the armour shader, so OptiFine is also given each item's own tile
# (its CIT, matched on custom model data): as leather's layer, every texel all but clear (alpha GHOST),
# which a shader pack drops and the armour shader draws whole; and as leather's overlay, the tile as it
# looks, which a shader pack draws undyed (the overlay always is) and the armour shader hides. The top
# right texel says which, as on the sheets: alpha SHEET for a sheet, OWN_TILE for an item's own tile,
# HIDE for its overlay.
SHEET, OWN_TILE, HIDE = 1, 2, 3
GHOST = 3
CIT = os.path.join(ROOT, "assets", "minecraft", "optifine", "cit", "minescape")
CIT_TEXTURES = "optifine/cit/minescape/armour"
MATERIALS = {"chest": ("leather_chestplate", 1), "legs": ("leather_leggings", 2), "boots": ("leather_boots", 1)}


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


def bake(px, area, colour):
    """The area's dyed texels in the colour, its light ones in a light shade of it, all its texels then
    their own colour (254), as the shader would dye them."""
    if colour is None:
        return
    s = art.SCALE
    tint = np.array(colour, np.float32) / 255.0
    light = tint + (1.0 - tint) * 0.55
    for u0, v0, u1, v1 in area:
        block = px[int(v0 * s):int(v1 * s), int(u0 * s):int(u1 * s)]
        alpha = block[..., 3]
        rgb = block[..., :3].astype(np.float32)
        for code, by in ((art.TINTED, tint), (art.LIGHT, light)):
            mask = alpha == code
            rgb[mask] = rgb[mask] * by
        block[..., :3] = np.clip(np.round(rgb), 0, 255).astype(np.uint8)
        block[..., 3] = np.where(alpha > 0, art.OWN, 0)


def tile(layer, spec):
    if layer == 1:
        (chest, chest_colour), (boots, boots_colour) = spec
        c = read(chest, "chest")
        art.neckline(c)
        c.copy(read(boots, "boots"), art.BOOTS_AREA)
        art.rims(c, 1)
        bake(c.px, art.CHEST_AREA, chest_colour)
        bake(c.px, art.BOOTS_AREA, boots_colour)
        return c.px
    (legs, colour), = spec
    c = read(legs, "legs")
    art.rims(c, 2)
    bake(c.px, AREAS["legs"], colour)
    return c.px


def sheet(layer):
    order, _ = looks.tiles(layer)
    w, h = looks.TILE
    rows = -(-len(order) // looks.COLUMNS)
    out = np.zeros((h * rows, w * looks.COLUMNS, 4), np.uint8)
    for i, paths in enumerate(order):
        x, y = (i % looks.COLUMNS) * w, (i // looks.COLUMNS) * h
        out[y:y + h, x:x + w] = tile(layer, paths)
    out[0, -1] = (255, 0 if layer == 1 else 128, 255, SHEET)
    return Image.fromarray(out), len(order)


def cit(layer, image):
    """The layer's sheet tiles as OptiFine's textures, and each armour item's rules for its tile."""
    w, h = looks.TILE
    px = np.array(image)
    mark = (255, 0 if layer == 1 else 128, 255)
    _, index = looks.tiles(layer)
    os.makedirs(os.path.join(CIT, "armour"), exist_ok=True)
    for t in sorted(set(index) - {0}):
        x, y = (t % looks.COLUMNS) * w, (t // looks.COLUMNS) * h
        own = px[y:y + h, x:x + w].copy()
        opaque = own[..., 3] > 0
        ghost, overlay = own.copy(), own.copy()
        ghost[..., 3] = np.where(opaque, GHOST, 0)
        overlay[..., 3] = np.where(opaque, 255, 0)
        ghost[0, -1], overlay[0, -1] = mark + (OWN_TILE,), mark + (HIDE,)
        Image.fromarray(ghost).save(os.path.join(CIT, "armour", "layer_%d_%d.png" % (layer, t)))
        Image.fromarray(overlay).save(os.path.join(CIT, "armour", "layer_%d_%d_overlay.png" % (layer, t)))
    for piece, (material, piece_layer) in MATERIALS.items():
        if piece_layer != layer:
            continue
        for tile, item in looks.items(piece).items():
            texture = "%s/layer_%d_%d" % (CIT_TEXTURES, layer, index[tile])
            for directory, _, _, rule in looks.CIT_MATCH:
                folder = os.path.join(ROOT, directory, "assets", "minecraft", "optifine", "cit", "minescape") if directory else CIT
                os.makedirs(folder, exist_ok=True)
                with open(os.path.join(folder, "%s_%d.properties" % (piece, item["custom_model_data"])), "w", newline="\n") as f:
                    f.write("# %s, built by .github/scripts/build_armour.py from armour/%s.json\n" % (item["name"], piece))
                    f.write("type=armor\nitems=%s\n%s\n" % (material, rule % item["custom_model_data"]))
                    f.write("texture.leather_layer_%d=%s.png\ntexture.leather_layer_%d_overlay=%s_overlay.png\n" % (layer, texture, layer, texture))


def build():
    import shutil
    shutil.rmtree(CIT, ignore_errors=True)
    for directory, _, _, _ in looks.CIT_MATCH:
        if directory:
            shutil.rmtree(os.path.join(ROOT, directory), ignore_errors=True)
    for layer in (1, 2):
        image, count = sheet(layer)
        cit(layer, image)
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
    # the same looks and shapes for the Stitch mod, under shader packs
    import armour_stitch
    armour_stitch.write(ROOT)
    print("stitch: assets/minescape/stitches/armour.*")


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
