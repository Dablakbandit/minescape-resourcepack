// MineScape's minimap (MinimapInfo in the plugin): invisible item frames near the player hold maps whose top row
// starts with these four colours, and wherever they are in the world this draws them in a corner of the screen,
// turned with the camera. Maps are their own 128 x 128 texture, whose corners are the quad's uvs. There are three
// (PlayerMinimap's layers), each drawn a little in front of the one before: the ground and the ring, OSRS's icons,
// then the dots, the hint arrow and the player, so the dots stay over the icons. Stitch weaves it into Minecraft's
// text shader for every release, and into a shader pack's text programs with the Stitch mod; in a shadow pass,
// which has no screen, the maps are left out.
// The colours are the map palette's fire and ice in two brightnesses, nothing a drawn map has in a row; the
// third's red says which layer: the ground, the icons or the dots.
const ivec3 MS_MINIMAP_MARK[4] = ivec3[](ivec3(255, 0, 0), ivec3(160, 160, 255), ivec3(180, 0, 0), ivec3(84, 84, 135));
const int MS_MINIMAP_LAYER[3] = int[](180, 220, 135);
// Half the map's height on screen, as a player chooses it, and its gap from the corner, in clip space
// (half the screen is 1), and how far past the map's own 64 pixels the frame round it reaches.
const float MS_MINIMAP_SIZE = 0.3;
const float MS_MINIMAP_SMALL = 0.2;
const float MS_MINIMAP_LARGE = 0.4;
const float MS_MINIMAP_EXTRA_LARGE = 0.5;
const float MS_MINIMAP_GAP = 0.03;
const float MS_MINIMAP_REACH = 66.0 / 64.0;
// The pixel after the marks is this colour when the map is to stay with north up.
const ivec3 MS_MINIMAP_NORTH_UP = ivec3(135, 0, 0);
// The pixel after that says which corner of the screen it goes in, if not the top right.
const ivec3 MS_MINIMAP_TOP_LEFT = ivec3(180, 0, 0);
const ivec3 MS_MINIMAP_BOTTOM_LEFT = ivec3(220, 0, 0);
const ivec3 MS_MINIMAP_BOTTOM_RIGHT = ivec3(255, 0, 0);
// Or that it goes along the bottom beside the hotbar, half of which is 91 GUI pixels wide, this many from it.
const ivec3 MS_MINIMAP_LEFT_OF_HOTBAR = ivec3(135, 0, 0);
const ivec3 MS_MINIMAP_RIGHT_OF_HOTBAR = ivec3(112, 112, 180);
const float MS_MINIMAP_HOTBAR = 91.0;
const float MS_MINIMAP_HOTBAR_GAP = 2.0;
// And the pixel after that its size, if not the usual one, in the same three colours.
const ivec3 MS_MINIMAP_CHOSE_SMALL = ivec3(180, 0, 0);
const ivec3 MS_MINIMAP_CHOSE_LARGE = ivec3(220, 0, 0);
const ivec3 MS_MINIMAP_CHOSE_EXTRA_LARGE = ivec3(255, 0, 0);
// Then how far it's moved right, and then up, in GUI pixels: each 128 more, in four base 4 digits, the
// first the largest, a digit being the fire colour of its brightness (these reds, 0 to 3). An older
// server sends none, which is not moved.
const int MS_MINIMAP_OFFSET_X = 7;
const int MS_MINIMAP_OFFSET_Y = 11;
const int MS_MINIMAP_DIGIT[4] = int[](180, 220, 255, 135);

// Which of the minimap's maps this is, or -1 for none.
int msMinimapLayer() {
    if (stitch_texture_size() != ivec2(128)) {
        return -1;
    }
    for (int i = 0; i < 4; i++) {
        if (i != 2 && ivec3(round(stitch_texel_fetch(ivec2(i, 0)).rgb * 255.0)) != MS_MINIMAP_MARK[i]) {
            return -1;
        }
    }
    ivec3 third = ivec3(round(stitch_texel_fetch(ivec2(2, 0)).rgb * 255.0));
    for (int layer = 0; layer < 3; layer++) {
        if (third == ivec3(MS_MINIMAP_LAYER[layer], 0, 0)) {
            return layer;
        }
    }
    return -1;
}

#if defined(STITCH_HAS_SCREEN_POSITION) && defined(STITCH_HAS_VIEW_ROTATION)
// Which way the camera faces, for the map to be turned by. The frame stays still on the screen.
float msMinimapYaw() {
    vec3 right = transpose(stitch_view_rotation()) * vec3(1.0, 0.0, 0.0);
    return atan(right.z, right.x);
}

// What the fragment shader is told besides where it is: the yaw, moved up by 8 to turn with the camera
// and by 24 to stay with north up, so that it is never 0, which is what everything else has.
float msMinimapTurn() {
    bool northUp = ivec3(round(stitch_texel_fetch(ivec2(4, 0)).rgb * 255.0)) == MS_MINIMAP_NORTH_UP;
    return (northUp ? 24.0 : 8.0) + msMinimapYaw();
}

vec2 msMinimapCorner() {
    ivec3 chosen = ivec3(round(stitch_texel_fetch(ivec2(5, 0)).rgb * 255.0));
    return vec2(chosen == MS_MINIMAP_TOP_LEFT || chosen == MS_MINIMAP_BOTTOM_LEFT ? -1.0 : 1.0, chosen == MS_MINIMAP_BOTTOM_LEFT || chosen == MS_MINIMAP_BOTTOM_RIGHT ? -1.0 : 1.0);
}

float msMinimapSize() {
    ivec3 chosen = ivec3(round(stitch_texel_fetch(ivec2(6, 0)).rgb * 255.0));
    return chosen == MS_MINIMAP_CHOSE_SMALL ? MS_MINIMAP_SMALL : chosen == MS_MINIMAP_CHOSE_LARGE ? MS_MINIMAP_LARGE : chosen == MS_MINIMAP_CHOSE_EXTRA_LARGE ? MS_MINIMAP_EXTRA_LARGE : MS_MINIMAP_SIZE;
}

float msMinimapOffset(int from) {
    int value = 0;
    for (int i = 0; i < 4; i++) {
        vec4 texel = stitch_texel_fetch(ivec2(from + i, 0));
        int red = int(round(texel.r * 255.0));
        int digit = red == MS_MINIMAP_DIGIT[0] ? 0 : red == MS_MINIMAP_DIGIT[1] ? 1 : red == MS_MINIMAP_DIGIT[2] ? 2 : red == MS_MINIMAP_DIGIT[3] ? 3 : -1;
        if (digit < 0 || texel.a < 0.5 || texel.g > 0.0) {
            return 0.0;
        }
        value = value * 4 + digit;
    }
    return float(value - 128);
}

// Where on the screen a corner of the map goes, sized by the screen's height. GUI pixels are the screen's at
// Minecraft's automatic GUI scale, which is all a shader can work out, from the screen's size in pixels.
vec2 msMinimapPosition(vec2 corner) {
    float half_size = msMinimapSize() * MS_MINIMAP_REACH;
    float shape = stitch_screen_size.y / stitch_screen_size.x;
    vec2 screen = stitch_screen_size;
    float gui = max(1.0, min(floor(screen.x / 320.0), floor(screen.y / 240.0)));
    vec2 pixel = 2.0 * gui / screen;
    ivec3 chosen = ivec3(round(stitch_texel_fetch(ivec2(5, 0)).rgb * 255.0));
    vec2 centre;
    if (chosen == MS_MINIMAP_LEFT_OF_HOTBAR || chosen == MS_MINIMAP_RIGHT_OF_HOTBAR) {
        float side = chosen == MS_MINIMAP_LEFT_OF_HOTBAR ? -1.0 : 1.0;
        centre = vec2(side * ((MS_MINIMAP_HOTBAR + MS_MINIMAP_HOTBAR_GAP) * pixel.x + half_size * shape), -1.0 + half_size + MS_MINIMAP_GAP);
    } else {
        centre = msMinimapCorner() * vec2(1.0 - (half_size + MS_MINIMAP_GAP) * shape, 1.0 - half_size - MS_MINIMAP_GAP);
    }
    centre += vec2(msMinimapOffset(MS_MINIMAP_OFFSET_X), msMinimapOffset(MS_MINIMAP_OFFSET_Y)) * pixel;
    return centre + vec2(corner.x, -corner.y) * 2.0 * half_size * vec2(shape, 1.0);
}
#endif

void stitch_vertex(inout StitchVertex v) {
    msMinimap = vec3(0.0);
    int msLayer = msMinimapLayer();
    if (msLayer < 0) {
        return;
    }
#if defined(STITCH_HAS_SCREEN_POSITION) && defined(STITCH_HAS_VIEW_ROTATION)
    vec2 msCorner = v.uv - 0.5;
    msMinimap = vec3(msCorner * 132.0, msMinimapTurn() + 32.0 * float(msLayer));
    stitch_set_screen_position(msMinimapPosition(msCorner), float(msLayer));
    // fully lit under a shader pack, whatever is round the frames (Minecraft's own shader draws it unlit)
    v.color = vec4(1.0);
    v.light = ivec2(240);
#else
    v.hidden = true;
#endif
}
