"""Builds the slot text shader into the pack for every Minecraft release from 1.18.2 on, new ones included.

The plugin writes numbers in the corners of menu slots through a window's title, which Minecraft draws
behind the items. The slot fonts (font/slot.png, font/slot_box.png) mark their glyph cells with a
pixel the text vertex shader looks for, and it lifts those glyphs level with stack counts, in front of
the items.

From 1.21.6 the GUI is drawn in layers, not by depth: an item goes in the layer above any text it
overlaps, and in a layer text is drawn after images. Lifted, slot text would stay behind the items it
overlaps. So for those releases an overlay (shader_slot_layers) sets the slot font's glyphs up in the
title's own line, clear of every item, which puts the title in the items' layer, and its markers say
which row each glyph belongs to; the shader moves it down there, in front of the items.

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
import hashlib, io, json, os, re, shutil, sys, urllib.request, zipfile

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
// From 1.21.6 the slot font sets its glyphs in the title's line (the shader_slot_layers overlay) and
// this moves them down to their row: the first row's 21 pixels below it, each row 18 under the last.
const float SLOT_DROP = 21.0;
const float SLOT_ROW = 18.0;

// 26.3 compiles every shader as Vulkan GLSL (OpenGL too, through SPIR-V), which has no gl_VertexID.
#ifdef VULKAN
#define SLOT_VERTEX gl_VertexIndex
#else
#define SLOT_VERTEX gl_VertexID
#endif

// Which slot text this glyph is: -1 for none, 0 where the font sets it in its row, or its row from 1
// where the font sets it in the title's line, from its marker's green.
int slotText() {
    vec2 size = vec2(textureSize(Sampler0, 0));
    int corner = SLOT_VERTEX % 4;
    float u = corner < 2 ? UV0.x : UV0.x - SLOT_CELL / size.x;
    float v = (corner == 0 || corner == 3) ? UV0.y : UV0.y - 1.0 / size.y;
    vec4 marker = texelFetch(Sampler0, ivec2(floor(u * size.x + 0.5), floor(v * size.y + 0.5)), 0);
    if (marker.a > 0.0 && marker.a < 2.5 / 255.0 && marker.r > 0.9 && marker.g < 0.1 && marker.b > 0.9) {
        return int(round(marker.g * 255.0));
    }
    return -1;
}

// MineScape overhead chat: OSRS's coloured and moving speech ("red:wave:hello"). The server colours
// each glyph of a speech bubble with its effect packed into the colour; only world text (a perspective
// projection) is read, and no vanilla world text uses these colours.
//   0xD-----  colour (4 bits), effect (3), start tick mod 64 (6), the glyph's index in the message (7)
//   0xE-----  scroll: colour (4), start tick / 8 mod 8 (3), the glyph's left edge / 4 (7, signed),
//             half the line's width plus the window / 5 (6)
// and in a pattern's colours (rainbow, "patternq3q3"), the colour one of MS_PATTERN's:
//   0xDC----  to 0xDF: pattern colour (6), effect less one (2), start tick / 8 mod 8 (3), index (7)
//   0xC-----  scroll: pattern colour (6), start tick / 8 mod 8 (3), left edge / 4 (7, signed),
//             half the line's width plus the window / 20 (4)
// Distances are a name tag's pixels (0.025 blocks), an OSRS pixel being three quarters of one; time is
// OSRS client cycles (20 ms) from the game clock, where the version gives text shaders one (MS_CLOCK).
// Without it everything shows as it would halfway through: readable, still.
const float MS_BLOCKS = 0.025;
const float MS_OSRS = 0.75;
const float MS_LIFE = 150.0;
// The default font's glyph cell, in pixels and texels alike.
const float MS_CELL = 8.0;
const float MS_WINDOW = 50.0 * MS_OSRS;

// OSRS's pattern colours, by their keys 0-9 then a-z.
const vec3 MS_PATTERN[36] = vec3[](
    vec3(0xFF, 0xFF, 0xFF), vec3(0xE4, 0x03, 0x03), vec3(0xFF, 0x8C, 0x00), vec3(0xFF, 0xED, 0x00),
    vec3(0x00, 0x80, 0x26), vec3(0x24, 0x40, 0x8E), vec3(0x73, 0x29, 0x82), vec3(0xFF, 0x21, 0x8C),
    vec3(0xB5, 0x56, 0x90), vec3(0x50, 0x49, 0xCC), vec3(0xA3, 0xA3, 0xA3), vec3(0xD5, 0x2D, 0x00),
    vec3(0xEF, 0x76, 0x27), vec3(0xFC, 0xF4, 0x34), vec3(0x07, 0x8D, 0x70), vec3(0x21, 0xB1, 0xFF),
    vec3(0x9B, 0x4F, 0x96), vec3(0xFF, 0xAF, 0xC7), vec3(0xD1, 0x62, 0xA4), vec3(0x7B, 0xAD, 0xE3),
    vec3(0xFF, 0x9A, 0x56), vec3(0x26, 0xCE, 0xAA), vec3(0x73, 0xD7, 0xEE), vec3(0x9C, 0x59, 0xD1),
    vec3(0x98, 0xE8, 0xC1), vec3(0xB5, 0x7E, 0xDC), vec3(0x2C, 0x2C, 0x2C), vec3(0x94, 0x02, 0x02),
    vec3(0x61, 0x39, 0x15), vec3(0xD0, 0xC1, 0x00), vec3(0x4A, 0x81, 0x23), vec3(0x00, 0x38, 0xA8),
    vec3(0x80, 0x00, 0x80), vec3(0xD6, 0x02, 0x70), vec3(0xA3, 0x02, 0x62), vec3(0x3D, 0x1A, 0x78));

float msAge(float ticks, float start) {
#ifdef MS_CLOCK
    return mod(ticks - start, 64.0) * 2.5;
#else
    return MS_LIFE / 2.0;
#endif
}

vec3 msScheme(int scheme, float cycle, float age) {
    bool first = mod(cycle, 20.0) < 10.0;
    float j = clamp(age, 0.0, MS_LIFE);
    float s = 5.0 / 255.0;
    if (scheme == 0) return vec3(1.0, 1.0, 0.0);
    if (scheme == 1) return vec3(1.0, 0.0, 0.0);
    if (scheme == 2) return vec3(0.0, 1.0, 0.0);
    if (scheme == 3) return vec3(0.0, 1.0, 1.0);
    if (scheme == 4) return vec3(1.0, 0.0, 1.0);
    if (scheme == 5) return vec3(1.0);
    if (scheme == 6) return first ? vec3(1.0, 0.0, 0.0) : vec3(1.0, 1.0, 0.0);
    if (scheme == 7) return first ? vec3(0.0, 0.0, 1.0) : vec3(0.0, 1.0, 1.0);
    if (scheme == 8) return first ? vec3(0.0, 176.0 / 255.0, 0.0) : vec3(128.0 / 255.0, 1.0, 128.0 / 255.0);
    if (scheme == 9) {
        if (j < 50.0) return vec3(1.0, j * s, 0.0);
        if (j < 100.0) return vec3(1.0 - (j - 50.0) * s, 1.0, 0.0);
        return vec3(0.0, 1.0, (j - 100.0) * s);
    }
    if (scheme == 10) {
        if (j < 50.0) return vec3(1.0, 0.0, j * s);
        if (j < 100.0) return vec3(1.0 - (j - 50.0) * s, 0.0, 1.0);
        return vec3((j - 100.0) * s, 0.0, 1.0 - (j - 100.0) * s);
    }
    if (j < 50.0) return vec3(1.0 - j * s, 1.0, 1.0 - j * s);
    if (j < 100.0) return vec3((j - 50.0) * s, 1.0, (j - 50.0) * s);
    return vec3(1.0 - (j - 100.0) * s, 1.0, 1.0);
}

// The glyph's colour and texture place for its effect, and how far to move this vertex, in blocks of
// view space (a name tag faces the camera, so its x and y are the view's).
vec2 msOverhead(inout vec4 colour, inout vec2 uv) {
    if (ProjMat[2][3] == 0.0) {
        return vec2(0.0);
    }
    ivec3 c = ivec3(round(colour.rgb * 255.0));
    int kind = c.r >> 4;
    int scheme = c.r & 15;
    int data = (c.g << 8) | c.b;
    // a pattern colour, or -1 for the scheme's
    int pattern = -1;
    int effect = 0;
    float start = 0.0;
    if (kind == 13 && scheme >= 12) {
        int bits = ((scheme & 3) << 16) | data;
        pattern = bits >> 12;
        effect = ((bits >> 10) & 3) + 1;
        start = float(((bits >> 7) & 7) * 8);
    } else if (kind == 13) {
        effect = data >> 13;
        start = float((data >> 7) & 63);
    } else if (kind == 12) {
        int bits = (scheme << 16) | data;
        pattern = bits >> 14;
        start = float(((bits >> 11) & 7) * 8);
    } else if (kind == 14 && scheme <= 11) {
        start = float(((data >> 13) & 7) * 8);
    } else {
        return vec2(0.0);
    }
    if (pattern >= 36 || effect > 4) {
        return vec2(0.0);
    }
#ifdef MS_CLOCK
    float ticks = MS_CLOCK * 24000.0;
#else
    float ticks = 0.0;
#endif
    float cycle = ticks * 2.5;
    int corner = SLOT_VERTEX % 4;
    vec2 texel = 1.0 / vec2(textureSize(Sampler0, 0));
    vec2 offset = vec2(0.0);
    float age;
    if (kind == 13) {
        age = msAge(ticks, start);
        float i = float(data & 127);
        if (effect == 1) {
            // wave
            offset.y = trunc(sin(i / 2.0 + cycle / 5.0) * 5.0);
        } else if (effect == 2) {
            // wave2
            offset = vec2(trunc(sin(i / 5.0 + cycle / 5.0) * 5.0), trunc(sin(i / 3.0 + cycle / 5.0) * 5.0));
        } else if (effect == 3) {
            // shake, settling over the first second
            offset.y = trunc(sin(i / 1.5 + cycle) * max(7.0 - age / 8.0, 0.0));
        }
        offset *= MS_OSRS;
        if (effect == 4) {
            // slide: down into its line, and on out of it at the end, cut to the line
            float shift = (age < 25.0 ? age - 25.0 : (age > 125.0 ? age - 125.0 : 0.0)) * MS_OSRS;
            bool top = corner == 0 || corner == 3;
            float drawn = clamp(shift, top ? -1.0 : -MS_CELL - 1.0, top ? MS_CELL + 1.0 : 1.0);
            uv.y += (drawn - shift) * texel.y;
            offset.y = drawn;
        }
    } else {
        // scroll: the line passes right to left through a window over the head
        age = msAge(ticks, start);
        int left = kind == 12 ? (data >> 4) & 127 : (data >> 6) & 127;
        float x = float(left >= 64 ? left - 128 : left) * 4.0 + (corner >= 2 ? MS_CELL : 0.0);
        float span = kind == 12 ? float(data & 15) * 20.0 : float(data & 63) * 5.0;
        float shift = span * (1.0 - age / (MS_LIFE / 2.0));
        float drawn = clamp(x + shift, -MS_WINDOW, MS_WINDOW);
        uv.x += (drawn - x - shift) * texel.x;
        offset.x = drawn - x;
    }
    colour = vec4(pattern >= 0 ? MS_PATTERN[pattern] / 255.0 : msScheme(scheme, cycle, age), 1.0);
    return vec2(offset.x, -offset.y) * MS_BLOCKS;
}

void main() {
    vec4 msColor = Color;
    vec2 msUV = UV0;
    vec2 msOffset = msOverhead(msColor, msUV);"""
MAIN = "void main() {"
POSITION = "gl_Position = ProjMat * ModelViewMat * vec4(Position, 1.0);"
LIFT = """vec3 position = Position;
    int slotRow = slotText();
    if (slotRow >= 0) {
        // level with the slots' stack counts, in front of their items
        position.z += SLOT_LIFT;
        if (slotRow > 0) {
            position.y += SLOT_DROP + SLOT_ROW * float(slotRow - 1);
        }
    }
    vec4 view = ModelViewMat * vec4(position, 1.0);
    view.xy += msOffset;
    gl_Position = ProjMat * view;"""
# The game clock the overhead effects animate by: up to 1.21.4 a GameTime uniform the program json
# declares; from 26.2 (pack format 88) the Globals block, which the text pipelines bind from then on.
# 1.21.5 to 26.1 give text shaders neither (their pipelines, decompiled, bind no clock), and a
# Vulkan pipeline rejects a shader using a block it does not bind.
GLOBALS_CLOCK_FROM = 88
GAME_TIME = {"name": "GameTime", "type": "float", "count": 1, "values": [0.0]}

# --- armour ----------------------------------------------------------------------------------------
# Leather armour wears the looks in armour_looks.py: the armour sheets (build_armour.py) hold a tile
# per look, and the item's dye carries which in its low bits. Up to 1.21.1 armour has its own shader;
# from 1.21.2 it is the entity shader every entity draws with, which this leaves alone for any
# texture that is not an armour sheet.
ARMOUR_NAMES = ("rendertype_armor_cutout_no_cull", "entity")
TEXTURE = "texture(Sampler0, texCoord0)"
# Before 1.20.5 (pack format 32) entities are drawn in view space; IViewRotMat turns that back.
VIEW_ROT_BEFORE = 32
VIEW_ROT = {"name": "IViewRotMat", "type": "matrix3x3", "count": 9, "values": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]}

ARMOUR_VERTEX = """
// MineScape armour looks. An armour sheet is a grid of 256x128 tiles, its top right texel marked
// (255, 0, 255, alpha 1; green 128 for the leggings'). The dye's low three bits per channel say the
// look, 0b10 then its number; the tables give its tile and its shape: for leggings, flared at the
// foot as a plateskirt (1) or robe (2); for a chestplate, lengthened below the waist (MS_TORSO_*).
#ifdef VULKAN
#define MS_VERTEX gl_VertexIndex
#else
#define MS_VERTEX gl_VertexID
#endif
const vec2 MS_SHEET_TILE = vec2(256.0, 128.0);
// A player model pixel, in blocks.
const float MS_PIXEL = 0.9375 / 16.0;
%(tables)s
int msSheet() {
    ivec2 size = textureSize(Sampler0, 0);
    vec4 mark = texelFetch(Sampler0, ivec2(size.x - 1, 0), 0);
    if (mark.a > 0.0 && mark.a < 2.5 / 255.0 && mark.r > 0.99 && mark.b > 0.99) {
        return mark.g < 0.25 ? 1 : 2;
    }
    return 0;
}

// The frame a vertex is moved in: the world's and its up, or in a screen's entity view (an inventory's
// player, drawn with an orthographic projection) the screen's up, found from the matrices. hand is -1
// where that frame is mirrored, so cross(up, n) * hand is always the way u runs across a face seen
// from outside: the character's left on its front.
void msFrame(out mat3 toWorld, out vec3 up, out float hand) {
    if (ProjMat[2][3] == 0.0) {
        mat3 view = mat3(ModelViewMat);
        toWorld = mat3(1.0);
        up = normalize(inverse(view) * vec3(0.0, sign(ProjMat[1][1]), 0.0));
        hand = sign(determinant(view)) * sign(ProjMat[0][0]) * sign(ProjMat[1][1]);
        return;
    }
#ifdef MS_VIEW_ROT
    toWorld = IViewRotMat;
#else
    toWorld = mat3(1.0);
#endif
    up = vec3(0.0, 1.0, 0.0);
    hand = 1.0;
}

// Vanilla draws armour well clear of the body: the chestplate, its sleeves and the boots a pixel out,
// the leggings half a pixel. Every box's sides come in to MS_NARROW out (the body box's front and back
// too), close to the skin's outer layer and clear of each other. A side corner knows its face from u,
// and its edge from which corner it is: maxU for corners 0 and 3, and the box mirrored (the left arm
// and leg) when its first two corners are the lower ones. Top and bottom faces can't be told across
// from the frame alone when a limb swings, so they stay, and the sheets clear their rims instead.
const float MS_NARROW[3] = float[](0.0, 0.5, 0.35);
const float MS_VANILLA[3] = float[](0.0, 1.0, 0.5);

void msNarrow(int layer, inout vec3 position) {
    vec2 p = UV0 * vec2(64.0, 32.0);
    if (p.y < 19.5 || p.x > 56.5) {
        return;
    }
    int corner = MS_VERTEX %% 4;
    bool maxU = corner == 0 || corner == 3;
    float u = p.x + (maxU ? -0.5 : 0.5);
    // the legs' strip from u 0, the body's from 16, the arms' from 40
    float u0 = u < 16.0 ? 0.0 : (u < 40.0 ? 16.0 : 40.0);
    float w = u0 == 16.0 ? 8.0 : 4.0;
    float x = u - u0;
    mat3 toWorld;
    vec3 up;
    float hand;
    msFrame(toWorld, up, hand);
    vec3 n = normalize(toWorld * Normal);
    // v 20 is both the sides' top edge and the top and bottom faces' edge (u 4 to 4 + 2w)
    if (p.y < 20.5 && x > 4.0 && x < 4.0 + 2.0 * w && abs(dot(n, up)) > 0.7071) {
        return;
    }
    bool mirrored = (corner < 2) == (p.y > 26.0);
    bool side = x < 4.0 || (x > 4.0 + w && x < 8.0 + w);
    float pull = MS_VANILLA[layer] - MS_NARROW[layer];
    float deep = u0 == 16.0 ? pull : 0.0;
    vec3 across = cross(up, n) * hand;
    vec3 inward = length(across) > 0.1 ? normalize(across) * (mirrored ? -1.0 : 1.0) * (maxU ? -1.0 : 1.0) : vec3(0.0);
    vec3 move = side ? -n * pull + inward * deep : inward * pull - n * deep;
    position += transpose(toWorld) * (move * MS_PIXEL);
}

// Leggings worn as a skirt or robe: each leg box flares at its foot, out to its own side and a little
// in from the middle, so the two halves open in a V between the legs and swing with them. Only the
// lower ring of the sides moves (v 32 on the leg boxes, u 0-16); the art leaves the rest of a leg box
// clear below the hem. Outward is a side face's normal; on the front and back it is found from up,
// the legs swinging about an axis level with the ground. The left leg's box is mirrored, so its
// corners run bottom first: a lower corner among the first two is the left leg's.
const float MS_FLARE_OUT[4] = float[](0.0, 3.5, 2.5, 0.0);
const float MS_FLARE_IN[4] = float[](0.0, 1.0, 0.75, 0.0);

void msHang(int shape, inout vec3 position) {
    vec2 p = UV0 * vec2(64.0, 32.0);
    if (p.x > 16.0 || p.y < 31.0) {
        return;
    }
    int corner = MS_VERTEX %% 4;
    bool maxU = corner == 0 || corner == 3;
    bool left = corner < 2;
    // into the face the vertex is on, off the edge it shares with the next
    float u = p.x + (maxU ? -0.5 : 0.5);
    mat3 toWorld;
    vec3 up;
    float hand;
    msFrame(toWorld, up, hand);
    vec3 n = normalize(toWorld * Normal);
    vec3 outward;
    if (u < 4.0) {
        outward = n;
    } else if (u > 8.0 && u < 12.0) {
        outward = -n;
    } else {
        // the character's left, seen from the front face (u 4-8); its right from the back
        vec3 leftward = normalize(cross(up, n)) * hand * (u > 12.0 ? -1.0 : 1.0);
        outward = left ? leftward : -leftward;
    }
    // the outer edges sit at u 0, 4 and 16, the inner at 8 and 12
    bool outerEdge = p.x < 6.0 || p.x > 14.0;
    position += transpose(toWorld) * (outward * (outerEdge ? MS_FLARE_OUT[shape] : MS_FLARE_IN[shape]) * MS_PIXEL);
}

// The chestplate's body box lengthened below the waist and flared there, into a plate fauld (1),
// a jerkin (2) or a tunic (3): its lower ring moves, as the leggings' does. Its top stays, its top face's
// corners being the one part of the box with no side to tell them where to go; its bottom face, under
// the hem, hides. False for a vertex to hide.
const float MS_TORSO_DROP[4] = float[](0.0, 1.5, 2.0, 3.0);
const float MS_TORSO_FLARE[4] = float[](0.0, 0.25, 0.5, 0.75);

bool msTorso(int shape, inout vec3 position) {
    vec2 p = UV0 * vec2(64.0, 32.0);
    int corner = MS_VERTEX %% 4;
    bool maxU = corner == 0 || corner == 3;
    float u = p.x + (maxU ? -0.5 : 0.5);
    if (u < 16.0 || u > 40.0 || p.y < 16.0) {
        return true;
    }
    mat3 toWorld;
    vec3 up;
    float hand;
    msFrame(toWorld, up, hand);
    vec3 n = normalize(toWorld * Normal);
    if (dot(n, up) > 0.7) {
        return true;
    }
    if (dot(n, up) < -0.7) {
        return false;
    }
    if (corner < 2) {
        return true;
    }
    vec3 side = normalize(cross(up, n)) * hand;
    vec3 move = -up * MS_TORSO_DROP[shape] + (n + side * (maxU ? 1.0 : -1.0)) * MS_TORSO_FLARE[shape];
    position += transpose(toWorld) * (move * MS_PIXEL);
    return true;
}

void main() {
    vec4 msColor = Color;
    vec2 msUV = UV0;
    vec3 msPosition = Position;
    bool msShown = true;
    msTint = vec4(0.0);
    int msLayer = msSheet();
    if (msLayer != 0) {
        ivec3 c = ivec3(round(Color.rgb * 255.0));
        int data = ((c.r & 7) << 6) | ((c.g & 7) << 3) | (c.b & 7);
        int look = (data >> 7) == 2 ? (data & 127) : 0;
        int tile = msLayer == 1 ? MS_TILE_1[look] : MS_TILE_2[look];
        ivec2 grid = textureSize(Sampler0, 0) / ivec2(MS_SHEET_TILE);
        msUV = (UV0 + vec2(tile %% grid.x, tile / grid.x)) / vec2(grid);
        // the fragment shader dyes the look, all but what it marks to keep its own colour
        msTint = vec4(Color.rgb, 1.0);
        msColor = vec4(1.0, 1.0, 1.0, Color.a);
        msNarrow(msLayer, msPosition);
        if (msLayer == 2 && MS_SHAPE_2[look] != 0) {
            msHang(MS_SHAPE_2[look], msPosition);
        } else if (msLayer == 1 && MS_SHAPE_1[look] != 0) {
            msShown = msTorso(MS_SHAPE_1[look], msPosition);
        }
    }"""
ARMOUR_POSITION = """gl_Position = msShown ? ProjMat * ModelViewMat * vec4(msPosition, 1.0) : vec4(-2.0, -2.0, -2.0, 1.0);"""
ARMOUR_FRAGMENT = """
// MineScape armour looks: the vertex shader's dye, kept off texels marked in their alpha as their own
// colour (254) and lightened for (t) trims (253).
vec4 msArmour(vec4 texel) {
    if (msTint.a < 0.5 || texel.a < 0.1) {
        return texel;
    }
    int code = int(round(texel.a * 255.0));
    vec3 dye = code == 254 ? vec3(1.0) : (code == 253 ? mix(msTint.rgb, vec3(1.0), 0.55) : msTint.rgb);
    return vec4(texel.rgb * dye, 1.0);
}

"""


def varying_location(*sources):
    """The next free varying location, or None where varyings have none."""
    found = [int(n) for s in sources for n in re.findall(r"layout\s*\(\s*location\s*=\s*(\d+)\s*\)\s*(?:flat\s+)?(?:in|out)\s+(?!vec3 Position|vec4 Color|vec2 UV|ivec2 UV|vec3 Normal)", s)]
    return max(found) + 1 if found else None


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


def release_shader(version, names=NAMES, cache_suffix=""):
    """(pack format, {file name: text}) of a release's shader, the first of `names` it has; cached
    after the first read."""
    cached = os.path.join(CACHE, version + cache_suffix + ".json")
    if os.path.exists(cached):
        data = json.load(open(cached, encoding="utf-8"))
        return data["format"], data["files"]
    meta = json.loads(fetch(VERSIONS[version]))["downloads"]["client"]
    try:
        jar = zipfile.ZipFile(io.BufferedReader(RemoteFile(meta["url"], meta["size"]), RemoteFile.BLOCK))
    except IOError:
        jar = zipfile.ZipFile(io.BytesIO(fetch(meta["url"])))
    entries = set(jar.namelist())
    name = next(n for n in names if CORE + n + ".vsh" in entries)
    files = {}
    for ext in (".vsh", ".fsh", ".json"):
        if CORE + name + ext in entries:
            files[name + ext] = jar.read(CORE + name + ext).decode("utf-8")
    form = pack_format(jar.read("version.json"))
    os.makedirs(CACHE, exist_ok=True)
    json.dump({"format": form, "files": files}, open(cached, "w", encoding="utf-8"))
    return form, files


def patch(files, form):
    """The shader with the slot text lift and overhead effects, or None if its anchors are not there."""
    vsh_name = next(n for n in files if n.endswith(".vsh"))
    json_name = vsh_name[:-4] + ".json"
    vsh = files[vsh_name]
    if vsh.count(MAIN) != 1 or vsh.count(POSITION) != 1:
        return None
    patched = dict(files)
    head, body = vsh.split(MAIN, 1)
    # main reads the effect's colour and texture place instead of the vertex's own
    body = re.sub(r"\bColor\b", "msColor", body)
    body = re.sub(r"\bUV0\b", "msUV", body)
    clock = ""
    if json_name in files:
        program = json.loads(files[json_name])
        if not any(u["name"] == GAME_TIME["name"] for u in program.get("uniforms", [])):
            program.setdefault("uniforms", []).append(GAME_TIME)
        patched[json_name] = json.dumps(program, indent=4) + "\n"
        clock = "uniform float GameTime;\n#define MS_CLOCK GameTime\n\n"
    elif form >= GLOBALS_CLOCK_FROM:
        directive = "#include" if "#include" in vsh else "#moj_import"
        include = "" if "globals.glsl" in vsh else directive + " <minecraft:globals.glsl>\n"
        clock = include + "#define MS_CLOCK GameTime\n\n"
    patched[vsh_name] = head + clock + FUNCTIONS + body.replace(POSITION, LIFT, 1)
    return patched


def patch_armour(files, form):
    """The armour shader with the looks, or None if its anchors are not there."""
    vsh_name = next(n for n in files if n.endswith(".vsh"))
    fsh_name = vsh_name[:-4] + ".fsh"
    json_name = vsh_name[:-4] + ".json"
    vsh, fsh = files[vsh_name], files.get(fsh_name, "")
    if vsh.count(MAIN) != 1 or vsh.count(POSITION) != 1 or fsh.count(MAIN) != 1 or fsh.count(TEXTURE) != 1:
        return None
    sys.path.insert(0, os.path.dirname(__file__))
    import armour_looks
    patched = dict(files)
    location = varying_location(vsh, fsh)
    layout = "" if location is None else "layout(location = %d) " % location
    declarations = layout + "out vec4 msTint;\n"
    if not re.search(r"uniform\s+sampler2D\s+Sampler0\s*;", vsh):
        declarations += "uniform sampler2D Sampler0;\n"
    if form < VIEW_ROT_BEFORE and json_name in files:
        program = json.loads(files[json_name])
        if not any(u["name"] == VIEW_ROT["name"] for u in program.get("uniforms", [])):
            program.setdefault("uniforms", []).append(VIEW_ROT)
        patched[json_name] = json.dumps(program, indent=4) + "\n"
        declarations += "uniform mat3 IViewRotMat;\n#define MS_VIEW_ROT\n"
    head, body = vsh.split(MAIN, 1)
    body = re.sub(r"\bColor\b", "msColor", body)
    body = re.sub(r"\bUV0\b", "msUV", body)
    body = body.replace(POSITION, ARMOUR_POSITION, 1)
    patched[vsh_name] = head + declarations + ARMOUR_VERTEX % {"tables": armour_looks.glsl()} + body
    head, body = fsh.split(MAIN, 1)
    patched[fsh_name] = (head + layout + "in vec4 msTint;\n" + ARMOUR_FRAGMENT + MAIN
                         + body.replace(TEXTURE, "msArmour(" + TEXTURE + ")", 1))
    return patched


TARGETS = [
    # (name, shader names, the files besides the vertex shader, patch, overlay directory prefix)
    ("text", NAMES, (".fsh", ".json"), patch, "shader_"),
    ("armour", ARMOUR_NAMES, (".fsh", ".json"), patch_armour, "shader_armour_"),
]


def write(files, directory, names):
    if os.path.exists(directory):
        for old in os.listdir(directory):
            if old.split(".")[0] in names:
                os.remove(os.path.join(directory, old))
    os.makedirs(directory, exist_ok=True)
    for name, text in files.items():
        open(os.path.join(directory, name), "w", encoding="utf-8", newline="\n").write(text)


# The slot font's rows, set in the title's line for the layered GUI from 1.21.6 (pack format 63).
LAYERED_GUI_FROM = 63
SLOT_OVERLAY = "shader_slot_layers"
GUI_FONT = "assets/gui/font/default.json"
SLOT_FONTS = ("slot", "slot_box")
# The base font's first row's ascent, each row 18 under the last; and the ascent that sets a glyph
# in the title's line (the label's 6 pixels down to 14, clear of the first row's items at 18).
SLOT_FIRST_ASCENT, SLOT_ROW_HEIGHT, SLOT_TITLE_ASCENT = -14, 18, 7


def slot_layers(last_format):
    """The overlay that sets slot text in the title's line, each row's glyphs from its own copy of the
    font texture (build_slot_rows.py), its markers' green the row from 1. None if the font has no slot
    rows."""
    font = json.load(open(os.path.join(ROOT, GUI_FONT), encoding="utf-8"))
    found = False
    for provider in font["providers"]:
        name = provider.get("file", "").removeprefix("minecraft:font/").removesuffix(".png")
        if name not in SLOT_FONTS:
            continue
        row = (SLOT_FIRST_ASCENT - provider["ascent"]) // SLOT_ROW_HEIGHT
        texture = "%s_row%d" % (name, row)
        if not os.path.exists(os.path.join(ROOT, "assets", "minecraft", "textures", "font", texture + ".png")):
            print("WARNING: no %s.png - run build_slot_rows.py; slot text stays behind items from 1.21.6" % texture)
            return None
        provider["file"] = "minecraft:font/%s.png" % texture
        provider["ascent"] = SLOT_TITLE_ASCENT
        found = True
    if not found:
        return None
    path = os.path.join(ROOT, SLOT_OVERLAY, GUI_FONT)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8", newline="\n").write(json.dumps(font, indent=2, ensure_ascii=False) + "\n")
    print("overlay %s: slot text in the title's line, formats %d-%d" % (SLOT_OVERLAY, LAYERED_GUI_FROM, last_format))
    return {"formats": {"min_inclusive": LAYERED_GUI_FROM, "max_inclusive": last_format},
            "min_format": LAYERED_GUI_FROM, "max_format": last_format, "directory": SLOT_OVERLAY}


def main():
    global VERSIONS
    no_base = "--no-base" in sys.argv[1:]
    manifest = json.loads(fetch(MANIFEST))
    releases = [v for v in manifest["versions"] if v["type"] == "release"]
    releases.reverse()
    ids = [v["id"] for v in releases]
    VERSIONS = {v["id"]: v["url"] for v in releases}
    releases = ids[ids.index(FIRST):]

    for path in os.listdir(ROOT):
        if path.startswith("shader_") and os.path.isdir(os.path.join(ROOT, path)):
            shutil.rmtree(os.path.join(ROOT, path))

    base = os.path.join(ROOT, CORE)
    entries = []
    for target, names, _, patcher, prefix in TARGETS:
        suffix = "" if target == "text" else "." + target
        # Consecutive releases with the same shader, each run one group.
        groups = []
        for version in releases:
            form, files = release_shader(version, names, suffix)
            digest = hashlib.sha1(json.dumps(files, sort_keys=True).encode()).hexdigest()
            if groups and groups[-1]["digest"] == digest:
                groups[-1]["last"] = form
            else:
                groups.append({"digest": digest, "first_version": version, "first": form, "last": form, "files": files})
        # A group runs up to the next one's format, covering the snapshots between releases.
        for group, following in zip(groups, groups[1:]):
            group["last"] = max(group["last"], following["first"] - 1)

        for i, group in enumerate(groups):
            patched = patcher(group["files"], group["first"])
            span = "%s %s, formats %d-%d" % (target, group["first_version"], group["first"], group["last"])
            if patched is None:
                print("WARNING: nothing for %s - its shader no longer has the anchor lines" % span)
                continue
            if i == 0 and not no_base:
                write(patched, base, names)
                print("base folder:", span)
                continue
            directory = prefix + group["first_version"].replace(".", "_")
            write(patched, os.path.join(ROOT, directory, CORE), names)
            # formats for clients before 1.21.9, min/max_format for those after; both, as the list spans both
            entries.append({"formats": {"min_inclusive": group["first"], "max_inclusive": group["last"]},
                            "min_format": group["first"], "max_format": group["last"], "directory": directory})
            print("overlay %s: %s" % (directory, span))
        if no_base:
            write({}, base, names)

    slot_entry = slot_layers(max(e["max_format"] for e in entries))
    if slot_entry:
        entries.append(slot_entry)

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
