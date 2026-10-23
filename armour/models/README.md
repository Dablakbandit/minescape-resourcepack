# Armour models

Each armour look is one Blockbench model, named after the look:

```
armour/models/chest/<look>.bbmodel     e.g. chest/80_platebody_normal.bbmodel
armour/models/legs/<look>.bbmodel      e.g. legs/72_plateskirt_normal.bbmodel
armour/models/boots/<look>.bbmodel     e.g. boots/64_armour_boots.bbmodel
```

Every item that uses a look (all its colours: bronze to rune, (g) and (t), degraded Barrows) gets that
look's model. The model is the whole look: its texture `<look>.png` is the flat look, which the build
also bakes into the armour sheets for players who can't run the model shaders.

## What's in a model

Open one in Blockbench ("Generic Model" format). The outliner has:

- one folder for the piece: **chestplate**, **leggings** or **boots**;
- inside it, a group per body part: **body**, **right_arm**, **left_arm**, **right_leg**, **left_leg**,
  each with its pivot where Minecraft's is (body `0 24 0`, right arm `5 22 0`, left arm `-5 22 0`, right
  leg `1.9 12 0`, left leg `-1.9 12 0`). A cube moves with the group it's in;
- **player (reference)**: a locked player to build around, grouped the same way so you can pose it. It is
  never exported.

Two textures:

- `<look>.png`: the flat look, on the boxes named `look <part>`, and what the armour sheets are baked
  from. It must keep this name: the build reads the look from it.
- `<look>_details.png`: everything else (pauldrons, skirts, belts, spikes).

Both follow the looks' colour rule, so one model works in every colour of its items:

| Texel | In game |
|---|---|
| exact grey (R = G = B), alpha 255 | dyed in the item's colour |
| alpha 254 | its own colour (gold, bone, gems) |
| grey, alpha 253 | a light shade of the item's colour ((t) trims) |
| alpha under 128 | nothing |

Blockbench shows the greys undyed.

## Limits

- Six faces of each body part make one layer; a look may use at most 8 layers (48 faces a body part),
  and 6 or fewer is better. Untextured faces cost nothing: leave faces that sit inside other cubes empty.
- Every cube within 32 pixels of its body part's pivot.
- At most 32 cubes a body part (the tracer, below, tests each one for every pixel: fewer is faster).
- No Blockbench animations: models move with the limbs.

## Where the models show

- **1.21.2 on:** drawn as geometry, by leather's extra layers (`.github/scripts/armour_models.py`).
- **1.18.2 to 1.21.1, and 26.3:** traced. Each body part's box becomes a card facing the eye, and the
  armour shader finds the model's cubes under each pixel of it. Costlier than geometry; cheaper with
  fewer cubes.
- **Shader packs:** with the Stitch mod (Iris or OptiFine), the same as without one. Without it the pack
  can't reach the armour: OptiFine shows the flat looks (its CIT), Iris cuts most of it out.
- **OptiFine from 1.21.2:** the flat looks. OptiFine gives an item's own texture to all its leather
  layers, the model layers too, so they can't draw the models.

The Barrows models are painted in the OSRS colours (own colours) rather than dyed.
