import json
import os
import sys

SOUNDS_SRC_DIR = 'assets/minecraft/sounds_src'
OUTPUT_FILE = 'assets/minecraft/sounds.json'


def merge_sounds():
    if not os.path.isdir(SOUNDS_SRC_DIR):
        print(f"ERROR: sounds source directory not found: {SOUNDS_SRC_DIR}")
        sys.exit(1)

    json_files = sorted(f for f in os.listdir(SOUNDS_SRC_DIR) if f.endswith('.json'))
    if not json_files:
        print(f"ERROR: no JSON files found in {SOUNDS_SRC_DIR}")
        sys.exit(1)

    merged = {}
    key_sources = {}
    errors = []

    for filename in json_files:
        filepath = os.path.join(SOUNDS_SRC_DIR, filename)
        # Use utf-8-sig so files with a UTF-8 BOM still parse as JSON.
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"ERROR: failed to parse {filename}: {e}")
                sys.exit(1)

        for key, value in data.items():
            if key in merged:
                errors.append(
                    f"  Duplicate key '{key}': first seen in '{key_sources[key]}', also in '{filename}'"
                )
            else:
                merged[key] = value
                key_sources[key] = filename

    if errors:
        print("ERROR: Duplicate sound keys found:")
        for msg in errors:
            print(msg)
        sys.exit(1)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(merged, f, indent=2)
        f.write('\n')

    print(
        f"Merged {len(json_files)} file(s) → {OUTPUT_FILE} ({len(merged)} sounds)"
    )


if __name__ == '__main__':
    merge_sounds()
