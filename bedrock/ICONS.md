# Item icons for Bedrock forms: `bedrock_icons.json`

`build_bedrock.py` writes `bedrock_icons.json` beside the pack (`build/bedrock/`), and CI publishes it with a
`.sha1` next to `minescape.mcpack` in each release. It names, for any Java item the server has, the picture in
`minescape.mcpack` that shows it, so the plugin can put it on a Floodgate form button as a `path` image. The
pack and the index come from the same build: take both from one release.

```json
{
  "build": "3f1c2a9b0d4e",
  "vanilla": {
    "book": "textures/ms/i/5d41402abc4b2a76",
    "chest": "textures/ms/i/7d793037a0760186"
  },
  "items": {
    "leather_horse_armor": {"by": "custom_model_data",
                            "icons": [[-1450, "textures/ms/i/..."], [1, "textures/ms/i/..."], [2, "textures/ms/i/..."]]},
    "diamond_hoe": {"by": "damage", "icons": [[1, "textures/ms/i/..."], [903, "textures/ms/i/..."]]},
    "leather_chestplate": {"by": "custom_model_data", "icons": [[10003, "textures/ms/i/..."]],
                           "fallback": {"by": "damage", "icons": [[5, "textures/ms/i/..."]]}}
  }
}
```

- `build`: a short hash of the index's contents; it changes whenever any path does.
- `vanilla`: every Minecraft 1.18.2 item (1,100, block items included), keyed by its id without `minecraft:`
  (the Bukkit `Material` in lower case), to its icon as the Java pack draws it with no custom model data.
- `items`: every material the Java pack has overrides for. `by` says what the thresholds are compared with:
  `custom_model_data`, or `damage` as a whole damage value (the build turns Java's damage fraction back into the
  lowest damage that reaches it, the same number as a Bedrock identifier's `_d<damage>`, e.g. `diamond_hoe_d903`).
  `icons` is ascending by threshold. `fallback`, on a material with both kinds (the leather armour pieces), is the
  other kind's rule, tried second as Geyser does.
- Every path is relative to the pack root without `.png`, as a form's `path` image wants it; files are named by
  their content, so many items share one.

## The rule

For an item of material `m`:

1. If `items[m]` exists: with `by` = `custom_model_data`, take the item's custom model data (skip to the
   fallback, or step 3, if it has none); with `damage`, its damage (0 if none). Pick the entry with the highest
   threshold at or under that number. If there is one, use its path.
2. Otherwise, if `items[m].fallback` exists, apply step 1 to it.
3. Otherwise use `vanilla[m]`.

A noted item's custom model data is negative (leather horse armour below zero): the same rule applies. A band
that is the material's own look, or whose model the pack hasn't got, holds `vanilla[m]`'s path.

## In the pack

`textures/item_texture.json` keys each Bedrock item's icon by its identifier (`ms.<identifier name>`, e.g.
`ms.diamond_hoe_d903`, `ms.leather_horse_armor_n12`), which is what `geyser_mappings.json`'s `icon` says, so the
mappings and the pack agree across builds. The forms read pictures by path, never by those keys.
