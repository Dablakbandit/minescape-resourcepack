import json
import os
import sys

ASSETS_DIR = 'assets'
SRC_DIRNAME = 'sounds_src'
OUTPUT_NAME = 'sounds.json'


def find_namespaces():
    """Every assets/<namespace> that has a sounds_src directory to merge."""
    if not os.path.isdir(ASSETS_DIR):
        print(f"ERROR: assets directory not found: {ASSETS_DIR}")
        sys.exit(1)

    namespaces = sorted(
        name for name in os.listdir(ASSETS_DIR)
        if os.path.isdir(os.path.join(ASSETS_DIR, name, SRC_DIRNAME))
    )
    if not namespaces:
        print(f"ERROR: no <namespace>/{SRC_DIRNAME} directories found under {ASSETS_DIR}")
        sys.exit(1)
    return namespaces


def merge_namespace(namespace):
    """
    Merge one namespace's sources into its own sounds.json.

    Sound events are per namespace, so skill sounds no longer have to be generated into
    minecraft's file alongside everything else. A key only has to be unique within its namespace -
    mob:rat.attack and skill:chop cannot collide - so each namespace is merged on its own.

    Only namespaces with a sounds_src directory are merged. The mob namespace has none: its
    sounds.json is a single hand-maintained file that is committed as-is.
    """
    src_dir = os.path.join(ASSETS_DIR, namespace, SRC_DIRNAME)
    output_file = os.path.join(ASSETS_DIR, namespace, OUTPUT_NAME)

    json_files = sorted(f for f in os.listdir(src_dir) if f.endswith('.json'))
    if not json_files:
        print(f"ERROR: no JSON files found in {src_dir}")
        sys.exit(1)

    merged = {}
    key_sources = {}
    errors = []

    for filename in json_files:
        filepath = os.path.join(src_dir, filename)
        # Use utf-8-sig so files with a UTF-8 BOM still parse as JSON.
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"ERROR: failed to parse {filepath}: {e}")
                sys.exit(1)

        for key, value in data.items():
            if key in merged:
                errors.append(
                    f"  [{namespace}] Duplicate key '{key}': first seen in '{key_sources[key]}', also in '{filename}'"
                )
            else:
                merged[key] = value
                key_sources[key] = filename

    if errors:
        print("ERROR: Duplicate sound keys found:")
        for msg in errors:
            print(msg)
        sys.exit(1)

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(merged, f, indent=2)
        f.write('\n')

    return len(json_files), len(merged), output_file


def merge_sounds():
    total = 0
    for namespace in find_namespaces():
        files, sounds, output_file = merge_namespace(namespace)
        total += sounds
        print(f"Merged {files} file(s) -> {output_file} ({sounds} sounds)")
    print(f"{total} sounds across all namespaces")


if __name__ == '__main__':
    merge_sounds()
