"""Builds the duel menu's icons into the pack: each rule and equipment slot on OSRS's 40px option button, as the
settings menu's are - plain when the thing is allowed, greyed and crossed out when the duel turns it off, and on
the red chosen button for Fun Weapons. Sprites are OSRS's own: item icons from .github/scripts/icons-items-complete.json
(osrsbox, by item id) and the equipment screen's slot sprites already in the pack. Writes the textures, their models
and bone.json overrides from BONE_START."""
import base64, glob, io, json, os, sys
from collections import Counter
from PIL import Image

PACK = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..")
BONE_START = 377
SETTINGS = os.path.join(PACK, 'assets/minecraft/textures/item/ms/interface/settings')
SLOTS = os.path.join(PACK, 'assets/minecraft/textures/item/ms/interface/equipment')
OUT_TEX = os.path.join(PACK, 'assets/minecraft/textures/item/ms/interface/duel')
OUT_MODEL = os.path.join(PACK, 'assets/ms/models/interface/duel')

# The rules in DuelRule's order, by OSRS item id; Fun Weapons is the one that allows rather than bans.
RULES = [('no_ranged', 841), ('no_melee', 1277), ('no_magic', 556), ('no_special_attack', 1215), ('fun_weapons', 4566),
         ('no_forfeit', 526), ('no_drinks', 2428), ('no_food', 385), ('no_prayer', 1718), ('no_movement', 1061),
         ('no_weapon_switch', 1325)]
# EquipmentSlot's order
SLOT_NAMES = ['head', 'cape', 'neck', 'ammo', 'body', 'shield', 'legs', 'hands', 'feet', 'ring', 'weapon']


def mode(files, keep=lambda p: True):
    ims = [Image.open(f).convert('RGBA') for f in files]
    w, h = ims[0].size
    res = Image.new('RGBA', (w, h))
    for y in range(h):
        for x in range(w):
            values = [i.getpixel((x, y)) for i in ims]
            kept = [v for v in values if keep(v)] or values
            res.putpixel((x, y), Counter(kept).most_common(1)[0][0])
    return res


def stone(p):
    # the button's grey stone, not the picture on it: little colour, neither dark nor bright
    r, g, b, a = p
    return a == 255 and max(r, g, b) - min(r, g, b) <= 14 and 45 <= (r + g + b) / 3 <= 125


def forty(pattern, keep):
    return [f for f in sorted(glob.glob(os.path.join(SETTINGS, pattern))) if Image.open(f).size == (40, 40) and keep(os.path.basename(f))]


# the stone button, as every plain 40px option has it behind its picture
plain = mode(forty('*.png', lambda n: not any(s in n for s in ('chosen', '_off', 'minimap', 'north_up'))))
# inside the frame, the stone alone (the outer ring is the frame, the same on all of them)
stone_only = mode(forty('*.png', lambda n: not any(s in n for s in ('chosen', '_off', 'minimap', 'north_up'))), stone)
for y in range(40):
    for x in range(40):
        if min(x, y, 39 - x, 39 - y) > 4:
            plain.putpixel((x, y), stone_only.getpixel((x, y)))
# where no button had stone showing, the nearest stone beside it
for y in range(5, 35):
    for x in range(5, 35):
        if not stone(plain.getpixel((x, y))):
            near = [plain.getpixel((x + dx, y + dy)) for d in range(1, 6) for dx, dy in ((-d, 0), (0, -d), (d, 0), (0, d)) if stone(plain.getpixel((x + dx, y + dy)))]
            if near:
                plain.putpixel((x, y), near[0])
# the chosen one's red ring: where the chosen minimap buttons differ from the plain ones
chosen_ring = mode(forty('minimap_*_chosen.png', lambda n: True))
plain_minimap = mode(forty('minimap_*.png', lambda n: 'chosen' not in n))
chosen = plain.copy()
for y in range(40):
    for x in range(40):
        if chosen_ring.getpixel((x, y)) != plain_minimap.getpixel((x, y)) and min(x, y, 39 - x, 39 - y) <= 4:
            chosen.putpixel((x, y), chosen_ring.getpixel((x, y)))
# the red cross from the turned-off compass, and how much darker a turned-off button is
off_example = Image.open(os.path.join(SETTINGS, 'north_up_off.png')).convert('RGBA')
cross = Image.new('RGBA', (40, 40))
for y in range(40):
    for x in range(40):
        r, g, b, a = off_example.getpixel((x, y))
        if a and x >= 20 and y >= 20 and r > 2 * g + 20 and r > 2 * b + 20:
            cross.putpixel((x, y), (r, g, b, a))
on_scoreboard = Image.open(os.path.join(SETTINGS, 'scoreboard_on.png')).convert('RGBA')
off_scoreboard = Image.open(os.path.join(SETTINGS, 'scoreboard_off.png')).convert('RGBA')
ratios = []
for y in range(6, 12):
    for x in range(3, 6):
        a, b = on_scoreboard.getpixel((x, y)), off_scoreboard.getpixel((x, y))
        if sum(a[:3]):
            ratios.append(sum(b[:3]) / sum(a[:3]))
DARK = sum(ratios) / len(ratios) if ratios else 0.75


def grey(im, factor):
    out = Image.new('RGBA', im.size)
    for y in range(im.size[1]):
        for x in range(im.size[0]):
            r, g, b, a = im.getpixel((x, y))
            v = int((0.3 * r + 0.59 * g + 0.11 * b) * factor)
            out.putpixel((x, y), (v, v, v, a))
    return out


def fit(sprite):
    sprite = sprite.crop(sprite.getbbox())
    w, h = sprite.size
    if max(w, h) > 30:
        s = 30 / max(w, h)
        sprite = sprite.resize((max(1, round(w * s)), max(1, round(h * s))), Image.NEAREST)
    return sprite


def compose(background, sprite, crossed):
    im = background.copy()
    if crossed:
        im = grey(im, DARK)
        sprite = grey(sprite, 0.6)
    w, h = sprite.size
    im.alpha_composite(sprite, ((40 - w) // 2, (40 - h) // 2))
    if crossed:
        im.alpha_composite(cross)
    return im


icons = json.load(open(os.path.join(PACK, '.github/scripts/icons-items-complete.json')))
os.makedirs(OUT_TEX, exist_ok=True)
os.makedirs(OUT_MODEL, exist_ok=True)
names = []
for name, item in RULES:
    sprite = fit(Image.open(io.BytesIO(base64.b64decode(icons[str(item)]))).convert('RGBA'))
    names.append((name, compose(plain, sprite, False)))
    names.append((name + '_on', compose(chosen, sprite, False) if name == 'fun_weapons' else compose(plain, sprite, True)))
for name in SLOT_NAMES:
    sprite = fit(Image.open(os.path.join(SLOTS, name + '_slot.png')).convert('RGBA'))
    names.append(('slot_' + name, compose(plain, sprite, False)))
    names.append(('slot_' + name + '_off', compose(plain, sprite, True)))

bone_path = os.path.join(PACK, 'assets/minecraft/models/item/bone.json')
raw = open(bone_path, 'rb').read().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
for i, (name, im) in enumerate(names):
    im.save(os.path.join(OUT_TEX, name + '.png'))
    with open(os.path.join(OUT_MODEL, name + '.json'), 'w', newline='\n') as f:
        f.write('{\n\t"parent": "item/generated",\n\t"textures": {\n\t\t"layer0": "item/ms/interface/duel/' + name + '"\n\t}\n}\n')
    cmd = BONE_START + i
    old = '{"predicate": {"custom_model_data":' + str(cmd) + '},"model":"item/empty"}'
    new = '{"predicate": {"custom_model_data":' + str(cmd) + '},"model":"ms:interface/duel/' + name + '"}'
    if new not in raw:
        assert raw.count(old) == 1, cmd
        raw = raw.replace(old, new)
open(bone_path, 'wb').write(raw.encode('utf-8'))
for i, (name, _) in enumerate(names):
    print(BONE_START + i, name)
