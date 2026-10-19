"""Copies the slot fonts' textures once per row, for the slot text overlay build_shaders.py writes
(shader_slot_layers): from 1.21.6 the slot font sets its glyphs in the title's line, and each row's
copy has its markers' green set to its row from 1, which the text shader reads to move the glyph down to
that row. Run it after changing font/slot.png or font/slot_box.png, and commit what it writes:

    python .github/scripts/build_slot_rows.py
"""
import os

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FONT = os.path.join(ROOT, "assets", "minecraft", "textures", "font")
NAMES = ("slot", "slot_box")
ROWS = 6


def main():
    for name in NAMES:
        px = np.array(Image.open(os.path.join(FONT, name + ".png")).convert("RGBA"))
        marker = (px[..., 0] == 255) & (px[..., 1] == 0) & (px[..., 2] == 255) & (px[..., 3] == 1)
        for row in range(ROWS):
            copy = px.copy()
            copy[marker, 1] = row + 1
            Image.fromarray(copy).save(os.path.join(FONT, "%s_row%d.png" % (name, row)))
        print("%s: %d markers, %d rows" % (name, marker.sum(), ROWS))


if __name__ == "__main__":
    main()
