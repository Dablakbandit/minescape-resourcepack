"""Fails the pack's build on an item model that would break its whole item from 26.1.

From 26.1 item models draw from their own texture atlas (textures/item/...), and a model must take all
its textures from one atlas. A texture that is missing (or a face naming a texture variable the model
never sets), or lives outside textures/item, comes from the
block atlas instead, so a model mixing it with item textures fails to bake - and takes every model of
its item definition down with it: one missing chicken texture turned every apple-headed mob into a
missing-texture square. Older clients show only that one texture missing.

    python .github/scripts/check_item_atlases.py [pack folder]

It reads item definitions (assets/minecraft/items), so CI runs it on the pack after the upgrade to
1.21.4's format.

Models whose textures are all outside textures/item only lose those textures, and are listed as
warnings. Vanilla parents and textures are taken as present.
"""
import json, os, sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", ".."))
ASSETS = os.path.join(ROOT, "assets")


def split(ref):
    namespace, _, path = ref.partition(":") if ":" in ref else ("minecraft", "", ref)
    return namespace, path


def model(ref):
    namespace, path = split(ref)
    file = os.path.join(ASSETS, namespace, "models", path + ".json")
    if not os.path.exists(file):
        return None
    with open(file, encoding="utf-8") as f:
        return json.load(f)


def textures(ref, depth=0):
    """The model's texture variables with its parents', or None if it isn't in the pack."""
    data = model(ref)
    if data is None or depth > 20:
        return None
    out = {}
    if data.get("parent"):
        out.update(textures(data["parent"], depth + 1) or {})
    out.update(data.get("textures") or {})
    return out


def faces(ref, depth=0):
    """What each face of the model's elements draws (its own elements, or its nearest parent's)."""
    data = model(ref)
    if data is None or depth > 20:
        return []
    if "elements" in data:
        return [face["texture"] for element in data["elements"] for face in (element.get("faces") or {}).values() if "texture" in face]
    return faces(data["parent"], depth + 1) if data.get("parent") else []


def resolve(value, variables):
    for _ in range(10):
        if not value.startswith("#"):
            return value
        value = variables.get(value[1:], value)
    return None


def models_in(node):
    if isinstance(node, dict):
        if node.get("type") in ("model", "minecraft:model") and isinstance(node.get("model"), str):
            yield node["model"]
        for value in node.values():
            yield from models_in(value)
    elif isinstance(node, list):
        for value in node:
            yield from models_in(value)


def main():
    items = os.path.join(ASSETS, "minecraft", "items")
    if not os.path.isdir(items):
        print("no item definitions (assets/minecraft/items): nothing to check")
        return 0
    fatal, warned, checked = [], [], set()
    for name in sorted(os.listdir(items)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(items, name), encoding="utf-8") as f:
            definition = json.load(f)
        for ref in sorted(set(models_in(definition))):
            if ref in checked:
                continue
            checked.add(ref)
            variables = textures(ref)
            if variables is None:
                continue
            in_items, other = [], []
            for value in variables.values():
                texture = resolve(value, variables)
                if texture is None or texture == "missingno":
                    continue
                namespace, path = split(texture)
                exists = os.path.exists(os.path.join(ASSETS, namespace, "textures", path + ".png"))
                # a vanilla texture the pack doesn't override; vanilla has no custom/ folders
                vanilla = namespace == "minecraft" and not exists and "custom/" not in path
                if path.startswith("item/") and (exists or vanilla):
                    in_items.append(texture)
                elif not (vanilla and not path.startswith("item/")):
                    other.append(texture + ("" if exists else " (missing)"))
            # a face naming a variable the model never sets draws the missing texture, from the block atlas
            for value in faces(ref):
                if resolve(value, variables) is None:
                    other.append(value + " (missing)")
            if in_items and other:
                fatal.append((name[:-5], ref, sorted(set(other))))
            elif other and any(o.endswith("(missing)") for o in other):
                warned.append((name[:-5], ref, sorted(set(other))))
    for item, ref, other in warned:
        print("warning: %s: %s draws %s" % (item, ref, ", ".join(other)))
    for item, ref, other in fatal:
        print("ERROR: %s: %s mixes item textures with %s - from 26.1 the whole %s item fails" % (item, ref, ", ".join(other), item))
    print("%d models checked, %d that break their item from 26.1, %d with textures missing" % (len(checked), len(fatal), len(warned)))
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
