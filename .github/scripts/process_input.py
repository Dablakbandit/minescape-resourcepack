import json
import math

def find_nearest_model(data, durability, damage):
    # Assuming the overrides are sorted by damage in ascending order
    tolerance = 1e-6  # Set a tolerance value for floating-point comparisons
    for override in data['overrides']:
        if 'predicate' in override:
            if 'damage' in override['predicate'] and abs(override['predicate']['damage'] - damage) < tolerance:
                return override['model']
            elif 'custom_model_data' in override['predicate'] and abs(override['predicate']['custom_model_data'] - durability) < tolerance:
                return override['model']
    return None  # Return the last model if no other is found

# --- Left-hand overlay items -------------------------------------------------------------
# Neck and body-overlay items are held in the LEFT hand of an armour stand riding the player.
# The stand keeps the default left arm pose (-10 deg about x, -10 deg about z), so the hand's
# axes are tilted against the world: pushing an item "away" along the hand's z also slides it
# sideways. The vertical/back shift below is tuned by eye; the x is solved so the model's
# geometric centre lands exactly on the stand's centre line instead of being tuned per item.
#
# Render chain (Minecraft 1.21+, stand at yaw 0, 1 unit = 1 block):
#   LivingEntityRenderer   Ry(180) * S(-1,-1,1) * T(0,-1.501,0)
#   left arm ModelPart     T(5/16, 2/16, 0) * Rz(-10) * Ry(0) * Rx(-10)
#   ItemInHandLayer        Rx(-90) * Ry(180) * T(-1/16, 0.125, -0.625)
#   ItemTransform (left)   T(-tx, ty, tz)/16 * Rx(rx)*Ry(-ry)*Rz(-rz) * S(scale) * T(-0.5)

LEFT_HAND_SHIFT_Y = -1.75
LEFT_HAND_SHIFT_Z = -6.95

def _rot(axis, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return {'x': [[1, 0, 0], [0, c, -s], [0, s, c]],
            'y': [[c, 0, s], [0, 1, 0], [-s, 0, c]],
            'z': [[c, -s, 0], [s, c, 0], [0, 0, 1]]}[axis]

def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]

def _apply(m, v):
    return [sum(m[i][k] * v[k] for k in range(3)) for i in range(3)]

def _left_hand_frame():
    # Linear part of the chain above, and the world position of the hand origin (tx=ty=tz=0).
    lin = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    origin = [0.0, 0.0, 0.0]
    def translate(v):
        nonlocal origin
        origin = [o + d for o, d in zip(origin, _apply(lin, v))]
    def rotate(m):
        nonlocal lin
        lin = _mul(lin, m)
    rotate(_rot('y', 180)); rotate([[-1, 0, 0], [0, -1, 0], [0, 0, 1]]); translate([0, -1.501, 0])
    translate([5 / 16, 2 / 16, 0]); rotate(_rot('z', -10)); rotate(_rot('x', -10))
    rotate(_rot('x', -90)); rotate(_rot('y', 180)); translate([-1 / 16, 0.125, -0.625])
    return lin, origin

LEFT_HAND_LIN, LEFT_HAND_ORIGIN = _left_hand_frame()

def _model_centre_offset(data, model_file):
    """Geometric centre of the model's elements relative to the (8, 8, 8) pivot, in model units."""
    seen = set()
    while data is not None and 'elements' not in data:
        parent = data.get('parent')
        if not parent or not parent.startswith('ms:') or parent in seen:
            return [0.0, 0.0, 0.0]
        seen.add(parent)
        with open(f"assets/ms/models/{parent.replace('ms:', '')}.json", 'r') as file:
            data = json.load(file)
    lo = [min(min(e['from'][i], e['to'][i]) for e in data['elements']) for i in range(3)]
    hi = [max(max(e['from'][i], e['to'][i]) for e in data['elements']) for i in range(3)]
    return [(lo[i] + hi[i]) / 2 - 8 for i in range(3)]

def centre_left_hand(data, model_file):
    """Solve translation.x so the model's geometric centre sits on the stand's centre line (world x = 0)."""
    display = data['display']['thirdperson_lefthand']
    translation = display['translation']
    rx, ry, rz = display.get('rotation', [0, 0, 0])
    scale = display.get('scale', [1, 1, 1])
    rot = _mul(_mul(_rot('x', rx), _rot('y', -ry)), _rot('z', -rz))
    centre = [c * s / 16 for c, s in zip(_model_centre_offset(data, model_file), scale)]
    centre_x = _apply(_mul(LEFT_HAND_LIN, rot), centre)[0]
    # world x = origin.x + lin.x*(-tx/16) + lin.y*(ty/16) + lin.z*(tz/16) + centre_x = 0
    ax, ay, az = LEFT_HAND_LIN[0]
    rest = LEFT_HAND_ORIGIN[0] + ay * translation[1] / 16 + az * translation[2] / 16 + centre_x
    translation[0] = round(16 * rest / ax, 4)

def modify_left_hand(model_file):
    with open(model_file, 'r') as file:
        data = json.load(file)
        
        if 'display' in data and 'thirdperson_lefthand' in data['display']:
            translation = data['display']['thirdperson_lefthand']['translation']
            translation[1] += LEFT_HAND_SHIFT_Y
            translation[2] += LEFT_HAND_SHIFT_Z
            centre_left_hand(data, model_file)
        elif 'parent' in data:
            return data['parent']

    with open(model_file, 'w') as file:
        json.dump(data, file, indent=4)
    return None

def modify_cape(model_file):
    with open(model_file, 'r') as file:
        data = json.load(file)
        
        if 'display' in data and 'head' in data['display']:
            translation = data['display']['head']['translation']
            translation[1] -= 13
        elif 'parent' in data:
            return data['parent']

    with open(model_file, 'w') as file:
        json.dump(data, file, indent=4)
    return None

def modify_trim(model_file):
    with open(model_file, 'r') as file:
        data = json.load(file)
        
        if 'display' in data and 'thirdperson_righthand' in data['display']:
            translation = data['display']['thirdperson_righthand']['translation']
            translation[0] -= 1.25
            translation[1] -= 1.75
            translation[2] -= 6.95
        elif 'parent' in data:
            return data['parent']

    with open(model_file, 'w') as file:
        json.dump(data, file, indent=4)
    return None

def list_files(input):
    with open(input, 'r') as file:
        seen_models = set()  # Set to store the models that have already been encountered
        for line in file:
            name, item, durability, damage = line.strip().split(',')
            damage = float(damage)
            durability = float(durability)

            json_file = f'assets/minecraft/models/item/{item.lower()}.json'
            try:
                with open(json_file, 'r') as jfile:
                    data = json.load(jfile)
                    model = find_nearest_model(data, durability, damage)
                    if model is None:
                        print(f'Missing Item: {name} {item} {damage}')
                    elif model not in seen_models:  # Check if the model is not None and has not been encountered
                        seen_models.add(model)  # Add the model to the set of seen models
            except FileNotFoundError:
                print(f'JSON file for item {item} not found')
        return seen_models

def process_input():
    neck = list_files('run/neck.txt')
    clone = neck.copy()
    for model in neck:
        print(f'Neck: {model}')
        # Example usage:
        model_file = f"assets/ms/models/{model.replace('ms:', '')}.json"
        parent = modify_left_hand(model_file)
        neck = list_files('run/neck.txt')
        if parent is not None and parent not in clone and parent != 'item/handheld':
            clone.add(parent)
            model_file = f"assets/ms/models/{parent.replace('ms:', '')}.json"
            modify_left_hand(model_file)
    # Body items that are not real chestplates (aprons, shirts...) are drawn on the overlay
    # armour stand's off-hand, exactly like neck items, so they need the same left-hand shift.
    # The plugin writes run/modify_body.txt with just those items.
    body = list_files('run/modify_body.txt')
    clone = body.copy()
    for model in body:
        print(f'Body: {model}')
        model_file = f"assets/ms/models/{model.replace('ms:', '')}.json"
        parent = modify_left_hand(model_file)
        # Flat icons inherit from item/generated or item/handheld and have no display block to shift.
        if parent is not None and parent not in clone and parent.startswith('ms:'):
            clone.add(parent)
            model_file = f"assets/ms/models/{parent.replace('ms:', '')}.json"
            modify_left_hand(model_file)
    cape = list_files('run/cape.txt')
    clone = cape.copy()
    for model in cape:
        print(f'Cape: {model}')
        # Example usage:
        model_file = f"assets/ms/models/{model.replace('ms:', '')}.json"
        parent = modify_cape(model_file)
        if parent is not None and parent not in clone and parent != 'item/handheld':
            clone.add(parent)
            model_file = f"assets/ms/models/{parent.replace('ms:', '')}.json"
            modify_cape(model_file)
    # Only process specific goldtrim parent models for trim
    goldtrim_models = ['ms:trim/goldtrim_legs', 'ms:trim/goldtrim_combined', 'ms:trim/goldtrim_chest']
    for model in goldtrim_models:
        print(f'Trim: {model}')
        # Example usage:
        model_file = f"assets/ms/models/{model.replace('ms:', '')}.json"
        modify_trim(model_file)


process_input()