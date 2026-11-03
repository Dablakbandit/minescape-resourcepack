"""Writes how far each of the pack's own fonts moves the pen for each of its characters, as the client works it
out, for the plugin to measure text with (its PackFonts): what the sidebar, the inventory titles and the like
line up by. The release publishes it beside the zips, with its SHA1, which the plugin fetches first and
reloads only when it changed.

    python .github/scripts/font_sizes.py OUT [pack folder]

OUT is JSON: {"emoji:default": {"9000": 9, ...}, ...}, each character as its code point in hex. A bitmap
glyph moves the pen its drawn width (the last column with a pixel not clear, as Minecraft finds it) scaled
to the provider's height, rounded, and one more; a space provider's as it says; a reference provider's as
the font it names. The first provider with a character keeps it, as in game. Minecraft's own fonts (its
default) aren't the pack's, so they aren't here.
"""
import json
import os
import sys

from PIL import Image

OUT = sys.argv[1]
ROOT = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", ".."))
ASSETS = os.path.join(ROOT, "assets")


def split(ref):
    namespace, _, path = ref.partition(":") if ":" in ref else ("minecraft", "", ref)
    return namespace, path


def fonts():
    """Every font the pack has, by its id: assets/<namespace>/font/<path>.json is <namespace>:<path>."""
    found = {}
    for namespace in sorted(os.listdir(ASSETS)):
        folder = os.path.join(ASSETS, namespace, "font")
        for here, _, files in os.walk(folder):
            for name in sorted(files):
                if name.endswith(".json"):
                    path = os.path.relpath(os.path.join(here, name), folder)[:-5].replace(os.sep, "/")
                    found["%s:%s" % (namespace, path)] = os.path.join(here, name)
    return found


def java_int(value):
    # Java's (int) cast, toward zero: the offset glyphs' negative heights depend on it
    return int(value)


def bitmap(provider, advances):
    namespace, path = split(provider["file"])
    image = Image.open(os.path.join(ASSETS, namespace, "textures", path))
    image.load()
    # what Minecraft reads a pixel by: its alpha, or its luminance where it has no alpha
    if "A" in image.getbands():
        clear = image.getchannel("A")
    elif image.mode in ("L", "P", "1"):
        clear = image.convert("L")
    else:
        clear = Image.new("L", image.size, 255)
    pixels = clear.load()
    rows = [list(row) for row in provider["chars"]]
    cell_width, cell_height = image.width // len(rows[0]), image.height // len(rows)
    scale = provider.get("height", 8) / cell_height
    for r, row in enumerate(rows):
        for c, char in enumerate(row):
            if char == "\0" or char in advances:
                continue
            width = 0
            for x in range(cell_width - 1, -1, -1):
                if any(pixels[c * cell_width + x, r * cell_height + y] for y in range(cell_height)):
                    width = x + 1
                    break
            advances[char] = java_int(0.5 + width * scale) + 1


def read(font, paths, done, reading=()):
    if font in done:
        return done[font]
    advances = {}
    if font in paths and font not in reading:
        for provider in json.load(open(paths[font], encoding="utf-8")).get("providers", []):
            kind = provider.get("type", "").removeprefix("minecraft:")
            if kind == "bitmap":
                bitmap(provider, advances)
            elif kind == "space":
                for char, advance in provider.get("advances", {}).items():
                    advances.setdefault(char, round(advance))
            elif kind == "reference":
                for char, advance in read(provider["id"], paths, done, reading + (font,)).items():
                    advances.setdefault(char, advance)
    done[font] = advances
    return advances


paths = fonts()
done = {}
out = {}
for font in paths:
    advances = read(font, paths, done)
    out[font] = {"%X" % ord(char): advances[char] for char in sorted(advances)}
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    json.dump(out, f, separators=(",", ":"), sort_keys=True)
print("%d fonts, %d characters" % (len(out), sum(len(a) for a in out.values())))
