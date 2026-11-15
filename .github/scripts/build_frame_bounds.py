"""How far each item's model reaches from the middle of an item frame holding it, for the plugin's culling.

The server hides an item frame from a player when blocks stand between them, and has to know how big the thing in the
frame is: much of MineScape's scenery is item models in frames, some three blocks across, whose frame can be hidden
while the model is in plain view. For every item model with overrides (and the plain ones they fall back to), this
writes the radius in blocks of a sphere round the frame's middle that holds the model as a frame draws it: the
frame's half scale, then the model's "fixed" display transform, then its elements.

    python .github/scripts/build_frame_bounds.py [run/frame_bounds.json]

Run it after count_icons.py and before the 1.21.4 item upgrade: it reads the 1.18.2 item models' "overrides" lists.
The output, published beside mobs.json:

    {"version": 1, "default": 0.5,
     "items": {"minecraft:stone_pickaxe": {"base": r, "overrides": [[{"damage": 0.0076, "damaged": 0}, r], ...]}}}

overrides are in the model's own order; as the client does, the last whose every predicate is at or below the item's
own value applies. The plugin works the predicates out (damage is the damage over the item's durability).
"""
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ITEMS = os.path.join(ROOT, "assets", "minecraft", "models", "item")
# A flat item (builtin/generated and the like) in a frame: a half-block square.
FLAT = 0.5
# Slack for the frame's own offset from its wall and rounding.
MARGIN = 0.1

_cache = {}


def _load(name):
    ns, _, path = name.partition(":") if ":" in name else ("minecraft", "", name)
    f = os.path.join(ROOT, "assets", ns, "models", path + ".json")
    if not os.path.exists(f):
        return None
    with open(f, encoding="utf-8") as fh:
        return json.load(fh)


def _resolve(name, depth=0):
    """A model's elements and fixed display transform, each from the nearest model in its parent chain that has it."""
    model = _load(name)
    if model is None:
        return None, None
    elements = model.get("elements")
    fixed = (model.get("display") or {}).get("fixed")
    parent = model.get("parent")
    if (elements is None or fixed is None) and parent and depth < 16:
        pe, pf = _resolve(parent, depth + 1)
        elements = elements if elements is not None else pe
        fixed = fixed if fixed is not None else pf
    return elements, fixed


def radius(name):
    if name in _cache:
        return _cache[name]
    elements, fixed = _resolve(name)
    fixed = fixed or {}
    scale = max(abs(v) for v in fixed.get("scale", [1, 1, 1]))
    move = math.sqrt(sum((v / 16) ** 2 for v in fixed.get("translation", [0, 0, 0])))
    if not elements:
        r = FLAT * max(1.0, scale) + move * 0.5
    else:
        reach = 0.0
        for e in elements:
            for x in (e["from"][0], e["to"][0]):
                for y in (e["from"][1], e["to"][1]):
                    for z in (e["from"][2], e["to"][2]):
                        reach = max(reach, math.dist((x, y, z), (8, 8, 8)) / 16)
        # The frame draws its item at half size; the fixed transform moves, turns and scales it inside that.
        r = 0.5 * (move + scale * reach)
    r = round(r + MARGIN, 2)
    _cache[name] = r
    return r


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "run", "frame_bounds.json")
    items = {}
    for file in sorted(os.listdir(ITEMS)):
        if not file.endswith(".json"):
            continue
        item = file[:-5]
        with open(os.path.join(ITEMS, file), encoding="utf-8") as fh:
            model = json.load(fh)
        overrides = model.get("overrides") or []
        if not overrides:
            continue
        entry = {"base": radius("minecraft:item/" + item), "overrides": []}
        for o in overrides:
            entry["overrides"].append([o.get("predicate", {}), radius(o["model"])])
        items["minecraft:" + item] = entry
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"version": 1, "default": FLAT + MARGIN, "items": items}, fh, separators=(",", ":"))
    count = sum(len(e["overrides"]) for e in items.values())
    big = sum(1 for e in items.values() for _, r in e["overrides"] if r > 1.5)
    print("frame bounds: %d items, %d overrides (%d reach past 1.5 blocks), %d KB -> %s"
          % (len(items), count, big, os.path.getsize(out) // 1024, out))


if __name__ == "__main__":
    main()
