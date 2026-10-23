"""Builds the armour sheets from armour/<piece>.json and the looks in armour/models/ (see
armour_looks.py), for the armour shader (build_shaders.py) to pick between. The pack's build runs it;
run it yourself to see a change in game:

    python .github/scripts/build_armour.py

A look is a whole 256x128 armour texture (Minecraft's 64x32 layout, four texels a pixel): the texture
<look>.png in its model, armour/models/<piece>/<look>.bbmodel, or armour/plain/<piece>.png for the plain
look. Only its part's boxes are read: the body and arms for chest, the legs for boots, the legs and
body for legs. Exact greys are dyed by the item's colour, any other colour keeps its own, alpha 253
dyes a grey a light shade of the colour, and alpha under 128 is clear. Each item's tile is baked in its
colour; tile 0, the plain look, keeps those codes for the shader to dye.

The top right texel of a sheet marks it as one: (255, 0, 255, alpha 1), green 128 on the leggings'.

It also writes OptiFine's per-item armour textures for shader packs (see CIT below): each item's tile
under assets/minecraft/optifine/cit/minescape/, and its rules there and in the cit_* overlays; and the
armour as a stitch for the Stitch mod (armour_stitch.py), in assets/minescape/stitches/.
"""
import os, sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
import armour_looks as looks

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TEXTURES = os.path.join(ROOT, "assets", "minecraft", "textures")
# up to 1.21.1, and the equipment assets' own from 1.21.2
OUTPUTS = {
    1: ["models/armor/leather_layer_1.png", "entity/equipment/humanoid/leather.png"],
    2: ["models/armor/leather_layer_2.png", "entity/equipment/humanoid_leggings/leather.png"],
}
# armour/layer_<n>_overlay.png, likewise
OVERLAYS = {
    1: ["models/armor/leather_layer_1_overlay.png", "entity/equipment/humanoid/leather_overlay.png"],
    2: ["models/armor/leather_layer_2_overlay.png", "entity/equipment/humanoid_leggings/leather_overlay.png"],
}

# A look is 256x128 RGBA: Minecraft's 64x32 armour layout at SCALE texels a model pixel. Greys the item's
# dye tints have alpha TINTED; OWN keeps a texel's own colour; LIGHT dyes a grey a light shade of the dye.
SCALE = 4
TINTED, OWN, LIGHT = 255, 254, 253
# Each part's boxes on the texture, as (u0, v0, u1, v1) in model pixels.
CHEST_AREA = [(16, 16, 56, 32)]
BOOTS_AREA = [(0, 16, 16, 32)]
AREAS = {"chest": CHEST_AREA, "boots": BOOTS_AREA, "legs": [(0, 16, 40, 32)]}
# How far in from vanilla's the armour shader draws each layer's sides (build_shaders.py, MS_NARROW).
# The top and bottom faces stay where they were, so their rims are cleared to match.
NARROW = {1: 0.5, 2: 0.15}

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


class Canvas:
    """A look's texels, addressed in model pixels."""

    def __init__(self, px=None):
        self.px = np.zeros((128, 256, 4), np.uint8) if px is None else px.copy()

    def _box(self, u, v, w, h):
        return (slice(int(round(v * SCALE)), int(round((v + h) * SCALE))),
                slice(int(round(u * SCALE)), int(round((u + w) * SCALE))))

    def clear(self, u, v, w, h):
        self.px[self._box(u, v, w, h)] = 0

    def copy(self, other, areas):
        for u0, v0, u1, v1 in areas:
            sl = self._box(u0, v0, u1 - u0, v1 - v0)
            self.px[sl] = other.px[sl]


def rims(c, layer):
    """Clear the top and bottom faces' rims across (and the body box's front and back) by as much as
    the shader pulls the sides in. Under a texel, as the leggings' is, it is left: a lip too thin to
    see."""
    k = NARROW[layer]
    if k * SCALE < 1:
        return
    boxes = [(0, 4), (16, 8)] + ([(40, 4)] if layer == 1 else [])
    for u0, w in boxes:
        for u in (u0 + 4, u0 + 4 + w):
            c.clear(u, 16, k, 4)
            c.clear(u + w - k, 16, k, 4)
            if w == 8:
                c.clear(u, 16, w, k)
                c.clear(u, 20 - k, w, k)


def neckline(c):
    """Clear where the chest box would sit in the jaw: the middle of its top face and of the top
    row of its front and back."""
    c.clear(21, 16, 6, 4)
    c.clear(21.5, 20, 5, 0.75)
    c.clear(33.5, 20, 5, 0.75)


def read(path, part):
    """A look file as a canvas in the sheets' alpha codes, only its part's boxes kept."""
    px = np.array(Image.open(path).convert("RGBA"))
    if px.shape[:2] != (looks.TILE[1], looks.TILE[0]):
        raise ValueError("%s is %dx%d, not %dx%d" % (path, px.shape[1], px.shape[0], looks.TILE[0], looks.TILE[1]))
    alpha = px[..., 3]
    grey = (px[..., 0] == px[..., 1]) & (px[..., 1] == px[..., 2])
    code = np.where(alpha == LIGHT, LIGHT, np.where(grey & (alpha != OWN), TINTED, OWN))
    out = px.copy()
    out[..., 3] = np.where(alpha >= 128, code, 0)
    out[alpha < 128] = 0
    c = Canvas()
    c.copy(Canvas(out), AREAS[part])
    return c


def bake(px, area, colour):
    """The area's dyed texels in the colour, its light ones in a light shade of it, all its texels then
    their own colour (254), as the shader would dye them."""
    if colour is None:
        return
    s = SCALE
    tint = np.array(colour, np.float32) / 255.0
    light = tint + (1.0 - tint) * 0.55
    for u0, v0, u1, v1 in area:
        block = px[int(v0 * s):int(v1 * s), int(u0 * s):int(u1 * s)]
        alpha = block[..., 3]
        rgb = block[..., :3].astype(np.float32)
        for code, by in ((TINTED, tint), (LIGHT, light)):
            mask = alpha == code
            rgb[mask] = rgb[mask] * by
        block[..., :3] = np.clip(np.round(rgb), 0, 255).astype(np.uint8)
        block[..., 3] = np.where(alpha > 0, OWN, 0)


def tile(layer, spec):
    if layer == 1:
        (chest, chest_colour), (boots, boots_colour) = spec
        c = read(chest, "chest")
        neckline(c)
        c.copy(read(boots, "boots"), BOOTS_AREA)
        rims(c, 1)
        bake(c.px, CHEST_AREA, chest_colour)
        bake(c.px, BOOTS_AREA, boots_colour)
        return c.px
    (legs, colour), = spec
    c = read(legs, "legs")
    rims(c, 2)
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
    order, index = looks.tiles(layer)
    modelled = set()
    os.makedirs(os.path.join(CIT, "armour"), exist_ok=True)
    import armour_models
    for t in sorted(set(index) - {0}):
        x, y = (t % looks.COLUMNS) * w, (t // looks.COLUMNS) * h
        own = px[y:y + h, x:x + w].copy()
        opaque = own[..., 3] > 0
        ghost, overlay = own.copy(), own.copy()
        ghost[..., 3] = np.where(opaque, GHOST, 0)
        overlay[..., 3] = np.where(opaque, 255, 0)
        ghost[0, -1], overlay[0, -1] = mark + (OWN_TILE,), mark + (HIDE,)
        # its pieces' models below it (all but clear too), traced by the armour shader and under shader
        # packs by the Stitch mod. From 1.21.2 OptiFine gives the tile to leather's extra layers as well,
        # each of which would trace them again, so there the tile is flat.
        parts = {kind: {"look": look, "colour": c} for kind, (look, c) in zip(looks.LAYER_PARTS[layer], order[t])}
        flat = Image.fromarray(ghost)
        traced = armour_models.traced(layer, flat, {0: parts})
        traced.save(os.path.join(CIT, "armour", "layer_%d_%d.png" % (layer, t)))
        if traced is not flat:
            flat.save(os.path.join(CIT, "armour", "layer_%d_%d_flat.png" % (layer, t)))
            modelled.add(t)
        Image.fromarray(overlay).save(os.path.join(CIT, "armour", "layer_%d_%d_overlay.png" % (layer, t)))
    for piece, (material, piece_layer) in MATERIALS.items():
        if piece_layer != layer:
            continue
        for tile, item in looks.items(piece).items():
            texture = "%s/layer_%d_%d" % (CIT_TEXTURES, layer, index[tile])
            for directory, first, _, rule in looks.CIT_MATCH:
                flat = first and first >= looks.CIT_FLAT_FROM and index[tile] in modelled
                own = texture + ("_flat" if flat else "")
                folder = os.path.join(ROOT, directory, "assets", "minecraft", "optifine", "cit", "minescape") if directory else CIT
                os.makedirs(folder, exist_ok=True)
                with open(os.path.join(folder, "%s_%d.properties" % (piece, item["custom_model_data"])), "w", newline="\n") as f:
                    f.write("# %s, built by .github/scripts/build_armour.py from armour/%s.json\n" % (item["name"], piece))
                    f.write("type=armor\nitems=%s\n%s\n" % (material, rule % item["custom_model_data"]))
                    f.write("texture.leather_layer_%d=%s.png\ntexture.leather_layer_%d_overlay=%s_overlay.png\n" % (layer, own, layer, texture))


def build():
    import shutil
    shutil.rmtree(CIT, ignore_errors=True)
    for directory, _, _, _ in looks.CIT_MATCH:
        if directory:
            shutil.rmtree(os.path.join(ROOT, directory), ignore_errors=True)
    import armour_models
    for layer in (1, 2):
        image, count = sheet(layer)
        cit(layer, image)
        # the models, traced on the sheet's own layer where there are no extra layers (to 1.21.1)
        image = armour_models.traced(layer, image)
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
    # the models, drawn by leather's extra layers from 1.21.2; the 1.21.2+ sheets say they have them
    modelled = armour_models.build()
    for layer in (1, 2):
        path = os.path.join(TEXTURES, OUTPUTS[layer][1])
        image = Image.open(path)
        image.putpixel((image.width - 1, 0), (255, (0 if layer == 1 else 128) | 32, 255, SHEET))
        image.save(path)
    # the same looks and shapes for the Stitch mod, under shader packs
    import armour_stitch
    armour_stitch.write(ROOT, modelled)
    print("stitch: assets/minescape/stitches/armour.*")


if __name__ == "__main__":
    build()
