"""Builds the slot text shader into the pack for every Minecraft release from 1.18.2 on, new ones included.

The plugin writes numbers in the corners of menu slots through a window's title, which Minecraft draws
behind the items. The slot fonts (font/slot.png, font/slot_box.png) mark their glyph cells with a
pixel the text vertex shader looks for, and it lifts those glyphs level with stack counts, in front of
the items.

The text shader changes form between versions (rendertype_text, then core/text from 26.2), so nothing
is stored here but the change itself. Mojang's version list gives every release since 1.18.2; from
each client jar only its text shader and pack format are read (HTTP range requests, cached in
cache/mc_shaders). Releases with the same shader share one overlay over their pack formats, holding
that vanilla shader with the change applied. Two lines anchor the change, the same in every release so
far: `void main()` and the line setting gl_Position. A release where either is missing gets no
overlay, keeps its vanilla shader and loses only the lift, and the build says so.

    python .github/scripts/build_shaders.py            base folder (1.18.2's shader) and overlays
    python .github/scripts/build_shaders.py --no-base  every shader in an overlay, the base folder empty

The base copy is for clients that read no overlays (1.20.1 and older), which only get the "normal"
pack. The 20 and 21 packs are built --no-base, so a release newer than the last build keeps its own
shader rather than meet an old one in the base folder and reject the pack.
"""
import hashlib, io, json, os, shutil, sys, urllib.request, zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CACHE = os.path.join(ROOT, "cache", "mc_shaders")
CORE = "assets/minecraft/shaders/core/"
MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
FIRST = "1.18.2"
# The base folder holds the oldest release's shader; overlays are named after their first release.
NAMES = ("text", "rendertype_text")

FUNCTIONS = """uniform sampler2D Sampler0;

// MineScape slot text: glyph cells 16 texels wide with a marker texel (255, 0, 255, alpha 1) at the
// top and bottom of their left column. A glyph's four vertices come in the order top left, bottom
// left, bottom right, top right; each reads the marker on its own row of the left column.
const float SLOT_CELL = 16.0;
// A container draws its slots' items at 200 and their stack counts at 300: level with the counts.
const float SLOT_LIFT = 300.0;

// 26.3 compiles every shader as Vulkan GLSL (OpenGL too, through SPIR-V), which has no gl_VertexID.
#ifdef VULKAN
#define SLOT_VERTEX gl_VertexIndex
#else
#define SLOT_VERTEX gl_VertexID
#endif

bool slotText() {
    vec2 size = vec2(textureSize(Sampler0, 0));
    int corner = SLOT_VERTEX % 4;
    float u = corner < 2 ? UV0.x : UV0.x - SLOT_CELL / size.x;
    float v = (corner == 0 || corner == 3) ? UV0.y : UV0.y - 1.0 / size.y;
    vec4 marker = texelFetch(Sampler0, ivec2(floor(u * size.x + 0.5), floor(v * size.y + 0.5)), 0);
    return marker.a > 0.0 && marker.a < 2.5 / 255.0 && marker.r > 0.9 && marker.g < 0.1 && marker.b > 0.9;
}

void main() {"""
MAIN = "void main() {"
POSITION = "gl_Position = ProjMat * ModelViewMat * vec4(Position, 1.0);"
LIFT = """vec3 position = Position;
    if (slotText()) {
        // level with the slots' stack counts, in front of their items
        position.z += SLOT_LIFT;
    }
    gl_Position = ProjMat * ModelViewMat * vec4(position, 1.0);"""


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


class RemoteFile(io.RawIOBase):
    """A file on a server read through Range requests, enough for zipfile to read a few entries."""

    BLOCK = 256 * 1024

    def __init__(self, url, size):
        self.url, self.size, self.pos, self.blocks = url, size, 0, {}

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset
        return self.pos

    def _block(self, index):
        if index not in self.blocks:
            start = index * self.BLOCK
            end = min(self.size, start + self.BLOCK) - 1
            request = urllib.request.Request(self.url, headers={"Range": "bytes=%d-%d" % (start, end)})
            with urllib.request.urlopen(request, timeout=60) as response:
                if response.status != 206:
                    raise IOError("no range requests")
                self.blocks[index] = response.read()
        return self.blocks[index]

    def readinto(self, buffer):
        if self.pos >= self.size:
            return 0
        count = min(len(buffer), self.size - self.pos)
        out, done = memoryview(buffer), 0
        while done < count:
            index, offset = divmod(self.pos + done, self.BLOCK)
            chunk = self._block(index)[offset:offset + count - done]
            out[done:done + len(chunk)] = chunk
            done += len(chunk)
        self.pos += count
        return count


def pack_format(version_json):
    pack = json.loads(version_json).get("pack_version")
    if isinstance(pack, int):
        return pack
    return pack.get("resource_major", pack.get("resource"))


def release_shader(version):
    """(pack format, {file name: text}) of a release's text shader, cached after the first read."""
    cached = os.path.join(CACHE, version + ".json")
    if os.path.exists(cached):
        data = json.load(open(cached, encoding="utf-8"))
        return data["format"], data["files"]
    meta = json.loads(fetch(VERSIONS[version]))["downloads"]["client"]
    try:
        jar = zipfile.ZipFile(io.BufferedReader(RemoteFile(meta["url"], meta["size"]), RemoteFile.BLOCK))
    except IOError:
        jar = zipfile.ZipFile(io.BytesIO(fetch(meta["url"])))
    entries = set(jar.namelist())
    name = next(n for n in NAMES if CORE + n + ".vsh" in entries)
    files = {}
    for ext in (".vsh", ".fsh", ".json"):
        if CORE + name + ext in entries:
            files[name + ext] = jar.read(CORE + name + ext).decode("utf-8")
    form = pack_format(jar.read("version.json"))
    os.makedirs(CACHE, exist_ok=True)
    json.dump({"format": form, "files": files}, open(cached, "w", encoding="utf-8"))
    return form, files


def patch(files):
    """The shader with the slot text lift, or None if its anchors are not there."""
    vsh_name = next(n for n in files if n.endswith(".vsh"))
    vsh = files[vsh_name]
    if vsh.count(MAIN) != 1 or vsh.count(POSITION) != 1:
        return None
    patched = dict(files)
    patched[vsh_name] = vsh.replace(MAIN, FUNCTIONS, 1).replace(POSITION, LIFT, 1)
    return patched


def write(files, directory):
    if os.path.exists(directory):
        for old in os.listdir(directory):
            if old.split(".")[0] in NAMES:
                os.remove(os.path.join(directory, old))
    os.makedirs(directory, exist_ok=True)
    for name, text in files.items():
        open(os.path.join(directory, name), "w", encoding="utf-8", newline="\n").write(text)


def main():
    global VERSIONS
    no_base = "--no-base" in sys.argv[1:]
    manifest = json.loads(fetch(MANIFEST))
    releases = [v for v in manifest["versions"] if v["type"] == "release"]
    releases.reverse()
    ids = [v["id"] for v in releases]
    VERSIONS = {v["id"]: v["url"] for v in releases}
    releases = ids[ids.index(FIRST):]

    # Consecutive releases with the same shader, each run one group.
    groups = []
    for version in releases:
        form, files = release_shader(version)
        digest = hashlib.sha1(json.dumps(files, sort_keys=True).encode()).hexdigest()
        if groups and groups[-1]["digest"] == digest:
            groups[-1]["last"] = form
        else:
            groups.append({"digest": digest, "first_version": version, "first": form, "last": form, "files": files})
    # A group runs up to the next one's format, covering the snapshots between releases.
    for group, following in zip(groups, groups[1:]):
        group["last"] = max(group["last"], following["first"] - 1)

    for path in os.listdir(ROOT):
        if path.startswith("shader_") and os.path.isdir(os.path.join(ROOT, path)):
            shutil.rmtree(os.path.join(ROOT, path))

    base = os.path.join(ROOT, CORE)
    entries = []
    for i, group in enumerate(groups):
        patched = patch(group["files"])
        span = "%s, formats %d-%d" % (group["first_version"], group["first"], group["last"])
        if patched is None:
            print("WARNING: no slot text lift for %s - its shader no longer has the anchor lines" % span)
            continue
        if i == 0 and not no_base:
            write(patched, base)
            print("base folder:", span)
            continue
        directory = "shader_" + group["first_version"].replace(".", "_")
        write(patched, os.path.join(ROOT, directory, CORE))
        # formats for clients before 1.21.9, min/max_format for those after; both, as the list spans both
        entries.append({"formats": {"min_inclusive": group["first"], "max_inclusive": group["last"]},
                        "min_format": group["first"], "max_format": group["last"], "directory": directory})
        print("overlay %s: %s" % (directory, span))
    if no_base:
        write({}, base)

    meta_path = os.path.join(ROOT, "pack.mcmeta")
    raw = open(meta_path, encoding="utf-8").read()
    meta = json.loads(raw)
    # Rewritten from the pack section as it stands, its escapes kept, then the overlays.
    start = raw.index('"pack"')
    depth, end = 0, start
    for i in range(raw.index("{", start), len(raw)):
        depth += {"{": 1, "}": -1}.get(raw[i], 0)
        if depth == 0:
            end = i + 1
            break
    overlays = json.dumps({"entries": entries}, indent=2).replace("\n", "\n  ")
    text = "{\n  " + raw[start:end] + ',\n  "overlays": ' + overlays + "\n}\n"
    assert json.loads(text)["pack"] == meta["pack"]
    open(meta_path, "w", encoding="utf-8", newline="\n").write(text)


if __name__ == "__main__":
    main()
