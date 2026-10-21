"""MineScape's armour as a stitch, for the Stitch mod: with it, a shader pack (Iris) draws each armour
item's own look and shape (skirts, robes, faulds), where the pack's core shaders can't reach. Without
the mod the pack's own armour shader (build_shaders.py) draws it, as before, and these files go unread.

build_armour.py writes them on every build, the tables from armour/*.json:

    assets/minescape/stitches/armour.json        where the stitch applies, what it needs
    assets/minescape/stitches/armour.vert.glsl   the looks and shapes: ARMOUR_VERTEX on the stitch interface
    assets/minescape/stitches/armour.frag.glsl   the dye: ARMOUR_FRAGMENT on the stitch interface

Pure Python: the tables come from armour_looks.glsl(), as the armour shader's do.
"""
import json, os

import armour_looks

VERTEX = """// MineScape armour looks. An armour sheet is a grid of 256x128 tiles, its top right texel marked
// (255, 0, 255; green 128 for the leggings'): alpha 1 a sheet, 2 an item's own tile (OptiFine's CIT,
// its texels all but clear), 3 that tile's overlay (for shader packs only, hidden here). The dye carries
// the item's tile, nine bits from bit 13; the tables give its sheet tile and its shape: leggings flared
// at the foot as a plateskirt (1) or robe (2); a chestplate lengthened below the waist.
%(tables)s
const vec2 SHEET_TILE = vec2(256.0, 128.0);
// a player model pixel, in blocks
const float PIXEL = 0.9375 / 16.0;
// leather's own colour: never dyed
const int UNDYED = %(undyed)d;

int sheet_mark() {
    ivec2 size = stitch_texture_size();
    vec4 mark = stitch_texel_fetch(ivec2(size.x - 1, 0));
    int alpha = int(round(mark.a * 255.0));
    if (alpha < 1 || alpha > 3 || mark.r < 0.99 || mark.b < 0.99) {
        return 0;
    }
    int layer = mark.g < 0.25 ? 1 : 2;
    return alpha == 1 ? layer : (alpha == 2 ? layer + 2 : -1);
}

// Vanilla draws armour well clear of the body: every box's sides come in to NARROW out, close to the
// skin's outer layer. A side corner knows its face from u, and its edge from which corner it is.
const float NARROW[3] = float[](0.0, 0.5, 0.35);
const float VANILLA[3] = float[](0.0, 1.0, 0.5);

void narrow(int layer, vec2 uv, inout StitchVertex v) {
    vec2 p = uv * vec2(64.0, 32.0);
    if (p.y < 19.5 || p.x > 56.5) {
        return;
    }
    bool maxU = v.corner == 0 || v.corner == 3;
    float u = p.x + (maxU ? -0.5 : 0.5);
    // the legs' strip from u 0, the body's from 16, the arms' from 40
    float u0 = u < 16.0 ? 0.0 : (u < 40.0 ? 16.0 : 40.0);
    float w = u0 == 16.0 ? 8.0 : 4.0;
    float x = u - u0;
    vec3 up = stitch_up();
    vec3 n = normalize(v.normal);
    // v 20 is both the sides' top edge and the top and bottom faces' edge
    if (p.y < 20.5 && x > 4.0 && x < 4.0 + 2.0 * w && abs(dot(n, up)) > 0.7071) {
        return;
    }
    bool mirrored = (v.corner < 2) == (p.y > 26.0);
    bool side = x < 4.0 || (x > 4.0 + w && x < 8.0 + w);
    float pull = VANILLA[layer] - NARROW[layer];
    float deep = u0 == 16.0 ? pull : 0.0;
    vec3 across = cross(up, n) * stitch_handedness();
    vec3 inward = length(across) > 0.1 ? normalize(across) * (mirrored ? -1.0 : 1.0) * (maxU ? -1.0 : 1.0) : vec3(0.0);
    vec3 move = side ? -n * pull + inward * deep : inward * pull - n * deep;
    v.position += move * PIXEL;
}

// Leggings worn as a skirt or robe: each leg box flares at its foot, out to its own side and a little
// in from the middle, so the two halves open in a V between the legs and swing with them.
const float FLARE_OUT[4] = float[](0.0, 3.5, 2.5, 0.0);
const float FLARE_IN[4] = float[](0.0, 1.0, 0.75, 0.0);

void hang(int shape, vec2 uv, inout StitchVertex v) {
    vec2 p = uv * vec2(64.0, 32.0);
    if (p.x > 16.0 || p.y < 31.0) {
        return;
    }
    bool maxU = v.corner == 0 || v.corner == 3;
    bool left = v.corner < 2;
    float u = p.x + (maxU ? -0.5 : 0.5);
    vec3 n = normalize(v.normal);
    vec3 outward;
    if (u < 4.0) {
        outward = n;
    } else if (u > 8.0 && u < 12.0) {
        outward = -n;
    } else {
        vec3 leftward = normalize(cross(stitch_up(), n)) * stitch_handedness() * (u > 12.0 ? -1.0 : 1.0);
        outward = left ? leftward : -leftward;
    }
    bool outerEdge = p.x < 6.0 || p.x > 14.0;
    v.position += outward * (outerEdge ? FLARE_OUT[shape] : FLARE_IN[shape]) * PIXEL;
}

// A chestplate's body box lengthened below the waist and flared: a plate fauld (1), a jerkin (2) or a
// tunic (3). Its bottom face, under the hem, hides.
const float TORSO_DROP[4] = float[](0.0, 1.5, 2.0, 3.0);
const float TORSO_FLARE[4] = float[](0.0, 0.25, 0.5, 0.75);

void torso(int shape, vec2 uv, inout StitchVertex v) {
    vec2 p = uv * vec2(64.0, 32.0);
    bool maxU = v.corner == 0 || v.corner == 3;
    float u = p.x + (maxU ? -0.5 : 0.5);
    if (u < 16.0 || u > 40.0 || p.y < 16.0) {
        return;
    }
    vec3 up = stitch_up();
    vec3 n = normalize(v.normal);
    if (dot(n, up) > 0.7) {
        return;
    }
    if (dot(n, up) < -0.7) {
        v.hidden = true;
        return;
    }
    if (v.corner < 2) {
        return;
    }
    vec3 side = normalize(cross(up, n)) * stitch_handedness();
    vec3 move = -up * TORSO_DROP[shape] + (n + side * (maxU ? 1.0 : -1.0)) * TORSO_FLARE[shape];
    v.position += move * PIXEL;
}

void stitch_vertex(inout StitchVertex v) {
    tint = vec4(0.0);
    int mark = sheet_mark();
    if (mark == 0) {
        return;
    }
    if (mark == -1) {
        v.hidden = true;
        return;
    }
    bool own = mark > 2;
    int layer = own ? mark - 2 : mark;
    ivec3 c = ivec3(round(v.color.rgb * 255.0));
    int dye = c.r << 16 | c.g << 8 | c.b;
    // the item's tile, or 0 (the plain look) for leather MineScape doesn't define
    int look = dye != UNDYED && (dye >> 22) == 0 ? (dye >> 13) & 511 : 0;
    int tile = layer == 1 ? MS_TILE_1[look] : MS_TILE_2[look];
    ivec2 grid = stitch_texture_size() / ivec2(SHEET_TILE);
    vec2 uv = v.uv;
    v.uv = own ? v.uv : (v.uv + vec2(tile % grid.x, tile / grid.x)) / vec2(grid);
    // an item's tile is coloured already; the plain one is dyed in the fragment; an own tile drawn whole
    tint = own ? vec4(0.0, 0.0, 0.0, 0.5) : (look == 0 ? vec4(v.color.rgb, 1.0) : vec4(0.0));
    v.color = vec4(1.0, 1.0, 1.0, v.color.a);
    if (v.corner < 0) {
        // a device that can't number corners: the looks on Minecraft's own boxes, unmoved
        return;
    }
    narrow(layer, uv, v);
    if (layer == 2 && MS_SHAPE_2[look] != 0) {
        hang(MS_SHAPE_2[look], uv, v);
    } else if (layer == 1 && MS_SHAPE_1[look] != 0) {
        torso(MS_SHAPE_1[look], uv, v);
    }
}
"""

FRAGMENT = """// MineScape armour looks: the vertex function's dye, kept off texels marked in their alpha as their
// own colour (254) and lightened for trims (253). An item's own tile (tint alpha 0.5) has every texel
// all but clear for shader packs to drop: here they are whole.
vec4 stitch_texel(StitchFragment f, vec4 texel) {
    if (tint.a > 0.25 && tint.a < 0.75) {
        return texel.a > 0.0 ? vec4(texel.rgb, 1.0) : texel;
    }
    if (tint.a < 0.5 || texel.a < 0.1) {
        return texel;
    }
    int code = int(round(texel.a * 255.0));
    vec3 dye = code == 254 ? vec3(1.0) : (code == 253 ? mix(tint.rgb, vec3(1.0), 0.55) : tint.rgb);
    return vec4(texel.rgb * dye, 1.0);
}
"""

DEFINITION = {
    "format": 1,
    "targets": ["armor"],
    "vertex": "minescape:stitches/armour.vert.glsl",
    "fragment": "minescape:stitches/armour.frag.glsl",
    "varyings": [{"name": "tint", "type": "vec4"}],
    "requires": ["vertex_corner", "texture_size", "orientation"],
    "passes": ["main", "shadow"],
}


def write(root):
    """The stitch's three files into the pack folder at root."""
    out = os.path.join(root, "assets", "minescape", "stitches")
    os.makedirs(out, exist_ok=True)
    vertex = VERTEX.replace("%(tables)s", armour_looks.glsl()).replace("%(undyed)d", str(0xA06540))
    with open(os.path.join(out, "armour.vert.glsl"), "w", encoding="utf-8", newline="\n") as f:
        f.write(vertex)
    with open(os.path.join(out, "armour.frag.glsl"), "w", encoding="utf-8", newline="\n") as f:
        f.write(FRAGMENT)
    with open(os.path.join(out, "armour.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(DEFINITION, f, indent=2)
        f.write("\n")
