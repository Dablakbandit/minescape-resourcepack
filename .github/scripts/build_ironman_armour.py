"""Adds the ironman armours to the pack: each mode's OSRS helm, platebody and platelegs, and the group modes' bracers.

Platebodies and platelegs are worn leather armour (armour/chest.json, legs.json) on the plate looks, dyed each mode's
colour, the trimmed ones' trim a lighter shade of it as the group armours have theirs; bracers are worn gloves on the
vambraces' look (armour/gloves.json). Helms are the iron full helm's model with a texture tinted each mode's colour, its plume too.
Icons are OSRS's sprites (icons-items-complete.json, osrsbox ids). Run again, it changes nothing it already did.
leather_horse_armor.json is edited in its committed form: run count_icons.py --restore first if it has been rewritten.
"""
import base64, io, json, os, sys
from PIL import Image

PACK = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', '..')
ICONS = json.load(open(os.path.join(PACK, '.github/scripts/icons-items-complete.json')))
SPRITES = os.path.join(PACK, 'assets/minecraft/textures/item/ms/armor/ironman')
HELM_TEX = os.path.join(PACK, 'assets/minecraft/textures/item/custom/ironman')

# mode: (helm, platebody, platelegs, bracers) as (horse armour or armour number, OSRS id), and the colours
MODES = {
    'ironman': dict(helm=(4250, 12810), body=(10156, 12811), legs=(10160, 12812), colour='#8a8a8a', legs_colour='#767676', helm_colour='#4e4e4e', trim=False),
    'ultimate_ironman': dict(helm=(4251, 12813), body=(10157, 12814), legs=(10161, 12815), colour='#d4d4d4', legs_colour='#c4c4c4', helm_colour='#bcbcbc', trim=False),
    'hardcore_ironman': dict(helm=(4252, 20792), body=(10158, 20794), legs=(10162, 20796), colour='#7a1f1f', legs_colour='#6a1b1b', helm_colour='#661a1a', trim=True),
    'group_ironman': dict(helm=(4253, 26156), body=(10159, 26158), legs=(10163, 26166), bracers=(4256, 26168), colour='#3e4c6b', legs_colour='#3a465f',
                          helm_colour='#3a4560', bracers_colour='#3d6fb0', trim=True),
    'hardcore_group_ironman': dict(helm=(4254, 26170), body=(10160, 26172), legs=(10164, 26180), bracers=(4257, 26182), colour='#5e2a2a', legs_colour='#552626',
                                   helm_colour='#552626', bracers_colour='#a83a3a', trim=True),
    'unranked_group_ironman': dict(helm=(4255, 27042), body=(10161, 27048), legs=(10165, 27044), bracers=(4258, 27046), colour='#3b5a48', legs_colour='#36503f',
                                   helm_colour='#354c3f', bracers_colour='#3a9a6a', trim=True),
}
# the plugin's ItemCount.WORN_STAND_INS: bracers numbered above the dye's twelve bits, and the number each is worn as
WORN_STAND_INS = {4256: 4093, 4257: 4094, 4258: 4095}
# what OSRS names each piece (the unranked group pieces end "(unranked)")
NAMES = {'helm': 'helm', 'body': 'platebody', 'legs': 'platelegs', 'bracers': 'bracers'}


def item_name(mode, piece):
    if mode == 'unranked_group_ironman':
        return 'group_ironman_' + NAMES[piece] + '_unranked'
    return mode + '_' + NAMES[piece]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='\n') as f:
        f.write(text)


def sprite(osrs_id, name):
    """The OSRS sprite, padded to 36x36 as the pack's other armour icons are."""
    s = Image.open(io.BytesIO(base64.b64decode(ICONS[str(osrs_id)]))).convert('RGBA')
    s = s.crop(s.getbbox())
    pad = Image.new('RGBA', (36, 36))
    pad.alpha_composite(s, ((36 - s.size[0]) // 2, (36 - s.size[1]) // 2))
    os.makedirs(SPRITES, exist_ok=True)
    pad.save(os.path.join(SPRITES, name + '.png'))


def tinted_helm(name, colour):
    """The iron full helm's texture, its greys turned the mode's colour."""
    base = Image.open(os.path.join(PACK, 'assets/minecraft/textures/item/custom/ironhat.png')).convert('RGBA')
    target = tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))
    px = [p for p in base.getdata() if p[3]]
    mean = sum((p[0] + p[1] + p[2]) / 3 for p in px) / len(px)
    out = Image.new('RGBA', base.size)
    for y in range(base.size[1]):
        for x in range(base.size[0]):
            r, g, b, a = base.getpixel((x, y))
            k = ((r + g + b) / 3) / mean
            out.putpixel((x, y), tuple(min(255, int(c * k)) for c in target) + (a,))
    os.makedirs(HELM_TEX, exist_ok=True)
    out.save(os.path.join(HELM_TEX, name + '.png'))


def add_entries(path, entries):
    raw = open(path, 'rb').read().decode('utf-8')
    data = json.loads(raw)
    have = {e['custom_model_data'] for e in data['items']}
    lines = [json.dumps(e) for e in entries if e['custom_model_data'] not in have]
    if not lines:
        return
    # the files are an entry a line: the new ones go after the last
    nl = '\r\n' if '\r\n' in raw else '\n'
    last = raw.rindex('}', 0, raw.rindex(']'))
    raw = raw[:last + 1] + ''.join(',' + nl + '        ' + line for line in lines) + raw[last + 1:]
    json.loads(raw)
    open(path, 'wb').write(raw.encode('utf-8'))


chest, legs, gloves, overrides = [], [], [], []
for mode, m in MODES.items():
    helm, body, plate, bracers = (item_name(mode, p) for p in ('helm', 'body', 'legs', 'bracers'))
    sprite(m['body'][1], body)
    sprite(m['legs'][1], plate)
    write(os.path.join(PACK, 'assets/ms/models/chestplate', body + '.json'),
          '{"parent":"item/generated","textures":{"layer0":"item/ms/armor/blank","layer1":"item/ms/armor/ironman/' + body + '"}}\n')
    write(os.path.join(PACK, 'assets/ms/models/leggings', plate + '.json'),
          '{"parent":"item/generated","textures":{"layer0":"item/ms/armor/blank","layer1":"item/ms/armor/ironman/' + plate + '"}}\n')
    chest.append({'custom_model_data': m['body'][0], 'name': body, 'look': '78_platebody_blue_trimmed' if m['trim'] else '80_platebody_normal', 'colour': m['colour'],
                  'icon': 'ms:chestplate/' + body, 'shape': 'none'})
    legs.append({'custom_model_data': m['legs'][0], 'name': plate, 'look': '73_platelegs_blue_trimmed' if m['trim'] else '75_platelegs_normal', 'colour': m['legs_colour'],
                 'icon': 'ms:leggings/' + plate, 'shape': 'legs'})
    tinted_helm(helm, m['helm_colour'])
    write(os.path.join(PACK, 'assets/ms/models/headwear', helm + '.json'),
          '{"parent":"ms:diamond_hoe/iron_full_helm","textures":{"texture":"item/custom/ironman/' + helm + '","hat3":"item/custom/ironman/' + helm + '","particle":"item/custom/ironman/' + helm + '"}}\n')
    overrides.append((m['helm'][0], 'ms:headwear/' + helm))
    if 'bracers' in m:
        sprite(m['bracers'][1], bracers)
        write(os.path.join(PACK, 'assets/ms/models/armor/ironman', bracers + '.json'), '{"parent":"item/generated","textures":{"layer0":"item/ms/armor/ironman/' + bracers + '"}}\n')
        # worn gloves go out as twelve bits, so bracers above 4095 are known here by the stand-in the plugin sends them as
        gloves.append({'custom_model_data': WORN_STAND_INS[m['bracers'][0]], 'name': bracers, 'look': '2_vambraces', 'colour': m['bracers_colour']})
        overrides.append((m['bracers'][0], 'ms:armor/ironman/' + bracers))

add_entries(os.path.join(PACK, 'armour/chest.json'), chest)
add_entries(os.path.join(PACK, 'armour/legs.json'), legs)
add_entries(os.path.join(PACK, 'armour/gloves.json'), gloves)

# the horse armour overrides, after the last one, in the file's own layout
path = os.path.join(PACK, 'assets/minecraft/models/item/leather_horse_armor.json')
raw = open(path, 'rb').read().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
have = {o['predicate'].get('custom_model_data') for o in json.loads(raw)['overrides']}
add = ''.join(',' + nl + '    {' + nl + '      "predicate": {' + nl + '        "custom_model_data": ' + str(cmd) + nl + '      },' + nl + '      "model": "' + model + '"' + nl + '    }'
              for cmd, model in sorted(overrides) if cmd not in have)
if add:
    end = raw.rindex('}', 0, raw.rindex(']'))
    raw = raw[:end + 1] + add + raw[end + 1:]
    json.loads(raw)
    open(path, 'wb').write(raw.encode('utf-8'))
for mode, m in MODES.items():
    print(mode, {k: v for k, v in m.items() if isinstance(v, tuple)})
