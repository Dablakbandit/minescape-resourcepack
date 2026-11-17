"""Models drawn with element rotations older clients reject, made into the nearest each client can take.

Up to 1.21.5 an element turns about one axis by -45, -22.5, 0, 22.5 or 45 degrees; 1.21.6 to 1.21.10 take
any angle from -45 to 45, still about one axis; from 1.21.11 any angle, or turns about x, y and z at once
("rotation": {"x": .., "y": .., "z": ..}, which Blockbench writes for 1.21.11 and later). A client that meets
a rotation it can't take drops the whole model: the item draws as the magenta and black missing model.

So every model in the pack with such an element keeps its own copy in an overlay for the clients that take
it, and in its place (and in an overlay for 1.21.6 to 1.21.10, if those can draw it nearer) a copy each
older client can load: each element that turns in a way the client can't take turns instead the nearest way
it can, about the middle of where it was drawn, so it stays where it was and only its angle is off a little.
The nearest way may also turn the box a quarter turn or two (any of a cube's 24 turns), its faces' textures
turned with it, so an element turned 90 degrees about y and 22.5 about x loses nothing.

    python .github/scripts/legacy_models.py           in CI, before count_icons.py: rewrites the models in
                                                      place and writes the overlays (git-ignored)
    python .github/scripts/legacy_models.py --sync    in CI, after the 1.21.4 upgrader: each overlay copy takes
                                                      everything but its elements from the model in the base
                                                      folder again, as the upgrader left it
    python .github/scripts/legacy_models.py --check   lists the models it would change, how far each
                                                      element ends up from where it was drawn, and changes
                                                      nothing

The upgrader rewrites only the base folder: it moves the block textures an item model draws to item/ (from
26.1 an item model can't take textures from both atlases), and an overlay copy still naming block/ would
then mix them and break every model of its item - every leather horse armour item. Hence --sync.

build_shaders.py lists OVERLAYS in pack.mcmeta. Don't commit the rewritten models: the pack's models stay as
the modeller exported them.
"""
import itertools
import json
import math
import os
import shutil
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ASSETS = os.path.join(ROOT, "assets")
# (directory, first pack format, last or None for the newest): the models as drawn for 1.21.11 on, and the
# nearest 1.21.6 to 1.21.10 can draw
OVERLAY_EXACT = "models_1_21_11"
OVERLAY_RANGE = "models_1_21_6"
OVERLAYS = [(OVERLAY_RANGE, 63, 74), (OVERLAY_EXACT, 75, None)]
# models the pack's own scripts write, which never carry such rotations
SKIP = (os.path.join("ms", "models", "count") + os.sep,)

OLD_ANGLES = (-45.0, -22.5, 0.0, 22.5, 45.0)
# what Minecraft's face vertices are, in uv order, for each face (FaceInfo): corners of the box as 0 for
# its min and 1 for its max on each axis
FACE_CORNERS = {
    "down": [(0, 0, 1), (0, 0, 0), (1, 0, 0), (1, 0, 1)],
    "up": [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)],
    "north": [(1, 1, 0), (1, 0, 0), (0, 0, 0), (0, 1, 0)],
    "south": [(0, 1, 1), (0, 0, 1), (1, 0, 1), (1, 1, 1)],
    "west": [(0, 1, 0), (0, 0, 0), (0, 0, 1), (0, 1, 1)],
    "east": [(1, 1, 1), (1, 0, 1), (1, 0, 0), (1, 1, 0)],
}
NORMALS = {"down": (0, -1, 0), "up": (0, 1, 0), "north": (0, 0, -1), "south": (0, 0, 1), "west": (-1, 0, 0), "east": (1, 0, 0)}
# the uv corner each vertex takes, by the face's uv rotation: vertex i takes corner (i + rotation / 90) % 4,
# corners being (u0, v0), (u0, v1), (u1, v1), (u1, v0)


def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def apply(m, v):
    return [sum(m[i][k] * v[k] for k in range(3)) for i in range(3)]


def axis_rotation(axis, degrees):
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return {"x": [[1, 0, 0], [0, c, -s], [0, s, c]],
            "y": [[c, 0, s], [0, 1, 0], [-s, 0, c]],
            "z": [[c, -s, 0], [s, c, 0], [0, 0, 1]]}[axis]


def rotation_matrix(rotation):
    """The element's rotation as Minecraft applies it: one axis, or (1.21.11+) z after y after x (JOML's
    rotationZYX, Rz * Ry * Rx)."""
    if "axis" in rotation:
        return axis_rotation(rotation["axis"], float(rotation.get("angle", 0)))
    m = axis_rotation("z", float(rotation.get("z", 0)))
    m = matmul(m, axis_rotation("y", float(rotation.get("y", 0))))
    return matmul(m, axis_rotation("x", float(rotation.get("x", 0))))


def cube_turns():
    """The cube's 24 turns: signed permutation matrices of determinant 1."""
    out = []
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((1, -1), repeat=3):
            m = [[0] * 3 for _ in range(3)]
            for i in range(3):
                m[i][perm[i]] = signs[i]
            det = (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                   + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
            if det == 1:
                out.append(m)
    return out


TURNS = cube_turns()


def legal(rotation, tier):
    """Whether a client of the tier ('old': to 1.21.5, 'range': 1.21.6 to 1.21.10) takes the rotation."""
    if rotation is None:
        return True
    if "axis" not in rotation:
        return False
    angle = float(rotation.get("angle", 0))
    if tier == "old":
        return any(abs(angle - a) < 1e-6 for a in OLD_ANGLES)
    return -45 <= angle <= 45


def candidates(tier, step=None, around=None):
    """The rotations a tier can take: (axis, angle), angle 0 for none; for 1.21.6 to 1.21.10 every step
    degrees, or around (axis, angle) by step."""
    if around:
        axis, middle = around
        for i in range(-50, 51):
            angle = middle + i * step
            if -45 <= angle <= 45:
                yield (axis, angle)
        return
    angles = [a for a in OLD_ANGLES if a] if tier == "old" else [a * 2.5 for a in range(-18, 19) if a]
    yield ("y", 0.0)
    for axis in "xyz":
        for angle in angles:
            yield (axis, angle)


def corners(half):
    return [[sx * half[0], sy * half[1], sz * half[2]] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]


def nearest(matrix, half, tier):
    """The (axis, angle, turn) whose rotation after the turn draws the box's corners nearest where matrix
    draws them, and the largest distance a corner moves, in model units."""
    target = [apply(matrix, c) for c in corners(half)]
    pre = [(t, [apply(t, c) for c in corners(half)]) for t in TURNS]

    def search(options, best=None):
        for axis, angle in options:
            r = axis_rotation(axis, angle)
            for turn, turned in pre:
                drawn = [apply(r, c) for c in turned]
                err = sum((a - b) ** 2 for p, q in zip(drawn, target) for a, b in zip(p, q))
                if best is None or err < best[0] - 1e-12:
                    best = (err, axis, angle, turn, max(math.dist(p, q) for p, q in zip(drawn, target)))
        return best

    best = search(candidates(tier))
    if tier != "old" and best[2]:
        # then to a twentieth of a degree about the best of every 2.5
        best = search(candidates(tier, 0.05, best[1:3]), best)
        best = best[:2] + (round(best[2], 2),) + best[3:]
    return best[1:]


def default_uv(face, lo, hi):
    """The uv Minecraft gives a face that names none, from the element's box."""
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    return {"down": [x0, 16 - z1, x1, 16 - z0], "up": [x0, z0, x1, z1], "north": [16 - x1, 16 - y1, 16 - x0, 16 - y0],
            "south": [x0, 16 - y1, x1, 16 - y0], "west": [z0, 16 - y1, z1, 16 - y0], "east": [16 - z1, 16 - y1, 16 - z0, 16 - y0]}[face]


def turn_faces(faces, turn, lo, hi):
    """The box's faces once the box is turned by turn: each face moves to the side it now looks at, its uv
    rotation changed so the texture turns with it."""
    out = {}
    for name, face in faces.items():
        face = dict(face)
        if "uv" not in face:
            face["uv"] = default_uv(name, lo, hi)
        face.pop("cullface", None)  # a turned element culls nothing
        normal = apply(turn, NORMALS[name])
        new = next(n for n, v in NORMALS.items() if all(abs(a - b) < 1e-9 for a, b in zip(v, normal)))
        rot = int(face.get("rotation", 0)) // 90
        # where each uv corner sits (box corner as -1/+1 per axis), before and after the turn
        corner_at = {}
        for i, c in enumerate(FACE_CORNERS[name]):
            corner_at[(i + rot) % 4] = apply(turn, [2 * x - 1 for x in c])
        for r in range(4):
            if all(all(abs(a - b) < 1e-9 for a, b in zip([2 * x - 1 for x in FACE_CORNERS[new][i]], corner_at[(i + r) % 4]))
                   for i in range(4)):
                break
        else:
            raise ValueError("no uv rotation turns %s onto %s" % (name, new))
        if r:
            face["rotation"] = 90 * r
        else:
            face.pop("rotation", None)
        out[new] = face
    return out


def convert_element(element, tier):
    """The element as a client of the tier can draw it, and how far a corner moved (0 if unchanged)."""
    rotation = element.get("rotation")
    if legal(rotation, tier):
        return element, 0.0
    lo = [min(a, b) for a, b in zip(element["from"], element["to"])]
    hi = [max(a, b) for a, b in zip(element["from"], element["to"])]
    centre = [(a + b) / 2 for a, b in zip(lo, hi)]
    half = [(b - a) / 2 for a, b in zip(lo, hi)]
    origin = rotation.get("origin", [8, 8, 8])
    matrix = rotation_matrix(rotation)
    # where the box's middle is drawn: the new element turns about it
    drawn = [o + d for o, d in zip(origin, apply(matrix, [c - o for c, o in zip(centre, origin)]))]
    axis, angle, turn, worst = nearest(matrix, half, tier)
    new_half = [abs(x) for x in apply(turn, half)]
    out = {k: v for k, v in element.items() if k not in ("from", "to", "rotation", "faces")}
    out["from"] = [round(d - h, 5) for d, h in zip(drawn, new_half)]
    out["to"] = [round(d + h, 5) for d, h in zip(drawn, new_half)]
    out["rotation"] = {"angle": angle, "axis": axis, "origin": [round(d, 5) for d in drawn]}
    if element.get("faces"):
        out["faces"] = turn_faces(element["faces"], turn, lo, hi)
    # keep the keys in the order Blockbench writes them
    order = ["name", "from", "to", "rotation", "shade", "light_emission", "faces"]
    return {k: out[k] for k in sorted(out, key=lambda k: order.index(k) if k in order else len(order))}, worst


def convert(model, tier):
    elements, worst = [], []
    for element in model["elements"]:
        new, moved = convert_element(element, tier)
        elements.append(new)
        if moved:
            worst.append((moved, element.get("name", "?")))
    out = dict(model)
    out["elements"] = elements
    return out, worst


def needs(model, tier):
    return any(not legal(e.get("rotation"), tier) for e in model.get("elements") or [])


def models():
    for namespace in sorted(os.listdir(ASSETS)):
        base = os.path.join(ASSETS, namespace, "models")
        for folder, _, files in os.walk(base):
            for name in sorted(files):
                path = os.path.join(folder, name)
                rel = os.path.relpath(path, ASSETS)
                if name.endswith(".json") and not rel.startswith(SKIP):
                    yield path, rel


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent="\t")
        f.write("\n")


def sync():
    """Each overlay copy as the base folder's model, the upgrader's changes and all, with its own elements."""
    synced = 0
    for directory, _, _ in OVERLAYS:
        overlay = os.path.join(ROOT, directory, "assets")
        for folder, _, files in os.walk(overlay):
            for name in files:
                path = os.path.join(folder, name)
                base = os.path.join(ASSETS, os.path.relpath(path, overlay))
                with open(path, encoding="utf-8") as f:
                    copy = json.load(f)
                with open(base, encoding="utf-8-sig") as f:
                    model = json.load(f)
                model["elements"] = copy["elements"]
                write(path, model)
                synced += 1
    print("%d overlay models take the base folder's textures and parents again" % synced)


def main():
    if "--sync" in sys.argv[1:]:
        sync()
        return
    check = "--check" in sys.argv[1:]
    if not check:
        for directory, _, _ in OVERLAYS:
            shutil.rmtree(os.path.join(ROOT, directory), ignore_errors=True)
    changed = 0
    for path, rel in models():
        try:
            with open(path, encoding="utf-8-sig") as f:
                model = json.load(f)
        except ValueError:
            continue
        if not isinstance(model, dict) or not needs(model, "old"):
            continue
        changed += 1
        old, old_worst = convert(model, "old")
        ranged, range_worst = (convert(model, "range") if needs(model, "range") else (model, []))
        print("%s: %d elements turned for clients to 1.21.5 (furthest corner %.2f units off, %s)%s" % (
            rel.replace(os.sep, "/"), len(old_worst), max(old_worst)[0], max(old_worst)[1],
            "; %d for 1.21.6 to 1.21.10 (%.2f)" % (len(range_worst), max(range_worst)[0]) if range_worst else
            "; 1.21.6 to 1.21.10 draw it as it is"))
        if check:
            continue
        write(os.path.join(ROOT, OVERLAY_EXACT, "assets", rel), model)
        write(os.path.join(ROOT, OVERLAY_RANGE, "assets", rel), ranged)
        write(path, old)
    print("%d models with rotations clients before 1.21.11 can't take%s" % (changed, "" if check else ", made into ones they can"))


if __name__ == "__main__":
    main()
