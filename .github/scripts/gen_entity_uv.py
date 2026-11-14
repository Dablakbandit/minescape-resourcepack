"""Where each pixel of a Bedrock entity texture comes from in Java's, for textures whose two layouts differ (chests,
beds): made once from the two games' own vanilla textures, written to bedrock_entity_uv.json, which build_bedrock.py
uses to lay the Java pack's chest and bed retextures out the Bedrock way (CI can't read the Bedrock game).

    python gen_entity_uv.py <bedrock vanilla textures dir> <1.18.2 client jar> <out json>

The Bedrock dir holds textures/entity/chest/*.png and textures/entity/bed/*.png as the game has them (in 26.x they
are inside resource_packs/vanilla/__brarchive/textures/entity/*.brarchive, PNGs one after another, named in its
header: gen_entity_uv.py --unpack <brarchive> <dir> writes them out).

Each Bedrock pixel is found by matching small patches against the Java texture turned each of the eight ways (box
UVs move whole faces, some flipped or turned): every pixel votes for the turn and offset its patch matches at, and a
face's pixels take the turn and offset most of their neighbours agree on, so a flat patch (a bed's sheet) goes where
its face goes. The map is checked by laying vanilla Java out with it and comparing with vanilla Bedrock."""
import io
import json
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict

import numpy as np
from PIL import Image

# Bedrock texture -> the Java textures it is made of (a double chest from Java's left and right halves)
TARGETS = {
    "chest/normal": ["chest/normal"],
    "chest/trapped": ["chest/trapped"],
    "chest/ender": ["chest/ender"],
    "chest/double_normal": ["chest/normal_left", "chest/normal_right"],
    "chest/trapped_double": ["chest/trapped_left", "chest/trapped_right"],
    "bed/red": ["bed/red"],   # every bed colour has the same layout
}
PATCH = 3
# boxes whose two layouts are known and whose pictures don't tell them apart (a bed's four 3x3x3 legs, plain wood
# that matches anywhere on the frame): Bedrock box UV <- Java box UV, both 12 x 6 (Bedrock's geometry.bed, Java's
# BedRenderer)
BOXES = {"bed/red": [((0, 38), (50, 0)), ((12, 38), (50, 6)), ((0, 44), (50, 12)), ((12, 44), (50, 18))]}


def unpack(archive, out):
    data = open(archive, "rb").read()
    names = re.findall(rb"[a-z0-9_]+\.png", data[:8192])
    starts = [m.start() for m in re.finditer(rb"\x89PNG\r\n\x1a\n", data)]
    os.makedirs(out, exist_ok=True)
    for name, start in zip(names, starts):
        end = data.find(b"IEND", start) + 8
        open(os.path.join(out, name.decode()), "wb").write(data[start:end])
    print("unpacked", len(starts), "to", out)


def back_point(x, y, w, h, flip, k):
    """A pixel of np.rot90(the image, flipped left to right if flip, k) back in the image (w x h)."""
    # np.rot90(a)[i, j] = a[j, W - 1 - i], W being a's width: undone one turn at a time, last turn first
    i, j = y, x
    for t in range(k, 0, -1):
        width = w if (t - 1) % 2 == 0 else h
        i, j = j, width - 1 - i
    x, y = j, i
    if flip:
        x = w - 1 - x
    return x, y


def clean(image):
    out = image.copy()
    out[out[..., 3] == 0] = 0
    return out


def build(bedrock, sources):
    bedrock, sources = clean(bedrock), [clean(s) for s in sources]
    bh, bw = bedrock.shape[:2]
    index = defaultdict(list)   # patch bytes -> [(source, flip, k, x, y)]
    turned = []
    for s, src in enumerate(sources):
        for flip in (False, True):
            base = src[:, ::-1] if flip else src
            for k in range(4):
                t = np.ascontiguousarray(np.rot90(base, k))
                turned.append((s, flip, k, t))
                th, tw = t.shape[:2]
                for y in range(th - PATCH + 1):
                    for x in range(tw - PATCH + 1):
                        patch = t[y:y + PATCH, x:x + PATCH]
                        if patch[PATCH // 2, PATCH // 2, 3] == 0:
                            continue
                        index[patch.tobytes()].append((s, flip, k, x, y))
    votes = {}
    for y in range(bh - PATCH + 1):
        for x in range(bw - PATCH + 1):
            patch = bedrock[y:y + PATCH, x:x + PATCH]
            if patch[PATCH // 2, PATCH // 2, 3] == 0:
                continue
            hits = index.get(patch.tobytes())
            if hits and len(hits) <= 12:
                for (s, flip, k, sx, sy) in hits:
                    key = (s, flip, k, sx - x, sy - y)
                    for dy in range(PATCH):
                        for dx in range(PATCH):
                            votes.setdefault((x + dx, y + dy), Counter())[key] += 1.0 / len(hits)
    # each opaque pixel: the transform its neighbourhood votes for most
    mapping = {}
    for y in range(bh):
        for x in range(bw):
            if bedrock[y, x, 3] == 0:
                continue
            tally = Counter()
            for r in (1, 3, 6):
                for yy in range(max(0, y - r), min(bh, y + r + 1)):
                    for xx in range(max(0, x - r), min(bw, x + r + 1)):
                        tally.update(votes.get((xx, yy), {}))
                if tally:
                    break
            if not tally:
                continue
            # the likeliest of the neighbourhood's transforms that gives this pixel its own vanilla colour (a face's
            # one-pixel edge, a flat patch), else the likeliest
            chosen = None
            for key, _ in tally.most_common():
                s, flip, k, ox, oy = key
                src = sources[s]
                th, tw = np.rot90(src, k).shape[:2]
                tx, ty = x + ox, y + oy
                if not (0 <= tx < tw and 0 <= ty < th):
                    continue
                sx, sy = back_point(tx, ty, src.shape[1], src.shape[0], flip, k)
                if chosen is None:
                    chosen = key
                if np.abs(src[sy, sx].astype(int) - bedrock[y, x].astype(int)).sum() <= 12:
                    chosen = key
                    break
            if chosen:
                mapping[(x, y)] = chosen
    return mapping


def spans(mapping):
    """The map as runs along rows, each [y, x0, length, source, flip, turns, dx, dy]: the run's pixels are those of
    the source flipped left to right (if flip), turned a quarter anticlockwise `turns` times (np.rot90), at
    (x + dx, y + dy). Exact at any scale: a texture n times vanilla's size copies n x n blocks."""
    runs, run = [], None
    for (x, y) in sorted(mapping, key=lambda p: (p[1], p[0])):
        s, flip, k, ox, oy = mapping[(x, y)]
        if run and run[0] == y and run[1] + run[2] == x and run[3:] == [s, int(flip), k, ox, oy]:
            run[2] += 1
            continue
        if run:
            runs.append(run)
        run = [y, x, 1, s, int(flip), k, ox, oy]
    if run:
        runs.append(run)
    return runs


def apply(runs, sources, size, scale=1):
    """The texture laid out by runs from sources (each `scale` times vanilla's size)."""
    out = np.zeros((size[1] * scale, size[0] * scale) + sources[0].shape[2:], sources[0].dtype)
    turned = {}
    for y, x0, n, s, flip, k, dx, dy in runs:
        if (s, flip, k) not in turned:
            base = sources[s][:, ::-1] if flip else sources[s]
            turned[(s, flip, k)] = np.rot90(base, k)
        t = turned[(s, flip, k)]
        piece = t[(y + dy) * scale:(y + dy + 1) * scale, (x0 + dx) * scale:(x0 + dx + n) * scale]
        out[y * scale:(y + 1) * scale, x0 * scale:x0 * scale + piece.shape[1]] = piece
    return out


def main():
    if sys.argv[1] == "--unpack":
        unpack(sys.argv[2], sys.argv[3])
        return
    bedrock_dir, jar_path, out_path = sys.argv[1:4]
    jar = zipfile.ZipFile(jar_path)
    java = lambda name: np.asarray(Image.open(io.BytesIO(jar.read("assets/minecraft/textures/entity/%s.png" % name))).convert("RGBA"))
    table = {"_about": __doc__.split("\n\n")[0].replace("\n", " "), "textures": {}}
    for target, names in TARGETS.items():
        bedrock = np.asarray(Image.open(os.path.join(bedrock_dir, target + ".png")).convert("RGBA"))
        sources = [java(n) for n in names]
        mapping = build(bedrock, sources)
        for (bx, by), (jx, jy) in BOXES.get(target, []):
            for dy in range(6):
                for dx in range(12):
                    if bedrock[by + dy, bx + dx, 3]:
                        mapping[(bx + dx, by + dy)] = (0, False, 0, jx - bx, jy - by)
        runs = spans(mapping)
        laid = apply(runs, sources, (bedrock.shape[1], bedrock.shape[0]))
        opaque = bedrock[..., 3] > 0
        same = (np.abs(laid.astype(int) - bedrock.astype(int)).sum(-1) <= 12) & opaque
        print("%-22s %4d of %4d pixels mapped, %5.1f%% of them as Bedrock's own, %d runs"
              % (target, len(mapping), opaque.sum(), 100.0 * same.sum() / max(1, len(mapping)), len(runs)))
        table["textures"][target] = {"size": [bedrock.shape[1], bedrock.shape[0]], "sources": names, "runs": runs}
    json.dump(table, open(out_path, "w"), separators=(",", ":"))
    print("wrote", out_path)


if __name__ == "__main__":
    main()
