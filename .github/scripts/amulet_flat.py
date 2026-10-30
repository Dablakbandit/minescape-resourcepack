"""An amulet's flat look drawn again from its model: armour/models/amulets/<look>.bbmodel's texture
<look>.png, the body's front (x 80-112, y 80-128 of its 256 x 128), which players see where the model
can't be drawn (the inventory's preview, clients without the tracer). Each texel is the model's nearest
surface seen from the front, of what lies in front of the body's middle (z below 0 in the body's own
space): the chain behind the neck, which the body hides, isn't painted over the chest. Run it after
changing an amulet's cubes or their colours in Blockbench; the rest of the texture is kept.

    python .github/scripts/amulet_flat.py                 every amulet with a model
    python .github/scripts/amulet_flat.py 16_gold_amulet_gem ...
    python .github/scripts/amulet_flat.py --check         which flat looks don't match their models

An amulet with no cubes (a flat look only) is left as painted.
"""
import base64, glob, io, json, os, sys

from PIL import Image

import armour_models

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
FOLDER = os.path.join(ROOT, "armour", "models", "amulets")
SCALE = 4
AREA = (20, 20, 28, 32)
ALPHA = {armour_models.DYED: 255, armour_models.OWN: 254, armour_models.LIGHT: 253}


def hit(corners, x, y):
    """Where a ray along z through (x, y) meets a face (its corners), as (z, a, b) across it, or None."""
    c0, c1, _, c3 = corners
    e1 = [c1[i] - c0[i] for i in range(3)]
    e2 = [c3[i] - c0[i] for i in range(3)]
    det = e1[0] * e2[1] - e1[1] * e2[0]
    if abs(det) < 1e-9:
        return None
    dx, dy = x - c0[0], y - c0[1]
    a = (dx * e2[1] - dy * e2[0]) / det
    b = (e1[0] * dy - e1[1] * dx) / det
    if not (-1e-6 <= a <= 1 + 1e-6 and -1e-6 <= b <= 1 + 1e-6):
        return None
    return c0[2] + a * e1[2] + b * e2[2], a, b


def front(path):
    """The body's front as the model shows it (the AREA, SCALE texels a pixel), or None with no cubes.
    From the front, the body's x runs to the right as the face's u does (u = 24 + x)."""
    faces, _, textures = armour_models.load(path, "amulet")
    polys = faces.get("body", [])
    if not polys:
        return None
    w, h = (AREA[2] - AREA[0]) * SCALE, (AREA[3] - AREA[1]) * SCALE
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = out.load()
    for j in range(h):
        for i in range(w):
            x, y = (i + 0.5) / SCALE - 4.0, (j + 0.5) / SCALE
            best = None
            for corners, uvs in polys:
                r = hit(corners, x, y)
                if r is None or r[0] >= 0.0 or (best is not None and r[0] >= best[0]):
                    continue
                u = uvs[0][1] + r[1] * (uvs[1][1] - uvs[0][1]) + r[2] * (uvs[3][1] - uvs[0][1])
                v = uvs[0][2] + r[1] * (uvs[1][2] - uvs[0][2]) + r[2] * (uvs[3][2] - uvs[0][2])
                image = textures[uvs[0][0]]
                p = image.getpixel((min(image.width - 1, max(0, int(u))), min(image.height - 1, max(0, int(v)))))
                if p[3]:
                    best = (r[0], p)
            if best:
                p = best[1]
                px[i, j] = (p[0], p[1], p[2], ALPHA[p[3]])
    return out


def flat_texture(model, look):
    t = next((t for t in model["textures"] if t["name"] == look + ".png"), None)
    if t is None:
        raise SystemExit("%s: no texture %s.png (its flat look)" % (look, look))
    return t, Image.open(io.BytesIO(base64.b64decode(t["source"].split(",", 1)[1]))).convert("RGBA")


def out_of_date():
    """The amulets whose flat look doesn't match their model (build_armour.py warns of them)."""
    return redraw([], check=True)


def redraw(names, check=False):
    """Each named amulet's flat look (every one's with none) drawn again from its model; with check, only
    the names of those that differ."""
    paths = [os.path.join(FOLDER, n if n.endswith(".bbmodel") else n + ".bbmodel") for n in names] or \
        sorted(glob.glob(os.path.join(FOLDER, "*.bbmodel")))
    box = tuple(v * SCALE for v in AREA)
    stale, drawn = [], 0
    for path in paths:
        if not os.path.exists(path):
            raise SystemExit("no amulet model %s" % path)
        look = os.path.basename(path)[:-len(".bbmodel")]
        new = front(path)
        if new is None:
            continue
        model = json.load(open(path, encoding="utf-8"))
        t, image = flat_texture(model, look)
        if image.crop(box).tobytes() == new.tobytes():
            continue
        if check:
            stale.append(look)
            continue
        image.paste(new, box[:2])
        buf = io.BytesIO()
        image.save(buf, "PNG")
        t["source"] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(model, fh, indent="\t")
        drawn += 1
    return stale if check else drawn


if __name__ == "__main__":
    args = sys.argv[1:]
    names = [a for a in args if not a.startswith("--")]
    if "--check" in args:
        stale = redraw(names, check=True)
        if stale:
            raise SystemExit("flat looks that don't match their models (run amulet_flat.py): " + ", ".join(stale))
        print("every amulet's flat look matches its model")
    else:
        print("flat looks drawn again: %d" % redraw(names))
