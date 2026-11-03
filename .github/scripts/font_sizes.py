"""Writes how far each of the pack's fonts, and Minecraft's own default font, moves the pen for each of their
characters, as the client works it out, for the plugin to measure text with (its PackFonts): what the
sidebar, the inventory titles and the like line up by. The release publishes it beside the zips, with its
SHA1, which the plugin fetches first and reloads only when it changed.

    python .github/scripts/font_sizes.py OUT [pack folder]

OUT is JSON: {"emoji:default": {"9000": 9, ...}, "minecraft:default": {...}, ...}, each character as its
code point in hex. A bitmap glyph moves the pen its drawn width (the last column with a pixel not clear, as
Minecraft finds it) scaled to the provider's height, rounded, and one more; a space provider's as it says; a
unihex glyph (unifont) half its width from its first set column to its last, and one more; a reference
provider's as the font it names. The first provider with a character keeps it, as in game, and a provider
filtered to an option a player has to turn on (Force Unicode Font, Japanese glyph variants) is left out.

What the pack doesn't have comes from the newest release: its client jar for most of Minecraft's fonts and
their textures, its asset index for unifont. Only the Basic Multilingual Plane, which the plugin's text is.
"""
import io
import json
import os
import sys
import zipfile

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_shaders import MANIFEST, RemoteFile, fetch  # noqa: E402

OUT = sys.argv[1]
ROOT = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", ".."))
ASSETS = os.path.join(ROOT, "assets")
OBJECTS = "https://resources.download.minecraft.net/"
# the options a provider's filter can ask for, as a player has them unless they change them
OPTIONS = {"uniform": False, "jp": False}


class Vanilla:
    """The newest release's resources: the asset index's objects over the client jar's, as the game has them."""

    def __init__(self):
        manifest = json.loads(fetch(MANIFEST))
        release = manifest["latest"]["release"]
        version = json.loads(fetch(next(v["url"] for v in manifest["versions"] if v["id"] == release)))
        client = version["downloads"]["client"]
        try:
            self.jar = zipfile.ZipFile(io.BufferedReader(RemoteFile(client["url"], client["size"]), RemoteFile.BLOCK))
        except IOError:
            self.jar = zipfile.ZipFile(io.BytesIO(fetch(client["url"])))
        self.objects = json.loads(fetch(version["assetIndex"]["url"]))["objects"]
        self.names = set(self.jar.namelist())
        print("Minecraft's fonts from", release)

    def read(self, path):
        key = path[len("assets/"):]
        if key in self.objects:
            digest = self.objects[key]["hash"]
            return fetch(OBJECTS + digest[:2] + "/" + digest)
        if path in self.names:
            return self.jar.read(path)
        return None


VANILLA = None


def resource(path):
    """assets/... from the pack, or else from Minecraft."""
    global VANILLA
    local = os.path.join(ROOT, path)
    if os.path.exists(local):
        return open(local, "rb").read()
    if VANILLA is None:
        VANILLA = Vanilla()
    return VANILLA.read(path)


def split(ref):
    namespace, _, path = ref.partition(":") if ":" in ref else ("minecraft", "", ref)
    return namespace, path


def pack_fonts():
    """Every font the pack has, by its id: assets/<namespace>/font/<path>.json is <namespace>:<path>."""
    found = []
    for namespace in sorted(os.listdir(ASSETS)):
        folder = os.path.join(ASSETS, namespace, "font")
        for here, _, files in os.walk(folder):
            for name in sorted(files):
                if name.endswith(".json"):
                    path = os.path.relpath(os.path.join(here, name), folder)[:-5].replace(os.sep, "/")
                    found.append("%s:%s" % (namespace, path))
    return found


def java_int(value):
    # Java's (int) cast, toward zero: the offset glyphs' negative heights depend on it
    return int(value)


def bitmap(provider, advances):
    namespace, path = split(provider["file"])
    image = Image.open(io.BytesIO(resource("assets/%s/textures/%s" % (namespace, path))))
    image.load()
    # what Minecraft reads a pixel by: its alpha (a palette's transparency becoming one, as it loads it), or
    # its luminance where it has no alpha
    if "A" in image.getbands() or "transparency" in image.info:
        clear = image.convert("RGBA").getchannel("A")
    elif image.mode in ("L", "1"):
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


def unihex(provider, advances):
    """As UnihexProvider: each row's bits as the top of an int, a glyph from its first set column to its
    last (an empty one its whole width and one), or as a size override says; half that and one."""
    namespace, path = split(provider["hex_file"])
    glyphs = {}
    with zipfile.ZipFile(io.BytesIO(resource("assets/%s/%s" % (namespace, path)))) as hexes:
        for entry in hexes.infolist():
            if not entry.filename.endswith(".hex"):
                continue
            for line in hexes.read(entry).decode("ascii").splitlines():
                point, _, data = line.partition(":")
                code = int(point, 16)
                if code > 0xFFFF or len(data) not in (32, 48, 64, 96):
                    continue
                bits = len(data) // 16 * 4
                mask = 0
                for row in range(16):
                    mask |= int(data[row * bits // 4:(row + 1) * bits // 4], 16) << (32 - bits)
                if mask == 0:
                    left, right = 0, bits
                else:
                    left = 32 - mask.bit_length()
                    right = 32 - ((mask & -mask).bit_length() - 1) - 1
                glyphs[code] = (left, right)
    for override in provider.get("size_overrides", []):
        for code in range(ord(override["from"]), ord(override["to"]) + 1):
            if code in glyphs:
                glyphs[code] = (override["left"], override["right"])
    for code, (left, right) in glyphs.items():
        advances.setdefault(chr(code), (right - left + 1) // 2 + 1)


def wanted(provider):
    return all(OPTIONS.get(option, False) == value for option, value in provider.get("filter", {}).items())


def read(font, done, reading=()):
    if font in done:
        return done[font]
    advances = {}
    namespace, path = split(font)
    text = resource("assets/%s/font/%s.json" % (namespace, path)) if font not in reading else None
    for provider in (json.loads(text).get("providers", []) if text else []):
        if not wanted(provider):
            continue
        kind = provider.get("type", "").removeprefix("minecraft:")
        if kind == "bitmap":
            bitmap(provider, advances)
        elif kind == "space":
            for char, advance in provider.get("advances", {}).items():
                advances.setdefault(char, round(advance))
        elif kind == "unihex":
            unihex(provider, advances)
        elif kind == "reference":
            for char, advance in read(provider["id"], done, reading + (font,)).items():
                advances.setdefault(char, advance)
    done[font] = advances
    return advances


done = {}
out = {}
for font in pack_fonts() + ["minecraft:default"]:
    advances = read(font, done)
    out[font] = {"%X" % ord(char): advances[char] for char in sorted(advances) if ord(char) <= 0xFFFF}
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    json.dump(out, f, separators=(",", ":"), sort_keys=True)
print("%d fonts, %d characters" % (len(out), sum(len(a) for a in out.values())))
