"""The trade window's pictures. The plugin (TradeInventory, TradeTitle) draws the window's background, the coin before
each side's value and the words on the line under the chest in the window's title, as glyphs of the gui font; the
Accept and Decline buttons and each side's state are items (bone, custom model data from 1600).

    python .github/scripts/build_trade_interface.py

Writes, replacing what it wrote before:
    assets/minecraft/textures/font/trade/*.png          the background (plain, and stage two's gold frames) and coin
    assets/gui/font/default.json                        the trade providers at its end: those glyphs, and a line
                                                        of the menu font's letters on the line under the chest
    assets/minecraft/textures/item/ms/interface/trade/  the buttons and state ticks
    assets/ms/models/interface/trade/                   their models
    assets/minecraft/models/item/bone.json              their overrides, from BONE_START
and checks each glyph moves the pen as far as TradeTitle says (ADVANCES): Minecraft moves it a bitmap glyph's drawn
width, scaled to its height, and one, its width ending at its last column with a pixel not clear. Commit what it writes.

The window, in GUI pixels from its top left (a chest slot's ring at 7 + 18 x column, 17 + 18 x row): the player's
offer in columns 0-3 and the other's in 5-8, six rows each; the middle column holds the scroll arrows (rows 0 and 5),
the player's state, Accept, Decline and the other's state; the line under the chest (y 127-139, where the client's
"Inventory" label was, which the pack's languages now leave empty) holds the values and the state in words. Drawn at
two texels a pixel, as the menu font's letters are. Every slot is left clear inside, so the pack's chest shows through
and the highlight under the mouse isn't covered (the title is drawn after it, at the same depth, before 1.21.6).

A glyph's top sits at the title's line (6) plus 7, less its ascent: ascent = 13 - top.
"""
import json
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TEX = os.path.join(ROOT, "assets", "minecraft", "textures")
FONT_OUT = os.path.join(TEX, "font", "trade")
ITEM_OUT = os.path.join(TEX, "item", "ms", "interface", "trade")
MODEL_OUT = os.path.join(ROOT, "assets", "ms", "models", "interface", "trade")
FONT = os.path.join(ROOT, "assets", "gui", "font", "default.json")
BONE = os.path.join(ROOT, "assets", "minecraft", "models", "item", "bone.json")
BONE_START = 1600
T = 2  # texels a GUI pixel

RECESS = (44, 40, 33, 255)
DARK = (28, 25, 19, 255)
LIGHT = (96, 88, 72, 255)
STONE = (78, 71, 56, 255)
PANEL = (58, 52, 44, 255)
GREEN_EDGE = (70, 160, 80, 255)
RED_EDGE = (190, 70, 60, 255)
GOLD = (214, 168, 54, 255)

# the line under the chest: its letters' top, and the coin's (7 px tall, level with the digits)
LINE_TOP, COIN_TOP = 130, 131
# the background's area, and where it is split in two (a font page holds 256x256 texels)
BG_X0, BG_X1, BG_Y0, BG_Y1, BG_SPLIT = 3, 173, 16, 141, 88
ADVANCES = {"background": 86, "coin": 9}
LANG = os.path.join(ROOT, "assets", "minecraft", "lang")
CRLF, LF = chr(13) + chr(10), chr(10)
# Every language a client offers (from 1.18.2 to 26.x, as their asset indexes list them): each needs its own file with
# the empty "Inventory" label, or a player on that language gets the client's own label drawn over the values, since a
# language's translations override en_us's.
LANGUAGES = [
    "af_za", "ar_sa", "ast_es", "az_az", "ba_ru", "bar", "be_by", "be_latn", "bg_bg", "br_fr", "brb", "bs_ba",
    "ca_es", "cbk_zam", "cs_cz", "cv_cu", "cy_gb", "da_dk", "de_at", "de_ch", "de_de", "el_gr", "en_au", "en_ca",
    "en_gb", "en_nz", "en_pt", "en_ud", "en_us", "enp", "enws", "eo_uy", "es_ar", "es_cl", "es_ec", "es_es", "es_mx",
    "es_uy", "es_ve", "esan", "et_ee", "eu_es", "fa_ir", "fi_fi", "fil_ph", "fo_fo", "fr_ca", "fr_ch", "fr_fr",
    "fra_de", "fur_it", "fy_nl", "ga_ie", "gd_gb", "gl_es", "go_fr", "got_de", "gv_im", "hal_ua", "haw_us", "he_il",
    "hi_in", "hn_no", "hr_hr", "hu_hu", "hy_am", "id_id", "ig_ng", "io_en", "is_is", "isv", "it_it", "ja_jp",
    "jbo_en", "jv_id", "ka_ge", "kab_kab", "kk_kz", "kn_in", "ko_kr", "ksh", "kw_gb", "ky_kg", "la_la", "lb_lu",
    "li_li", "lmo", "lo_la", "lol_us", "lt_lt", "lv_lv", "lzh", "mi_nz", "mk_mk", "mn_mn", "moh_ca", "ms_my",
    "mt_mt", "nah", "nds_de", "nl_be", "nl_nl", "nn_no", "no_no", "nuk", "oc_fr", "oj_ca", "ovd", "pl_pl", "pls",
    "pt_br", "pt_pt", "qcb_es", "qid", "qya_aa", "ro_ro", "rpr", "ru_ru", "ry_ua", "sah_sah", "se_no", "sk_sk",
    "sl_si", "so_so", "sq_al", "sr_cs", "sr_sp", "sv_se", "swg", "sxu", "szl", "ta_in", "th_th", "tl_ph", "tlh_aa",
    "tok", "tr_tr", "tt_ru", "tzl_tzl", "tzo_mx", "uk_ua", "uz_uz", "val_es", "vec_it", "vi_vn", "vp_vl", "vro",
    "yi_de", "yo_ng", "zh_cn", "zh_hk", "zh_tw", "zlm_arab"]
# the items, in BONE_START order: (name, what it is)
ITEMS = [("accept", "Accept"), ("accepted", "Accept, pressed: this player has accepted"),
         ("accept_other", "Accept, outlined green: the other player has accepted"), ("confirm", "Confirm (stage two)"),
         ("confirmed", "Confirm, pressed: this player has confirmed"),
         ("confirm_locked", "Confirm, locked until the other offer has been seen to its end"), ("decline", "Decline"),
         ("state_accepted", "a side's state: accepted"), ("state_confirmed", "a side's state: confirmed")]


class Canvas:
    """A picture of part of the window, drawn in GUI pixels from x0, y0."""

    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0 = x0, y0
        self.img = Image.new("RGBA", ((x1 - x0) * T, (y1 - y0) * T), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def rect(self, x, y, w, h, colour):
        l, t = round((x - self.x0) * T), round((y - self.y0) * T)
        r, b = round((x + w - self.x0) * T) - 1, round((y + h - self.y0) * T) - 1
        if r >= l and b >= t:
            self.d.rectangle([l, t, r, b], fill=colour)

    def clear(self, x, y, w, h):
        self.rect(x, y, w, h, (0, 0, 0, 0))

    def bevel(self, x, y, w, h, inset):
        tl, br = (DARK, LIGHT) if inset else (LIGHT, DARK)
        self.rect(x, y, w, 0.5, tl)
        self.rect(x, y, 0.5, h, tl)
        self.rect(x, y + h - 0.5, w, 0.5, br)
        self.rect(x + w - 0.5, y, 0.5, h, br)


def offer_panel(c, x, edge):
    """Four columns of six slots from x: a ring round each slot, clear inside, in a bevelled recess."""
    y = 17
    for col in range(4):
        for row in range(6):
            sx, sy = x + 18 * col, y + 18 * row
            c.rect(sx, sy, 18, 1, RECESS)
            c.rect(sx, sy + 17, 18, 1, RECESS)
            c.rect(sx, sy, 1, 18, RECESS)
            c.rect(sx + 17, sy, 1, 18, RECESS)
    c.bevel(x, y, 72, 108, True)
    c.rect(x + 0.5, y + 0.5, 71, 0.5, edge)


def background(gold):
    full = Canvas(BG_X0, BG_Y0, BG_X1, BG_Y1)
    offer_panel(full, 7, GREEN_EDGE)
    offer_panel(full, 97, RED_EDGE)
    # the middle column: stone, each slot clear inside
    full.rect(79, 17, 18, 108, STONE)
    for row in range(6):
        full.clear(80, 18 + 18 * row, 16, 16)
    full.bevel(79, 17, 18, 108, False)
    # the line under the chest: a band over the gap between the chest and the inventory
    full.rect(3, 127, 170, 12, PANEL)
    full.rect(3, 127, 170, 0.5, DARK)
    full.rect(3, 138.5, 170, 0.5, LIGHT)
    if gold:
        for x0 in (6, 96):
            full.rect(x0, 16, 74, 1, GOLD)
            full.rect(x0, 125, 74, 1, GOLD)
            full.rect(x0, 16, 1, 110, GOLD)
            full.rect(x0 + 73, 16, 1, 110, GOLD)
    split = (BG_SPLIT - BG_X0) * T
    return full.img.crop((0, 0, split, full.img.height)), full.img.crop((split, 0, full.img.width, full.img.height))


def texture(path):
    return Image.open(os.path.join(TEX, *path.split("/"))).convert("RGBA")


def coin():
    pile = texture("item/custom/stone_hoe/10gp.png")
    pile = pile.crop(pile.getbbox())
    h = 7 * T
    w = max(1, round(pile.width * h / pile.height))
    pile = pile.resize((w, h), Image.NEAREST)
    out = Image.new("RGBA", (8 * T, h))
    out.alpha_composite(pile, ((8 * T - w) // 2, 0))
    return out


def shade(im, f, grey=False):
    out = im.copy()
    o = out.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = o[x, y]
            if grey:
                r = g = b = int(r * .3 + g * .59 + b * .11)
            o[x, y] = (int(r * f), int(g * f), int(b * f), a)
    return out


def framed(im, colour, width):
    out = im.copy()
    x0, y0, x1, y1 = im.getbbox()
    d = ImageDraw.Draw(out)
    for i in range(width):
        d.rectangle([x0 + i, y0 + i, x1 - 1 - i, y1 - 1 - i], outline=colour)
    return out


def check(tick, colour):
    """The tick alone, off its stone, recoloured, in the middle of a picture the stone's size."""
    mark = Image.new("RGBA", tick.size)
    p, o = tick.load(), mark.load()
    for y in range(tick.height):
        for x in range(tick.width):
            r, g, b, a = p[x, y]
            if a and g > r + 30 and g > b + 30:
                v = g / 255
                o[x, y] = (int(colour[0] * v), int(colour[1] * v), int(colour[2] * v), 255)
            elif a and r < 40 and g < 40 and b < 40 and any(
                    0 <= x + dx < tick.width and 0 <= y + dy < tick.height and p[x + dx, y + dy][1] > p[x + dx, y + dy][0] + 30
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                o[x, y] = (0, 0, 0, 255)  # its dark outline
    box = mark.getbbox()
    mark = mark.crop(box)
    out = Image.new("RGBA", tick.size)
    out.alpha_composite(mark, ((tick.width - mark.width) // 2, (tick.height - mark.height) // 2))
    return out


def items():
    """The buttons from the pack's own stone tick and cross buttons, cropped to the stone so they fill a slot."""
    tick = texture("item/custom/wooden_shovel/tick.png")
    tick = tick.crop(tick.getbbox())
    cross = texture("item/custom/wooden_shovel/cross.png")
    cross = cross.crop(cross.getbbox())
    pressed = shade(tick, 0.6, grey=True)
    return {
        "accept": tick,
        "accepted": pressed,
        "accept_other": framed(tick, (60, 220, 90, 255), 3),
        "confirm": framed(tick, GOLD, 3),
        "confirmed": framed(pressed, (150, 118, 40, 255), 3),
        "confirm_locked": framed(shade(tick, 0.45, grey=True), (110, 90, 40, 255), 3),
        "decline": cross,
        "state_accepted": check(tick, (90, 230, 90)),
        "state_confirmed": check(tick, (255, 200, 60)),
    }


def advance(im, height):
    alpha = im.getchannel("A").load()
    width = 0
    for x in range(im.width - 1, -1, -1):
        if any(alpha[x, y] for y in range(im.height)):
            width = x + 1
            break
    return int(0.5 + width * height / im.height) + 1


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(text.encode("utf-8"))


def blank_inventory_label():
    """The client's "Inventory" label over the player's inventory in every chest window, left empty in every language:
    the trade window writes its values on that line, and the pack's chest background leaves it no room anyway."""
    made = changed = 0
    for code in LANGUAGES:
        path = os.path.join(LANG, code + ".json")
        if not os.path.exists(path):
            write(path, '{' + CRLF + '  "container.inventory": ""' + CRLF + '}' + CRLF)
            made += 1
            continue
        text = open(path, "rb").read().decode("utf-8-sig")
        if "container.inventory" in json.loads(text):
            continue
        nl = CRLF if CRLF in text else LF
        start = text.index("{") + 1
        write(path, text[:start] + nl + '  "container.inventory": "",' + nl + text[start:].lstrip(CRLF))
        json.loads(open(path, encoding="utf-8").read())
        changed += 1
    return made, changed


def main():
    problems = []
    os.makedirs(FONT_OUT, exist_ok=True)
    for f in os.listdir(FONT_OUT):
        os.remove(os.path.join(FONT_OUT, f))
    left, right = background(False)
    gleft, gright = background(True)
    glyphs = [("background_left", left), ("background_right", right), ("background_left_gold", gleft),
              ("background_right_gold", gright)]
    height = BG_Y1 - BG_Y0
    providers = []
    for i, (name, im) in enumerate(glyphs):
        im.save(os.path.join(FONT_OUT, name + ".png"), optimize=True)
        providers.append({"file": "minecraft:font/trade/%s.png" % name, "height": height, "ascent": 13 - BG_Y0,
                          "chars": [chr(0xEB00 + i)],
                          "comment": "trade window: the window's %s half%s" % ("left" if "left" in name else "right",
                                                                              ", stage two's gold frames" if "gold" in name else "")})
        if advance(im, height) != ADVANCES["background"]:
            problems.append("%s moves the pen %d, TradeTitle says %d" % (name, advance(im, height), ADVANCES["background"]))
        if im.width > 256 or im.height > 256:
            problems.append("%s is %dx%d: a font's page holds 256x256" % (name, im.width, im.height))
    c = coin()
    c.save(os.path.join(FONT_OUT, "coin.png"), optimize=True)
    providers.append({"file": "minecraft:font/trade/coin.png", "height": 7, "ascent": 13 - COIN_TOP, "chars": [chr(0xEB20)],
                      "comment": "trade window: the coin before each side's value"})
    if advance(c, 7) != ADVANCES["coin"]:
        problems.append("coin moves the pen %d, TradeTitle says %d" % (advance(c, 7), ADVANCES["coin"]))
    # the menu font's letters once more, on the line under the chest (InventoryFontManager's order, 96 from U+EB40)
    rows = ["".join(chr(0xEB40 + r * 16 + i) for i in range(16)) for r in range(6)]
    providers.append({"file": "minecraft:font/characters.png", "height": 8, "ascent": 13 - LINE_TOP, "chars": rows,
                      "comment": "trade window: the menu font on the line under the chest"})

    # the providers at the end of the gui font, in its hand-written style, replacing any written before
    text = open(FONT, "rb").read().decode("utf-8")
    nl = "\r\n" if "\r\n" in text else "\n"
    end = nl + "  ]" + nl + "}"
    first = text.find('"comment": "trade window:')
    body = text[:text.rindex(nl + "    {", 0, first) - 1] if first >= 0 else text[:text.rindex(end)]
    block = ""
    for p in providers:
        chars = ", ".join('"%s"' % "".join("\\u%04x" % ord(ch) for ch in row) for row in p["chars"])
        block += "," + nl + "    {" + nl
        block += '      "file":"%s",%s' % (p["file"], nl)
        block += '      "height": %d,%s' % (p["height"], nl)
        block += '      "ascent": %d,%s' % (p["ascent"], nl)
        block += '      "chars":[%s],%s' % (chars, nl)
        block += '      "type":"bitmap",%s' % nl
        block += '      "comment": %s%s' % (json.dumps(p["comment"]), nl)
        block += "    }"
    write(FONT, body + block + text[text.rindex(end):])
    json.loads(open(FONT, encoding="utf-8").read())

    # the items: textures, models, and their overrides at the end of bone.json
    os.makedirs(ITEM_OUT, exist_ok=True)
    pictures = items()
    for name, _ in ITEMS:
        pictures[name].save(os.path.join(ITEM_OUT, name + ".png"), optimize=True)
        write(os.path.join(MODEL_OUT, name + ".json"),
              '{\r\n\t"parent": "item/generated",\r\n\t"textures": {\r\n\t\t"layer0": "item/ms/interface/trade/%s"\r\n\t}\r\n}' % name)
    bone = open(BONE, "rb").read().decode("utf-8")
    bnl = "\r\n" if "\r\n" in bone else "\n"
    lines = [l for l in bone.split(bnl) if '"ms:interface/trade/' not in l]
    close = max(i for i, l in enumerate(lines) if l.strip() == "]")
    last = close - 1
    lines[last] = lines[last].rstrip(",")
    used = {json.loads(l.rstrip(","))["predicate"].get("custom_model_data") for l in lines[:close] if l.startswith('{"predicate"')}
    added = []
    for i, (name, _) in enumerate(ITEMS):
        cmd = BONE_START + i
        if cmd in used:
            problems.append("bone %d is taken" % cmd)
        added.append('{"predicate": {"custom_model_data":%d},"model":"ms:interface/trade/%s"}' % (cmd, name))
    lines[last] += ","
    lines[close:close] = [l + "," for l in added[:-1]] + [added[-1]]
    write(BONE, bnl.join(lines))
    json.loads(open(BONE, encoding="utf-8").read())

    made, changed = blank_inventory_label()
    print("the Inventory label left empty: %d language files added, %d given the key" % (made, changed))
    for name, im in glyphs + [("coin", c)]:
        print("%-24s %3dx%-3d" % (name, im.width, im.height))
    for i, (name, what) in enumerate(ITEMS):
        print("bone %d  %-16s %s" % (BONE_START + i, name, what))
    if problems:
        print("\n".join(problems))
        sys.exit(1)


if __name__ == "__main__":
    main()
