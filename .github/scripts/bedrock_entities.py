"""Bedrock custom entities for MineScape's Geyser extension: the animated mobs and skillcape props of
mobs/animated.json as Bedrock client entities, and bedrock_entities.json, the contract that also lists the item-frame
entities build_bedrock.py writes (one per 3D item look, drawn with the item's own geometry).

    bedrock_entities.build(pack_dir, out_dir, frames, frame_items)
        what build_bedrock.py calls: the mobs and props into the Bedrock pack it is putting together, and
        out_dir/bedrock_entities.json with them and the frames it passes
    python .github/scripts/bedrock_entities.py [--out DIR]
        the mobs and props alone into DIR (default cache/bedrock_entities), bedrock_entities.json beside them

On Java a mob is an item on an armour stand's head and a frame model an item in a (pack-invisible) item frame;
Geyser would show Bedrock players a bare stand and a frame block with a flat icon. The plugin tags those stands
and frames for Bedrock viewers, and the extension (bedrock/geyser-extension in the plugin repo) swaps them for
the entities written here. What ties the three together is bedrock_entities.json:

  {"format": 1, "tag": <16 bits, changes whenever an entity or what matches it does>,
   "entities": [{"identifier": "minescape:mob_mithril_dragon", "kind": "mob" | "prop" | "frame",
                 "match": {"item": "minecraft:leather_horse_armor", "custom_model_data": 100001}       (mob, prop)
                        | {"items": [["minecraft:stone_pickaxe", <cmd>, <damage>, <unbreakable>], ...]}  (frame)
                 "index": 12, "model": "ms:..."                 (frame: what the plugin's tag names, its Java model)
                 "clips": {"walking": 1, ...}, "clip_max": 8,   (mob, prop: the pack's clip ids; 0 is at rest)
                 "hitbox": [x0, y0, z0, x1, y1, z1],            (blocks about the entity's feet)
                 "scale": 1.0, ...}],
   "frame_items": {"<material>": {"by": "custom_model_data" | "damage", "entities": [[threshold, index], ...],
                                  "fallback": {...the other predicate, where a material has both}}}}

A frame's match lists every custom model data (or damage) the pack names for its look, with unbreakable false.
frame_items gives the same for any number: an item takes the entity of the highest threshold at or under its custom
model data (or damage); -1 is none (a flat item, the material's own look).

Properties (registered by the extension, read by the animation controllers here and build_bedrock.py's frame pose):
  minescape:clip      int 0..clip_max   the clip playing (mobs and props)
  minescape:seq       int 0..1023       counts clip starts, so the same clip played twice starts over
  minescape:facing    int 0..5          an item frame's facing (down, up, north, south, west, east)
  minescape:rotation  int 0..7          its item's rotation, 45 degrees a step
  minescape:invisible bool              an invisible frame, whose item sits a pixel nearer the wall

Geometry is built the way Blockbench exports a model to Bedrock (x mirrored, bones' x and y rotation negated)
from a model whose +z is the way the entity faces, under a root bone turned half round, since a Bedrock model
faces -z. A mob's .bbmodel is that already ("origin" props too).
"""
import argparse
import hashlib
import json
import math
import os
import re
import sys

import numpy as np
from PIL import Image

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(SCRIPTS, "..", ".."))
sys.path.insert(0, SCRIPTS)
import build_mobs  # noqa: E402  (its model definitions and texture reading; nothing of it is changed)

NAMESPACE = "minescape"
DEFAULT_OUT = os.path.join(ROOT, "cache", "bedrock_entities")
# the root bone's turn: a Bedrock model faces -z, these models face +z
ROOT_TURN = 180
RENDER_CONTROLLER = "controller.render.%s.default" % NAMESPACE
SEQ_MAX = 1023


# ---- geometry -----------------------------------------------------------------------------------------------------

def rnd(v, places=4):
    v = round(float(v), places)
    return 0.0 if v == 0 else v


class Atlas:
    """One texture for a model: whole textures and rotated patches packed in shelves; a face asks for a rectangle of
    one, and its place on the sheet is known once everything is in."""

    def __init__(self):
        self.images, self._by_key = [], {}

    def add(self, image, key=None):
        if key is not None and key in self._by_key:
            return self._by_key[key]
        self.images.append(image)
        index = len(self.images) - 1
        if key is not None:
            self._by_key[key] = index
        return index

    def patch(self, index, u0, v0, u1, v1, rotation):
        """A face's rectangle of image index turned clockwise as the face turns it, as a patch of its own."""
        image = self.images[index]
        a, b = sorted((u0, u1)), sorted((v0, v1))
        box = (int(math.floor(a[0])), int(math.floor(b[0])), max(int(math.floor(a[0])) + 1, int(math.ceil(a[1]))),
               max(int(math.floor(b[0])) + 1, int(math.ceil(b[1]))))
        piece = image.crop(box)
        if u0 > u1:
            piece = piece.transpose(Image.FLIP_LEFT_RIGHT)
        if v0 > v1:
            piece = piece.transpose(Image.FLIP_TOP_BOTTOM)
        piece = piece.rotate(-rotation, expand=True)
        return self.add(piece), (0, 0, piece.width, piece.height)

    def pack(self):
        """Lays everything out; returns the sheet and each image's corner on it."""
        area = sum(i.width * i.height for i in self.images)
        width = max([16] + [i.width for i in self.images])
        width = max(width, int(math.ceil(math.sqrt(area) / 16.0)) * 16)
        order = sorted(range(len(self.images)), key=lambda i: (-self.images[i].height, -self.images[i].width))
        places, x, y, row = {}, 0, 0, 0
        for i in order:
            w, h = self.images[i].size
            if x + w > width:
                x, y, row = 0, y + row, 0
            places[i] = (x, y)
            x += w
            row = max(row, h)
        height = max(16, y + row)
        sheet = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        for i, (px, py) in places.items():
            sheet.paste(self.images[i], (px, py))
        return sheet, places


def bedrock_face(name, rect):
    """A face's uv as Blockbench exports it to Bedrock: the up and down faces turned round."""
    u0, v0, u1, v1 = rect
    uv, size = [u0, v0], [u1 - u0, v1 - v0]
    if name in ("up", "down"):
        uv, size = [u0 + size[0], v0 + size[1]], [-size[0], -size[1]]
    return {"uv": [rnd(uv[0]), rnd(uv[1])], "uv_size": [rnd(size[0]), rnd(size[1])]}


class Cube:
    """A cube in model space (+z the way the entity faces, 16 a block, y up) as Blockbench keeps one: from, to,
    origin (pivot) and rotation (x, y, z degrees, Rz Ry Rx), and per face (atlas image, u0, v0, u1, v1)."""

    def __init__(self, low, high, origin=None, rotation=None, faces=None, inflate=0.0):
        self.low, self.high = np.array(low, float), np.array(high, float)
        self.origin = np.array(origin if origin is not None else (0, 0, 0), float)
        self.rotation = list(rotation) if rotation is not None else [0.0, 0.0, 0.0]
        self.faces = faces or {}
        self.inflate = inflate

    def export(self, places):
        size = self.high - self.low
        out = {"origin": [rnd(-self.high[0]), rnd(self.low[1]), rnd(self.low[2])], "size": [rnd(v) for v in size]}
        if any(abs(a) > 1e-6 for a in self.rotation):
            out["pivot"] = [rnd(-self.origin[0]), rnd(self.origin[1]), rnd(self.origin[2])]
            out["rotation"] = [rnd(-self.rotation[0]), rnd(-self.rotation[1]), rnd(self.rotation[2])]
        if self.inflate:
            out["inflate"] = rnd(self.inflate)
        faces = {}
        for name, (index, u0, v0, u1, v1) in self.faces.items():
            px, py = places[index]
            faces[name] = bedrock_face(name, (u0 + px, v0 + py, u1 + px, v1 + py))
        out["uv"] = faces
        return out


class Bone:
    def __init__(self, name, parent=None, pivot=(0, 0, 0), rotation=(0, 0, 0)):
        self.name, self.parent = name, parent
        self.pivot, self.rotation = list(pivot), list(rotation)
        self.cubes = []

    def export(self, places):
        out = {"name": self.name}
        if self.parent:
            out["parent"] = self.parent
        out["pivot"] = [rnd(-self.pivot[0]), rnd(self.pivot[1]), rnd(self.pivot[2])]
        if any(abs(a) > 1e-6 for a in self.rotation):
            out["rotation"] = [rnd(-self.rotation[0]), rnd(-self.rotation[1]), rnd(self.rotation[2])]
        if self.cubes:
            out["cubes"] = [c.export(places) for c in self.cubes]
        return out


def geometry(identifier, bones, atlas, bounds):
    """A geometry file and the atlas sheet its faces read."""
    sheet, places = atlas.pack()
    width, height, offset = bounds
    return {"format_version": "1.12.0", "minecraft:geometry": [{
        "description": {"identifier": identifier, "texture_width": sheet.width, "texture_height": sheet.height,
                        "visible_bounds_width": rnd(width, 2), "visible_bounds_height": rnd(height, 2),
                        "visible_bounds_offset": [0, rnd(offset, 2), 0]},
        "bones": [b.export(places) for b in bones]}]}, sheet


def client_entity(identifier, texture, geo, animations, animate, scripts=None):
    description = {"identifier": identifier, "materials": {"default": "entity_alphatest"},
                   "textures": {"default": texture}, "geometry": {"default": geo},
                   "render_controllers": [RENDER_CONTROLLER]}
    if animations:
        description["animations"] = animations
        description["scripts"] = dict(scripts or {}, animate=animate)
    return {"format_version": "1.10.0", "minecraft:client_entity": {"description": description}}


def write_json(path, data, indent=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=indent, separators=None if indent else (",", ":"))


def save_png(path, image):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    image.save(path, optimize=True)


# ---- mobs and props -----------------------------------------------------------------------------------------------

def keyframe_value(point):
    out = []
    for axis in "xyz":
        v = point.get(axis, 0)
        try:
            out.append(rnd(build_mobs.number(v)))
        except ValueError:
            out.append(str(v))  # Molang, as Blockbench would write it
    return out


def channel(keys):
    """A bone's keyframes of one channel as a Bedrock timeline."""
    keys = sorted(keys, key=lambda k: float(k["time"]))
    out, previous = {}, None
    for k in keys:
        value = keyframe_value(k["data_points"][0])
        stamp = "%g" % round(float(k["time"]), 4)
        interpolation = k.get("interpolation", "linear")
        if interpolation == "catmullrom":
            out[stamp] = {"post": value, "lerp_mode": "catmullrom"}
        elif interpolation == "step":
            out[stamp] = {"pre": previous if previous is not None else value, "post": value}
        else:
            out[stamp] = value
        previous = value
    return out


def controller(identifier, clip_ids):
    """Every clip a state twice over, one of each pair for an odd seq and one for an even: each start of a clip
    (seq goes up by one) is a move to the other of its pair, so a clip played again starts over."""
    states = {}
    names = [(c, p) for c in [0] + clip_ids for p in (0, 1)]

    def state(c, p):
        return "rest_%d" % p if c == 0 else "clip_%d_%d" % (c, p)

    for c, p in names:
        moves = [{state(c2, p2): "q.property('%s:clip') == %d && math.mod(q.property('%s:seq'), 2) == %d" % (NAMESPACE, c2, NAMESPACE, p2)}
                 for c2, p2 in names if (c2, p2) != (c, p)]
        body = {"transitions": moves, "blend_transition": 0.15}
        if c:
            body["animations"] = ["clip_%d" % c]
        states[state(c, p)] = body
    states["default"] = {"transitions": [{state(c, p): "q.property('%s:clip') == %d && math.mod(q.property('%s:seq'), 2) == %d"
                                          % (NAMESPACE, c, NAMESPACE, p)} for c, p in names]}
    return {"format_version": "1.10.0", "animation_controllers": {identifier: {"initial_state": "default", "states": states}}}


def build_mob(mob, out):
    """One animated mob or prop: geometry, texture, animations, controller and client entity. Returns its contract entry."""
    name = mob["name"]
    path = os.path.join(build_mobs.SOURCES, mob["model"])
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    errors, _ = build_mobs.check(d, mob)
    if errors:
        raise build_mobs.ModelError("\n".join("%s: %s" % (name, e) for e in errors))
    elements = {e["uuid"]: e for e in d["elements"]}
    groups = {g["uuid"]: g for g in d.get("groups", [])}
    animations = {a["name"]: a for a in d.get("animations", [])}
    clips = build_mobs.clip_list(mob, animations)

    lo = np.min([e["from"] for e in d["elements"]] + [e["to"] for e in d["elements"]], axis=0)
    hi = np.max([e["from"] for e in d["elements"]] + [e["to"] for e in d["elements"]], axis=0)
    anchored = bool(mob.get("origin", False))
    # a mob's middle over the stand, a prop's own origin (as build_mobs.py places them)
    shift = np.zeros(3) if anchored else np.array([-(lo[0] + hi[0]) / 2, 0.0, -(lo[2] + hi[2]) / 2])

    atlas = Atlas()
    per = {}

    def texture_of(ref):
        if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
            index = int(ref)
        else:
            index = next((i for i, t in enumerate(d["textures"]) if ref in (t.get("uuid"), t.get("id"))), None)
        if index is None or not 0 <= index < len(d["textures"]):
            raise build_mobs.ModelError("%s: a face reads a texture the model hasn't got" % name)
        if index not in per:
            t = d["textures"][index]
            image = build_mobs.texture_image(t, mob)
            per[index] = (atlas.add(image, ("bb", index)), image.width / float(t.get("uv_width", image.width)),
                          image.height / float(t.get("uv_height", image.height)))
        return per[index]

    root = "minescape_root"
    bones = [Bone(root, None, (0, 0, 0), (0, ROOT_TURN, 0))]
    names, used = {}, {root}

    def unique(n):
        base, i = re.sub(r"[^A-Za-z0-9_.]", "_", n or "bone"), 1
        out_name = base
        while out_name in used:
            i += 1
            out_name = "%s_%d" % (base, i)
        used.add(out_name)
        return out_name

    def walk(nodes, parent):
        for n in nodes:
            uid = n if isinstance(n, str) else n.get("uuid")
            if uid in elements:
                bone = next(b for b in bones if b.name == parent)
                bone.cubes.append(mob_cube(elements[uid]))
                continue
            g = groups.get(uid, n if isinstance(n, dict) else {})
            bone_name = unique(g.get("name"))
            names[uid] = bone_name
            bones.append(Bone(bone_name, parent, np.array(g.get("origin", [0, 0, 0]), float) + shift, g.get("rotation", [0, 0, 0])))
            walk(n.get("children", []) if isinstance(n, dict) else [], bone_name)

    def mob_cube(e):
        faces = {}
        for face, fd in e.get("faces", {}).items():
            if fd.get("texture") is None or not fd.get("uv"):
                continue
            index, pu, pv = texture_of(fd["texture"])
            u0, v0, u1, v1 = fd["uv"][0] * pu, fd["uv"][1] * pv, fd["uv"][2] * pu, fd["uv"][3] * pv
            if abs(u1 - u0) < 1e-9 or abs(v1 - v0) < 1e-9:
                continue
            rotation = int(fd.get("rotation", 0) or 0) % 360
            if rotation:
                patch, (a, b, c, e2) = atlas.patch(index, u0, v0, u1, v1, rotation)
                faces[face] = (patch, a, b, c, e2)
            else:
                faces[face] = (index, u0, v0, u1, v1)
        return Cube(np.array(e["from"], float) + shift, np.array(e["to"], float) + shift, np.array(e.get("origin", [0, 0, 0]), float) + shift,
                    e.get("rotation", [0, 0, 0]), faces, float(e.get("inflate", 0) or 0))

    # outliner groups may arrive as uuids with the groups listed apart (Blockbench 5) or inline (older)
    walk(d.get("outliner", []), root)

    # the size it is drawn at on Java, a block a 16 units for a prop, and a hitbox about its feet as build_mobs.py fits one
    if anchored:
        blocks_per_unit = 1.0 / 16
    else:
        f = 47.0 / float(max(hi - lo))
        blocks_per_unit = f * build_mobs.HEAD_ITEM * float(mob.get("scale", 1))
    scale = blocks_per_unit * 16
    extent = hi - lo
    half_x, half_z, height = 0.4 * extent[0] * blocks_per_unit, 0.4 * extent[2] * blocks_per_unit, max(0.1, hi[1] * blocks_per_unit)
    hitbox = [0, 0, 0, 0, 0, 0] if anchored else [rnd(-half_x, 2), 0, rnd(-half_z, 2), rnd(half_x, 2), rnd(height, 2), rnd(half_z, 2)]

    reach = max(abs(lo[0] + shift[0]), abs(hi[0] + shift[0]), abs(lo[2] + shift[2]), abs(hi[2] + shift[2])) / 16.0
    bounds = (2 * reach + 1, max(1.0, hi[1] / 16.0 + 1), hi[1] / 32.0)
    identifier = "%s:mob_%s" % (NAMESPACE, name)
    geo_id = "geometry.%s.mob.%s" % (NAMESPACE, name)
    geo, sheet = geometry(geo_id, bones, atlas, bounds)
    write_json(os.path.join(out, "models", "entity", NAMESPACE, "mob_%s.geo.json" % name), geo)
    texture = "textures/entity/%s/mobs/%s" % (NAMESPACE, name)
    save_png(os.path.join(out, texture + ".png"), sheet)

    anim_file = {"format_version": "1.8.0", "animations": {}}
    entity_animations = {"controller": "controller.animation.%s.mob.%s" % (NAMESPACE, name)}
    for cid, anim, end in clips:
        a = animations[anim]
        bones_out = {}
        for uid, an in a.get("animators", {}).items():
            if an.get("type") != "bone":
                continue
            # animators are keyed by their bone's uuid; by name for a model saved without one
            bone_name = names.get(uid) or names.get(next((u for u, g in groups.items() if g.get("name") == an.get("name")), None))
            if bone_name is None:
                continue
            timelines = {}
            for ch in ("rotation", "position", "scale"):
                keys = [k for k in an.get("keyframes", []) if k.get("channel") == ch]
                if keys:
                    timelines[ch] = channel(keys)
            if timelines:
                bones_out[bone_name] = timelines
        loop = {build_mobs.LOOP: True, build_mobs.HOLD: "hold_on_last_frame", build_mobs.ONCE: False}[end]
        anim_id = "animation.%s.mob.%s.%s" % (NAMESPACE, name, anim)
        anim_file["animations"][anim_id] = {"loop": loop, "animation_length": rnd(float(a.get("length", 0)), 4), "bones": bones_out}
        entity_animations["clip_%d" % cid] = anim_id
    write_json(os.path.join(out, "animations", NAMESPACE, "mob_%s.animation.json" % name), anim_file)
    clip_ids = [cid for cid, _, _ in clips]
    write_json(os.path.join(out, "animation_controllers", NAMESPACE, "mob_%s.ac.json" % name),
               controller(entity_animations["controller"], clip_ids))
    write_json(os.path.join(out, "entity", NAMESPACE, "mob_%s.entity.json" % name),
               client_entity(identifier, texture, geo_id, entity_animations, ["controller"]), indent=1)
    print("  %-26s %3d cubes, %2d bones, %d clips, %dx%d sheet, scale %.3f" % (identifier, len(d["elements"]), len(bones) - 1, len(clips),
                                                                            sheet.width, sheet.height, scale))
    return {"identifier": identifier, "kind": "prop" if anchored else "mob", "name": name,
            "match": {"item": "minecraft:leather_horse_armor", "custom_model_data": mob["custom_model_data"]},
            "clips": {anim: cid for cid, anim, _ in clips}, "clip_max": max(clip_ids) if clip_ids else 0,
            "hitbox": hitbox, "scale": rnd(scale, 5)}


# ---- the whole -----------------------------------------------------------------------------------------------------

def render_controllers():
    return {"format_version": "1.8.0", "render_controllers": {RENDER_CONTROLLER: {
        "geometry": "Geometry.default", "materials": [{"*": "Material.default"}], "textures": ["Texture.default"]}}}


def build(pack_dir, out_dir, frames=(), frame_items=None):
    """Writes the animated mobs and props into a Bedrock resource pack folder, and out_dir/bedrock_entities.json:
    them and the frame entities (entries) build_bedrock.py wrote. A model that can't be built stops the build.
    Returns the contract."""
    pack_dir = os.path.abspath(pack_dir)
    print("Bedrock entities -> %s" % pack_dir)
    write_json(os.path.join(pack_dir, "render_controllers", "%s.render_controllers.json" % NAMESPACE), render_controllers(), indent=1)
    entities, failed = [], []
    for mob in build_mobs.definitions():
        try:
            entities.append(build_mob(mob, pack_dir))
        except build_mobs.ModelError as e:
            failed.append(str(e))
    if failed:
        raise build_mobs.ModelError("These models can't be built for Bedrock:\n  " + "\n  ".join("\n".join(failed).split("\n")))
    entities += list(frames)
    signature = json.dumps([(e["identifier"], e["match"], e.get("clips")) for e in entities], sort_keys=True)
    contract = {"format": 1, "tag": int(hashlib.sha1(signature.encode("utf-8")).hexdigest()[:4], 16),
                "namespace": NAMESPACE,
                "properties": {"clip": "%s:clip" % NAMESPACE, "seq": "%s:seq" % NAMESPACE, "seq_max": SEQ_MAX,
                               "facing": "%s:facing" % NAMESPACE, "rotation": "%s:rotation" % NAMESPACE, "invisible": "%s:invisible" % NAMESPACE},
                "entities": entities, "frame_items": frame_items or {}}
    write_json(os.path.join(out_dir, "bedrock_entities.json"), contract, indent=1)
    print("  %d entities (%d frames), tag %04x -> %s" % (len(entities), len(frames), contract["tag"],
                                                         os.path.join(out_dir, "bedrock_entities.json")))
    return contract


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", default=DEFAULT_OUT, help="the Bedrock pack folder (default cache/bedrock_entities)")
    args = parser.parse_args()
    build(args.out, args.out)


if __name__ == "__main__":
    main()
