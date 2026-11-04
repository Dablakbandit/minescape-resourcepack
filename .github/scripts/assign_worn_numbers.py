"""Gives every gloves, amulet and cape item numbered past the dye's twelve bits (above 4095) a number to be worn as.

A worn item's number goes out in its armour piece's dye, which has twelve bits for it (armour_looks.GLOVES_NUMBERS).
An item numbered up to 4095 is worn as its own number; one above gets "worn": the highest number its table doesn't
use, kept from then on, so an item never changes what it's worn as. The plugin learns them from these tables (its
tools/generate_worn_numbers.py), and sends nothing for an item whose own number another's has been given.
"""
import json, os, re, sys

ARMOUR = os.path.join(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', '..'), 'armour')
LIMIT = 4096

for kind in ('gloves', 'amulets', 'capes'):
    path = os.path.join(ARMOUR, kind + '.json')
    raw = open(path, 'rb').read().decode('utf-8')
    entries = json.loads(raw)['items']
    used = {e.get('worn', e['custom_model_data']) for e in entries if 'worn' in e or e['custom_model_data'] < LIMIT}
    free = (n for n in range(LIMIT - 1, 0, -1) if n not in used)
    for entry in entries:
        if entry['custom_model_data'] < LIMIT or 'worn' in entry:
            continue
        number = next(free)
        # each entry is a line: the number goes in after its custom model data
        line = re.compile(r'("custom_model_data": %d)(, )' % entry['custom_model_data'])
        raw, n = line.subn(r'\1, "worn": %d\2' % number, raw, count=1)
        assert n == 1, (kind, entry['custom_model_data'])
        print('%s %s (%d): worn as %d' % (kind, entry.get('name'), entry['custom_model_data'], number))
    json.loads(raw)
    open(path, 'wb').write(raw.encode('utf-8'))
