"""Every MineScape item is leather horse armour: its custom model data picks its model, and its dye
carries its stack count, which the item shader draws over the icon.

    assets/minecraft/models/item/leather_horse_armor.json   the items' models, by custom model data;
                                                            edited by hand like any other item model
    assets/minecraft/models/item/feather.json               noted icons, by the number noted_icons.json
                                                            gives them; a noted item is the negative

The plugin's items take their number from the overrides here (Items.java, MembersItems.java), and a
noted item's custom model data is minus its noted icon's number, so the noted icons need no list of
their own.

Leather armour keeps its own material, to be worn: armour/<piece>.json (armour_looks.py) defines each
piece's items by custom model data, 10000 + their tile, and this bakes each item's icon in its colour
and adds it to leather_chestplate.json, leather_leggings.json or leather_boots.json after their own
overrides; build_armour.py bakes how it looks worn. Its dye is any item's, with its tile. The models the items had before stay where they were, so anything still on its old
material (an item frame, a chest in the world) looks as it did.

The count: the dye's 24 bits are colour << 22 | suffix << 20 | decimal << 19 | number (DYE below), the
count shortened the OSRS way by the plugin (ItemCount). An undyed item's own colour, 0xA06540, means no
count. Every item model gets one more face, the count face, along the icon's top, textured with
count.png: every texel there is a marker whose colour says which quarter of the texture it is in, so the
item shader (build_shaders.py) finds the face's corners by reading the texture at its own vertex. It
draws the digits on that face in the slot font's glyphs, and hides the face anywhere but a screen (a
perspective projection: in a hand, on the ground) and on an item without a count.

    python .github/scripts/count_icons.py            in CI, before zipping: leather_horse_armor.json's
                                                     overrides moved onto copies of their models with
                                                     the count face, the noted icons added below zero
    python .github/scripts/count_icons.py --items    after the 1.21.4 upgrader: each model as it is in
                                                     the hand, with the count face in a screen
    python .github/scripts/count_icons.py --restore  leather_horse_armor.json as committed, for a script that
                                                     reads the items' own models (process_input.py), to be
                                                     followed by this again
    python .github/scripts/count_icons.py --migrate looks.json
                                                     once, from the plugin's old looks (id, material,
                                                     damage, custom model data): the models those looks
                                                     had, as leather_horse_armor.json's overrides

The first two rewrite leather_horse_armor.json in place (a copy of the original is kept in cache/ and
read back if it is run again); in CI that's the checkout. Don't commit the rewritten file.

Written (git-ignored):
    assets/ms/models/count/                              the count face's models and the copies
    assets/minecraft/items/leather_horse_armor.json      the 1.21.4 item definition
    assets/minecraft/textures/item/custom/count.png      the count face's markers
"""
import json, math, os, shutil, sys

from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODELS = os.path.join(ROOT, "assets", "minecraft", "models", "item")
COUNT_MODELS = os.path.join(ROOT, "assets", "ms", "models", "count")
ITEMS = os.path.join(ROOT, "assets", "minecraft", "items")
CACHE = os.path.join(ROOT, "cache")
FONT = os.path.join(ROOT, "assets", "minecraft", "textures", "font", "slot.png")
MARKER_TEXTURE = os.path.join(ROOT, "assets", "minecraft", "textures", "item", "custom", "count.png")
ITEM = "leather_horse_armor"
NOTED = "feather"
SOURCE = os.path.join(MODELS, ITEM + ".json")
SOURCES = os.path.join(CACHE, "count_sources.json")
# Leather armour, each piece on its own material, defined in armour/<piece>.json (armour_looks.py)
ARMOUR = {"chest": "leather_chestplate", "legs": "leather_leggings", "boots": "leather_boots"}

# The count face's texels: red and green fixed, blue MARKER_BLUE + the quarter (0 top left, 1 top
# right, 2 bottom left, 3 bottom right), opaque: along its edge, where a face square to the slot has
# its corners; inside it, where a centred face (a 3D model's, below) has them (uv 1 to 15), blue
# MARKER_BLUE + CENTRED + the quarter. One texture, so no other marker sits beside it in the atlas.
MARKER_RED, MARKER_GREEN, MARKER_BLUE = 0x3D, 0xC1, 0x58
CENTRED = 4

# The dye, 24 bits: layout << 22 | tile << 13 | selected << 12 | count.
#   layout   0, an item's; any other is not a count (leather's own colour, 0xA06540, an item never
#            dyed, is one of them)
#   tile     an armour piece's look when worn (512 a part), 0 for other items
#   selected a light blue frame inside the icon, as the player's selected item
#   count    the stack's count, shortened to four characters at most (the plugin's ItemCount):
#              0-999         as it is                       0-999
#              1000-1089     1.0K-9.9K (tenths of a K)      1000 + tenths - 10
#              1090-2079     10K-999K                       1090 + K - 10
#              2080-2169     1.0M-9.9M                      2080 + tenths - 10
#              2170-3159     10M-999M                       2170 + M - 10
#              3160-3171     1.0B-2.1B                      3160 + tenths - 10
#              4095          no count (a selected item without one)
#            a decimal of 0 is left out ("2K"); yellow, white from 100K, green from 10M
DYE = "layout << 22 | tile << 13 | selected << 12 | count"
UNDYED = 0xA06540

# The count face, in GUI pixels from the icon's top left: over the icon's 16, no further. From 1.21.6
# an item drawn past its 16 (oversized) is layered by its model's whole extent, which would overlap its
# neighbours and lift them over a menu's slot text; so the count and the frame stay inside. In front of
# the icon: a flat copy's face just before it; the overlay's, drawn beside a model of any depth, at the
# front of the model's box.
COUNT_FACE = {"left": 0, "top": 0, "width": 16, "height": 16}
COUNT_FACE_Z = {"flat": 9, "overlay": 16}

# A 3D model before 1.21.4 can't have the count face square to the slot: it is drawn in the model's
# GUI pose, tilted and scaled with it. So its face is centred: put where the pose takes it to the
# slot's middle, on the side the pose turns to the camera, big enough that the pose leaves the slot and
# its count inside it; the shader draws the count and frame square to the slot from where the face
# lands, whatever its tilt, taking the face's middle for the slot's. What it must cover, in GUI pixels
# around the slot's middle (y up), the same each way so its middle stays the slot's: the icon's 16.
CENTRED_COVER = ((-8, 8, -8, 8),)
# Minecraft's block model's display, for a block model with none of its own.
BLOCK_DISPLAY = {
    "gui": {"rotation": [30, 225, 0], "translation": [0, 0, 0], "scale": [0.625, 0.625, 0.625]},
    "ground": {"rotation": [0, 0, 0], "translation": [0, 3, 0], "scale": [0.25, 0.25, 0.25]},
    "fixed": {"rotation": [0, 0, 0], "translation": [0, 0, 0], "scale": [0.5, 0.5, 0.5]},
    "thirdperson_righthand": {"rotation": [75, 45, 0], "translation": [0, 2.5, 0], "scale": [0.375, 0.375, 0.375]},
    "firstperson_righthand": {"rotation": [0, 45, 0], "translation": [0, 0, 0], "scale": [0.4, 0.4, 0.4]},
    "firstperson_lefthand": {"rotation": [0, 225, 0], "translation": [0, 0, 0], "scale": [0.4, 0.4, 0.4]},
}
CONTEXTS = ("thirdperson_righthand", "thirdperson_lefthand", "firstperson_righthand", "firstperson_lefthand",
            "gui", "head", "ground", "fixed")
# Display scales are capped at 4. A model too small in its GUI pose, or moved too far off its middle,
# for any side of its box to cover the slot is copied smaller, its display scales that much larger,
# so it looks the same everywhere and its box has room: by the first of these that leaves room.
SHRINK = (1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8)
MAX_DISPLAY_SCALE = 4.0

# Display transforms of Minecraft's own flat item models, which a flat copy keeps: a model with
# item/generated at its root is baked from its layers, never from elements, so it can't be the parent.
GENERATED = {
    "ground": {"rotation": [0, 0, 0], "translation": [0, 2, 0], "scale": [0.5, 0.5, 0.5]},
    "head": {"rotation": [0, 180, 0], "translation": [0, 13, 7], "scale": [1, 1, 1]},
    "thirdperson_righthand": {"rotation": [0, 0, 0], "translation": [0, 3, 1], "scale": [0.55, 0.55, 0.55]},
    "firstperson_righthand": {"rotation": [0, -90, 25], "translation": [1.13, 3.2, 1.13], "scale": [0.68, 0.68, 0.68]},
    "fixed": {"rotation": [0, 180, 0], "scale": [1, 1, 1]},
}
HANDHELD = dict(GENERATED, **{
    "thirdperson_righthand": {"rotation": [0, -90, 55], "translation": [0, 4.0, 0.5], "scale": [0.85, 0.85, 0.85]},
    "thirdperson_lefthand": {"rotation": [0, 90, -55], "translation": [0, 4.0, 0.5], "scale": [0.85, 0.85, 0.85]},
    "firstperson_righthand": {"rotation": [0, -90, 25], "translation": [1.13, 3.2, 1.13], "scale": [0.68, 0.68, 0.68]},
    "firstperson_lefthand": {"rotation": [0, 90, -25], "translation": [1.13, 3.2, 1.13], "scale": [0.68, 0.68, 0.68]},
})
FLAT_ROOTS = {"builtin/generated": "generated", "item/generated": "generated",
              "item/handheld": "handheld", "item/handheld_rod": "handheld"}
FLAT_DISPLAYS = {"generated": GENERATED, "handheld": HANDHELD}

# Durability of the materials whose models pick their icons by damage (for --migrate).
DURABILITY = {
    "wooden": 59, "stone": 131, "iron": 250, "golden": 32, "diamond": 1561, "netherite": 2031,
    "leather_helmet": 55, "leather_chestplate": 80, "leather_leggings": 75, "leather_boots": 65,
    "chainmail_helmet": 165, "chainmail_chestplate": 240, "chainmail_leggings": 225, "chainmail_boots": 195,
    "iron_helmet": 165, "iron_chestplate": 240, "iron_leggings": 225, "iron_boots": 195,
    "golden_helmet": 77, "golden_chestplate": 112, "golden_leggings": 105, "golden_boots": 91,
    "diamond_helmet": 363, "diamond_chestplate": 528, "diamond_leggings": 495, "diamond_boots": 429,
    "netherite_helmet": 407, "netherite_chestplate": 592, "netherite_leggings": 555, "netherite_boots": 481,
    "turtle_helmet": 275, "bow": 384, "crossbow": 465, "fishing_rod": 64, "shears": 238, "shield": 336,
    "trident": 250, "elytra": 432, "flint_and_steel": 64, "carrot_on_a_stick": 25, "warped_fungus_on_a_stick": 100,
}
TOOLS = ("_sword", "_shovel", "_pickaxe", "_axe", "_hoe")


def durability(material):
    if material in DURABILITY:
        return DURABILITY[material]
    for tool in TOOLS:
        if material.endswith(tool):
            return DURABILITY.get(material[:-len(tool)])
    return None


def model_path(ref):
    ns, _, path = ref.partition(":") if ":" in ref else ("minecraft", "", ref)
    return os.path.join(ROOT, "assets", ns, "models", path + ".json")


def full(ref):
    return ref if ":" in ref else "minecraft:" + ref


def read_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path, data, compact=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        if compact:
            json.dump(data, f, separators=(",", ":"))
        else:
            json.dump(data, f, indent=4)
            f.write("\n")


def resolve(material, damage, cmd):
    """The model the material's overrides pick for the look, as the client picks it: the last override
    whose every predicate is at most the item's value. None if the material has no such model."""
    path = os.path.join(MODELS, material + ".json")
    if not os.path.exists(path):
        return None
    model = read_json(path)
    most = durability(material)
    values = {"custom_model_data": cmd, "damaged": 0,  # the plugin's items are unbreakable
              "damage": damage / most if most else 0.0}
    picked = None
    for override in model.get("overrides", []):
        predicate = override.get("predicate", {})
        if all(k in values and values[k] >= v - 1e-9 for k, v in predicate.items()):
            picked = override["model"]
    return full(picked) if picked else None


def chain(ref):
    """The model and its parents in the pack, child first, and the root it ends on outside the pack."""
    models, seen = [], set()
    while ref and ref not in seen:
        seen.add(ref)
        path = model_path(ref)
        if not os.path.exists(path):
            return models, ref.split(":", 1)[1]
        model = read_json(path)
        models.append(model)
        ref = full(model["parent"]) if "parent" in model else None
    return models, None


def count_face(z):
    f = COUNT_FACE
    # model y runs up from the icon's bottom
    return {"from": [f["left"], 16 - f["top"] - f["height"], z], "to": [f["left"] + f["width"], 16 - f["top"], z], "shade": False,
            "faces": {"south": {"uv": [0, 0, 16, 16], "texture": "#count", "tintindex": 0}}}


def flat_parent(kind, layers):
    """The shared model of a flat copy: its layers as faces before and behind, the count face, and the
    flat item's display; the copy names only its textures."""
    elements = []
    for i in range(layers):
        front, back = 8.5 + i * 0.01, 7.5 - i * 0.01
        elements.append({"from": [0, 0, front], "to": [16, 16, front], "shade": False,
                         "faces": {"south": {"uv": [0, 0, 16, 16], "texture": "#layer%d" % i}}})
        elements.append({"from": [0, 0, back], "to": [16, 16, back], "shade": False,
                         "faces": {"north": {"uv": [16, 0, 0, 16], "texture": "#layer%d" % i}}})
    elements.append(count_face(COUNT_FACE_Z["flat"]))
    return {"gui_light": "front", "textures": {"count": "item/custom/count"}, "elements": elements,
            "display": FLAT_DISPLAYS[kind]}


def flatten(ref, parents):
    """A flat copy of the icon with the count face, or None if it is not a flat icon (a model of its
    own elements is used as it is, without a count, before 1.21.4)."""
    models, root = chain(ref)
    if not models and ref.startswith("minecraft:item/"):
        # a vanilla item's own icon, outside the pack: a flat item of its texture
        models, root = [{"textures": {"layer0": ref}}], "item/generated"
    if any("elements" in m for m in models) or root not in FLAT_ROOTS:
        return None
    kind = FLAT_ROOTS[root]
    textures, display = {}, {}
    for model in reversed(models):
        textures.update(model.get("textures", {}))
        display.update(model.get("display", {}))

    def texture(name, depth=0):
        value = textures.get(name)
        return texture(value[1:], depth + 1) if value and value.startswith("#") and depth < 8 else value

    layers = []
    for i in range(16):
        value = texture("layer%d" % i)
        if value is None:
            break
        layers.append(value)
    if not layers:
        return None
    parent = "ms:count/flat/%s_%d" % (kind, len(layers))
    parents[parent] = flat_parent(kind, len(layers))
    copy = {"parent": parent, "textures": dict({"layer%d" % i: t for i, t in enumerate(layers)}, particle=layers[0])}
    if display:
        copy["display"] = display
    return copy


def marker_texture():
    image = Image.new("RGBA", (16, 16))
    for y in range(16):
        for x in range(16):
            edge = x in (0, 15) or y in (0, 15)
            base = MARKER_BLUE if edge else MARKER_BLUE + CENTRED
            image.putpixel((x, y), (MARKER_RED, MARKER_GREEN, base + (x >= 8) + 2 * (y >= 8), 255))
    os.makedirs(os.path.dirname(MARKER_TEXTURE), exist_ok=True)
    image.save(MARKER_TEXTURE)


def full_display(models, root):
    """Every display context of the model as Minecraft resolves it: its own or its parents', the root's
    (a vanilla block or flat item) for the rest, and a left hand as its right where it has none."""
    display = {}
    if root and root.startswith("block/"):
        display.update(BLOCK_DISPLAY)
    elif root in FLAT_ROOTS:
        display.update(FLAT_DISPLAYS[FLAT_ROOTS[root]])
    for model in reversed(models):
        display.update(model.get("display", {}))
    for left, right in (("thirdperson_lefthand", "thirdperson_righthand"), ("firstperson_lefthand", "firstperson_righthand")):
        if left not in display and right in display:
            display[left] = display[right]
    out = {}
    for context in CONTEXTS:
        t = display.get(context, {})
        out[context] = {"rotation": [float(v) for v in t.get("rotation", [0, 0, 0])],
                        "translation": [float(v) for v in t.get("translation", [0, 0, 0])],
                        "scale": [float(v) for v in t.get("scale", [1, 1, 1])]}
    return out


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def pose_matrix(rotation, scale):
    """Rotation about x, then y, then z as Minecraft's item transforms compose them (Rx Ry Rz), then
    the scale."""
    rx, ry, rz = (math.radians(a) for a in rotation)
    x = [[1, 0, 0], [0, math.cos(rx), -math.sin(rx)], [0, math.sin(rx), math.cos(rx)]]
    y = [[math.cos(ry), 0, math.sin(ry)], [0, 1, 0], [-math.sin(ry), 0, math.cos(ry)]]
    z = [[math.cos(rz), -math.sin(rz), 0], [math.sin(rz), math.cos(rz), 0], [0, 0, 1]]
    return mat_mul(mat_mul(mat_mul(x, y), z), [[scale[0], 0, 0], [0, scale[1], 0], [0, 0, scale[2]]])


def cofactor(m):
    """The inverse transpose of m, times its determinant: how it turns a surface's normal."""
    return [[m[(r + 1) % 3][(c + 1) % 3] * m[(r + 2) % 3][(c + 2) % 3]
             - m[(r + 1) % 3][(c + 2) % 3] * m[(r + 2) % 3][(c + 1) % 3] for c in range(3)] for r in range(3)]


# A face on each side of a box: its name, the axis it faces along and which way, and the two it spans
SIDES = (("east", 0, 1, 1, 2), ("west", 0, -1, 1, 2), ("up", 1, 1, 0, 2), ("down", 1, -1, 0, 2),
         ("south", 2, 1, 0, 1), ("north", 2, -1, 0, 1))


def centred_face(gui, cover):
    """The centred count face for a 3D model in this GUI pose covering this much, an element, or None if
    no side of its box can hold one."""
    rotation, translation, scale = gui["rotation"], gui["translation"], gui["scale"]
    m = pose_matrix(rotation, scale)
    turned = cofactor(m)
    det_m = sum(m[0][c] * turned[0][c] for c in range(3))
    best = None
    for name, axis, sign, a, b in SIDES:
        p, q = [m[0][a], m[1][a]], [m[0][b], m[1][b]]
        det = p[0] * q[1] - p[1] * q[0]
        # the side's outward normal after the pose: facing the camera (+z) or culled
        facing = sign * turned[2][axis] * (1 if det_m > 0 else -1)
        if facing <= 1e-6 or abs(det) < 1e-6:
            continue
        if best is None or abs(det) > best[0]:
            best = (abs(det), name, a, b, p, q, det)
    if best is None:
        return None
    _, name, a, b, p, q, det = best

    def solve(x, y):
        return (x * q[1] - y * q[0]) / det, (p[0] * y - p[1] * x) / det

    # the point the pose takes to the slot's middle, on the side's plane through the model's middle
    da, db = solve(-translation[0], -translation[1])
    if True:
        corners = [solve(x, y) for x in cover[:2] for y in cover[2:]]
        frm, to = [8.0, 8.0, 8.0], [8.0, 8.0, 8.0]
        frm[a], to[a] = 8 + da + min(c[0] for c in corners), 8 + da + max(c[0] for c in corners)
        frm[b], to[b] = 8 + db + min(c[1] for c in corners), 8 + db + max(c[1] for c in corners)
        if min(frm + to) >= -16 and max(frm + to) <= 32:
            return {"from": [round(v, 4) for v in frm], "to": [round(v, 4) for v in to], "shade": False,
                    "faces": {name: {"uv": [1, 1, 15, 15], "texture": "#count", "tintindex": 0}}}
    return None


def shrunk(element, k):
    """The element k times smaller about the model's middle."""
    element = json.loads(json.dumps(element))
    for key in ("from", "to"):
        element[key] = [round(8 + (v - 8) / k, 5) for v in element[key]]
    if "rotation" in element and "origin" in element["rotation"]:
        element["rotation"]["origin"] = [round(8 + (v - 8) / k, 5) for v in element["rotation"]["origin"]]
    return element


def solid_copy(ref):
    """A 3D model with its centred count face, for the packs before 1.21.4, or None."""
    models, root = chain(ref)
    elements = next((m["elements"] for m in models if "elements" in m), None)
    if not elements:
        return None
    display = full_display(models, root)
    # as far as the cap allows: a scale already at it (Minecraft clamps those beyond) can't grow
    largest = max(min(abs(v), MAX_DISPLAY_SCALE) for t in display.values() for v in t["scale"])
    most = MAX_DISPLAY_SCALE / largest
    # the full cover at any size first, the slot alone only if none fits
    for cover in CENTRED_COVER:
        for k in [k for k in SHRINK if k <= most] + ([most] if most > 1 else []):
            gui = dict(display["gui"], scale=[v * k for v in display["gui"]["scale"]])
            face = centred_face(gui, cover)
            if face is None:
                continue
            copy = {"parent": ref, "textures": {"count": "item/custom/count"}}
            if k == 1:
                copy["elements"] = elements + [face]
            else:
                copy["elements"] = [shrunk(e, k) for e in elements] + [face]
                copy["display"] = {c: dict(t, scale=[round(min(abs(v), MAX_DISPLAY_SCALE) * k, 5) * (1 if v >= 0 else -1) for v in t["scale"]])
                                   for c, t in display.items()}
            centred_check(ref, gui, face)
            return copy
    return None


def centred_check(ref, gui, face):
    """Fails unless the GUI pose takes the face's middle to the slot's middle, where the shader puts it."""
    m = pose_matrix(gui["rotation"], gui["scale"])
    middle = [(a + b) / 2 - 8 for a, b in zip(face["from"], face["to"])]
    lands = [sum(m[i][k] * middle[k] for k in range(3)) + gui["translation"][i] for i in range(2)]
    if max(abs(v) for v in lands) > 0.01:
        raise SystemExit("%s: its count face's middle lands at %s, not the slot's middle" % (ref, lands))


def models_by_number(source):
    numbers = {}
    for override in source.get("overrides", []):
        number = override.get("predicate", {}).get("custom_model_data")
        if number is not None and len(override["predicate"]) == 1:
            numbers[int(number)] = full(override["model"])
    return numbers


def source(name):
    """models/item/<name>.json as committed: the copy in cache/ if this has already rewritten it."""
    path, copy = os.path.join(MODELS, name + ".json"), os.path.join(CACHE, name + ".source.json")
    item = read_json(path)
    if any(o["model"].startswith("ms:count/") for o in item.get("overrides", [])):
        return read_json(copy)
    os.makedirs(CACHE, exist_ok=True)
    shutil.copyfile(path, copy)
    return item


def texture_path(ref):
    ns, _, path = ref.partition(":") if ":" in ref else ("minecraft", "", ref)
    return os.path.join(ROOT, "assets", ns, "textures", path + ".png")


def armour_icon(piece, item):
    """The armour item's icon in its colour: its icon model with the layers the dye colours (layer0 of
    a flat icon, as leather's item colours tint index 0; or the faces with tint index 0) baked in the
    item's colour, a model of its own whose parent is the icon. Returns its reference."""
    ref = full(item["icon"])
    models, root = chain(ref)
    if not models and not ref.startswith("minecraft:"):
        raise SystemExit("armour/%s.json %s: no icon model %s" % (piece, item["name"], ref))
    textures, tinted = {}, set()
    for model in reversed(models):
        textures.update(model.get("textures", {}))
    elements = next((m["elements"] for m in models if "elements" in m), None)
    if elements:
        for element in elements:
            for face in element.get("faces", {}).values():
                if face.get("tintindex") == 0:
                    tinted.add(face["texture"].lstrip("#"))
    elif "layer0" in textures:
        tinted.add("layer0")
    baked = {}
    for name in sorted(tinted):
        value = textures.get(name)
        while value and value.startswith("#"):
            value = textures.get(value[1:])
        source = texture_path(value) if value else None
        if not source or not os.path.exists(source):
            raise SystemExit("armour/%s.json %s: no texture %s for its icon's %s" % (piece, item["name"], value, name))
        image = Image.open(source).convert("RGBA")
        r, g, b = item["colour"]
        pixels = [(round(pr * r / 255), round(pg * g / 255), round(pb * b / 255), pa) for pr, pg, pb, pa in image.getdata()]
        image.putdata(pixels)
        out = "item/custom/count/armour/%s/%d_%s" % (piece, item["custom_model_data"], name)
        os.makedirs(os.path.dirname(texture_path(out)), exist_ok=True)
        image.save(texture_path(out))
        baked[name] = out
    model = "ms:count/armour/%s/%d" % (piece, item["custom_model_data"])
    write_json(model_path(model), {"parent": ref, "textures": baked})
    return model


def copies(numbers, name, parents, failed):
    """Each number's model with its count face before 1.21.4: a flat copy, or a 3D model's own copy with
    a centred face; written under ms:count/flat/<name>/ and ms:count/solid/<name>/. Returns the overrides
    and how many of each."""
    overrides = []
    flat = centred = 0
    for number in sorted(numbers):
        ref = numbers[number]
        if not ref.startswith("minecraft:") and not os.path.exists(model_path(ref)):
            failed.append("%s %d %s: no such model" % (name, number, ref))
            continue
        label = ("n%d" % -number) if number < 0 else str(number)
        copy = flatten(ref, parents)
        if copy is None:
            copy = solid_copy(ref)
            if copy is None:
                failed.append("%s %d %s: no count face fits it before 1.21.4" % (name, number, ref))
                continue
            target = "ms:count/solid/%s/%s" % (name, label)
            centred += 1
        else:
            target = "ms:count/flat/%s/%s" % (name, label)
            flat += 1
        write_json(model_path(target), copy, compact=True)
        overrides.append({"predicate": {"custom_model_data": number}, "model": target})
    return overrides, flat, centred


def build():
    shutil.rmtree(COUNT_MODELS, ignore_errors=True)
    shutil.rmtree(os.path.dirname(texture_path("item/custom/count/armour/x")), ignore_errors=True)
    marker_texture()
    write_json(os.path.join(COUNT_MODELS, "overlay.json"),
               {"gui_light": "front", "textures": {"count": "item/custom/count", "particle": "item/custom/count"},
                "elements": [count_face(COUNT_FACE_Z["overlay"])]})
    parents, failed, sources = {}, [], {}

    # the items: leather horse armour, the noted icons below zero
    item = source(ITEM)
    numbers = models_by_number(item)
    for number, ref in models_by_number(read_json(os.path.join(MODELS, NOTED + ".json"))).items():
        if number > 0:
            numbers[-number] = ref
    overrides, flat, centred = copies(numbers, ITEM, parents, failed)
    write_json(os.path.join(MODELS, ITEM + ".json"), dict(item, overrides=overrides))
    sources[ITEM] = {str(n): r for n, r in numbers.items()}
    print("%s: %d items and %d noted, %d as flat copies with a count, %d 3D with a centred count"
          % (ITEM, sum(1 for n in numbers if n > 0), sum(1 for n in numbers if n < 0), flat, centred))

    # the armour, on its own leather material: each item's icon in its colour, after the material's own
    # overrides (things placed in the world before items had these)
    import armour_looks
    for piece, material in ARMOUR.items():
        own = source(material)
        numbers = {i["custom_model_data"]: armour_icon(piece, i) for i in armour_looks.items(piece).values()}
        overrides, flat, centred = copies(numbers, material, parents, failed)
        write_json(os.path.join(MODELS, material + ".json"), dict(own, overrides=own.get("overrides", []) + overrides))
        sources[material] = {str(n): r for n, r in numbers.items()}
        print("%s: %d armour items, %d as flat copies with a count, %d 3D with a centred count" % (material, len(numbers), flat, centred))

    for ref, model in parents.items():
        write_json(model_path(ref), model)
    write_json(SOURCES, sources)
    # every item shows its count and selection on every client, or the pack isn't built
    if failed:
        raise SystemExit("%d items without a count face:\n  " % len(failed) + "\n  ".join(failed))


def items():
    """The 1.21.4+ item definitions: in a screen the model and the count face over it, a model of any
    shape; anywhere else the model alone. Leather armour's fall back to the upgrader's definition, its
    models from before."""
    sources = read_json(SOURCES)
    for material, numbers in sources.items():
        entries = []
        for number, ref in sorted(numbers.items(), key=lambda e: int(e[0])):
            icon = {"type": "minecraft:model", "model": ref}
            count = {"type": "minecraft:model", "model": "ms:count/overlay",
                     "tints": [{"type": "minecraft:dye", "default": UNDYED}]}
            entries.append({"threshold": int(number), "model": {
                "type": "minecraft:select", "property": "minecraft:display_context",
                "cases": [{"when": "gui", "model": {"type": "minecraft:composite", "models": [icon, count]}}],
                "fallback": icon}})
        path = os.path.join(ITEMS, material + ".json")
        if material == ITEM:
            fallback = {"type": "minecraft:model", "model": "minecraft:item/" + ITEM,
                        "tints": [{"type": "minecraft:dye", "default": -6265536}]}
        else:
            fallback = read_json(path)["model"] if os.path.exists(path) else {
                "type": "minecraft:model", "model": "minecraft:item/" + material,
                "tints": [{"type": "minecraft:dye", "default": -6265536}]}
        write_json(path, {"model": {"type": "minecraft:range_dispatch", "property": "minecraft:custom_model_data",
                                    "fallback": fallback, "entries": entries}})
        print("%s: %d in the item definition" % (material, len(entries)))
    # the flat and 3D copies are for the packs before 1.21.4
    shutil.rmtree(os.path.join(COUNT_MODELS, "flat"), ignore_errors=True)
    shutil.rmtree(os.path.join(COUNT_MODELS, "solid"), ignore_errors=True)


def migrate(path):
    """leather_horse_armor.json's overrides from the plugin's old looks: [{"id", "material", "damage",
    "cmd"}], each id given the model its old look had."""
    looks = read_json(path)
    # 1 is the noted items' own look (their custom model data is minus their noted icon's): the plain
    # note, should one ever show it
    overrides, missing = [{"predicate": {"custom_model_data": 1}, "model": "ms:wooden_shovel/note"}], []
    for look in sorted(looks, key=lambda l: l["id"]):
        ref = resolve(look["material"].lower(), look["damage"], look["cmd"])
        if ref is None or not os.path.exists(model_path(ref)):
            # no override: the material's own icon, as the item showed before
            missing.append(look)
            ref = "minecraft:item/" + look["material"].lower()
        overrides.append({"predicate": {"custom_model_data": look["id"]}, "model": ref})
    write_json(SOURCE, {"parent": "minecraft:item/generated", "textures": {"layer0": "minecraft:item/" + ITEM},
                        "overrides": overrides})
    print("%s: %d overrides, %d with the vanilla icon of their old material" % (ITEM, len(overrides), len(missing)))
    for look in missing[:30]:
        print("  no model for", look)


def glyphs():
    """The slot font's digits, K, M, the point and B, as GLSL: each glyph's 5x7 pixels as two ints (rows
    0-3 then 4-6, five bits a row, the left pixel lowest), its advance, and its blank columns on the left."""
    image = Image.open(FONT).convert("RGBA")
    rows, advances, blanks = [], [], []
    for ch in "0123456789KM.B":
        i = ord(ch) - 32
        x0, y0 = (i % 16) * 16, (i // 16) * 16 + 6
        bits = [[1 if image.getpixel((x0 + x, y0 + y))[3] > 128 and sum(image.getpixel((x0 + x, y0 + y))[:3]) > 100 else 0
                 for x in range(5)] for y in range(7)]
        value = lambda ys: sum(bits[y][x] << ((y - ys[0]) * 5 + x) for y in ys for x in range(5))
        rows.append("ivec2(%d, %d)" % (value(range(0, 4)), value(range(4, 7))))
        lit = [x for y in range(7) for x in range(5) if bits[y][x]]
        advances.append(str(max(lit, default=0) + 2))
        blanks.append(str(min(lit, default=0)))
    return rows, advances, blanks


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--items" in args:
        items()
    elif "--restore" in args:
        for name in [ITEM] + list(ARMOUR.values()):
            source(name)
            shutil.copyfile(os.path.join(CACHE, name + ".source.json"), os.path.join(MODELS, name + ".json"))
    elif "--migrate" in args:
        migrate(args[args.index("--migrate") + 1])
    else:
        build()
