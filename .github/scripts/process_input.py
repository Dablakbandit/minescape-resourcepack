import json
import json

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

def modify_neck(model_file):
    with open(model_file, 'r') as file:
        data = json.load(file)
        
        if 'display' in data and 'thirdperson_lefthand' in data['display']:
            translation = data['display']['thirdperson_lefthand']['translation']
            translation[0] -= 1.25
            translation[1] -= 1.75
            translation[2] -= 6.95
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
                    print(f'Model: {name} {model}')
                    if model is None:
                        print(f'Missing Item: {name} {item} {damage}')
                    elif model not in seen_models:  # Check if the model is not None and has not been encountered
                        seen_models.add(model)  # Add the model to the set of seen models
            except FileNotFoundError:
                print(f'JSON file for item {item} not found')
        return seen_models

def process_input():
    neck = list_files('run/neck.txt')
    for model in neck:
        print(f'Neck: {model}')
        # Example usage:
        model_file = f"assets/ms/models/{model.replace('ms:', '')}.json"
        parent = modify_neck(model_file)
        neck = list_files('run/neck.txt')
        if parent is not None and parent not in neck:
            neck.add(parent)
            model_file = f"assets/ms/models/{parent.replace('ms:', '')}.json"
            parent = modify_neck(model_file)
    cape = list_files('run/cape.txt')
    for model in cape:
        print(f'Cape: {model}')
        # Example usage:
        model_file = f"assets/ms/models/{model.replace('ms:', '')}.json"
        parent = modify_cape(model_file)
        if parent is not None and parent not in cape:
            cape.add(parent)
            model_file = f"assets/ms/models/{parent.replace('ms:', '')}.json"
            modify_cape(model_file)


process_input()