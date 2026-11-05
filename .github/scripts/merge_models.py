"""Puts looks of one shape onto one model, the build swapping in the others' textures: armour/models/
<piece>/<model>.bbmodel keeps the cubes and the first look's textures (<model>.png, its flat look, and
<model>_details.png), and each other look's textures that differ become images beside it,
armour/models/<piece>/<model>/<look>.png and <look>_details.png. Their items in armour/<piece>.json then
wear the model with those images in place of its textures:

    {"custom_model_data": 661, "name": "attack", "look": "skill_cape", "textures": {"skill_cape_details.png": "skill_cape/11_attack_details.png"}}

    python .github/scripts/merge_models.py capes/skill_cape 9_agility 10_agility_trimmed ...

The looks are models of their own (<look>.bbmodel) with the same cubes: the same groups and pivots, the
same places, sizes and turns, the same faces textured. An image swapped in keeps the model's layout (where
its faces are on the texture), so looks whose details are laid out differently are laid out again as one:
a face keeps its texels where the first look whose layout has room for every look's puts them; when no
look's has, every face gets its own place in a new layout, as many texels as the most any look gives it.
A face's texels are only ever scaled up by a whole number, so each look draws as it did, and the script
checks it does. The flat looks are kept as they are. The looks' own models are then removed.
"""
import base64, io, json, math, os, re, sys

from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
import armour_looks as looks

MODELS = looks.MODELS


def image(texture):
    return Image.open(io.BytesIO(base64.b64decode(texture["source"].split(",", 1)[1]))).convert("RGBA")


def source(img):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def rounded(v):
    return tuple(round(float(x), 4) for x in v)


def cubes(model):
    """The model's cubes outside the reference player, by where they are: {key: element}, the key its groups
    (name, pivot, turn) and its own place, size, turn and inflation."""
    elements = {e["uuid"]: e for e in model["elements"]}
    groups = {g["uuid"]: g for g in model.get("groups", []) if "uuid" in g}
    out = {}

    def walk(children, at):
        for child in children:
            if isinstance(child, str):
                e = elements.get(child)
                if e is None:
                    continue
                key = (at, rounded(e["from"]), rounded(e["to"]), rounded(e.get("origin", (0, 0, 0))),
                       rounded(e.get("rotation", (0, 0, 0))), round(float(e.get("inflate", 0)), 4))
                if key in out:
                    raise SystemExit("two cubes of %s are in one place (%s)" % (model.get("name"), e.get("name")))
                out[key] = e
                continue
            group = dict(groups.get(child.get("uuid"), {}), **child) if "name" not in child else child
            if group.get("name", "").startswith("player (reference)"):
                continue
            walk(child.get("children", []), at + ((group.get("name"), rounded(group.get("origin", (0, 0, 0))),
                                                   rounded(group.get("rotation", (0, 0, 0)))),))
    walk(model["outliner"], ())
    return out


class Look:
    """One look as its model has it: its textures, and each of its cubes' textured faces."""

    def __init__(self, piece, name):
        self.name = name
        self.path = os.path.join(MODELS, piece, name + ".bbmodel")
        if not os.path.exists(self.path):
            raise SystemExit("no model armour/models/%s/%s.bbmodel" % (piece, name))
        self.model = json.load(open(self.path, encoding="utf-8"))
        names = [t.get("name") for t in self.model["textures"]]
        for need in (name + ".png", name + "_details.png"):
            if need not in names:
                raise SystemExit("%s: no texture %s" % (self.path, need))
        # each texture's part in the look: its flat look, its details, or one of its own (the reference
        # player's)
        self.role = {i: "flat" if n == name + ".png" else "details" if n == name + "_details.png" else None
                     for i, n in enumerate(names)}
        self.flat = image(self.model["textures"][names.index(name + ".png")])
        self.details_texture = self.model["textures"][names.index(name + "_details.png")]
        self.details = image(self.details_texture)
        t = self.details_texture
        self.scale = (self.details.width / t.get("uv_width", self.details.width),
                      self.details.height / t.get("uv_height", self.details.height))
        self.cubes = cubes(self.model)
        self.faces = {}
        for key, e in self.cubes.items():
            for face, spec in (e.get("faces") or {}).items():
                if not spec or spec.get("texture") is None:
                    continue
                role = self.role.get(spec["texture"])
                if role is None:
                    raise SystemExit("%s: %s's %s face is drawn from %s, not the look's own textures"
                                     % (self.path, e.get("name"), face, names[spec["texture"]]))
                self.faces[key, face] = (role, tuple(spec["uv"]), int(spec.get("rotation", 0)))

    def rect(self, face):
        """A details face's texels: (x at the face's left, y at its top, x at its right, y at its bottom)."""
        u1, v1, u2, v2 = self.faces[face][1]
        r = (u1 * self.scale[0], v1 * self.scale[1], u2 * self.scale[0], v2 * self.scale[1])
        if any(abs(x - round(x)) > 1e-6 for x in r):
            raise SystemExit("%s: a face's texels don't start and end on whole texels" % self.path)
        r = tuple(int(round(x)) for x in r)
        if r[0] == r[2] or r[1] == r[3]:
            raise SystemExit("%s: a face has no texels across" % self.path)
        return r


def bake(look, face, target, into, written):
    """The look's texels for the face drawn where the target (its rect) has them, in the image into; False
    if a texel already written there by another face isn't the same."""
    sx1, sy1, sx2, sy2 = look.rect(face)
    tx1, ty1, tx2, ty2 = target
    px, src = into.load(), look.details.load()
    for y in range(min(ty1, ty2), max(ty1, ty2)):
        b = (y + 0.5 - ty1) / (ty2 - ty1)
        for x in range(min(tx1, tx2), max(tx1, tx2)):
            a = (x + 0.5 - tx1) / (tx2 - tx1)
            p = src[int(math.floor(sx1 + a * (sx2 - sx1))), int(math.floor(sy1 + b * (sy2 - sy1)))]
            if (x, y) in written and written[x, y] != p and not (written[x, y][3] < 128 and p[3] < 128):
                return False
            written[x, y] = p
            px[x, y] = p
    return True


def size(r):
    return abs(r[2] - r[0]), abs(r[3] - r[1])


def layout_of(base, all_looks, details):
    """Every look's details in the base look's layout, or None if it hasn't room for them all."""
    for face in details:
        w, h = size(base.rect(face))
        for look in all_looks:
            lw, lh = size(look.rect(face))
            if w % lw or h % lh or look.faces[face][2] != base.faces[face][2]:
                return None
    baked = {}
    for look in all_looks:
        if look is base:
            baked[look.name] = look.details
            continue
        img, written = Image.new("RGBA", base.details.size, (0, 0, 0, 0)), {}
        for face in details:
            if not bake(look, face, base.rect(face), img, written):
                return None
        baked[look.name] = img
    uv = (base.details_texture.get("uv_width", base.details.width), base.details_texture.get("uv_height", base.details.height))
    return {face: base.faces[face][1] for face in details}, baked, uv


def new_layout(all_looks, details, width):
    """Every look's details in a layout of their own: faces that every look draws from the same texels, the
    same way round, share a place, as many texels as the most any look has (a whole number of each's)."""
    first = all_looks[0]
    places, order = {}, []
    for face in details:
        key = tuple((look.rect(face), look.faces[face][2]) for look in all_looks)
        if key not in places:
            places[key] = (math.lcm(*(size(look.rect(face))[0] for look in all_looks)),
                           math.lcm(*(size(look.rect(face))[1] for look in all_looks)))
            order.append(key)
    width = max([width] + [places[k][0] for k in order])
    at, x, y, row = {}, 0, 0, 0
    for key in sorted(order, key=lambda k: (-places[k][1], -places[k][0])):
        w, h = places[key]
        if x + w > width:
            x, y, row = 0, y + row, 0
        at[key] = (x, y)
        x += w
        row = max(row, h)
    height = y + row
    uvs = {}
    for face in details:
        key = tuple((look.rect(face), look.faces[face][2]) for look in all_looks)
        (x0, y0), (w, h) = at[key], places[key]
        # the same way round as the first look's (a face mirrored runs its texels right to left)
        r = first.rect(face)
        x1, x2 = (x0 + w, x0) if r[2] < r[0] else (x0, x0 + w)
        y1, y2 = (y0 + h, y0) if r[3] < r[1] else (y0, y0 + h)
        uvs[face] = (x1, y1, x2, y2)
    baked = {}
    for look in all_looks:
        img, written = Image.new("RGBA", (width, height), (0, 0, 0, 0)), {}
        for face in details:
            if not bake(look, face, uvs[face], img, written):
                raise SystemExit("faces sharing texels in the new layout disagree; this shouldn't happen")
        baked[look.name] = img
    return uvs, baked, (width, height)


def sample(img, uv, scale, n):
    """A face's texels as drawn, n by n across it."""
    u1, v1, u2, v2 = (uv[0] * scale[0], uv[1] * scale[1], uv[2] * scale[0], uv[3] * scale[1])
    px = img.load()
    out = []
    for j in range(n):
        for i in range(n):
            a, b = (i + 0.5) / n, (j + 0.5) / n
            p = px[int(math.floor(u1 + a * (u2 - u1))), int(math.floor(v1 + b * (v2 - v1)))]
            out.append(p if p[3] >= 128 else (0, 0, 0, 0))
    return out


def same(a, b):
    return a.size == b.size and a.tobytes() == b.tobytes()


def wear(piece, merged, model, swaps):
    """The items in armour/<piece>.json that wore the merged looks wear the model instead, with their
    images swapped in: each item's line changed where it names its look."""
    path = os.path.join(looks.SOURCE, piece + ".json")
    text = open(path, encoding="utf-8", newline="").read()
    worn = 0
    for look in merged:
        textures = ""
        if swaps[look]:
            textures = ', "textures": {%s}' % ", ".join('"%s": "%s"' % kv for kv in sorted(swaps[look].items()))
        text, n = re.subn(r'"look": "%s"' % re.escape(look), lambda m: '"look": "%s"%s' % (model, textures), text)
        worn += n
    json.loads(text)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return worn


def merge(target, names):
    piece, name = target.replace("\\", "/").split("/")
    out_path = os.path.join(MODELS, piece, name + ".bbmodel")
    all_looks = [Look(piece, n) for n in names]
    first = all_looks[0]
    for look in all_looks[1:]:
        if set(look.cubes) != set(first.cubes):
            raise SystemExit("%s hasn't %s's cubes: %d of %d differ" % (look.name, first.name, len(set(look.cubes) ^ set(first.cubes)), len(first.cubes)))
        if {f: v[0] for f, v in look.faces.items()} != {f: v[0] for f, v in first.faces.items()}:
            raise SystemExit("%s hasn't %s's faces textured alike" % (look.name, first.name))
        if any(look.faces[f][2] != v[2] for f, v in first.faces.items()):
            raise SystemExit("%s turns a face's texture other than %s does" % (look.name, first.name))
        if look.flat.size != first.flat.size:
            raise SystemExit("%s's flat look isn't as big as %s's" % (look.name, first.name))
        for f, v in first.faces.items():
            if v[0] == "flat" and look.faces[f][1:] != v[1:]:
                raise SystemExit("%s draws its flat look onto a face other than %s does" % (look.name, first.name))
    details = sorted(f for f, v in first.faces.items() if v[0] == "details")
    laid = None
    for base in all_looks:
        laid = layout_of(base, all_looks, details)
        if laid is not None:
            print("%s: the details laid out as %s's" % (name, base.name))
            break
    if laid is None:
        laid = new_layout(all_looks, details, first.details.width)
        print("%s: the details laid out anew, %dx%d" % (name, laid[2][0], laid[2][1]))
    uvs, baked, uv_size = laid
    scale = (baked[first.name].width / uv_size[0], baked[first.name].height / uv_size[1])
    # every look draws as it did, on a grid fine enough for both layouts
    for look in all_looks:
        for f in details:
            new = tuple(int(round(x)) for x in (uvs[f][0] * scale[0], uvs[f][1] * scale[1], uvs[f][2] * scale[0], uvs[f][3] * scale[1]))
            n = math.lcm(*size(new), *size(look.rect(f)))
            if sample(look.details, look.faces[f][1], look.scale, n) != sample(baked[look.name], uvs[f], scale, n):
                raise SystemExit("%s's %s face draws differently laid out again" % (look.name, f))

    # the model: the first look's, its textures named for the model, its faces in the layout
    model = json.loads(json.dumps(first.model))
    model["name"] = name
    for i, t in enumerate(model["textures"]):
        if first.role[i] == "details":
            t.update(name=name + "_details.png", source=source(baked[first.name]), uv_width=uv_size[0], uv_height=uv_size[1],
                     width=baked[first.name].width, height=baked[first.name].height)
        elif first.role[i] == "flat":
            t["name"] = name + ".png"
    keys = {e["uuid"]: k for k, e in cubes(model).items()}
    for e in model["elements"]:
        for face, spec in (e.get("faces") or {}).items():
            if spec and spec.get("texture") is not None and first.role.get(spec["texture"]) == "details":
                spec["uv"] = list(uvs[keys[e["uuid"]], face])
    # the other looks' textures that differ from the model's, as images in its folder (details only if a
    # face is drawn from them)
    swaps = {}
    for look in all_looks:
        swaps[look.name] = {}
        if look is first:
            continue
        for texture, img, own in ((name + "_details.png", baked[look.name], baked[first.name]), (name + ".png", look.flat, first.flat)):
            if same(img, own) or (texture.endswith("_details.png") and not details):
                continue
            os.makedirs(os.path.join(MODELS, piece, name), exist_ok=True)
            image_name = look.name + texture[len(name):]
            img.save(os.path.join(MODELS, piece, name, image_name))
            swaps[look.name][texture] = "%s/%s" % (name, image_name)
    if model != first.model or os.path.abspath(first.path) != os.path.abspath(out_path):
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(model, f, indent="\t")
    for look in all_looks:
        if os.path.abspath(look.path) != os.path.abspath(out_path):
            os.remove(look.path)
    worn = wear(piece, [look.name for look in all_looks], name, swaps)
    print("armour/models/%s/%s.bbmodel: %d looks, %d of them with images swapped in (%d images), worn by %d items"
          % (piece, name, len(all_looks), sum(1 for v in swaps.values() if v), sum(len(v) for v in swaps.values()), worn))


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    merge(sys.argv[1], sys.argv[2:])
