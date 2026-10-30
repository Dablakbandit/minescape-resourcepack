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

// The item's tile from its dye, or 0 (the plain look) for leather MineScape doesn't define. Layout 1 is
// worn armour's, with the gloves or amulet worn beside it in place of a count.
int item_tile(vec4 color) {
    ivec3 c = ivec3(round(color.rgb * 255.0));
    int dye = c.r << 16 | c.g << 8 | c.b;
    return dye != UNDYED && (dye >> 22) <= 1 ? (dye >> 13) & 511 : 0;
}

// What worn armour's dye carries (its low twelve bits, the item's number, in layout 1): a chestplate's
// gloves (layer 1), a pair of leggings' amulet (layer 2), by its place in their table; -1 for none or one
// without a look.
int worn_index(int layer, vec4 color) {
    ivec3 c = ivec3(round(color.rgb * 255.0));
    int dye = c.r << 16 | c.g << 8 | c.b;
    if ((dye >> 22) != 1) {
        return -1;
    }
    int number = dye & 4095;
    if (layer == 1) {
        for (int i = 0; i < MS_GLOVES_COUNT; i++) {
            if (MS_GLOVES_NUMBER[i] == number) {
                return i;
            }
        }
    } else {
        for (int i = 0; i < MS_AMULET_COUNT; i++) {
            if (MS_AMULET_NUMBER[i] == number) {
                return i;
            }
        }
    }
    return -1;
}

// its look's sheet tile, or -1
int worn_tile(int layer, vec4 color) {
    int i = worn_index(layer, color);
    return i < 0 ? -1 : (layer == 1 ? MS_GLOVES_TILE[i] : MS_AMULET_TILE[i]);
}

// The cape carried in worn boots' dye (layout 1, armour_looks.capes()): its place in MS_CAPE_NUMBER,
// which is its column in the boots' table past MS_CAPE_COLUMN, else -1.
int cape_index(vec4 color) {
    ivec3 c = ivec3(round(color.rgb * 255.0));
    int dye = c.r << 16 | c.g << 8 | c.b;
    if ((dye >> 22) != 1) {
        return -1;
    }
    int number = dye & 4095;
    for (int i = 0; i < MS_CAPE_COUNT; i++) {
        if (MS_CAPE_NUMBER[i] == number) {
            return i;
        }
    }
    return -1;
}

// a unit vector in 30 bits, for an int varying (armour.frag.glsl's unpack_unit)
int pack_unit(vec3 n) {
    ivec3 q = ivec3(round((clamp(n, -1.0, 1.0) * 0.5 + 0.5) * 1023.0));
    return (q.x << 20) | (q.y << 10) | q.z;
}

// Armour models (armour_models.py), from 1.21.2: leather's extra layers, each with its own texture,
// marked (255, layer, 255) with alpha 4 for the humanoid's, 5 for the leggings'. Each face of the
// armour's boxes becomes one face of the item's model, placed by the limb's transform, read from the
// box face's four corners (shared between its vertices). Every texel of the layers is all but clear
// (alpha 1 to 3), so a shader that doesn't know them cuts them out.
const vec3 BOX_FROM[7] = vec3[](vec3(-4.0, -8.0, -4.0), vec3(-4.0, -8.0, -4.0), vec3(-4.0, 0.0, -2.0),
                                vec3(-3.0, -2.0, -2.0), vec3(-1.0, -2.0, -2.0), vec3(-2.0, 0.0, -2.0), vec3(-2.0, 0.0, -2.0));

vec3 decode_corner(vec4 t) {
    return (round(t.rgb * 255.0) - 128.0) / 4.0;
}

vec2 decode_uv(vec4 t) {
    ivec3 b = ivec3(round(t.rgb * 255.0));
    int n = (b.r << 16) | (b.g << 8) | b.b;
    return vec2(float(n >> 12), float(n & 4095));
}

// A corner's place on its box, from where it sits in the box's texture layout (Minecraft's box UV):
// face 0 down, 1 up, 2 west, 3 north, 4 east, 5 south; uv in texture pixels from the box's corner.
vec3 on_box(int face, vec2 uv, vec3 dim, vec3 lo, vec3 hi) {
    vec3 span = hi - lo;
    if (face == 0) {
        return vec3(lo.x + (uv.x - dim.z) / dim.x * span.x, lo.y, hi.z - uv.y / dim.z * span.z);
    } else if (face == 1) {
        return vec3(lo.x + (uv.x - dim.z - dim.x) / dim.x * span.x, hi.y, hi.z - uv.y / dim.z * span.z);
    } else if (face == 2) {
        return vec3(lo.x, lo.y + (uv.y - dim.z) / dim.y * span.y, hi.z - uv.x / dim.z * span.z);
    } else if (face == 3) {
        return vec3(lo.x + (uv.x - dim.z) / dim.x * span.x, lo.y + (uv.y - dim.z) / dim.y * span.y, lo.z);
    } else if (face == 4) {
        return vec3(hi.x, lo.y + (uv.y - dim.z) / dim.y * span.y, lo.z + (uv.x - dim.z - dim.x) / dim.z * span.z);
    }
    return vec3(hi.x - (uv.x - 2.0 * dim.z - dim.x) / dim.x * span.x, lo.y + (uv.y - dim.z) / dim.y * span.y, hi.z);
}

#ifdef STITCH_HAS_QUAD_CORNERS
void model_layer(bool leggings, inout StitchVertex v) {
    int look = item_tile(v.color);
    v.color = vec4(1.0, 1.0, 1.0, v.color.a);
    vec3 p[4];
    vec2 t[4];
    if (!stitch_quad_corners(p, t)) {
        v.hidden = true;
        return;
    }
    for (int k = 0; k < 4; k++) {
        t[k] *= vec2(64.0, 32.0);
    }
    // which box and which face, from where the face sits in the texture layout
    vec2 tmin = min(min(t[0], t[1]), min(t[2], t[3]));
    vec2 tmax = max(max(t[0], t[1]), max(t[2], t[3]));
    int box = tmax.y < 16.01 ? (tmin.x > 31.99 ? 1 : 0) : (tmin.x > 39.99 ? 3 : (tmin.x > 15.99 ? 2 : 4));
    vec3 dim = box < 2 ? vec3(8.0) : (box == 2 ? vec3(8.0, 12.0, 4.0) : vec3(4.0, 12.0, 4.0));
    vec2 offs = box == 0 ? vec2(0.0) : (box == 1 ? vec2(32.0, 0.0) : (box == 2 ? vec2(16.0, 16.0) : (box == 3 ? vec2(40.0, 16.0) : vec2(0.0, 16.0))));
    vec2 rect = tmin - offs;
    int face = rect.y < dim.z - 0.01 ? (rect.x < dim.z + dim.x - 0.01 ? 0 : 1)
        : (rect.x < dim.z - 0.01 ? 2 : (rect.x < dim.z + dim.x - 0.01 ? 3 : (rect.x < 2.0 * dim.z + dim.x - 0.01 ? 4 : 5)));
    // the corners at the face's u and v edges
    int c00 = 0;
    int c10 = 0;
    int c01 = 0;
    for (int k = 0; k < 4; k++) {
        bool uLow = t[k].x < (tmin.x + tmax.x) * 0.5;
        bool vLow = t[k].y < (tmin.y + tmax.y) * 0.5;
        if (uLow && vLow) c00 = k;
        if (!uLow && vLow) c10 = k;
        if (uLow && !vLow) c01 = k;
    }
    vec3 du = p[c10] - p[c00];
    vec3 dv = p[c01] - p[c00];
    // a mirrored box (the left limbs) runs its texture the other way round its face; so does a
    // mirrored space (a screen's entity preview)
    float hand = stitch_handedness();
    float sense = sign(dot(cross(du, dv), v.normal)) * hand;
    bool mirrored = (box == 3 || box == 4) && sense != (face == 1 ? 1.0 : -1.0);
    int slot = box < 3 ? box : (box == 3 ? (mirrored ? 4 : 3) : (mirrored ? 6 : 5));
    float grow = slot == 1 ? 1.5 : (slot >= 5 ? (leggings ? 0.4 : 0.9) : (slot == 2 && leggings ? 0.5 : 1.0));

    // the item's model: its row (0 none) and colour, from the tables by the item's tile
    int table = leggings ? 0 : (slot >= 5 ? 1 : 0);
    vec4 entry = stitch_texel_fetch(ivec2(look, table));
    int row = int(round(entry.r * 255.0)) * 256 + int(round(entry.g * 255.0)) - 1;
    int record = (slot * 6 + face) * 10;
    if (row < 0 || stitch_texel_fetch(ivec2(record + 9, 4 + row)).r < 0.5) {
        v.hidden = true;
        return;
    }
    tint = vec4(stitch_texel_fetch(ivec2(look, 2 + table)).rgb, 1.0);
    // the fragment reads the model's colour codes
    rt_info = ivec4(3, 0, 0, 0);

    // the limb's transform, from the face: two edges give two of its axes, their cross the third
    vec3 lo = BOX_FROM[slot] - grow;
    vec3 hi = BOX_FROM[slot] + dim + grow;
    vec3 l00 = on_box(face, t[c00] - offs, dim, lo, hi);
    vec3 l10 = on_box(face, t[c10] - offs, dim, lo, hi);
    vec3 l01 = on_box(face, t[c01] - offs, dim, lo, hi);
    if (mirrored) {
        l00.x = lo.x + hi.x - l00.x;
        l10.x = lo.x + hi.x - l10.x;
        l01.x = lo.x + hi.x - l01.x;
    }
    int au = (face == 2 || face == 4) ? 2 : 0;
    int av = face < 2 ? 2 : 1;
    int aw = 3 - au - av;
    vec3 mu = du / (l10 - l00)[au];
    vec3 mv = dv / (l01 - l00)[av];
    bool cyclic = (au + 1) % 3 == av;
    vec3 mw = cross(mu, mv) / length(mu) * (cyclic ? 1.0 : -1.0) * hand;
    mat3 m;
    m[au] = mu;
    m[av] = mv;
    m[aw] = mw;
    vec3 origin = p[c00] - m * l00;

    // this corner of the model's face
    ivec2 at = ivec2(record, 4 + row);
    v.normal = normalize(m * (stitch_texel_fetch(at + ivec2(4, 0)).rgb * 2.0 - 1.0));
    // a face turned away from the eye (at the origin) is behind its cube: dropped, unless its texels
    // have clear ones to see it through (a screen's preview has no eye there, and keeps every face).
    // The stored normals point into their cubes (armour_models.normal: the corners as seen from outside).
    if (!stitch_in_screen() && dot(v.normal, m * decode_corner(stitch_texel_fetch(at)) + origin) < 0.0
            && stitch_texel_fetch(at + ivec2(9, 0)).g < 0.5) {
        v.hidden = true;
        return;
    }
    v.position = m * decode_corner(stitch_texel_fetch(at + ivec2(v.corner, 0))) + origin;
    v.uv = decode_uv(stitch_texel_fetch(at + ivec2(5 + v.corner, 0))) / vec2(stitch_texture_size());
}
#endif

// The tracer (armour_models.traced): where there are no extra layers (to 1.21.1), an item with a model
// draws it on its own layer. One face of each of its boxes becomes a card facing the eye, wide enough
// to cover the body part's model; the fragment function finds the limb from how the face's corners
// (where Minecraft put them, and where they sit on the part's box) change across the screen, and
// traces the model's triangles in the part's own space.
// A box's faces come in one of two orders: east, west, down, up, north, south (1.18.2), or down, up,
// west, north, east, south (later releases). Where the two disagree, the faces they name sit in
// texture columns that don't overlap, so a corner's own column says which order this is.
const int LATER_ORDER[6] = int[](2, 3, 1, 4, 0, 5);

// whether a point inside a face sits in that face's column of its box's texture layout: faces east,
// west, down, up, north, south; rel from the box's left edge, w its width, d its depth
bool in_face_column(int face, float rel, float w, float d) {
    float lo = face == 0 ? d + w : (face == 1 ? 0.0 : (face == 3 ? d + w : (face == 5 ? 2.0 * d + w : d)));
    float hi = face == 0 ? 2.0 * d + w : (face == 1 ? d : (face == 3 ? d + 2.0 * w : (face == 5 ? 2.0 * d + 2.0 * w : d + w)));
    return rel > lo && rel < hi;
}
const ivec3 CORNER[8] = ivec3[](ivec3(0, 0, 0), ivec3(1, 0, 0), ivec3(1, 1, 0), ivec3(0, 1, 0),
                                ivec3(0, 0, 1), ivec3(1, 0, 1), ivec3(1, 1, 1), ivec3(0, 1, 1));
// each face's corners, faces numbered east, west, down, up, north, south
const int FACE[24] = int[](5, 1, 2, 6, 0, 4, 7, 3, 5, 4, 0, 1, 2, 3, 7, 6, 1, 0, 3, 2, 4, 5, 6, 7);
const vec2 SPREAD[4] = vec2[](vec2(-1.0, -1.0), vec2(1.0, -1.0), vec2(1.0, 1.0), vec2(-1.0, 1.0));

int u24(vec4 t) {
    ivec3 b = ivec3(round(t.rgb * 255.0));
    return (b.r << 16) | (b.g << 8) | b.b;
}


#if defined(STITCH_HAS_FRAGMENT_POSITION) && defined(STITCH_HAS_FRAGMENT_DEPTH) && defined(STITCH_HAS_VERTEX_INDEX)
// amulet >= 0: that amulet's model (the leggings' second table, by its place in MS_AMULET_NUMBER) on the
// leggings' body's top face alone, which sits inside the torso and is never seen; any other face is left.
// cape >= 0 likewise: that cape's model (the boots' table past MS_CAPE_COLUMN) on the right leg's top face,
// inside the torso too (rt_info kind 7, traced in the body's frame: armour.frag.glsl's trace_cape).
bool trace_card(int layer, int column, int amulet, int cape, inout StitchVertex v) {
    ivec2 size = stitch_texture_size();
    int top = u24(stitch_texel_fetch(ivec2(size.x - 2, 0)));
    int vid = stitch_vertex_index();
    if (top <= 0 || vid < 0) {
        return false;
    }
    int corner = vid % 4;
    vec2 p = v.uv * vec2(64.0, 32.0);
    // Which box, from a point just inside this corner's face (corners 0 and 3 sit on the face's high u
    // edge, mirrored or not), so a quad's four corners agree and take the same path. The head's faces
    // and the limbs' meet at v 16: their tops and bottoms (faces 2, 3) reach v 8 or 16, the sides v 16
    // or 20, so the thresholds between never touch a corner.
    float u = p.x + ((corner == 0 || corner == 3) ? -0.5 : 0.5);
    // the head's boxes sit above v 16; chestplates, leggings and boots never draw them
    bool head = p.y < 15.5;
    int box = head ? 0 : (u < 16.0 ? 3 : (u < 40.0 ? 1 : 2));
    int k = (vid / 4) % 6;
    float bw = box == 1 ? 8.0 : 4.0;
    float rel = u - (box == 3 ? 0.0 : (box == 1 ? 16.0 : 40.0));
    int face = in_face_column(k, rel, bw, 4.0) ? k : LATER_ORDER[k];
#ifdef STITCH_HAS_QUAD_CORNERS
    // Where the quad's corners can be shared, the face by its own rectangle in the box's texture layout,
    // as the model layers find it: a draw may start a box part way through its faces (26.2 batches
    // entities), and the vertex's number then names the wrong one. Faces east, west, down, up, north,
    // south: the top row down then up, the row below west, north, east, south.
    vec3 fp[4];
    vec2 ft[4];
    if (box != 0 && stitch_quad_corners(fp, ft)) {
        vec2 corner0 = min(min(ft[0], ft[1]), min(ft[2], ft[3])) * vec2(64.0, 32.0);
        vec2 rect = corner0 - vec2(box == 3 ? 0.0 : (box == 1 ? 16.0 : 40.0), 16.0);
        face = rect.y < 3.99 ? (rect.x < 3.99 + bw ? 2 : 3)
            : (rect.x < 3.99 ? 1 : (rect.x < 3.99 + bw ? 4 : (rect.x < 7.99 + bw ? 0 : 5)));
    }
#endif
    // a mirrored box (the left limbs) lists its corners backwards
    float g = face == 2 ? 16.0 : 20.0;
    float i = face == 2 ? 20.0 : (face == 3 ? 16.0 : 32.0);
    bool mirrored = box >= 2 && abs(p.y - (corner < 2 ? g : i)) > 0.5;
    int part = box == 1 ? 1 : (box == 2 ? (mirrored ? 3 : 2) : (box == 3 ? (mirrored ? 5 : 4) : 0));
    vec3 from = part == 1 ? vec3(-4.0, 0.0, -2.0) : (part == 2 ? vec3(-3.0, -2.0, -2.0) : (part == 3 ? vec3(-1.0, -2.0, -2.0) : vec3(-2.0, 0.0, -2.0)));
    vec3 extent = part == 1 ? vec3(8.0, 12.0, 4.0) : vec3(4.0, 12.0, 4.0);
    // which of the item's models: the chest's (or leggings') on the body and arms, the boots' on the legs
    int kind = layer == 1 && part >= 4 ? 1 : 0;
    if (amulet >= 0) {
        if (part != 1 || face != 3) {
            return false;
        }
        kind = 1;
        column = amulet;
    }
    if (cape >= 0) {
        if (part != 4 || face != 2) {
            return false;
        }
        kind = 1;
        column = MS_CAPE_COLUMN + cape;
    }
    int model = u24(stitch_texel_fetch(ivec2(column, top + kind)));
    if (model <= 0 || part == 0) {
        return false;
    }
    tint = vec4(stitch_texel_fetch(ivec2(column, top + 2 + kind)).rgb, 1.0);
    v.color = vec4(1.0, 1.0, 1.0, v.color.a);
    // a cape's rows from the model's first (its fixed ones, then its swinging ones)
    int row = cape >= 0 ? model : model + part - 1;
    int cubes = int(round(stitch_texel_fetch(ivec2(0, row)).r * 255.0));
    if (face != (amulet >= 0 ? 3 : (cape >= 0 ? 2 : 0)) || cubes == 0) {
        v.hidden = true;
        return true;
    }
    bool leggings = layer == 2;
    float grow = part >= 4 ? (leggings ? 0.4 : 0.9) : (part == 1 && leggings ? 0.5 : 1.0);
    vec3 lo = from - grow;
    vec3 hi = from + extent + grow;
    ivec3 side = CORNER[FACE[face * 4 + (mirrored ? 3 - corner : corner)]];
    vec3 local = vec3((side.x == 1) != mirrored ? hi.x : lo.x, side.y == 1 ? hi.y : lo.y, side.z == 1 ? hi.z : lo.z);

    vec3 centre = (round(stitch_texel_fetch(ivec2(1, row)).rgb * 255.0) - 128.0) / 4.0;
    float sphere = stitch_texel_fetch(ivec2(2, row)).r * 255.0 / 4.0;
    vec3 up = stitch_up();
    // an amulet's (kind 6) is drawn nearer the eye (AMULET_PULL); a cape's (kind 7) takes the world's up
    rt_info = ivec4(cape >= 0 ? 7 : (amulet >= 0 ? 6 : 1), row, cape >= 0 ? pack_unit(up) : face / 2, cubes);
    // lit from above: the fragment shades the model itself
    v.normal = up;
#ifdef STITCH_HAS_QUAD_CORNERS
    // Where the face's corners can be shared, the limb's transform is known here: the card is the
    // smallest rectangle that covers the model's box as the eye sees it, and each of its corners
    // carries its own place in the part's space, so the fragment reads the same transform back. Not for
    // an amulet's, on the body's top face, whose transform this reads mirrored: its card is rounded below.
    vec3 qp[4];
    vec2 qt[4];
    if (amulet < 0 && cape < 0 && stitch_quad_corners(qp, qt)) {
        vec3 l[4];
        for (int k = 0; k < 4; k++) {
            ivec3 s = CORNER[FACE[face * 4 + (mirrored ? 3 - k : k)]];
            l[k] = vec3((s.x == 1) != mirrored ? hi.x : lo.x, s.y == 1 ? hi.y : lo.y, s.z == 1 ? hi.z : lo.z);
        }
        vec3 e1 = l[1] - l[0];
        vec3 e2 = l[3] - l[0];
        int a = abs(e1.x) > 0.5 ? 0 : (abs(e1.y) > 0.5 ? 1 : 2);
        int b = abs(e2.x) > 0.5 ? 0 : (abs(e2.y) > 0.5 ? 1 : 2);
        int c = 3 - a - b;
        mat3 m;
        m[a] = (qp[1] - qp[0]) / e1[a];
        m[b] = (qp[3] - qp[0]) / e2[b];
        float s = length(m[a]);
        m[c] = cross(m[a], m[b]) / s * ((a + 1) % 3 == b ? 1.0 : -1.0);
        vec3 t = qp[0] - m * l[0];
        vec3 cp = m * centre + t;
        float dc = length(cp);
        if (s > 1e-6 && dc > 1e-4) {
            vec3 dir = cp / dc;
            vec3 right = cross(dir, up);
            right = length(right) > 1e-3 ? normalize(right) : vec3(1.0, 0.0, 0.0);
            vec3 above = cross(right, dir);
            // the rectangle the model's box covers, seen from the eye, on the plane through its nearest
            // corner, so every hit lies beyond the card
            vec3 blo = decode_corner(stitch_texel_fetch(ivec2(3, row)));
            vec3 bhi = decode_corner(stitch_texel_fetch(ivec2(4, row)));
            vec3 c[8];
            float near = 1e30;
            for (int k = 0; k < 8; k++) {
                c[k] = m * vec3((k & 1) != 0 ? bhi.x : blo.x, (k & 2) != 0 ? bhi.y : blo.y, (k & 4) != 0 ? bhi.z : blo.z) + t;
                near = min(near, dot(c[k], dir));
            }
            if (near > dc * 0.02) {
                vec2 rlo = vec2(1e30);
                vec2 rhi = vec2(-1e30);
                for (int k = 0; k < 8; k++) {
                    vec3 x = c[k] * (near / dot(c[k], dir));
                    vec2 at = vec2(dot(x, right), dot(x, above));
                    rlo = min(rlo, at);
                    rhi = max(rhi, at);
                }
                vec2 pad = vec2(0.02 * s);
                vec2 at = mix(rlo - pad, rhi + pad, SPREAD[corner] * 0.5 + 0.5);
                vec3 card = dir * near + right * at.x + above * at.y;
                rt_orig = card;
                rt_local = transpose(m) / (s * s) * (card - t);
                v.position = card;
                return true;
            }
        }
    }
#endif
    // otherwise round this corner, wide enough to cover the part's model wherever the limb is
    float reach = length(centre - local) + sphere;
    if (cape >= 0) {
        // a cape is turned from the leg's frame to the body's about the leg's pivot, and its swinging rows
        // about the hinge: every point of it is within this of the corner
        vec4 split = stitch_texel_fetch(ivec2(9, row));
        int fixedRows = int(round(split.r * 255.0));
        int swingEnd = fixedRows + int(round(split.g * 255.0));
        int rows = swingEnd + int(round(split.b * 255.0)) + int(round(stitch_texel_fetch(ivec2(11, row)).r * 255.0));
        vec3 hinge = decode_corner(stitch_texel_fetch(ivec2(5, row)));
        vec3 pivot = decode_corner(stitch_texel_fetch(ivec2(10, row)));
        float far = 0.0;
        for (int k = 0; k < 5; k++) {
            if (k < rows) {
                vec3 c = decode_corner(stitch_texel_fetch(ivec2(1, row + k)));
                float span = stitch_texel_fetch(ivec2(2, row + k)).r * 255.0 / 4.0;
                vec3 about = k < fixedRows ? vec3(0.0) : (k < swingEnd ? hinge : pivot);
                far = max(far, length(about) + length(c - about) + span);
            }
        }
        reach = length(local) + far;
    }
    float radius = reach * PIXEL;
    vec3 at = v.position;
    float d = length(at);
    vec3 dir = at / max(d, 1e-4);
    vec3 right = cross(dir, up);
    right = length(right) > 1e-3 ? normalize(right) : vec3(1.0, 0.0, 0.0);
    vec3 above = cross(right, dir);
    float spread = d > radius * 1.2 ? 1.4 * radius * d / sqrt(d * d - radius * radius) : 4.0 * radius;
    rt_orig = at;
    rt_local = local;
    // drawn nearer the eye (the same rays) by the model's reach, so every hit lies beyond the card
    v.position = (at + (right * SPREAD[corner].x + above * SPREAD[corner].y) * spread) * (max(d - radius, 0.06) / max(d, 1e-4));
    return true;
}
#endif

// An amulet hangs over any chestplate, whose models stand up to two pixels proud of the body: it sits
// AMULET_OUT pixels out from the body, along the body's own front (its model is built so,
// armour_models.seated()), and is drawn nearer the eye by up to AMULET_PULL more, along the eye's own line,
// for the few that stand out further.
const float AMULET_OUT = %(amulet_out)s;
const float AMULET_PULL = 2.25;

// An amulet's flat look drawn over a chestplate by its depth (armour.frag.glsl): in the world along the
// face's own front, in rt_orig (rt_info w 1); in a screen, whose preview faces the viewer and may be drawn
// mirrored with its normals not (1.20.1), towards the viewer, found from the face's own steps across the
// screen made right-handed by rt_orig.x (w 2)
void lift_amulet(inout StitchVertex v) {
    if (stitch_in_screen()) {
        rt_orig = vec3(stitch_handedness(), 0.0, 0.0);
        rt_info.w = 2;
    } else if (length(v.normal) > 1e-4) {
        rt_orig = normalize(v.normal);
        rt_info.w = 1;
    }
}

// Gloves alone on an arm's face where a chestplate's model draws the arm, or an amulet alone on the front
// of the leggings' body: their texels on the box as a flat look would be, nothing between them (rt_info
// kind 5).
void worn_only(int layer, int tile, inout StitchVertex v) {
    vec2 uv = v.uv;
    vec2 sheet = vec2(stitch_texture_size());
    int columns = int(sheet.x) / int(SHEET_TILE.x);
    v.hidden = false;
    v.uv = (uv + vec2(tile % columns, tile / columns)) * SHEET_TILE / sheet;
    v.color = vec4(1.0, 1.0, 1.0, v.color.a);
    tint = vec4(0.0);
    rt_info = ivec4(5, 0, 0, 0);
    narrow(layer, uv, v);
    if (layer == 2 && !stitch_in_screen()) {
        // as the traced model's: out from the body, then nearer the eye from the front alone (armour.frag.glsl)
        v.position += normalize(v.normal) * AMULET_OUT * PIXEL;
        float d = length(v.position);
        float front = clamp(dot(-v.position / max(d, 1e-4), normalize(v.normal)), 0.0, 1.0);
        v.position *= max(d - AMULET_PULL * PIXEL * front, d * 0.5) / max(d, 1e-4);
    } else if (layer == 2) {
        // in a screen (an inventory's preview), whose scale isn't the world's: the fragment lifts it
        lift_amulet(v);
    }
}

void stitch_vertex(inout StitchVertex v) {
    tint = vec4(0.0);
    rt_orig = vec3(0.0);
    rt_local = vec3(0.0);
    rt_info = ivec4(0);
    vec4 marker = stitch_texel_fetch(ivec2(stitch_texture_size().x - 1, 0));
    int code = int(round(marker.a * 255.0));
    if ((code == 4 || code == 5) && marker.r > 0.99 && marker.b > 0.99) {
#ifdef STITCH_HAS_QUAD_CORNERS
        model_layer(code == 5, v);
#else
        v.hidden = true;
#endif
        return;
    }
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
    int look = item_tile(v.color);
    // what's worn with the armour, on the faces it covers: gloves on a chestplate's arms, an amulet on the
    // front of the leggings' body (by a point inside the face: corners 0 and 1 sit on its low v edge, 0 and 3
    // on its high u). Its sheet tile, else -1.
    int worn = -1;
    if (!own && v.corner >= 0) {
        vec2 p = v.uv * vec2(64.0, 32.0);
        float u = p.x + ((v.corner == 0 || v.corner == 3) ? -0.5 : 0.5);
        float w = p.y + (v.corner < 2 ? 0.5 : -0.5);
        if (layer == 1 ? (p.y > 15.5 && u > 40.0 && u < 56.0) : (u > 20.0 && u < 28.0 && w > 20.0 && w < 32.0)) {
            worn = worn_tile(layer, v.color);
        }
    }
#if defined(STITCH_HAS_FRAGMENT_POSITION) && defined(STITCH_HAS_FRAGMENT_DEPTH) && defined(STITCH_HAS_VERTEX_INDEX)
    // an amulet in 3D where the tracer can draw it, its model traced on the leggings' body's top face, in
    // place of its flat look on the front
    if (layer == 2 && !own && !stitch_in_screen()) {
        int amulet = worn_index(2, v.color);
        int top = u24(stitch_texel_fetch(ivec2(stitch_texture_size().x - 2, 0)));
        // one with no model (too many cubes for the tracer) keeps its flat look
        if (amulet >= 0 && top > 0 && u24(stitch_texel_fetch(ivec2(amulet, top + 1))) > 0) {
            worn = -1;
            if (trace_card(layer, 0, amulet, -1, v)) {
                return;
            }
        }
    }
    // a cape, carried on the boots, traced from the right leg's top face in the body's own frame
    if (layer == 1 && !own && !stitch_in_screen()) {
        int cape = cape_index(v.color);
        int top = u24(stitch_texel_fetch(ivec2(stitch_texture_size().x - 2, 0)));
        if (cape >= 0 && top > 0 && u24(stitch_texel_fetch(ivec2(MS_CAPE_COLUMN + cape, top + 1))) > 0
                && trace_card(layer, 0, -1, cape, v)) {
            return;
        }
    }
#endif
#ifdef STITCH_HAS_QUAD_CORNERS
    // a sheet with models (1.21.2 on): an item with a model draws it in the layers above, where its
    // corners can be shared; its look here hides, but for the gloves or amulet worn on it
    vec2 at = v.uv * vec2(64.0, 32.0);
    int piece = layer == 2 ? 4 : (at.x < 16.0 && at.y > 16.0 ? 2 : 1);
    if (!own && (int(round(marker.g * 255.0)) & 32) != 0 && (MS_MODELLED[look] & piece) != 0) {
        vec3 p[4];
        vec2 t[4];
        if (stitch_quad_corners(p, t)) {
            if (worn >= 0) {
                worn_only(layer, worn, v);
            } else {
                v.hidden = true;
            }
            return;
        }
    }
#endif
#if defined(STITCH_HAS_FRAGMENT_POSITION) && defined(STITCH_HAS_FRAGMENT_DEPTH) && defined(STITCH_HAS_VERTEX_INDEX)
    // the tables are by item tile on a sheet, in column 0 on an item's own tile; a modelled part's faces
    // but the one its model is traced on would hide, and draw what's worn on them instead
    if (!stitch_in_screen() && trace_card(layer, own ? 0 : look, -1, -1, v)) {
        if (v.hidden && worn >= 0) {
            worn_only(layer, worn, v);
        }
        return;
    }
#endif
    int tile = layer == 1 ? MS_TILE_1[look] : MS_TILE_2[look];
    // the item's tile on the sheet (its looks are a grid of tiles at the top, any traced models' data
    // below them); an own tile is the sheet's first
    vec2 sheet = vec2(stitch_texture_size());
    int columns = int(sheet.x) / int(SHEET_TILE.x);
    vec2 uv = v.uv;
    v.uv = (v.uv + (own ? vec2(0.0) : vec2(tile % columns, tile / columns))) * SHEET_TILE / sheet;
    // what's worn over a flat look: the face reads its tile too, by how far it is from the armour's (rt_info
    // kind 4, unused by a sheet's look otherwise), and the fragment draws its texels over the armour's
    if (worn >= 0) {
        rt_info = ivec4(4, worn % columns - tile % columns, worn / columns - tile / columns, 0);
        if (layer == 2) {
            lift_amulet(v);
        }
    }
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

// A model's texel (armour_models.py), all but clear in its colour code: alpha 1 dyed, 2 its own
// colour, 3 a light shade, 0 clear.
vec4 model_texel(vec4 texel, float light) {
    int code = int(round(texel.a * 255.0));
    if (code == 0) {
        return vec4(0.0);
    }
    vec3 dye = code == 2 ? vec3(1.0) : (code == 3 ? mix(tint.rgb, vec3(1.0), 0.55) : tint.rgb);
    return vec4(texel.rgb * dye * light, 1.0);
}
vec3 decode_point(vec4 t) {
    return (round(t.rgb * 255.0) - 128.0) / 4.0;
}

// the most cubes a traced part has, a cube's texels, and where a part's header row lists its cubes
// (armour_models.most_cubes(), CUBE, HEADER_CUBES)
const int MAX_CUBES = %(max_cubes)d;
const int CUBE_TEXELS = %(cube)d;
const int HEADER_CUBES = %(header_cubes)d;
// as armour.vert.glsl's: how far out from the body an amulet sits, and how much nearer the eye its model is
// drawn on top, in pixels
const float AMULET_OUT = %(amulet_out)s;
const float AMULET_PULL = 2.25;

int read24(vec4 t) {
    ivec3 b = ivec3(round(t.rgb * 255.0));
    return (b.r << 16) | (b.g << 8) | b.b;
}

// armour_models.fixed and unit_pair
float fixed24(vec4 t) {
    return float(read24(t) - 8388608) / 1024.0;
}

vec2 unit_pair(vec4 t) {
    int n = read24(t);
    return vec2(float(n >> 12), float(n & 4095)) / 4095.0 * 2.0 - 1.0;
}

// a cube face's top left, top right and bottom left corners, by the ends of the cube's own axes they
// take, in armour_models.FACE_ORDER (west, east, down, up, north, south)
const vec3 FACE_TL[6] = vec3[](vec3(0.0, 1.0, 0.0), vec3(1.0, 1.0, 1.0), vec3(0.0, 0.0, 1.0), vec3(0.0, 1.0, 0.0), vec3(1.0, 1.0, 0.0), vec3(0.0, 1.0, 1.0));
const vec3 FACE_TR[6] = vec3[](vec3(0.0, 1.0, 1.0), vec3(1.0, 1.0, 0.0), vec3(1.0, 0.0, 1.0), vec3(1.0, 1.0, 0.0), vec3(0.0, 1.0, 0.0), vec3(1.0, 1.0, 1.0));
const vec3 FACE_BL[6] = vec3[](vec3(0.0, 0.0, 0.0), vec3(1.0, 0.0, 1.0), vec3(0.0, 0.0, 0.0), vec3(0.0, 1.0, 1.0), vec3(1.0, 0.0, 0.0), vec3(0.0, 0.0, 1.0));

// The tracer's nearest hit so far: how far along the ray; its cube's texels, face and the point on it
// (by the cube's own axes, 0 to 1); the face's normal in the part's space.
struct Hit {
    float best;
    ivec2 cube;
    int face;
    vec3 q;
    vec3 normal;
};

// A face's texel position at q, kept inside the face: at an edge it would read the next face's texels.
vec2 face_texel(ivec2 cube, int face, vec3 q) {
    int n0 = read24(stitch_texel_fetch(cube + ivec2(3 + 3 * face, 0)));
    int n1 = read24(stitch_texel_fetch(cube + ivec2(4 + 3 * face, 0)));
    int n2 = read24(stitch_texel_fetch(cube + ivec2(5 + 3 * face, 0)));
    vec2 a = vec2(float(n0 >> 12), float(n0 & 4095));
    vec2 b = vec2(float(n1 >> 12), float(n1 & 4095));
    vec2 c = vec2(float(n2 >> 12), float(n2 & 4095));
    vec2 d = b + c - a;
    float u = dot(q - FACE_TL[face], FACE_TR[face] - FACE_TL[face]);
    float v = dot(q - FACE_TL[face], FACE_BL[face] - FACE_TL[face]);
    return clamp(a + (b - a) * u + (c - a) * v, min(min(a, b), min(c, d)) + 0.01, max(max(a, b), max(c, d)) - 0.01);
}

// The ray against one cube: where it goes in, and where it comes out of it (by the cube's back
// faces, seen through a clear texel of the front), if nearer than h and drawn there. Its flags and box
// are read from the part's header row (head); the rest of its texels only once the ray meets the box.
void trace_cube(ivec2 head, int index, int first, int width, int shift, vec3 origin, vec3 dir, vec3 inv, inout Hit h) {
    vec4 flags = stitch_texel_fetch(head);
    vec3 lo = decode_point(stitch_texel_fetch(head + ivec2(1, 0)));
    vec3 hi = decode_point(stitch_texel_fetch(head + ivec2(2, 0)));
    vec3 t0 = (lo - origin) * inv;
    vec3 t1 = (hi - origin) * inv;
    vec3 near = min(t0, t1);
    vec3 far = max(t0, t1);
    float enter = max(max(near.x, near.y), near.z);
    float leave = min(min(far.x, far.y), far.z);
    if (enter > leave || leave <= 0.0 || enter >= h.best) {
        return;
    }
    int record = index * CUBE_TEXELS;
    ivec2 cube = ivec2(record & (width - 1), first + (record >> shift));
    bool turned = flags.r > 0.5;
    mat3 m = mat3(1.0);
    vec3 o = origin;
    vec3 d = dir;
    vec3 size = hi - lo;
    if (turned) {
        // into the cube's own space, its corner at 0 (the box above is only round it)
        vec2 a01 = unit_pair(stitch_texel_fetch(cube + ivec2(21, 0)));
        vec2 a23 = unit_pair(stitch_texel_fetch(cube + ivec2(22, 0)));
        vec2 a45 = unit_pair(stitch_texel_fetch(cube + ivec2(23, 0)));
        vec2 a67 = unit_pair(stitch_texel_fetch(cube + ivec2(24, 0)));
        vec2 a8 = unit_pair(stitch_texel_fetch(cube + ivec2(25, 0)));
        m = transpose(mat3(a01.x, a01.y, a23.x, a23.y, a45.x, a45.y, a67.x, a67.y, a8.x));
        o = m * origin + vec3(fixed24(stitch_texel_fetch(cube + ivec2(26, 0))), fixed24(stitch_texel_fetch(cube + ivec2(27, 0))),
                              fixed24(stitch_texel_fetch(cube + ivec2(28, 0))));
        d = m * dir;
        size = vec3(fixed24(stitch_texel_fetch(cube + ivec2(29, 0))), fixed24(stitch_texel_fetch(cube + ivec2(30, 0))),
                    fixed24(stitch_texel_fetch(cube + ivec2(31, 0))));
        lo = vec3(0.0);
        vec3 iv = 1.0 / d;
        t0 = -o * iv;
        t1 = (size - o) * iv;
        near = min(t0, t1);
        far = max(t0, t1);
        enter = max(max(near.x, near.y), near.z);
        leave = min(min(far.x, far.y), far.z);
        if (enter > leave || leave <= 0.0 || enter >= h.best) {
            return;
        }
    }
    int faces = int(round(flags.g * 255.0));
    int cut = int(round(flags.b * 255.0));
    for (int k = 0; k < 2; k++) {
        float at = k == 0 ? enter : leave;
        if (at <= 0.0 || at >= h.best) {
            continue;
        }
        vec3 ends = k == 0 ? near : far;
        int axis = ends.x == at ? 0 : (ends.y == at ? 1 : 2);
        // the side of the cube it crosses, low (0) or high, by the cube's own axes: an unturned cube's
        // box is in the part's space, whose x and y run the other way to the model's
        int side = (d[axis] > 0.0) == (k == 0) ? 0 : 1;
        vec3 q = (o + d * at - lo) / max(size, vec3(1e-4));
        if (!turned && axis < 2) {
            side = 1 - side;
        }
        if (!turned) {
            q = vec3(1.0 - q.x, 1.0 - q.y, q.z);
        }
        int face = axis * 2 + side;
        if (((faces >> face) & 1) == 0) {
            continue;
        }
        if (((cut >> face) & 1) != 0 && stitch_texel_fetch(ivec2(face_texel(cube, face, q))).a < 0.5 / 255.0) {
            continue;
        }
        vec3 n = vec3(0.0);
        n[axis] = side == 1 ? 1.0 : -1.0;
        h = Hit(at, cube, face, q, turned ? transpose(m) * n : vec3(-n.x, -n.y, n.z));
        return;
    }
}

// The tracer (armour.vert.glsl, trace_card): the model under this pixel of the card, or clear.
vec4 trace(StitchFragment f, vec3 dpx, vec3 dpy, vec3 dlx, vec3 dly) {
    // the limb's transform m (model pixels to the position space, a rotation and a scale s) maps the
    // card's steps across the screen in the part's space onto its steps in the position space: two
    // directions from the screen's x and y, the third their cross
    vec3 nl = cross(dlx, dly);
    vec3 np = cross(dpx, dpy);
    float ln = length(nl);
    if (ln < 1e-12) {
        return vec4(0.0);
    }
    float s = sqrt(length(np) / ln);
    mat3 m = mat3(dpx, dpy, np / s) * inverse(mat3(dlx, dly, nl));
    vec3 t = rt_orig - m * rt_local;
    mat3 mi = transpose(m) / (s * s);
    // the eye is at the position space's origin
    vec3 origin = mi * (-t);
    vec3 dir = mi * f.position;

    int row = rt_info.y;
    vec3 inv = 1.0 / dir;
    vec3 t0 = (decode_point(stitch_texel_fetch(ivec2(3, row))) - origin) * inv;
    vec3 t1 = (decode_point(stitch_texel_fetch(ivec2(4, row))) - origin) * inv;
    vec3 near = min(t0, t1);
    vec3 far = max(t0, t1);
    if (max(max(near.x, near.y), near.z) > min(min(far.x, far.y), far.z) || min(min(far.x, far.y), far.z) <= 0.0) {
        return vec4(0.0);
    }
    // every cube of the part, each read where its texels start (a power of two wide: a shift)
    ivec2 size = stitch_texture_size();
    int first = read24(stitch_texel_fetch(ivec2(size.x - 3, 0)));
    int shift = int(round(log2(float(size.x))));
    int start = read24(stitch_texel_fetch(ivec2(8, row)));
    int cubes = min(rt_info.w, MAX_CUBES);
    Hit h = Hit(1e30, ivec2(0), -1, vec3(0.0), vec3(0.0));
    for (int c = 0; c < MAX_CUBES; c++) {
        if (c < cubes) {
            trace_cube(ivec2(HEADER_CUBES + 3 * c, row), start + c, first, size.x, shift, origin, dir, inv, h);
        }
    }
    if (h.face < 0) {
        return vec4(0.0);
    }
    vec3 n = normalize(m * h.normal);
    vec3 hitPos = m * (origin + dir * h.best) + t;
    vec3 eye = normalize(-hitPos);
    if (dot(n, eye) < 0.0) {
        n = -n;
    }
#ifdef STITCH_HAS_FRAGMENT_DEPTH
    // an amulet's (kind 6) nearer the eye along its line, over a chestplate's model that stands out from
    // the chest: by AMULET_PULL pixels where it hangs in front of the body (its part's front is z -2) and
    // is seen from the front, less as the eye goes round, none from the side or behind, where the
    // chestplate covers it as it would
    float d = length(hitPos);
    float pull = 0.0;
    if (rt_info.x == 6 && (origin + dir * h.best).z < -2.0) {
        pull = AMULET_PULL * 0.9375 / 16.0 * clamp(dot(eye, normalize(m * vec3(0.0, 0.0, -1.0))), 0.0, 1.0);
    }
    stitch_set_depth(hitPos * max(d - pull, d * 0.5) / max(d, 1e-4));
#endif
    // lit towards the eye
    return model_texel(stitch_texel_fetch(ivec2(face_texel(h.cube, h.face, h.q))), 0.55 + 0.45 * max(dot(n, eye), 0.0));
}

// One part's cubes against a ray (trace()'s loop, for a row of its own): its box first.
void trace_row(int row, vec3 origin, vec3 dir, inout Hit h) {
    vec3 inv = 1.0 / dir;
    vec3 t0 = (decode_point(stitch_texel_fetch(ivec2(3, row))) - origin) * inv;
    vec3 t1 = (decode_point(stitch_texel_fetch(ivec2(4, row))) - origin) * inv;
    vec3 near = min(t0, t1);
    vec3 far = max(t0, t1);
    if (max(max(near.x, near.y), near.z) > min(min(far.x, far.y), far.z) || min(min(far.x, far.y), far.z) <= 0.0) {
        return;
    }
    ivec2 size = stitch_texture_size();
    int first = read24(stitch_texel_fetch(ivec2(size.x - 3, 0)));
    int shift = int(round(log2(float(size.x))));
    int start = read24(stitch_texel_fetch(ivec2(8, row)));
    int cubes = min(int(round(stitch_texel_fetch(ivec2(0, row)).r * 255.0)), MAX_CUBES);
    for (int c = 0; c < MAX_CUBES; c++) {
        if (c < cubes) {
            trace_cube(ivec2(HEADER_CUBES + 3 * c, row), start + c, first, size.x, shift, origin, dir, inv, h);
        }
    }
}

// how far a cape's swinging part hangs back standing still, and how much more for each radian the legs
// swing (radians): it sways back with each step, and none past a sitting leg's. It rolls a little to the
// side with each step too (CAPE_SWAY a radian of the legs' swing, one way then the other), and by
// CAPE_BREEZE either way, once every CAPE_BREEZE_SECONDS, standing still.
const float CAPE_REST = 0.07;
const float CAPE_SWING = 0.35;
const float CAPE_SWAY = 0.12;
const float CAPE_BREEZE = 0.025;
const float CAPE_BREEZE_SECONDS = 3.0;
// a cape's flapping sides (wings): back from where they're modelled by up to CAPE_FLAP radians and in
// again, once every CAPE_FLAP_SECONDS, and by CAPE_FLAP_WALK more for each radian the legs swing (a side
// on the pivot's left turns by the angle, the right side by its opposite: both tips back)
const float CAPE_FLAP = 0.25;
const float CAPE_FLAP_WALK = 0.35;
const float CAPE_FLAP_SECONDS = 1.6;

// p turned about x by a, y towards z
vec3 turn_x(vec3 p, float a) {
    float c = cos(a);
    float s = sin(a);
    return vec3(p.x, p.y * c - p.z * s, p.y * s + p.z * c);
}

// p turned about y by a, z towards x
vec3 turn_y(vec3 p, float a) {
    float c = cos(a);
    float s = sin(a);
    return vec3(p.x * c + p.z * s, p.y, p.z * c - p.x * s);
}

// p turned about z by a, x towards y
vec3 turn_z(vec3 p, float a) {
    float c = cos(a);
    float s = sin(a);
    return vec3(p.x * c - p.y * s, p.x * s + p.y * c, p.z);
}

// A hit's texel: on a face with an animated texture (its first texture position's alpha 2,
// armour_models.ANIMATED), the frame for the game's clock, by the part's row (texels 6 and 7: frames,
// ticks a frame, how many a row, blended or not; a frame's size), blended into the next as Minecraft's
// own animations are.
vec4 animated_texel(Hit h, int row) {
    vec2 at = face_texel(h.cube, h.face, h.q);
    if (int(round(stitch_texel_fetch(h.cube + ivec2(3 + 3 * h.face, 0)).a * 255.0)) != 2) {
        return stitch_texel_fetch(ivec2(at));
    }
    vec4 info = stitch_texel_fetch(ivec2(6, row));
    int frames = max(1, int(round(info.r * 255.0)));
    float ticks = max(1.0, info.g * 255.0);
    int grid = max(1, int(round(info.b * 255.0)));
    int size = read24(stitch_texel_fetch(ivec2(7, row)));
    vec2 frame = vec2(float(size >> 12), float(size & 4095));
    float now = stitch_game_time * 24000.0 / ticks;
    int k = int(mod(floor(now), float(frames)));
    int next = (k + 1) % frames;
    vec4 a = stitch_texel_fetch(ivec2(at + vec2(float(k % grid), float(k / grid)) * frame));
    if (int(round(info.a * 255.0)) != 2) {
        return a;
    }
    vec4 b = stitch_texel_fetch(ivec2(at + vec2(float(next % grid), float(next / grid)) * frame));
    return vec4(mix(a.rgb, b.rgb, fract(now)), a.a);
}

// A cape (rt_info kind 7), traced from the right leg's card. A walking leg turns about its own x, which is
// the body's too, and the body stands up (rt_info z, the world's up): the leg's turn from it is found and
// undone, so the cape keeps to the body. Its rows from the model's first (texels 9 and 11 of it: how
// many are fixed, swing, flap on the left and on the right): the fixed rows keep to the body; the
// swinging ones turn back about the hinge (texel 5) as the leg swings; the flapping ones turn about the
// upright through the pivot (texel 10), each side the other way.
vec4 trace_cape(StitchFragment f, vec3 dpx, vec3 dpy, vec3 dlx, vec3 dly) {
    vec3 nl = cross(dlx, dly);
    vec3 np = cross(dpx, dpy);
    float ln = length(nl);
    if (ln < 1e-12) {
        return vec4(0.0);
    }
    float s = sqrt(length(np) / ln);
    mat3 m = mat3(dpx, dpy, np / s) * inverse(mat3(dlx, dly, nl));
    vec3 t = rt_orig - m * rt_local;
    mat3 mi = transpose(m) / (s * s);
    vec3 origin = mi * (-t);
    vec3 dir = mi * f.position;
    int n = rt_info.z;
    vec3 up = vec3(float((n >> 20) & 1023), float((n >> 10) & 1023), float(n & 1023)) / 1023.0 * 2.0 - 1.0;
    vec3 x = normalize(m[0]);
    vec3 down = -up + dot(up, x) * x;
    float swing = 0.0;
    if (length(down) > 1e-3) {
        down = normalize(down);
        vec3 y = normalize(m[1]);
        swing = atan(dot(cross(down, y), x), dot(down, y));
    }
    // the ray in the body's frame, about the leg's pivot (its space's origin)
    vec3 o = turn_x(origin, swing);
    vec3 d = turn_x(dir, swing);
    int row = rt_info.y;
    vec4 split = stitch_texel_fetch(ivec2(9, row));
    int fixedRows = int(round(split.r * 255.0));
    int swingEnd = fixedRows + int(round(split.g * 255.0));
    int leftEnd = swingEnd + int(round(split.b * 255.0));
    int rows = leftEnd + int(round(stitch_texel_fetch(ivec2(11, row)).r * 255.0));
    float walk = abs(swing) > 1.2 ? 0.0 : clamp(swing, -0.9, 0.9);
    float seconds = stitch_game_time * 1200.0;
    float back = CAPE_REST + CAPE_SWING * abs(walk);
    float sway = CAPE_SWAY * walk + CAPE_BREEZE * sin(seconds / CAPE_BREEZE_SECONDS * 6.2831853);
    // only ever back from where the wings are modelled, never forward into the body
    float flap = (CAPE_FLAP + CAPE_FLAP_WALK * abs(walk)) * (0.5 - 0.5 * cos(seconds / CAPE_FLAP_SECONDS * 6.2831853));
    vec3 hinge = decode_point(stitch_texel_fetch(ivec2(5, row)));
    vec3 pivot = decode_point(stitch_texel_fetch(ivec2(10, row)));
    // every row against the one nearest hit: the fixed rows' ray as it is; the swinging rows' turned back
    // about the hinge and rolled, the other way to how they're drawn; each flapping side's turned about
    // the upright through the pivot, the sides opposite
    Hit h = Hit(1e30, ivec2(0), -1, vec3(0.0), vec3(0.0));
    int hitRow = row;
    int hitKind = 0;
    for (int k = 0; k < 5; k++) {
        if (k < rows) {
            int kind = k < fixedRows ? 0 : (k < swingEnd ? 1 : (k < leftEnd ? 2 : 3));
            vec3 ok = o;
            vec3 dk = d;
            if (kind == 1) {
                ok = hinge + turn_x(turn_z(o - hinge, -sway), -back);
                dk = turn_x(turn_z(d, -sway), -back);
            } else if (kind >= 2) {
                float a = kind == 2 ? flap : -flap;
                ok = pivot + turn_y(o - pivot, -a);
                dk = turn_y(d, -a);
            }
            float before = h.best;
            trace_row(row + k, ok, dk, h);
            if (h.best < before) {
                hitRow = row + k;
                hitKind = kind;
            }
        }
    }
    if (h.face < 0) {
        return vec4(0.0);
    }
    vec3 nb = h.normal;
    if (hitKind == 1) {
        nb = turn_z(turn_x(nb, back), sway);
    } else if (hitKind >= 2) {
        nb = turn_y(nb, hitKind == 2 ? flap : -flap);
    }
    vec3 nrm = normalize(m * turn_x(nb, -swing));
    vec3 hitPos = m * (origin + dir * h.best) + t;
    vec3 eye = normalize(-hitPos);
    if (dot(nrm, eye) < 0.0) {
        nrm = -nrm;
    }
#ifdef STITCH_HAS_FRAGMENT_DEPTH
    stitch_set_depth(hitPos);
#endif
    return model_texel(animated_texel(h, hitRow), 0.55 + 0.45 * max(dot(nrm, eye), 0.0));
}

vec4 stitch_texel(StitchFragment f, vec4 texel) {
    // derivatives first, while every pixel of the quad still runs
    vec3 dpx = dFdx(rt_orig);
    vec3 dpy = dFdy(rt_orig);
    vec3 dlx = dFdx(rt_local);
    vec3 dly = dFdy(rt_local);
    if (rt_info.x == 1 || rt_info.x == 6) {
        return trace(f, dpx, dpy, dlx, dly);
    }
    if (rt_info.x == 7) {
        return trace_cape(f, dpx, dpy, dlx, dly);
    }
    if (rt_info.x == 3) {
        return model_texel(texel, 1.0);
    }
    // An amulet's flat look (rt_info w 1 or 2, armour.vert.glsl's lift_amulet), on the leggings' body half a
    // pixel inside a chestplate's own and further inside its models: drawn as though AMULET_OUT + 0.5 pixels
    // out, a pixel's size from how Minecraft's texture layout (four of the sheet's texels a pixel) steps
    // across the face, so the same in an inventory's preview as in the world
    vec3 lifted = f.position;
    if (rt_info.w != 0) {
        vec3 px = dFdx(f.position);
        vec3 py = dFdy(f.position);
        vec3 across = cross(px, py);
        vec2 ux = dFdx(f.uv) * vec2(stitch_texture_size()) / 4.0;
        vec2 uy = dFdy(f.uv) * vec2(stitch_texture_size()) / 4.0;
        float area = abs(ux.x * uy.y - ux.y * uy.x);
        if (area > 1e-12 && length(across) > 1e-12) {
            vec3 away = rt_info.w == 1 ? rt_orig : normalize(across) * rt_orig.x;
            lifted += away * (AMULET_OUT + 0.5) * sqrt(length(across) / area);
        }
    }
    if (rt_info.x == 5) {
        // what's worn, alone (armour.vert.glsl, worn_only)
        if (texel.a > 0.5) {
#ifdef STITCH_HAS_FRAGMENT_DEPTH
            if (rt_info.w != 0) {
                stitch_set_depth(lifted);
            }
#endif
            return vec4(texel.rgb, 1.0);
        }
        return vec4(0.0);
    }
    if (rt_info.x == 4) {
        // the worn item's tile, baked in its colour: a texel there is drawn as it is
        vec4 g = stitch_texel_fetch(ivec2(floor(f.uv * vec2(stitch_texture_size()))) + rt_info.yz * ivec2(256, 128));
        if (g.a > 0.5) {
#ifdef STITCH_HAS_FRAGMENT_DEPTH
            if (rt_info.w != 0) {
                stitch_set_depth(lifted);
            }
#endif
            return vec4(g.rgb, 1.0);
        }
    }
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
    "varyings": [{"name": "tint", "type": "vec4"}, {"name": "rt_orig", "type": "vec3"},
                 {"name": "rt_local", "type": "vec3"}, {"name": "rt_info", "type": "ivec4", "flat": True}],
    "uniforms": ["game_time"],
    "requires": ["vertex_corner", "texture_size", "orientation"],
    "uses": ["quad_corners", "vertex_index", "fragment_position", "fragment_depth"],
    "passes": ["main", "shadow"],
}


def write(root, modelled=None):
    """The stitch's three files into the pack folder at root; modelled, the item tiles with a model by
    piece (armour_models.build())."""
    out = os.path.join(root, "assets", "minescape", "stitches")
    os.makedirs(out, exist_ok=True)
    import armour_models
    vertex = VERTEX.replace("%(tables)s", armour_looks.glsl() + armour_models.glsl(modelled or {"chest": set(), "boots": set(), "legs": set()}))
    vertex = vertex.replace("%(undyed)d", str(0xA06540)).replace("%(amulet_out)s", repr(float(armour_models.AMULET_OUT)))
    with open(os.path.join(out, "armour.vert.glsl"), "w", encoding="utf-8", newline="\n") as f:
        f.write(vertex)
    with open(os.path.join(out, "armour.frag.glsl"), "w", encoding="utf-8", newline="\n") as f:
        f.write(FRAGMENT.replace("%(max_cubes)d", str(armour_models.most_cubes())).replace("%(header_cubes)d", str(armour_models.HEADER_CUBES)).replace("%(cube)d", str(armour_models.CUBE)).replace("%(amulet_out)s", repr(float(armour_models.AMULET_OUT))))
    with open(os.path.join(out, "armour.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(DEFINITION, f, indent=2)
        f.write("\n")
