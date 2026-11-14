"""The Bedrock hud's JSON UI: the pack's ui/hud_screen.json and ui/hud/ms_hud.json.

The plugin (BedrockHud) sends a Bedrock player their orbs, compass and XP drops as one action bar line of tokens,
starting "ms:hud:"; Geyser puts "§r" in front. The vanilla action bar control is made anew for each line with it as
$actionbar_text, so hud_screen.json clears that control's own label and gives it two children: the MineScape hud,
shown when the line has the tag, and a copy of the vanilla action bar, shown when it hasn't.

What Bedrock's JSON UI does reliably, tested in the game (26.63): a view binding that tests whether a property holds
a piece of text, ((#hud - 'piece') = #hud), on the line kept as a property (#hud) of the control. What it didn't do:
cut characters out of a worked-out string ('%.Ns' * (...)), join strings into a texture path ('a' + ...), or test
$actionbar_text in "ignored" or "requires". So nothing here reads a value out of the line: every orb picture, compass
direction, skill icon and digit the hud can show is a control of its own, shown while its token is in the line.

Tokens (BedrockHud): |c=N| compass; |h=KFF| an orb ('h' hitpoints, 'p' prayer, 'r' run, 's' special attack), kind
and fill; |h1=DC| .. |h3=DC| its number's digits, D the digit and C its colour; |dRsK=NN| an XP drop in row R, skill
icon K as a SkillType ordinal; |dRaK=D| its amount's digits, K from the left of 8.

Keep the tokens here in step with BedrockHud's. build_bedrock.py calls write_all(pack_dir); by hand:
    python .github/scripts/bedrock_hud_ui.py [PACK_DIR]       (default build/bedrock/pack)
"""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DEFAULT_PACK = os.path.join(ROOT, 'build', 'bedrock', 'pack')

TAG = 'ms:hud:'
# what starts a boss bar's title when the bar itself isn't to be drawn (BedrockBossBarListener.MARK)
BOSS_MARK = ''  # drawn blank by the pack's glyph page F8 (build_bedrock.py)
TEXTURES = 'textures/ms/hud/'
# the orbs in OSRS order (hp, prayer, run, spec), laid out two by two under the compass: (token, texture name, kinds)
ORBS = [('h', 'hp', 'np'), ('p', 'prayer', 'n'), ('r', 'run', 'fo'), ('s', 'spec', 'ra')]
FILLS = 27
NUMBER = 3
COLOURS = {'a': [0.0, 1.0, 0.0], 'e': [1.0, 1.0, 0.0], 'c': [1.0, 0.0, 0.0]}
SKILLS = 23
DROPS, DROP_SKILLS, AMOUNT = 6, 4, 8

ORB, TAB_WIDTH, TAB_HEIGHT, TAB_UNDER, GAP = 17, 26, 12, 2, 3
UNIT_WIDTH = TAB_WIDTH + ORB - TAB_UNDER
DIGIT = 6
ICON, ROW_HEIGHT = 10, 12
DROPS_WIDTH = DROP_SKILLS * (ICON + 1) + 2 + AMOUNT * DIGIT


def view(expression, target):
    return {'binding_type': 'view', 'source_property_name': expression, 'target_property_name': target}


def shown_with(token):
    """What makes a control show only while the line holds this token: the line as a property, tested in a binding."""
    return {'property_bag': {'#hud': '$actionbar_text'},
            'bindings': [view("(not ((#hud - '%s') = #hud))" % token, '#visible')]}


def picture(texture, size, token, **more):
    return dict({'type': 'image', 'texture': texture, 'size': size}, **shown_with(token), **more)


def digit(text, colour, token, **more):
    return dict({'type': 'label', 'text': text, 'color': colour, 'shadow': True, 'localize': False,
                 'size': [DIGIT, 10], 'text_alignment': 'center'}, **shown_with(token), **more)


def orb_unit(code, name, kinds):
    """An orb with its number on a tab to its left."""
    controls = [{'tab': {'type': 'image', 'texture': TEXTURES + 'tab_left', 'size': [TAB_WIDTH, TAB_HEIGHT],
                         'anchor_from': 'left_middle', 'anchor_to': 'left_middle', 'layer': 1}}]
    for kind in kinds:
        for fill in range(FILLS):
            controls.append({'o_%s%02d' % (kind, fill): picture(
                '%s%s_%s%02d' % (TEXTURES, name, kind, fill), [ORB, ORB], '|%s=%s%02d|' % (code, kind, fill),
                anchor_from='right_middle', anchor_to='right_middle', layer=2)})
    right = ORB + GAP
    for place in range(1, NUMBER + 1):
        x = -(right + (NUMBER - place) * DIGIT)
        for d in '0123456789':
            for c, colour in COLOURS.items():
                controls.append({'n%d_%s%s' % (place, d, c): digit(
                    d, colour, '|%s%d=%s%s|' % (code, place, d, c),
                    anchor_from='right_middle', anchor_to='right_middle', offset=[x, 1], layer=3)})
    return {'type': 'panel', 'size': [UNIT_WIDTH, ORB + 2], 'controls': controls}


def compass_unit():
    controls = [{'c%d' % n: picture('%scompass_%d' % (TEXTURES, n), [20, 20], '|c=%d|' % n,
                                    anchor_from='right_middle', anchor_to='right_middle', layer=2)} for n in range(8)]
    return {'type': 'panel', 'size': [UNIT_WIDTH, 22], 'controls': controls}


def drop_row(row):
    """One row of the XP drops: up to four skill icons, then the amount, right aligned."""
    controls = []
    for k in range(DROP_SKILLS):
        for skill in range(SKILLS):
            controls.append({'s%d_%02d' % (k, skill): picture(
                '%sskill_%02d' % (TEXTURES, skill), [ICON, ICON], '|d%ds%d=%02d|' % (row, k, skill),
                anchor_from='left_middle', anchor_to='left_middle', offset=[k * (ICON + 1), 0])})
    left = DROP_SKILLS * (ICON + 1) + 2
    for k in range(AMOUNT):
        for d in '0123456789':
            controls.append({'a%d_%s' % (k, d): digit(
                d, [1.0, 1.0, 1.0], '|d%da%d=%s|' % (row, k, d),
                anchor_from='left_middle', anchor_to='left_middle', offset=[left + k * DIGIT, 1])})
    return {'type': 'panel', 'size': [DROPS_WIDTH, ROW_HEIGHT], 'controls': controls}


def ms_hud():
    ui = {'namespace': 'ms_hud', 'compass': compass_unit()}
    for code, name, kinds in ORBS:
        ui['orb_' + name] = orb_unit(code, name, kinds)
    for row in range(DROPS):
        ui['drop_row_%d' % row] = drop_row(row)
    # the compass, and under it the orbs two by two: a single column of five ran down into Bedrock's sidebar,
    # which sits in the middle of the right edge
    pairs = [ORBS[i:i + 2] for i in range(0, len(ORBS), 2)]
    for i, pair in enumerate(pairs):
        ui['orb_row_%d' % i] = {
            'type': 'stack_panel', 'orientation': 'horizontal', 'size': [2 * UNIT_WIDTH, '100%c'],
            'controls': [{name + '@ms_hud.orb_' + name: {}} for _, name, _ in pair],
        }
    column_shown = {'property_bag': {'#hud': '$actionbar_text'},
                    'bindings': [view("((#hud - '|l=r|') = #hud)", '#visible')]}
    ui['orbs'] = dict(column_shown, **{
        'type': 'stack_panel', 'orientation': 'vertical', 'size': [2 * UNIT_WIDTH, '100%c'],
        'anchor_from': 'top_right', 'anchor_to': 'top_right', 'offset': [-4, 4],
        'controls': [{'compass_row': {'type': 'panel', 'size': [2 * UNIT_WIDTH, 22], 'controls': [
            {'compass@ms_hud.compass': {'anchor_from': 'top_right', 'anchor_to': 'top_right'}}]}}]
        + [{'row_%d@ms_hud.orb_row_%d' % (i, i): {}} for i in range(len(pairs))],
    })
    # "Orbs by Minimap" off (|l=r|): the Java hud's row above the hotbar, special attack, hitpoints, the compass,
    # prayer, run, left to right
    names = {code: name for code, name, _ in ORBS}
    ui['orbs_row'] = {
        'type': 'stack_panel', 'orientation': 'horizontal', 'size': ['100%c', 22],
        'anchor_from': 'bottom_middle', 'anchor_to': 'bottom_middle', 'offset': [0, -30],
        'property_bag': {'#hud': '$actionbar_text'}, 'bindings': [view("(not ((#hud - '|l=r|') = #hud))", '#visible')],
        'controls': [{'spec@ms_hud.orb_' + names['s']: {}}, {'hp@ms_hud.orb_' + names['h']: {}},
                     {'compass_cell': {'type': 'panel', 'size': [24, 22], 'controls': [
                         {'compass@ms_hud.compass': {'anchor_from': 'right_middle', 'anchor_to': 'right_middle', 'offset': [-2, 0]}}]}},
                     {'prayer@ms_hud.orb_' + names['p']: {}}, {'run@ms_hud.orb_' + names['r']: {}}],
    }
    # row 0 is the newest drop, at the foot; each older one a row higher, as OSRS's rise
    ui['drops'] = {
        'type': 'panel', 'size': [DROPS_WIDTH, DROPS * ROW_HEIGHT],
        'anchor_from': 'top_right', 'anchor_to': 'top_right', 'offset': [-(2 * UNIT_WIDTH + 10), 4],
        'controls': [{'row_%d@ms_hud.drop_row_%d' % (row, row): {
            'anchor_from': 'top_left', 'anchor_to': 'top_left', 'offset': [0, (DROPS - 1 - row) * ROW_HEIGHT]}}
            for row in range(DROPS)],
    }
    ui['hud'] = {
        'type': 'panel', 'size': ['100%', '100%'], 'layer': 10,
        'controls': [{'orbs@ms_hud.orbs': {}}, {'orbs_row@ms_hud.orbs_row': {}}, {'drops@ms_hud.drops': {}}],
    }
    return ui


def hud_screen():
    return {
        'namespace': 'hud',
        # the control the action bar factory makes for each line. A pack's element of a vanilla name is merged
        # into vanilla's, not put in its place: vanilla's own label (actionbar_message) would stay and print the
        # line as text. So its label is taken out, its background cleared, and it holds either the MineScape
        # hud or a copy of the vanilla action bar, chosen by a binding on the line held as a property (#hud).
        'hud_actionbar_text': {
            'size': ['100%', '100%'],
            'offset': [0, 0],
            'texture': '',
            'modifications': [
                {'array_name': 'controls', 'operation': 'remove', 'control_name': 'actionbar_message'},
                {'array_name': 'controls', 'operation': 'insert_back', 'value': [
                    {'ms_hud@ms_hud.hud': {'property_bag': {'#hud': '$actionbar_text'},
                                           'bindings': [view("(not ((#hud - '%s') = #hud))" % TAG, '#visible')]}},
                    {'vanilla_actionbar@hud.ms_vanilla_actionbar': {'property_bag': {'#hud': '$actionbar_text'},
                                                                    'bindings': [view("((#hud - '%s') = #hud)" % TAG, '#visible')]}},
                ]},
            ],
        },
        # boss bars: the Java pack's bar art, tinted by the bar's colour, and none at all for a bar the server marks
        # (BedrockBossBarListener: a yellow bar, whose bar the Java pack draws blank, starts its title with BOSS_MARK)
        'boss_health_panel': {
            'modifications': [
                {'array_name': 'controls', 'operation': 'remove', 'control_name': 'progress_bar_for_collections'},
                {'array_name': 'controls', 'operation': 'insert_back', 'value': [{'ms_boss_bar@hud.ms_boss_bar': {'offset': [0, 10]}}]},
            ],
        },
        'ms_boss_bar': {
            'type': 'panel', 'size': [182, 5], 'anchor_from': 'top_middle', 'anchor_to': 'top_middle',
            'bindings': [{'binding_name': '#bossName', 'binding_type': 'collection', 'binding_collection_name': 'boss_bars'},
                         view("((#bossName - '%s') = #bossName)" % BOSS_MARK, '#visible')],
            'controls': [
                {'background': {'type': 'image', 'texture': 'textures/ms/ui/boss_background', 'size': ['100%', '100%'], 'layer': 1,
                                'color': '#color', 'bindings': [{'binding_name': '#bar_color', 'binding_name_override': '#color',
                                                                 'binding_type': 'collection', 'binding_collection_name': 'boss_bars'}]}},
                {'progress': {'type': 'image', 'texture': 'textures/ms/ui/boss_progress', 'size': ['100%', '100%'], 'layer': 2,
                              'clip_direction': 'left', 'clip_pixelperfect': False, 'color': '#color',
                              'bindings': [{'binding_name': '#progress_percentage', 'binding_name_override': '#clip_ratio',
                                            'binding_type': 'collection', 'binding_collection_name': 'boss_bars'},
                                           {'binding_name': '#bar_color', 'binding_name_override': '#color',
                                            'binding_type': 'collection', 'binding_collection_name': 'boss_bars'}]}},
            ],
        },
        # the vanilla action bar, as hud_actionbar_text has it
        'ms_vanilla_actionbar': {
            'type': 'image',
            'size': ['100%c + 12px', '100%c + 5px'],
            'offset': [0, '50%-68px'],
            'texture': 'textures/ui/hud_tip_text_background',
            'alpha': '@hud.anim_actionbar_text_background_alpha_out',
            'controls': [{
                'actionbar_message': {
                    'type': 'label',
                    'anchor_from': 'center',
                    'anchor_to': 'center',
                    'color': '$tool_tip_text',
                    'enable_profanity_filter': True,
                    'layer': 31,
                    'text': '$actionbar_text',
                    'shadow': True,
                    'localize': False,
                    'alpha': '@hud.anim_actionbar_text_alpha_out',
                },
            }],
        },
    }


def write(path, ui):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as out:
        json.dump(ui, out, indent=1, ensure_ascii=False)
        out.write('\n')


def write_all(pack):
    """hud_screen.json and hud/ms_hud.json into the pack folder's ui/. Returns them, relative to the pack."""
    write(os.path.join(pack, 'ui', 'hud_screen.json'), hud_screen())
    write(os.path.join(pack, 'ui', 'hud', 'ms_hud.json'), ms_hud())
    return ['ui/hud_screen.json', 'ui/hud/ms_hud.json']


if __name__ == '__main__':
    print('Wrote', ', '.join(write_all(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PACK)))
