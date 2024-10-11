import json
import os
import argparse

parser = argparse.ArgumentParser(description='Process sound files for MineScape resource pack.')
parser.add_argument('soundsLocation', type=str, help='The path to the sounds location')
args = parser.parse_args()

soundsLocation = args.soundsLocation
if not os.path.exists(soundsLocation):
    print(f"Path {soundsLocation} does not exist.")
    exit(1)

with open('assets/minecraft/sounds.json') as f:
    sounds = json.load(f)

for sound_name, sound in sounds.items():
    soundFile = sound['sounds'][0]
    if not os.path.exists(f'assets/minecraft/sounds/{soundFile}.ogg'):
        # Get input from user
        user_input = input(f"Enter the path for {soundFile} (leave empty to skip): ").strip()
        if user_input:
            fromFile = os.path.join(soundsLocation, user_input + '.ogg')
            if os.path.exists(fromFile):
                with open(fromFile, 'rb') as sound_data:
                    with open(f'assets/minecraft/sounds/{soundFile}.ogg', 'wb') as out_file:
                        out_file.write(sound_data.read())
            else:
                print(f"File {user_input} does not exist.")