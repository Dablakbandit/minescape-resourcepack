"""Checks a built Bedrock pack and its Geyser mappings without starting a client.

    python check_bedrock.py DIR      (DIR holds minescape.mcpack, geyser_mappings.json, geyser_block_mappings.json)

Fails (exit 1) on what makes the game crash or draw nothing, so it is caught before anyone joins:
  - a texture over the size Bedrock accepts (over 16,384 px on a side aborts the game; we cap at 4,096)
  - a JSON file the game can't parse
  - a geometry identifier used by a block mapping, attachable or entity that no models/ file defines
  - a texture path used by an attachable, entity, item_texture.json or terrain_texture.json that isn't in the pack
  - an item icon or block texture key in the Geyser mappings that item_texture.json / terrain_texture.json lacks
Prints at most 20 examples of each problem and a count."""
import json
import re
import struct
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

MAX_SIDE = 4096
VANILLA_TEXTURES = {"textures/misc/enchanted_item_glint", "textures/misc/enchanted_actor_glint"}
VANILLA_GEOMETRY = re.compile(r"^minecraft:geometry\.|^geometry\.(humanoid|player|item_sprite|cross)")


def png_size(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", data[16:24])


def loads(text):
    # Bedrock accepts // comments in its JSON; strip whole-line ones before parsing.
    return json.loads("\n".join(l for l in text.splitlines() if not l.lstrip().startswith("//")))


def main(folder):
    folder = Path(folder)
    pack = zipfile.ZipFile(folder / "minescape.mcpack")
    names = set(pack.namelist())
    problems = defaultdict(list)
    docs = {}

    for name in names:
        if name.endswith(".json"):
            try:
                docs[name] = loads(pack.read(name).decode("utf-8-sig"))
            except Exception as e:
                problems["unparsable JSON"].append("%s: %s" % (name, e))
        elif name.endswith(".png"):
            size = png_size(pack.read(name)[:24])
            if size is None:
                problems["not a PNG"].append(name)
            elif max(size) > MAX_SIDE:
                problems["texture too large (crashes over 16384)"].append("%s %dx%d" % (name, *size))

    textures = {n[:-4] for n in names if n.endswith((".png", ".tga"))}

    def texture(path, where):
        if path and path not in textures and path not in VANILLA_TEXTURES:
            problems["missing texture"].append("%s -> %s" % (where, path))

    geometry = set()
    for name, doc in docs.items():
        if not name.startswith("models/") or not isinstance(doc, dict):
            continue
        for g in doc.get("minecraft:geometry", []):
            geometry.add(g.get("description", {}).get("identifier"))
        geometry.update(k.split(":")[0] for k in doc if k.startswith("geometry."))

    def geo(ident, where):
        if ident and not VANILLA_GEOMETRY.match(ident) and ident not in geometry:
            problems["missing geometry"].append("%s -> %s" % (where, ident))

    for name, doc in docs.items():
        for key in ("minecraft:attachable", "minecraft:client_entity"):
            desc = doc.get(key, {}).get("description") if isinstance(doc, dict) else None
            if not desc:
                continue
            for g in desc.get("geometry", {}).values():
                geo(g, name)
            for t in desc.get("textures", {}).values():
                texture(t, name)

    item_textures = docs.get("textures/item_texture.json", {}).get("texture_data", {})
    terrain = docs.get("textures/terrain_texture.json", {}).get("texture_data", {})
    for table, label in ((item_textures, "item_texture.json"), (terrain, "terrain_texture.json")):
        for key, entry in table.items():
            ts = entry.get("textures")
            for t in ts if isinstance(ts, list) else [ts]:
                texture(t if isinstance(t, str) else (t or {}).get("path"), "%s %s" % (label, key))

    items = json.loads((folder / "geyser_mappings.json").read_text("utf-8"))
    for java, defs in items["items"].items():
        for d in defs:
            icon = d.get("bedrock_options", {}).get("icon")
            if icon and icon not in item_textures:
                problems["item icon not in item_texture.json"].append("%s %s -> %s" % (java, d.get("bedrock_identifier"), icon))

    blocks_file = folder / "geyser_block_mappings.json"
    if blocks_file.exists():
        blocks = json.loads(blocks_file.read_text("utf-8"))["blocks"]
        for java, b in blocks.items():
            states = [b] + list(b.get("state_overrides", {}).values())
            for s in states:
                g = s.get("geometry")
                geo(g if isinstance(g, str) else (g or {}).get("identifier"), "block %s (%s)" % (java, b.get("name")))
                for m in s.get("material_instances", {}).values():
                    t = m.get("texture")
                    if t and t not in terrain:
                        problems["block texture not in terrain_texture.json"].append("%s -> %s" % (java, t))

    if not problems:
        print("bedrock pack OK: %d files, %d geometries, %d item icons, %d terrain textures"
              % (len(names), len(geometry), len(item_textures), len(terrain)))
        return 0
    for kind, found in sorted(problems.items()):
        unique = sorted(set(found))
        print("%s: %d" % (kind, len(unique)))
        for line in (unique if "-v" in sys.argv else unique[:20]):
            print("  " + line)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
