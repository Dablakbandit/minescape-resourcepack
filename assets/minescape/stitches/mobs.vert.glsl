// MineScape's animated mobs (.github/scripts/build_mobs.py, mobs/animated.json): a mob is an item on an
// armour stand's head whose texture is a sprite carrying its animations, S x S (256, 512 or 1024), wherever the
// atlas put it: the faces from the top, each saying in the low bits of its corner texels which it is, how big the
// sprite is and where in it the face sits; a header in the bottom row (the magic at both ends, where the clips and
// keyframes start, the bone count); the records up from it. Each vertex finds its quad's corners, and from them
// the sprite, works out how the model was turned and scaled where it is drawn, and poses its bone as the clip the
// item's dye names has it at this tick. Anything else drawn with these shaders has no magic where its corners say
// and is left as it is.

const int MARK = 254;
const ivec3 MAGIC = ivec3(77, 66, 51);
const int FACE_TEXELS = 12;
const int KEY_TEXELS = 5;
const int LOOP = 1;
const int ONCE = 2;
const int NO_CLIP = 31;

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

// The quad's face from the low 3 bits of the red, green and blue of its four corner texels (top left, top right,
// bottom right, bottom left; 9 bits each, the first's lowest): its number (12 bits), the sprite's size (2) and
// its own top left in the sprite (10 across, 10 down); with that the sprite's own top left in the atlas. False
// where its sprite has no magic: not a mob's.
bool faceOf(vec2 uvs[4], ivec2 atlas, out int face, out int size, out ivec2 origin) {
    ivec2 lo = ivec2(1 << 20);
    ivec2 hi = ivec2(-(1 << 20));
    for (int i = 0; i < 4; i++) {
        ivec2 c = ivec2(round(uvs[i] * vec2(atlas)));
        lo = min(lo, c);
        hi = max(hi, c);
    }
    face = 0;
    size = 0;
    origin = ivec2(0);
    if (any(lessThan(hi - lo, ivec2(2))) || any(lessThan(lo, ivec2(0))) || any(greaterThan(hi, atlas))) {
        return false;
    }
    ivec2 corner[4] = ivec2[](lo, ivec2(hi.x - 1, lo.y), hi - 1, ivec2(lo.x, hi.y - 1));
    int bits[4];
    for (int k = 0; k < 4; k++) {
        ivec4 t = texel(corner[k]);
        bits[k] = (t.r & 7) | ((t.g & 7) << 3) | ((t.b & 7) << 6);
    }
    int low = bits[0] | (bits[1] << 9) | (bits[2] << 18);
    face = low & 4095;
    int sizeCode = (low >> 12) & 3;
    size = 256 << sizeCode;
    origin = lo - ivec2((low >> 14) & 1023, ((low >> 24) | (bits[3] << 3)) & 1023);
    return sizeCode < 3 && all(greaterThanEqual(origin, ivec2(0))) && all(lessThanEqual(origin + size, atlas))
        && magic(origin + ivec2(0, size - 1)) && magic(origin + ivec2(size - 1));
}

// Where the model rests at the face's uv rect corner nearest this one.
vec3 restCorner(ivec2 origin, int size, int face, ivec2 local) {
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
    int k = bottom ? (right ? 2 : 3) : (right ? 1 : 0);
    ivec4 a = record(origin, size, at + 4 + 2 * k);
    ivec4 b = record(origin, size, at + 5 + 2 * k);
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
    vec3 corners[4];
    vec2 uvs[4];
    // every vertex shares its corners, whatever it is (the lanes beside it may be a mob's)
    bool quad = stitch_quad_corners(corners, uvs);

    ivec2 atlas = stitch_texture_size();
    int face;
    int size;
    ivec2 origin;
    if (!quad || !faceOf(uvs, atlas, face, size, origin)) {
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
    if (!fading && !posing(origin, size, clips, clip, since)) {
        return;
    }
    // the model's turn and scale where it was drawn, from two edges of this face at rest and as drawn
    vec3 rest[4];
    for (int i = 0; i < 4; i++) {
        rest[i] = restCorner(origin, size, face, ivec2(round(uvs[i] * vec2(atlas))) - origin);
    }
    vec3 r1 = rest[1] - rest[0];
    vec3 r3 = rest[3] - rest[0];
    vec3 e1 = corners[1] - corners[0];
    vec3 e3 = corners[3] - corners[0];
    float scale = length(e1) / length(r1);
    mat3 turn = frame(e1, e3) * transpose(frame(r1, r3));

    int bone = record(origin, size, face * FACE_TEXELS).r;
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

    int corner = v.corner;
    if (corner < 0) {
        return;
    }
    vec3 here = rest[corner];
    vec3 posed = grow * rotate(q, here) + offset;
    v.position += scale * (turn * (posed - here));
    v.normal = turn * rotate(q, transpose(turn) * v.normal);
}
