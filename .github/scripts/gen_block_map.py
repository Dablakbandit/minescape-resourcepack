"""Builds .github/scripts/bedrock_block_textures.json (read by build_bedrock.py): each Java block texture (assets/minecraft/textures/block/*.png)
-> the Bedrock vanilla texture paths it replaces. Bedrock paths come from the installed game's vanilla
terrain_texture.json (read here once; CI only reads the committed table).

    python gen_block_map.py <vanilla resource pack dir> <java block texture dir> <out json>
"""
import json, os, re, sys

VAN, JAVA, OUT = sys.argv[1:4]


def load(p):
    return json.loads(re.sub(r'//.*', '', open(p, encoding='utf-8').read()))


import glob
terrain = {}
for f in sorted(glob.glob(os.path.join(os.path.dirname(VAN), 'vanilla*', 'textures', 'terrain_texture.json'))):
    try:
        terrain.update(load(f)['texture_data'])
    except (OSError, ValueError, KeyError):
        pass
paths = set()
flip = set()
for v in terrain.values():
    tx = v['textures']
    for x in (tx if isinstance(tx, list) else [tx]):
        if isinstance(x, dict):
            if 'variations' in x:
                for y in x['variations']:
                    paths.add(y['path'])
                continue
            x = x.get('path')
        if isinstance(x, str):
            paths.add(x)
for fb in glob.glob(os.path.join(os.path.dirname(VAN), 'vanilla*', 'textures', 'flipbook_textures.json')):
    try:
        for f in load(fb):
            flip.add(f['flipbook_texture'])
    except (OSError, ValueError):
        pass
by_name = {}
for p in paths:
    by_name.setdefault(os.path.basename(p), set()).add(p)

WOOD = {'oak': 'oak', 'spruce': 'spruce', 'birch': 'birch', 'jungle': 'jungle', 'acacia': 'acacia', 'dark_oak': 'big_oak'}
COLOUR = {c: c for c in ['white', 'orange', 'magenta', 'light_blue', 'yellow', 'lime', 'pink', 'gray', 'cyan', 'purple', 'blue',
                          'brown', 'green', 'red', 'black']}
COLOUR['light_gray'] = 'silver'
FIXED = {
    'grass_block_top': ['grass_top'],
    'grass_block_snow': ['grass_side_snowed'], 'dirt_path_top': ['grass_path_top'], 'dirt_path_side': ['grass_path_side'],
    'grass_path_top': ['grass_path_top'], 'grass_path_side': ['grass_path_side'],
    'stone_bricks': ['stonebrick'], 'mossy_stone_bricks': ['stonebrick_mossy'], 'cracked_stone_bricks': ['stonebrick_cracked'],
    'chiseled_stone_bricks': ['stonebrick_carved'], 'bricks': ['brick'], 'mossy_cobblestone': ['cobblestone_mossy'],
    'andesite': ['stone_andesite'], 'polished_andesite': ['stone_andesite_smooth'], 'diorite': ['stone_diorite'],
    'polished_diorite': ['stone_diorite_smooth'], 'granite': ['stone_granite'], 'polished_granite': ['stone_granite_smooth'],
    'smooth_stone': ['stone_slab_top'], 'smooth_stone_slab_side': ['stone_slab_side'],
    'terracotta': ['hardened_clay'], 'farmland': ['farmland_dry'], 'farmland_moist': ['farmland_wet'],
    'sandstone': ['sandstone_normal'], 'cut_sandstone': ['sandstone_smooth'], 'chiseled_sandstone': ['sandstone_carved'],
    'red_sandstone': ['red_sandstone_normal'], 'cut_red_sandstone': ['red_sandstone_smooth'],
    'chiseled_red_sandstone': ['red_sandstone_carved'], 'nether_bricks': ['nether_brick'], 'red_nether_bricks': ['red_nether_brick'],
    'chiseled_quartz_block': ['quartz_block_chiseled'], 'chiseled_quartz_block_top': ['quartz_block_chiseled_top'],
    'quartz_pillar': ['quartz_block_lines'], 'quartz_pillar_top': ['quartz_block_lines_top'],
    'hay_block_side': ['hayblock_side'], 'hay_block_top': ['hayblock_top'], 'lily_pad': ['waterlily'], 'cobweb': ['web'],
    'dead_bush': ['deadbush'], 'sugar_cane': ['reeds'], 'short_grass': ['tallgrass'], 'grass': ['tallgrass'],
    'tall_grass_top': ['double_plant_grass_top'], 'tall_grass_bottom': ['double_plant_grass_bottom'],
    'large_fern_top': ['double_plant_fern_top'], 'large_fern_bottom': ['double_plant_fern_bottom'],
    'packed_ice': ['ice_packed'], 'torch': ['torch_on'], 'redstone_torch': ['redstone_torch_on'],
    'redstone_torch_off': ['redstone_torch_off'], 'note_block': ['noteblock'], 'furnace_front': ['furnace_front_off'],
    'carved_pumpkin': ['pumpkin_face_off'], 'jack_o_lantern': ['pumpkin_face_on'],
    'brown_mushroom_block': ['mushroom_block_skin_brown'], 'red_mushroom_block': ['mushroom_block_skin_red'],
    'mushroom_stem': ['mushroom_block_skin_stem'], 'mushroom_block_inside': ['mushroom_block_inside'],
    'oak_door_top': ['door_wood_upper'], 'oak_door_bottom': ['door_wood_lower'], 'iron_door_top': ['door_iron_upper'],
    'iron_door_bottom': ['door_iron_lower'], 'oak_trapdoor': ['trapdoor'], 'iron_trapdoor': ['iron_trapdoor'],
    'dandelion': ['flower_dandelion'], 'poppy': ['flower_rose'], 'blue_orchid': ['flower_blue_orchid'], 'allium': ['flower_allium'],
    'azure_bluet': ['flower_houstonia'], 'red_tulip': ['flower_tulip_red'], 'orange_tulip': ['flower_tulip_orange'],
    'white_tulip': ['flower_tulip_white'], 'pink_tulip': ['flower_tulip_pink'], 'oxeye_daisy': ['flower_oxeye_daisy'],
    'cornflower': ['flower_cornflower'], 'lily_of_the_valley': ['flower_lily_of_the_valley'],
    'sunflower_front': ['double_plant_sunflower_front'], 'sunflower_back': ['double_plant_sunflower_back'],
    'sunflower_top': ['double_plant_sunflower_top'], 'sunflower_bottom': ['double_plant_sunflower_bottom'],
    'lilac_top': ['double_plant_syringa_top'], 'lilac_bottom': ['double_plant_syringa_bottom'],
    'rose_bush_top': ['double_plant_rose_top'], 'rose_bush_bottom': ['double_plant_rose_bottom'],
    'peony_top': ['double_plant_paeonia_top'], 'peony_bottom': ['double_plant_paeonia_bottom'],
    'melon_stem': ['melon_stem_disconnected'], 'pumpkin_stem': ['pumpkin_stem_disconnected'],
    'attached_melon_stem': ['melon_stem_connected'], 'attached_pumpkin_stem': ['pumpkin_stem_connected'],
    'comparator': ['comparator_off'], 'comparator_on': ['comparator_on'], 'repeater': ['repeater_off'], 'repeater_on': ['repeater_on'],
    'redstone_lamp': ['redstone_lamp_off'], 'redstone_lamp_on': ['redstone_lamp_on'], 'piston_top': ['piston_top_normal'],
    'piston_top_sticky': ['piston_top_sticky'], 'dispenser_front': ['dispenser_front_horizontal'],
    'dispenser_front_vertical': ['dispenser_front_vertical'], 'dropper_front': ['dropper_front_horizontal'],
    'dropper_front_vertical': ['dropper_front_vertical'], 'nether_quartz_ore': ['quartz_ore'], 'brown_mushroom': ['mushroom_brown'],
    'red_mushroom': ['mushroom_red'], 'dark_oak_door_top': ['door_dark_oak_upper'], 'dark_oak_door_bottom': ['door_dark_oak_lower'],
    'dried_kelp_bottom': ['dried_kelp_top'], 'nether_portal': ['portal'], 'redstone_dust_dot': ['redstone_dust_cross'],
    'redstone_dust_line0': ['redstone_dust_line'], 'end_portal_frame_eye': ['endframe_eye'], 'end_portal_frame_side': ['endframe_side'],
    'end_portal_frame_top': ['endframe_top'], 'horn_coral_block': ['coral_yellow'], 'dead_brain_coral_block': ['coral_pink_dead'],
    'dead_bubble_coral_block': ['coral_purple_dead'], 'dead_fire_coral_block': ['coral_red_dead'],
    'dead_horn_coral_block': ['coral_yellow_dead'], 'tube_coral': ['coral_plant_blue'], 'dead_tube_coral': ['coral_plant_blue_dead'],
    'dead_fire_coral': ['coral_plant_red_dead'], 'red_sand': ['red_sand'], 'coarse_dirt': ['coarse_dirt'], 'podzol_top': ['dirt_podzol_top'], 'podzol_side': ['dirt_podzol_side'],
    'mycelium_top': ['mycelium_top'], 'snow': ['snow'], 'sea_lantern': ['sea_lantern'], 'end_stone_bricks': ['end_bricks'],
    'prismarine_bricks': ['prismarine_bricks'], 'dark_prismarine': ['prismarine_dark'], 'prismarine': ['prismarine_rough'],
    'purpur_pillar': ['purpur_pillar'], 'purpur_pillar_top': ['purpur_pillar_top'], 'smooth_red_sandstone': ['red_sandstone_top'],
    'smooth_sandstone': ['sandstone_top'], 'magma': ['magma'], 'nether_wart_block': ['nether_wart_block'],
    'enchanting_table_top': ['enchanting_table_top'], 'cauldron_inner': ['cauldron_inner'], 'iron_bars': ['iron_bars'],
    'lever': ['lever'], 'ladder': ['ladder'], 'rail': ['rail_normal'], 'rail_corner': ['rail_normal_turned'],
    'powered_rail': ['rail_golden'], 'powered_rail_on': ['rail_golden_powered'], 'detector_rail': ['rail_detector'],
    'detector_rail_on': ['rail_detector_powered'], 'activator_rail': ['rail_activator'], 'activator_rail_on': ['rail_activator_powered'],
    'beetroots_stage0': ['beetroots_stage_0'], 'beetroots_stage1': ['beetroots_stage_1'], 'beetroots_stage2': ['beetroots_stage_2'],
    'beetroots_stage3': ['beetroots_stage_3'], 'sweet_berry_bush_stage0': ['sweet_berry_bush_stage0'],
    'nether_wart_stage0': ['nether_wart_stage_0'], 'nether_wart_stage1': ['nether_wart_stage_1'], 'nether_wart_stage2': ['nether_wart_stage_2'],
    'cocoa_stage0': ['cocoa_stage_0'], 'cocoa_stage1': ['cocoa_stage_1'], 'cocoa_stage2': ['cocoa_stage_2'],
    'slime_block': ['slime'], 'spawner': ['mob_spawner'], 'tnt_side': ['tnt_side'], 'dried_kelp_side': ['dried_kelp_side_a'],
    'brain_coral_block': ['coral_pink'], 'tube_coral_block': ['coral_blue'], 'dead_tube_coral_block': ['coral_blue_dead'],
    'snow_block': ['snow'], 'bone_block_side': ['bone_block_side'], 'bone_block_top': ['bone_block_top'],
    'end_rod': ['end_rod'], 'fire_0': ['fire_0'], 'fire_1': ['fire_1'], 'light_gray_glazed_terracotta': ['glazed_terracotta_silver'],
}


def candidates(j):
    out = list(FIXED.get(j, []))
    m = re.fullmatch(r'(\w+?)_(planks|log|log_top|leaves|sapling|trapdoor|door_top|door_bottom|stripped)', j)
    for wood, alias in WOOD.items():
        if j == wood + '_planks':
            out.append('planks_' + alias)
        elif j == wood + '_log':
            out.append('log_' + alias)
        elif j == wood + '_log_top':
            out.append('log_' + alias + '_top')
        elif j == wood + '_leaves':
            out += ['leaves_' + alias, 'leaves_' + alias + '_opaque', 'leaves_' + alias + '_carried']
        elif j == wood + '_sapling':
            out.append('sapling_' + ('roofed_oak' if wood == 'dark_oak' else wood))
        elif j == wood + '_trapdoor':
            out.append(wood + '_trapdoor')
        elif j == wood + '_door_top':
            out.append('door_' + alias + '_upper')
        elif j == wood + '_door_bottom':
            out.append('door_' + alias + '_lower')
        elif j == 'stripped_' + wood + '_log':
            out.append('stripped_' + wood + '_log')
        elif j == 'stripped_' + wood + '_log_top':
            out.append('stripped_' + wood + '_log_top')
    for c, bc in COLOUR.items():
        if j == c + '_wool':
            out.append('wool_colored_' + bc)
        elif j == c + '_terracotta':
            out.append('hardened_clay_stained_' + bc)
        elif j == c + '_stained_glass':
            out.append('glass_' + bc)
        elif j == c + '_stained_glass_pane_top':
            out.append('glass_pane_top_' + bc)
        elif j == c + '_concrete':
            out.append('concrete_' + bc)
        elif j == c + '_concrete_powder':
            out.append('concrete_powder_' + bc)
        elif j == c + '_glazed_terracotta':
            out.append('glazed_terracotta_' + bc)
        elif j == c + '_carpet':
            out.append('wool_colored_' + bc)
    m = re.fullmatch(r'(wheat|carrots|potatoes)_stage(\d)', j)
    if m:
        out.append('%s_stage_%s' % (m.group(1), m.group(2)))
    out.append(j)
    return out


table, missing = {}, []
for f in sorted(os.listdir(JAVA)):
    if not f.endswith('.png'):
        continue
    j = f[:-4]
    hit = []
    for c in candidates(j):
        for p in sorted(by_name.get(c, ())):
            if p not in hit:
                hit.append(p)
    if hit:
        table[j] = hit
    else:
        missing.append(j)
out = {'_about': 'Java block texture (assets/minecraft/textures/block/<name>.png) -> the Bedrock vanilla texture paths it '
                 'replaces, made with the installed game\'s terrain_texture.json by gen_block_map.py. A name not listed has no '
                 'Bedrock block texture (a MineScape-only texture a Java model uses, or a block Bedrock draws another way).',
       'flipbook': sorted(p for ps in table.values() for p in ps if p in flip),
       'textures': table}
json.dump(out, open(OUT, 'w', encoding='utf-8', newline='\n'), indent=1)
print('mapped', len(table), 'of', len(table) + len(missing))
print('unmapped:', ' '.join(missing))
