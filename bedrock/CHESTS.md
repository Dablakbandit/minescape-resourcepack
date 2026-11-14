# Item-grid windows on Bedrock

The bank, deposit box, group storage, shops, trades, the Grand Exchange and equipment stats stay real
chest windows for Bedrock players, so items can still be clicked. `.github/scripts/bedrock_chest_ui.py`
generates `ui/chest_screen.json` (desktop) and `ui/pocket_containers.json` (touch) into the pack, which
redraw them by the window's title. Every other
menu reaches Bedrock players as a Floodgate form, or as a plain chest.

## Title contract

The plugin (`BedrockLayout`, written by `WindowTitleListener`, Bedrock players only) sends:

    ms:<key>;<title>

- `<key>` is lower case letters and underscores, then a semicolon.
- `<title>` is the plain title to print: no glyphs, no colour codes.

The keys live in one place here, `LAYOUTS` in `bedrock_chest_ui.py` (key, the chest it draws over:
`large` 54 slots or `small` up to 27, the plugin's inventory class, its tints): the strip chain and each
key's layout come from it, so a new key is one line there plus the plugin's `ms:<key>;` title. Keys are
bank, deposit_box, group_storage, shop, trade, ge_main, ge_offer, ge_view, equipment.

A title containing `ms:` is printed with every known `ms:<key>;` taken out (`ms_chest_label`, and
`ms_title_label` on touch screens); any other title keeps the vanilla label and chest untouched. Each
key's layout (`ms_layout_<key>`) tints the rows and columns that are tabs, buttons or sides, one white
texture (`textures/ms/ui/white`) tinted by `color`:

- bank: the tab row (gold) and the button row (blue)
- group storage: the button row
- shop: the last slot, the Bedrock tap button
- trade: your side (green), the middle column, their side (red)
- deposit box: its two buttons

## How a layout is picked

The title is only readable through a property bag: each control that looks at it has
`"property_bag": {"#ms_t": "$container_title"}` (on touch screens `$header_label`) and view bindings on
`#ms_t`. A layout's `#visible` is `(not ((#ms_t - $ms_key) = #ms_t))`, true when the title contains its key;
the vanilla label is visible only when the title has no `ms:`; the printed title is `#ms_t` with every key
subtracted. Checked in game (1.26.63) with the bank, with the tints as single-colour textures; the white
texture tinted by `color` is not yet checked in game.

Tested and not working, so don't go back to them: `ignored` or `variables` `requires` on `$container_title`
(the variable is never the title while the screen is built), and a view binding straight from `#container_title`
into a label's text (visibility from it works, text doesn't). Images keep their texture's aspect ratio unless
`keep_ratio` is false, so the 16x16 tint needs it to stretch over a row.

## Taps

A touch screen has no right or shift click. In the bank and shops the info slot is a tap button for
Bedrock players that steps through what a tap does (bank: move, 1, 5, 10, X, all; shop: 1, 5, 10, X).
In a trade a tap on a stack asks how many, starting at all of it. Counts are written into item names
(`BedrockCountListener`), since Bedrock can't draw the Java pack's count shader.
