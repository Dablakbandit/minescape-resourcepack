// MineScape's animated mobs (.github/scripts/build_mobs.py, mobs/animated.json): a mob is an item on an
// armour stand's head whose texture is a sprite carrying its animations, S x S (256, 512 or 1024), wherever the
// atlas put it: the faces from the top, the 2 x 2 block at each of a face's corners saying in its low bits which face
// it is, how big the sprite is and where in it that corner sits; a header in the bottom row (the magic at both ends,
// where the clips and keyframes start, the bone count, the head display's scale); the records up from it. Each vertex
// finds the sprite from its own uv, works out how the model was turned and scaled where it is drawn, and poses its
// bone as the clip the item's dye names has it at this tick. Anything else drawn with these shaders has no magic where
// its corners say and is left as it is.
//
// How the model was turned: where the program can share a quad's corners (subgroup shuffles), from two edges of the
// face at rest and as drawn. Where it can't (26.3: its OpenGL backend can't take shuffles), a mob stands upright and
// only turns about the vertical, so its turn is the one that takes the face's rest normal to the drawn one and the
// model's up to the world's; 26.3's models are drawn with every cube tilted (build_mobs.py's TILT) so that no face
// points straight up or down, and each vertex is put back where the untilted model, posed, has it.

const int MARK = 254;
const ivec3 MAGIC = ivec3(77, 66, 51);
const int FACE_TEXELS = 20;
const int KEY_TEXELS = 5;
const int LOOP = 1;
const int ONCE = 2;
const int NO_CLIP = 31;
// how far in from its face's edges a mob's uv sits, in texels, and how far off that a vertex may be (some versions
// pull a model's uvs a little towards each face's middle)
const float INSET = 0.125;
const float INSET_SLACK = 0.05;
// an armour stand draws its head item at 0.625 of a block per 16 units, times the head display's scale
const float HEAD_ITEM = 0.625 / 16.0;

ivec4 texel(ivec2 p) {
    return ivec4(round(stitch_texel_fetch(p) * 255.0));
}

bool magic(ivec2 p) {
    ivec4 t = texel(p);
    return t.rgb == MAGIC && t.a == MARK;
}

ivec4 record(ivec2 origin, int size, int i) {
    return texel(origin + ivec2(i % size, size - 2 - i / size));
}

int number(ivec4 t) {
    return (t.r << 16) | (t.g << 8) | t.b;
}

// The face a vertex is a corner of, from its own uv: an eighth of a texel in from its face's edges, so its texel is
// the face's corner texel and the side of it the uv sits says which corner. The 2 x 2 block in from that corner holds
// in the low 3 bits of its red, green and blue (9 bits each: the corner's own, the one beside it, the one under or
// over it, the one across) the face's number (12 bits), the sprite's size (2) and the corner texel's own place in the
// sprite (10 across, 10 down); with that the sprite's top left in the atlas. False where it isn't a mob's.
bool faceAt(vec2 uv, ivec2 atlas, out int face, out int size, out ivec2 origin, out ivec2 local) {
    face = 0;
    size = 0;
    origin = ivec2(0);
    local = ivec2(0);
    vec2 t = uv * vec2(atlas);
    vec2 f = fract(t);
    vec2 in_by = min(f, 1.0 - f);
    if (any(greaterThan(abs(in_by - INSET), vec2(INSET_SLACK)))) {
        return false;
    }
    ivec2 p = ivec2(floor(t));
    ivec2 d = ivec2(f.x > 0.5 ? -1 : 1, f.y > 0.5 ? -1 : 1);
    if (any(lessThan(p, ivec2(1))) || any(greaterThanEqual(p, atlas - 1))) {
        return false;
    }
    ivec2 at[4] = ivec2[](p, p + ivec2(d.x, 0), p + ivec2(0, d.y), p + d);
    int bits[4];
    for (int k = 0; k < 4; k++) {
        ivec4 c = texel(at[k]);
        bits[k] = (c.r & 7) | ((c.g & 7) << 3) | ((c.b & 7) << 6);
    }
    int low = bits[0] | (bits[1] << 9) | (bits[2] << 18);
    face = low & 4095;
    int sizeCode = (low >> 12) & 3;
    size = 256 << sizeCode;
    local = ivec2((low >> 14) & 1023, ((low >> 24) | (bits[3] << 3)) & 1023);
    origin = p - local;
    return sizeCode < 3 && all(greaterThanEqual(origin, ivec2(0))) && all(lessThanEqual(origin + size, atlas))
        && magic(origin + ivec2(0, size - 1)) && magic(origin + ivec2(size - 1));
}

// Which of the face's uv rect corners (min-min, max-min, max-max, min-max) is nearest a place in the sprite.
int cornerOf(ivec2 origin, int size, int face, ivec2 local) {
    int at = face * FACE_TEXELS;
    ivec4 t1 = record(origin, size, at + 1);
    ivec4 t2 = record(origin, size, at + 2);
    ivec4 t3 = record(origin, size, at + 3);
    int u0 = t1.r * 256 + t1.g;
    int v0 = t1.b * 256 + t2.r;
    int u1 = t2.g * 256 + t2.b;
    int v1 = t3.r * 256 + t3.g;
    bool right = abs(local.x - u1) < abs(local.x - u0);
    bool bottom = abs(local.y - v1) < abs(local.y - v0);
    return bottom ? (right ? 2 : 3) : (right ? 1 : 0);
}

// Where the model rests at one of the face's uv rect corners; tilted, where 26.3's tilted model draws it.
vec3 restAt(ivec2 origin, int size, int face, int k, bool tilted) {
    int at = face * FACE_TEXELS + (tilted ? 12 : 4) + 2 * k;
    ivec4 a = record(origin, size, at);
    ivec4 b = record(origin, size, at + 1);
    return vec3(a.r * 256 + a.g, a.b * 256 + b.r, b.g * 256 + b.b) / 512.0 - 32.0;
}

vec4 keyRotation(ivec2 origin, int size, int at) {
    ivec4 a = record(origin, size, at);
    ivec4 b = record(origin, size, at + 1);
    vec4 q = vec4(a.r * 16 + (a.g >> 4), (a.g & 15) * 256 + a.b, b.r * 16 + (b.g >> 4), (b.g & 15) * 256 + b.b);
    return q / 4095.0 * 2.0 - 1.0;
}

vec3 keyOffset(ivec2 origin, int size, int at) {
    ivec4 a = record(origin, size, at + 2);
    ivec4 b = record(origin, size, at + 3);
    return vec3(a.r * 256 + a.g, a.b * 256 + b.r, b.g * 256 + b.b) / 512.0 - 64.0;
}

float keyScale(ivec2 origin, int size, int at) {
    ivec4 a = record(origin, size, at + 4);
    return float(a.r * 256 + a.g) / 16384.0;
}

// Whether a clip moves the model at this time: not the resting pose, nor a once-clip that has ended.
bool posing(ivec2 origin, int size, int clips, int clip, float ticks) {
    if (clip == 0 || clip == NO_CLIP) {
        return false;
    }
    int frames = record(origin, size, clips + 2 * clip).b;
    int end = record(origin, size, clips + 2 * clip + 1).r;
    return frames > 0 && !(end == ONCE && ticks >= float(frames - 1));
}

// A bone's transform in a clip, ticks into it (a looping clip plays on the game's clock instead): rotation,
// offset and scale; the resting pose's where the clip is 0 or a once-clip has ended.
void pose(ivec2 origin, int size, int clips, int keys, int bones, int bone, int clip, float ticks, float now,
          out vec4 q, out vec3 offset, out float grow) {
    q = vec4(0.0, 0.0, 0.0, 1.0);
    offset = vec3(0.0);
    grow = 1.0;
    if (!posing(origin, size, clips, clip, ticks)) {
        return;
    }
    ivec4 c0 = record(origin, size, clips + 2 * clip);
    int first = c0.r * 256 + c0.g;
    int frames = c0.b;
    int end = record(origin, size, clips + 2 * clip + 1).r;
    float f = end == LOOP ? mod(now, float(frames)) : min(ticks, float(frames - 1));
    int f0 = int(floor(f));
    int f1 = end == LOOP ? (f0 + 1) % frames : min(f0 + 1, frames - 1);
    float k = f - float(f0);
    int k0 = keys + ((first + f0) * bones + bone) * KEY_TEXELS;
    int k1 = keys + ((first + f1) * bones + bone) * KEY_TEXELS;
    vec4 q0 = keyRotation(origin, size, k0);
    vec4 q1 = keyRotation(origin, size, k1);
    q = normalize(mix(q0, dot(q0, q1) < 0.0 ? -q1 : q1, k));
    offset = mix(keyOffset(origin, size, k0), keyOffset(origin, size, k1), k);
    grow = mix(keyScale(origin, size, k0), keyScale(origin, size, k1), k);
}

vec3 rotate(vec4 q, vec3 v) {
    return v + 2.0 * cross(q.xyz, cross(q.xyz, v) + q.w * v);
}

// An orthonormal frame from two edges of a face.
mat3 frame(vec3 a, vec3 b) {
    vec3 x = normalize(a);
    vec3 y = normalize(b - x * dot(x, b));
    return mat3(x, y, cross(x, y));
}

void stitch_vertex(inout StitchVertex v) {
#ifdef STITCH_HAS_QUAD_CORNERS
    vec3 corners[4];
    vec2 uvs[4];
    // every vertex shares its corners, whatever it is (the lanes beside it may be a mob's)
    bool quad = stitch_quad_corners(corners, uvs);
#endif
    ivec2 atlas = stitch_texture_size();
    int face;
    int size;
    ivec2 origin;
    ivec2 local;
    if (!faceAt(v.uv, atlas, face, size, origin, local)) {
        return;
    }
    // the dye: the clip (5 bits), the clip before it (5, 31 for none to fade from), how many ticks into that one
    // it was when this one started (6), and the tick this one started (the game time mod 240)
    ivec3 dye = ivec3(round(v.color.rgb * 255.0));
    int value = (dye.r << 16) | (dye.g << 8) | dye.b;
    // the dye is data, not a tint
    v.color = vec4(1.0, 1.0, 1.0, v.color.a);
    int clip = value >> 19;
    int before = (value >> 14) & 31;
    int beforeAt = (value >> 8) & 63;
    int header = size - 1;
    int clips = number(texel(origin + ivec2(1, header)));
    int keys = number(texel(origin + ivec2(2, header)));
    int bones = texel(origin + ivec2(3, header)).r;
    // a clip the model hasn't got is its rest (an undyed head's leather colour reads as one)
    int count = (keys - clips) / 2 - 1;
    if (clip > count) {
        clip = 0;
    }
    if (before > count) {
        before = NO_CLIP;
    }
    float now = stitch_game_time * 24000.0;
    float since = mod(now - float(value & 255), 240.0);
    int blend = clip == NO_CLIP ? 0 : record(origin, size, clips + 2 * clip + 1).g;
    bool fading = before != NO_CLIP && float(blend) > since;
    bool moving = fading || posing(origin, size, clips, clip, since);
    int at = face * FACE_TEXELS;
    int k = cornerOf(origin, size, face, local);
    vec3 rest = restAt(origin, size, face, k, false);
    mat3 turn;
    float scale;
    vec3 here;
    vec3 restNormal;
#ifdef STITCH_HAS_QUAD_CORNERS
    // the turn and scale from two edges of this face at rest and as drawn, each corner's rest found by its own uv
    if (!moving || !quad) {
        // at rest, or no corners to measure from (a device without subgroup shuffles): it stands still
        return;
    }
    vec3 r[4];
    for (int i = 0; i < 4; i++) {
        r[i] = restAt(origin, size, face, cornerOf(origin, size, face, ivec2(round(uvs[i] * vec2(atlas))) - origin), false);
    }
    vec3 r1 = r[1] - r[0];
    vec3 r3 = r[3] - r[0];
    vec3 e1 = corners[1] - corners[0];
    vec3 e3 = corners[3] - corners[0];
    scale = length(e1) / length(r1);
    turn = frame(e1, e3) * transpose(frame(r1, r3));
    here = rest;
    restNormal = transpose(turn) * v.normal;
#elif defined(STITCH_HAS_ORIENTATION)
    // upright, turned about the vertical: the turn that takes the tilted face's rest normal to its drawn one and the
    // model's up to the world's, at the head display's scale; always, to untilt it
    vec3 t[4];
    vec3 u[4];
    for (int i = 0; i < 4; i++) {
        t[i] = restAt(origin, size, face, i, true);
        u[i] = restAt(origin, size, face, i, false);
    }
    float sgn = (record(origin, size, at).g & 1) != 0 ? -1.0 : 1.0;
    // Minecraft gives a face the normal of the axis nearest its own, which the tilt keeps level
    vec3 n = sgn * cross(t[1] - t[0], t[3] - t[0]);
    vec3 a = abs(n);
    vec3 snapped = a.x >= a.z && a.x >= a.y ? vec3(sign(n.x), 0.0, 0.0) : a.z >= a.y ? vec3(0.0, 0.0, sign(n.z)) : vec3(0.0, sign(n.y), 0.0);
    turn = frame(normalize(v.normal), stitch_up()) * transpose(frame(snapped, vec3(0.0, 1.0, 0.0)));
    scale = HEAD_ITEM * float(number(texel(origin + ivec2(4, header)))) / 4096.0;
    here = t[k];
    restNormal = sgn * normalize(cross(u[1] - u[0], u[3] - u[0]));
#else
    return;
#endif

    int bone = record(origin, size, at).r;
    vec4 q;
    vec3 offset;
    float grow;
    pose(origin, size, clips, keys, bones, bone, clip, since, now, q, offset, grow);
    if (fading) {
        // the clip before goes on from where it was, fading into this one
        vec4 qb;
        vec3 ob;
        float gb;
        pose(origin, size, clips, keys, bones, bone, before, float(beforeAt) + since, now, qb, ob, gb);
        float w = smoothstep(0.0, 1.0, since / float(blend));
        q = normalize(mix(qb, dot(qb, q) < 0.0 ? -q : q, w));
        offset = mix(ob, offset, w);
        grow = mix(gb, grow, w);
    }
    vec3 posed = grow * rotate(q, rest) + offset;
    v.position += scale * (turn * (posed - here));
    v.normal = turn * rotate(q, restNormal);
}
