# Armour models

Each armour look is one Blockbench model, named after the look:

```
armour/models/chest/<look>.bbmodel     e.g. chest/80_platebody_normal.bbmodel
armour/models/legs/<look>.bbmodel      e.g. legs/72_plateskirt_normal.bbmodel
armour/models/boots/<look>.bbmodel     e.g. boots/64_armour_boots.bbmodel
armour/models/gloves/<look>.bbmodel    e.g. gloves/gloves.bbmodel
armour/models/amulets/<look>.bbmodel   e.g. amulets/16_gold_amulet_gem.bbmodel
armour/models/capes/<look>.bbmodel     e.g. capes/3_firecape.bbmodel
```

## One model, its textures swapped

Items whose looks have the same cubes can wear one model, each with its own images in place of the
model's textures. The item's line says which, by the texture's name in the model:

```json
{"custom_model_data": 661, "name": "attack", "look": "skill_cape", "textures": {"skill_cape_details.png": "skill_cape/11_attack_details.png"}}
```

The image's path is from the piece's folder (`armour/models/capes/` here). The build draws the item from
the model's cubes with the image in that texture's place; swap the flat look (`<model>.png`) and the
sheets get the item's own flat look too. An item with no `textures` wears the model as it is. An image is
laid out as the texture it takes the place of (the model's faces read the same places on it), and is as
big.

| Model | Its own textures | Images swapped in (in the folder named after it) |
|---|---|---|
| `capes/skill_cape` | the agility cape | every other skill cape and trimmed one: `<look>_details.png` |
| `amulets/gem_amulet` | the gold amulet (17 items) | accuracy, bronze, eternal glory, silver: `<look>.png`, `<look>_details.png` |
| `amulets/gem_necklace` | the gold necklace (20 items) | brass, silver |
| `amulets/flat_amulet` | the onyx necklace (no cubes) | each other's flat look, `<look>.png`: the god stoles, the unblessed and holy symbols, the amulet of power (t), the scarf |
| `amulets/36_glarials_amulet` | Glarial's amulet | none: the gnome amulet looks the same |
| `capes/basic_cape` | the red cape | the other colours, the Castle Wars cloaks, graceful, spotted and spottier |
| `capes/wings` | the wings | their colours |
| `capes/jester_cape` | the jester cape | black, orange |
| `capes/team_cape_<pattern>` | one team colour (circle, outline, x, claw, box, cross, dashed, horizontal, boxattop, scarab) | the pattern's other colours |
| `chest/apron` | the apron | the builder's shirt |
| `chest/dhide_body`, `legs/dhide_chaps` | the d'hide body and chaps | the (g) and (t) |
| `chest/mystic_robe_top`, `legs/mystic_robe_bottom` | blue | dusk, light, dark |
| `boots/boots` | the boots | the mime boots |
| `boots/decorative_boots` | gold | red, white |
| `boots/bark_boots` | splitbark | swampbark, bloodbark |
| `gloves/gloves` | the gloves | the vambraces and bracelets (their flat looks) |

To change a swapped look, paint its image. It has the model's layout, so you can paint it over an export
of the model's texture, or load it into the model in Blockbench to see it on the cubes (save the image,
not the model with it loaded). Change the cubes and every item wearing the model has them. For an amulet,
after changing its cubes or an image, `python .github/scripts/amulet_flat.py gem_amulet` draws the flat
looks again, the swapped ones into their own images.

To put more looks of one shape onto one model:

```
python .github/scripts/merge_models.py amulets/gem_necklace 27_gold_necklace_gem 23_brass_necklace_gem 29_silver_necklace_gem
```

The first look's textures become the model's, the others' that differ are written as images, the items
in `armour/<piece>.json` are changed to wear the model with them, and the looks' own models are removed.
It checks each look draws as it did; cubes stacked in one place are matched in the outliner's order. Looks whose textures are laid out differently are laid out again
as one, a face's texels only ever scaled up by a whole number.

Gloves, amulets and capes (`armour/gloves.json`, `armour/amulets.json`, `armour/capes.json`; how to
make and update them, with pictures, in [../README.md](../README.md) sections 4a and 4b) are looks too.
A cape's model has a **cape** folder of `shoulders`, `swing` and `flap` groups (section 4b). Gloves and
amulets:

- **gloves**: a flat look only, painted on the arms (dyed like any look). Their projects show it on
  `look right_arm` and `look left_arm` boxes in a **gloves** folder, over the reference player, so you
  can see it on the hands; only the texture is read.
- **amulets**: a model in an **amulet** folder whose **body** group holds its cubes (at most 32), hung
  from the neck: the chain round it, the pendant on the chest's front, about 2.6 pixels out (Blockbench z
  -2.6). Build it to sit on the bare body: the game sets what hangs in front of the body 1.5 pixels further
  out (`armour_models.AMULET_OUT`), and the chain over the shoulders stretches to meet the part behind
  the neck, so it lies on any chestplate from every side. The flat look `<look>.png` is its front, on the
  body's front (x 80-112, y 80-128), for where the model can't be drawn: made from the model by
  `python .github/scripts/amulet_flat.py <look>`, run after changing its cubes (the build warns if one
  is out of date). Painted in its own colours (alpha 254); an amulet with no cubes is drawn flat
  everywhere, its flat look painted by hand.

Every item that uses a look (all its colours: bronze to rune, (g) and (t), degraded Barrows) gets that
look's model. The model is the whole look: its texture `<look>.png` is the flat look, which the build
also bakes into the armour sheets for players who can't run the model shaders.

## What's in a model

Open one in Blockbench ("Generic Model" format). The outliner has:

- one folder for the piece: **chestplate**, **leggings**, **boots**, **gloves**, **amulet** or **cape**;
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
