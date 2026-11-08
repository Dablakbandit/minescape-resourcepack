// MineScape's minimap (MinimapInfo in the plugin), as the vertex stitch placed it: msMinimap is where on the frame
// this is, in map pixels from the middle, and the turn moved up 32 a layer. The ground's map: the ground inside the
// ring, unmapped ground black, and round it a thin band of stone with a dark line either side, as OSRS's, lit from
// the top left, in pixels as big as the map's. The icons' map: OSRS's icons (from its top rows), each a sprite from
// its map with a black edge round it, upright however the map turns, inside the ring. The dots' map: markers and the
// player, a square white dot that stays square however the map turns. A marker is one pixel of the map in a colour
// the ground never takes (MinimapColours), found from the five by five round where this is and drawn upright, as
// OSRS's are: round, lit from the top left and with a shadow to the bottom right, in half pixels to be round at that
// size. Over them OSRS's yellow hint arrow, where the top row says (msMinimapNumber), on where the player is led or
// at the ring pointing to it. The icons' and the dots' maps leave the rest to the map under them.
const int MS_MINIMAP_DIGIT[4] = int[](180, 220, 255, 135);

// One of the icons on the icons' map (PlayerMinimap's ICON_LIST): from the second row, eleven of the same
// digits each, its sprite's slot, then its pixel across and down, 7 bits each. One more than that, or 0
// where there is none.
uint msMinimapIcon(int index) {
    uint value = 0u;
    for (int i = 0; i < 11; i++) {
        int at = 128 + index * 11 + i;
        vec4 texel = stitch_texel_fetch(ivec2(at % 128, at / 128));
        int red = int(round(texel.r * 255.0));
        int digit = red == MS_MINIMAP_DIGIT[0] ? 0 : red == MS_MINIMAP_DIGIT[1] ? 1 : red == MS_MINIMAP_DIGIT[2] ? 2 : red == MS_MINIMAP_DIGIT[3] ? 3 : -1;
        if (digit < 0 || texel.a < 0.5 || texel.g > 0.0) {
            return 0u;
        }
        value = value * 4u + uint(digit);
    }
    return value + 1u;
}

int msMinimapNumber(int from) {
    int value = 0;
    for (int i = 0; i < 4; i++) {
        vec4 texel = stitch_texel_fetch(ivec2(from + i, 0));
        int red = int(round(texel.r * 255.0));
        int digit = red == 180 ? 0 : red == 220 ? 1 : red == 255 ? 2 : red == 135 ? 3 : -1;
        if (digit < 0 || texel.a < 0.5 || texel.g > 0.0) {
            return -1;
        }
        value = value * 4 + digit;
    }
    return value;
}

// The minimap's colour here: alpha -1 where this isn't one of its maps, 0 where it draws nothing.
vec4 msMinimapColour() {
    if (msMinimap.z > 0.5) {
        int msLayer = msMinimap.z > 64.0 ? 2 : msMinimap.z > 32.0 ? 1 : 0;
        float msTurn = msMinimap.z - 32.0 * float(msLayer);
        vec2 msAt = floor(msMinimap.xy) + 0.5;
        float msRadius = length(msAt);
        vec4 msPixel = vec4(-1.0);
        bool msNorthUp = msTurn > 16.0;
        float msYaw = msTurn - (msNorthUp ? 24.0 : 8.0);
        float msCos = cos(msYaw), msSin = sin(msYaw);
        mat2 msTurned = mat2(msCos, -msSin, msSin, msCos);
        vec2 msMap = vec2(msMinimap.x, -msMinimap.y);
        if (!msNorthUp) {
            msMap = msTurned * msMap;
        }
        if (msLayer > 0 && msRadius >= 60.0) {
            return vec4(0.0);
        }
        if (msLayer == 1) {
            // nearest first, and so on top: 15 of the sprite's pixels across, each three quarters of the map's;
            // the black edge's outermost pixels drawn here, the rest from the sprite's slot, 13 by 13, nine a
            // row from the fifth row down
            for (int msI = 0; msI < 24 && msPixel.a < 0.0; msI++) {
                uint msEntry = msMinimapIcon(msI);
                if (msEntry == 0u) {
                    break;
                }
                int msValue = int(msEntry - 1u);
                int msSlot = msValue >> 14;
                vec2 msSpot = vec2(float((msValue >> 7) & 127), float(msValue & 127)) + 0.5 - 64.0;
                vec2 msOnScreen = vec2(msSpot.x, -msSpot.y);
                if (!msNorthUp) {
                    msOnScreen = msOnScreen * msTurned;
                }
                ivec2 msP = ivec2(floor((msMinimap.xy - vec2(msOnScreen.x, -msOnScreen.y)) / 0.75 + 7.5));
                if (msP.x < 0 || msP.y < 0 || msP.x > 14 || msP.y > 14) {
                    continue;
                }
                vec4 msTexel;
                if (msP.x == 0 || msP.y == 0 || msP.x == 14 || msP.y == 14) {
                    int msAlong = msP.x == 0 || msP.x == 14 ? msP.y : msP.x;
                    msTexel = msAlong >= 5 && msAlong <= 9 ? vec4(0.0, 0.0, 0.0, 1.0) : vec4(0.0);
                } else {
                    msTexel = stitch_texel_fetch(ivec2(msSlot % 9 * 13 + msP.x - 1, 4 + msSlot / 9 * 13 + msP.y - 1));
                }
                if (msTexel.a > 0.5) {
                    msPixel = vec4(msTexel.rgb, 1.0);
                }
            }
            if (msPixel.a < 0.0) {
                return vec4(0.0);
            }
        } else if (msLayer == 2) {
            ivec2 msHome = ivec2(floor(vec2(msMap.x, -msMap.y) + 64.0));
            vec3 msDot = vec3(-1.0);
            bool msShadow = false;
            for (int msV = -2; msV <= 2; msV++) {
                for (int msU = -2; msU <= 2; msU++) {
                    ivec2 msTexel = msHome + ivec2(msU, msV);
                    ivec3 msMark = ivec3(round(stitch_texel_fetch(msTexel).rgb * 255.0));
                    vec3 msColour = msMark == ivec3(180, 0, 0) ? vec3(1.0, 1.0, 1.0)
                        : msMark == ivec3(220, 0, 0) ? vec3(1.0, 0.0, 0.0)
                        : msMark == ivec3(255, 0, 0) ? vec3(1.0, 1.0, 0.0)
                        : msMark == ivec3(135, 0, 0) ? vec3(0.0, 1.0, 0.0)
                        : msMark == ivec3(112, 112, 180) ? vec3(1.0, 0.5, 0.0)
                        : msMark == ivec3(138, 138, 220) ? vec3(0.2, 0.45, 1.0)
                        : vec3(-1.0);
                    if (msColour.r < 0.0) {
                        continue;
                    }
                    vec2 msSpot = vec2(msTexel) + 0.5 - 64.0;
                    vec2 msOnScreen = vec2(msSpot.x, -msSpot.y);
                    if (!msNorthUp) {
                        msOnScreen = msOnScreen * msTurned;
                    }
                    vec2 msFrom = (floor(msMinimap.xy * 2.0) + 0.5) / 2.0 - floor(vec2(msOnScreen.x, -msOnScreen.y) * 2.0) / 2.0;
                    if (length(msFrom) < 1.6) {
                        msDot = msColour * (msFrom.x + msFrom.y > 1.0 ? 0.75 : 1.0);
                    } else if (length(msFrom - vec2(0.5)) < 1.6) {
                        msShadow = true;
                    }
                }
            }
            if (msDot.r >= 0.0) {
                msPixel = vec4(msDot, 1.0);
            } else if (msShadow) {
                msPixel = vec4(0.0, 0.0, 0.0, 1.0);
            }
            // The hint arrow over where the player is being led (PlayerMinimap's HINT): a pixel across and down,
            // across 128 more when the place is past the map. Over it, the arrow points down on to it, upright as
            // the dots are; past the map it stands at the ring pointing the way it lies. Yellow, its right side
            // darker, edged black, in half pixels as the dots are; the server blinks it.
            int msHintU = msMinimapNumber(15), msHintV = msMinimapNumber(19);
            if (msHintU >= 0 && msHintV >= 0) {
                bool msAway = msHintU >= 128;
                vec2 msSpot = vec2(float(msAway ? msHintU - 128 : msHintU), float(msHintV)) + 0.5 - 64.0;
                vec2 msOnScreen = vec2(msSpot.x, -msSpot.y);
                if (!msNorthUp) {
                    msOnScreen = msOnScreen * msTurned;
                }
                vec2 msWhere = vec2(msOnScreen.x, -msOnScreen.y);
                vec2 msAhead = msAway ? normalize(msWhere) : vec2(0.0, 1.0);
                vec2 msTip = msAway ? msAhead * 58.5 : msWhere;
                vec2 msQ = (floor(msMinimap.xy * 2.0) + 0.5) / 2.0 - msTip;
                // how far behind the tip, and to one side, + being the screen's right when it points down
                float msBack = -dot(msQ, msAhead);
                float msSide = dot(msQ, vec2(msAhead.y, -msAhead.x));
                float msWide = abs(msSide);
                // a narrow head 6 wide and 5 deep, then a tail 2 wide to 8.5 behind the tip; the black edge
                // round it lies along the head's sides, so its point stays sharp
                float msOver = (msWide - 0.6 * msBack) / 1.166;
                if (msBack >= 0.0 && (msBack <= 5.0 && msOver <= 0.0 || msBack <= 8.5 && msWide <= 1.0)) {
                    msPixel = vec4(msSide > 0.0 ? vec3(0.8, 0.7, 0.0) : vec3(1.0, 1.0, 0.0), 1.0);
                } else if (msBack <= 5.75 && msOver <= 0.75 || msBack >= 0.0 && msBack <= 9.25 && msWide <= 1.75) {
                    msPixel = vec4(0.0, 0.0, 0.0, 1.0);
                }
            }
            if (abs(msAt.x) < 2.0 && abs(msAt.y) < 2.0) {
                msPixel = vec4(1.0);
            }
            if (msPixel.a < 0.0) {
                return vec4(0.0);
            }
        } else if (msRadius < 60.0) {
            msPixel = stitch_texel_fetch(ivec2(floor((vec2(msMap.x, -msMap.y) / 128.0 + 0.5) * vec2(stitch_texture_size()))));
            if (msPixel.a < 0.5) {
                msPixel = vec4(0.0, 0.0, 0.0, 1.0);
            }
        } else {
            if (msRadius > 65.0) {
                return vec4(0.0);
            }
            float msLit = dot(msAt / msRadius, vec2(-0.7071, -0.7071));
            float msGrain = fract(sin(dot(floor(msAt / 2.0), vec2(12.9898, 78.233))) * 43758.5453);
            vec3 msStone = msGrain < 0.2 ? vec3(0.365, 0.329, 0.290) : msGrain < 0.8 ? vec3(0.298, 0.263, 0.220) : vec3(0.243, 0.204, 0.141);
            if (msRadius > 64.0 || msRadius < 61.0) {
                msStone = vec3(0.075, 0.067, 0.055);
            } else if (fract((atan(msAt.y, msAt.x) / 6.28318 + 0.5) * 16.0) < 0.03) {
                msStone = vec3(0.125, 0.129, 0.125);
            } else if (msRadius > 63.0) {
                msStone = msLit > 0.25 ? vec3(0.545, 0.506, 0.427) : msLit < -0.25 ? vec3(0.176, 0.173, 0.161) : msStone;
            } else if (msRadius < 62.0) {
                msStone = msLit < -0.25 ? vec3(0.494, 0.455, 0.380) : msLit > 0.25 ? vec3(0.176, 0.173, 0.161) : msStone;
            }
            // N, E, S and W on the ring, upright, where those ways lie on the map: five by five letters, a
            // bit a pixel from the top left, light (N red) with a shadow below and right
            for (int msK = 0; msK < 4; msK++) {
                vec2 msWay = msK == 0 ? vec2(0.0, 1.0) : msK == 1 ? vec2(1.0, 0.0) : msK == 2 ? vec2(0.0, -1.0) : vec2(-1.0, 0.0);
                if (!msNorthUp) {
                    msWay = vec2(msCos * msWay.x - msSin * msWay.y, msSin * msWay.x + msCos * msWay.y);
                }
                int msGlyph = msK == 0 ? 18667121 : msK == 1 ? 32010782 : msK == 2 ? 16267326 : 18405233;
                vec2 msCell = floor(msMinimap.xy - vec2(msWay.x, -msWay.y) * 62.5 + 2.5);
                for (int msShade = 0; msShade < 2; msShade++) {
                    ivec2 msQ = ivec2(msCell) - ivec2(msShade == 0 ? 0 : 1);
                    if (msQ.x >= 0 && msQ.x < 5 && msQ.y >= 0 && msQ.y < 5 && ((msGlyph >> (24 - msQ.y * 5 - msQ.x)) & 1) != 0) {
                        msStone = msShade == 1 ? min(msStone, vec3(0.075, 0.067, 0.055)) : msK == 0 ? vec3(0.906, 0.157, 0.118) : vec3(0.941, 0.910, 0.784);
                        break;
                    }
                }
            }
            msPixel = vec4(msStone, 1.0);
        }
        return msPixel;
    }
    return vec4(-1.0);
}

// Drawn as it is, neither light nor fog reaching it: in Minecraft's own text shader exactly, and under a shader
// pack (Iris, with the Stitch mod) over the colour it lit, only its full-screen passes still running over it.
bool stitch_final(out vec4 color) {
    color = msMinimapColour();
    if (color.a < -0.5) {
        return false;
    }
    if (color.a <= 0.0) {
        discard;
    }
    return true;
}

// Under a shader pack, the map's colour as its texel, so the shader pack keeps and drops the same fragments.
vec4 stitch_texel(StitchFragment f, vec4 texel) {
    vec4 colour = msMinimapColour();
    return colour.a < -0.5 ? texel : colour;
}
