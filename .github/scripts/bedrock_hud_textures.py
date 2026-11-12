"""The Bedrock hud's pictures, from the Java pack's: the orbs at every fill, the number tabs, the compass and the
skill icons the XP drops show, under the pack's textures/ms/hud/ by the names the Bedrock hud builds from the
plugin's hud line (BedrockHud in the plugin, ui/hud/ms_hud.json from bedrock_hud_ui.py):

    <orb>_<kind><fill>.png   hp_n, hp_p (poisoned), prayer_n, run_f (walking), run_o (running), spec_r (ready),
                             spec_a (armed); fill 00..26
    compass_<n>.png          n 0..7, the way the camera faces in eighths from south, west of it first
    tab_left.png, tab_right.png
    skill_<nn>.png           SkillType's order, 00..22

build_bedrock.py calls write_all(pack_dir); by hand: python .github/scripts/bedrock_hud_textures.py [PACK_DIR]
(default build/bedrock/pack).
"""
import os
import sys

from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
HUD = os.path.join(ROOT, 'assets', 'minecraft', 'textures', 'font', 'hud')
SKILLS = os.path.join(ROOT, 'assets', 'minecraft', 'textures', 'font', 'unicode_page_90_flat.png')
DEFAULT_PACK = os.path.join(ROOT, 'build', 'bedrock', 'pack')
OUT = os.path.join(DEFAULT_PACK, 'textures', 'ms', 'hud')

FILLS = range(27)
# the Java hud font's compass glyphs, in its order (HudUtils.COMPASS_POINT)
COMPASS = ['south', 'south_west', 'west', 'north_west', 'north', 'north_east', 'east', 'south_east']
# SkillType, in its order: the hud font's skill icons U+F400 on, one 16 pixel cell each of the page
SKILL_COUNT = 23
CELL = 16


def save(image, name):
    image.convert('RGBA').save(os.path.join(OUT, name + '.png'), optimize=True)


def orb(folder, prefix, out, lowest=0):
    """An orb at every fill, 0 to 26; one with no picture for a fill takes the lowest it has (hitpoints start at 1)."""
    for fill in FILLS:
        source = os.path.join(HUD, folder, '%s%d.png' % (prefix, max(fill, lowest)))
        save(Image.open(source), '%s%02d' % (out, fill))


def write_all(pack):
    """Every hud texture into the pack folder's textures/ms/hud/. Returns how many."""
    global OUT
    OUT = os.path.join(pack, 'textures', 'ms', 'hud')
    os.makedirs(OUT, exist_ok=True)
    orb('hitpoints', '', 'hp_n', lowest=1)
    orb('hitpoints_poison', '', 'hp_p', lowest=1)
    orb('prayer', '', 'prayer_n')
    orb('run', 'off_', 'run_f')
    orb('run', 'on_', 'run_o')
    orb('spec', 'ready_', 'spec_r')
    orb('spec', 'armed_', 'spec_a')
    for index, way in enumerate(COMPASS):
        save(Image.open(os.path.join(HUD, 'compass', way + '.png')), 'compass_%d' % index)
    for side in ('left', 'right'):
        save(Image.open(os.path.join(HUD, 'orb_tab', side + '.png')), 'tab_' + side)
    page = Image.open(SKILLS).convert('RGBA')
    for skill in range(SKILL_COUNT):
        save(page.crop((skill * CELL, 0, skill * CELL + CELL, CELL)), 'skill_%02d' % skill)
    return len(os.listdir(OUT))


if __name__ == '__main__':
    count = write_all(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PACK)
    print('Wrote %d Bedrock hud textures to %s' % (count, OUT))
