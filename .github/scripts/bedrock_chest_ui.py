"""MineScape's item-grid windows for Bedrock players: ui/chest_screen.json (desktop) and ui/pocket_containers.json
(touch). build_bedrock.py calls write_all(pack).

    python .github/scripts/bedrock_chest_ui.py [PACK_DIR]     default build/bedrock/pack

The bank, deposit box, group storage, shops, trades, the Grand Exchange and equipment stats stay real chest windows
(items can still be clicked and moved); these files redraw the top half of a chest by the window's title. The plugin
(BedrockLayout, sent by WindowTitleListener to Bedrock players only) titles such a window

    ms:<key>;<title>

<key> lower case letters and underscores, then a semicolon, then the plain title to print. LAYOUTS below is the one
list of keys in this repo: the strip chain and each key's layout come from it (bedrock/CHESTS.md). A title containing "ms:" prints with every known
"ms:<key>;" taken out; any other title keeps the vanilla label and chest. A key's layout tints the slots that are
tabs, buttons or sides, drawn as one white texture tinted by its colour.
"""
import json
import os
import sys

from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CELL = 18
LARGE, SMALL = [162, 108], [162, 54]   # the 9x6 grid of a large chest, the 9x3 of a small one
TINT_TEXTURE = "textures/ms/ui/white"
TINT_ALPHA = 0.35
# the tints' colours, 0-255
COLOURS = {"tabs": (214, 168, 54), "buttons": (64, 120, 200), "divider": (90, 90, 90),
           "yours": (70, 160, 80), "theirs": (190, 70, 60)}
# key -> (window, menu, [(tint, column, row, columns, rows)]): a window of up to 27 slots is a small chest
LAYOUTS = {
    "bank": ("large", "BankInventory", [("tabs", 0, 0, 9, 1), ("buttons", 0, 5, 9, 1)]),
    "deposit_box": ("small", "DepositBoxInventory", [("buttons", 3, 0, 1, 1), ("buttons", 5, 0, 1, 1)]),
    "group_storage": ("large", "GroupStorageInventory", [("buttons", 0, 5, 9, 1)]),
    "shop": ("large", "ShopInventory", [("buttons", 8, 5, 1, 1)]),
    "trade": ("large", "TradeInventory", [("yours", 0, 0, 4, 6), ("divider", 4, 0, 1, 6), ("theirs", 5, 0, 4, 6)]),
    "ge_main": ("large", "GrandExchangeMainInventory", []),
    "ge_offer": ("large", "GrandExchangeSlotInventory", []),
    "ge_view": ("large", "GrandExchangeViewInventory", []),
    "equipment": ("large", "EquipmentStatsInventory", []),
}


def colour(name):
    return [round(c / 255.0, 4) for c in COLOURS[name]]


def view(source, target):
    return {"binding_type": "view", "source_property_name": source, "target_property_name": target}


def stripped(prop):
    """The title with every known key taken out."""
    expression = prop
    for key in LAYOUTS:
        expression = "(%s - 'ms:%s;')" % (expression, key)
    return expression


def has_key(prop):
    return "(not ((%s - 'ms:') = %s))" % (prop, prop)


def no_key(prop):
    return "((%s - 'ms:') = %s)" % (prop, prop)


def label(text, colour_var, **more):
    return dict({"type": "label", "layer": 2, "offset": [7, -1], "size": ["90%", "default"],
                 "anchor_from": "top_left", "anchor_to": "top_left", "text": text, "color": colour_var}, **more)


def chest_screen():
    """The chest screen's top halves with the keyed title and layouts; the rest of the vanilla screen is kept."""
    ui = {"namespace": "chest"}
    ui["chest_label"] = label("$container_title", "$title_text_color", localize="$localize_title",
                              enable_profanity_filter=True, property_bag={"#ms_t": "$container_title"},
                              bindings=[view(no_key("#ms_t"), "#visible")])
    ui["ms_chest_label"] = label("#ms_title", "$title_text_color", localize=False, enable_profanity_filter=True,
                                 bindings=[view(stripped("#ms_t"), "#ms_title"), view(has_key("#ms_t"), "#visible")],
                                 property_bag={"#ms_t": "$container_title", "#ms_title": ""})
    # images keep their texture's aspect ratio unless keep_ratio is false: the tint stretches over its slots
    ui["ms_tint"] = {"type": "image", "texture": TINT_TEXTURE, "color": "$ms_tint_color", "alpha": TINT_ALPHA, "layer": 3,
                     "anchor_from": "top_left", "anchor_to": "top_left", "size": "$ms_tint_size", "offset": "$ms_tint_offset",
                     "keep_ratio": False}
    ui["ms_layout"] = {"type": "panel", "anchor_from": "top_left", "anchor_to": "top_left", "$ms_key|default": "ms:none;",
                       "property_bag": {"#ms_t": "$container_title"},
                       "bindings": [view("(not ((#ms_t - $ms_key) = #ms_t))", "#visible")]}

    def layouts(name, window, size):
        controls = []
        for key, (kind, _, tints) in LAYOUTS.items():
            if kind != window:
                continue
            element = "ms_layout_" + key
            ui[element] = {"type": "panel", "size": size, "$ms_key": "ms:%s;" % key, "controls": [
                {"%s_%d@chest.ms_tint" % (tint, i): {"$ms_tint_color": colour(tint),
                                                       "$ms_tint_size": [columns * CELL, rows * CELL],
                                                       "$ms_tint_offset": [column * CELL, row * CELL]}}
                for i, (tint, column, row, columns, rows) in enumerate(tints)]}
            controls.append({"%s@chest.ms_layout" % key: {"size": size, "$ms_key": "ms:%s;" % key,
                                                          "controls": [{"tints@chest." + element: {}}]}})
        ui[name] = {"type": "panel", "size": size, "anchor_from": "top_left", "anchor_to": "top_left", "controls": controls}

    layouts("ms_large_layouts", "large", LARGE)
    layouts("ms_small_layouts", "small", SMALL)
    for half, size, offset, grid, grid_offset in (("small", ["100%", "50%"], [0, 12], "small", [7, 9]),
                                                  ("large", ["100%", 132], [0, 11], "large", [7, 10])):
        ui["%s_chest_panel_top_half" % half] = {
            "type": "panel", "size": size, "offset": offset, "anchor_to": "top_left", "anchor_from": "top_left",
            "controls": [{"chest_label@chest.chest_label": {}}, {"ms_chest_label@chest.ms_chest_label": {}},
                         {"%s_chest_grid@chest.%s_chest_grid" % (grid, grid): {"offset": grid_offset}},
                         {"ms_%s_layouts@chest.ms_%s_layouts" % (grid, grid): {"offset": grid_offset}}]}
    return ui


def pocket_containers():
    """The touch-screen chest's header: a keyed title prints without its key; every other header is vanilla's."""
    return {"namespace": "pocket_containers", "header_panel": {
        "type": "panel", "layer": 1, "size": ["50%", "27px"], "anchor_from": "top_left", "anchor_to": "top_left",
        "controls": [
            {"header_background": {"type": "image", "texture": "textures/ui/header_bar"}},
            {"title_label@generic_label": {"text": "$header_label", "localize": "$localize_title", "enable_profanity_filter": True,
                                           "property_bag": {"#ms_t": "$header_label"},
                                           "bindings": [view(no_key("#ms_t"), "#visible")]}},
            {"ms_title_label@generic_label": {"text": "#ms_title", "localize": False, "enable_profanity_filter": True,
                                              "bindings": [view(stripped("#ms_t"), "#ms_title"), view(has_key("#ms_t"), "#visible")],
                                              "property_bag": {"#ms_t": "$header_label", "#ms_title": ""}}},
        ]}}


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, indent=2) + "\n")


def write_all(pack):
    """The two ui files and the tint texture into the pack folder. Returns the ui files written, relative to it."""
    write(os.path.join(pack, "ui", "chest_screen.json"), chest_screen())
    write(os.path.join(pack, "ui", "pocket_containers.json"), pocket_containers())
    texture = os.path.join(pack, *TINT_TEXTURE.split("/")) + ".png"
    os.makedirs(os.path.dirname(texture), exist_ok=True)
    Image.new("RGBA", (16, 16), (255, 255, 255, 255)).save(texture, optimize=True)
    return ["ui/chest_screen.json", "ui/pocket_containers.json"]


if __name__ == "__main__":
    print("wrote", ", ".join(write_all(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "build", "bedrock", "pack"))))
