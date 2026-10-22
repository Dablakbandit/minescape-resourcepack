"""The Barrows sets as OSRS draws them: two or three flat tones each, lit a little from above, and only
the details that make each one: Dharok's bone spikes and knee guards, Guthan's spearhead and studs
over mail, Karil's spikes and ragged cloak, Torag's riveted plate and buckle, Verac's strap and sash,
Ahrim's chevrons. Painted in their own colours: their dyes are near black.
"""
from armour_art import BONE, BONE_DARK
from armour_detail import BODY, ARM, LEG, SIDES, LIMB_SIDES, faces

# Skirts are worn on the leg boxes (the shader flares them at the foot): to the knee, this many texels
# down from the hip.
KNEE = 26


def belt(c, colour):
    """A belt round the waist, on the leggings' body box."""
    def paint(f, name):
        f.clear(0, 0, f.w, 38)
        f.alpha[38:46] = True
        f.base(colour, 0.02, 7)
    faces(c, BODY, SIDES, paint)

SPIKE = ["..ab..", "..ab..", ".aabb.", ".aabb.", "aaabbb", "aaabbb"]
SPIKES = {"a": BONE, "b": BONE_DARK}


def plate(f, colour, seed, lames=0):
    f.base(colour, 0.02, seed).light(1.1, 0.88)
    if lames:
        for y in range(lames, f.h, lames):
            f.rgb[y - 1] *= 0.75
            f.rgb[y] *= 1.12
    return f


# --- Dharok's: dark plate, bone spikes, bone knee guards ----------------------------------------------
DHAROK, DHAROK_DARK = (64, 68, 62), (46, 48, 44)


def dharok_chest(c):
    faces(c, BODY, SIDES, lambda f, n: plate(f, DHAROK, 11, 12))
    faces(c, BODY, ("top",), lambda f, n: plate(f, DHAROK, 12))

    def arm(f, name):
        plate(f, DHAROK_DARK, 13, 12)
        f.rect(0, 0, f.w, 16, DHAROK)
        if name in ("outer", "front", "back"):
            f.sprite(1, 0, SPIKE, SPIKES)
            f.sprite(9, 0, SPIKE, SPIKES)
    faces(c, ARM, LIMB_SIDES, arm)
    faces(c, ARM, ("top",), lambda f, n: plate(f, DHAROK, 14).sprite(5, 5, SPIKE, SPIKES))


def dharok_legs(c):
    def leg(f, name):
        plate(f, DHAROK, 21, 16)
        if name == "front":
            f.rect(2, 14, 14, 21, BONE)
    faces(c, LEG, LIMB_SIDES, leg)
    faces(c, LEG, ("top",), lambda f, n: plate(f, DHAROK, 22))

    def belt(f, name):
        f.clear(0, 0, f.w, 38)
        f.alpha[38:46] = True
        f.base((58, 44, 30), 0.02, 23)
    faces(c, BODY, SIDES, belt)


# --- Guthan's: a plate breastplate over mail, bone studs, leather bracers ------------------------------
GUTHAN, GUTHAN_MAIL, GUTHAN_LEATHER = (92, 94, 78), (66, 68, 60), (88, 72, 50)


def guthan_chest(c):
    def body(f, name):
        f.base(GUTHAN_MAIL, 0.02, 31).chain(GUTHAN_MAIL)
        if name == "front":
            f.rect(4, 2, 28, 28, GUTHAN)
            f.sprite(13, 9, ["..a..", ".aaa.", "aaaaa", "..a..", "..a..", "..a.."], {"a": BONE})
            for x in (6, 24):
                f.rivet(x, 4, BONE)
    faces(c, BODY, SIDES, body)
    faces(c, BODY, ("top",), lambda f, n: plate(f, GUTHAN, 32))

    def arm(f, name):
        f.clear(0, 0, f.w, 28)
        f.alpha[28:] = True
        plate(f, GUTHAN_LEATHER, 33)
        f.rivet(6, 34, BONE)
    faces(c, ARM, LIMB_SIDES, arm)


def guthan_legs(c):
    def leg(f, name):
        # wrapped legs below a mail skirt
        f.base((70, 60, 44), 0.02, 35).light(1.08, 0.9)
        wrap = ((f.xx + f.yy) % 8) < 2
        f.rgb[wrap] *= 1.25
        mail = f.rgb.copy()
        f.base(GUTHAN_MAIL, 0.02, 34).chain(GUTHAN_MAIL)
        f.rgb[KNEE:] = mail[KNEE:]
        f.rect(0, 0, f.w, 3, GUTHAN_LEATHER)
    faces(c, LEG, LIMB_SIDES, leg)
    belt(c, GUTHAN_LEATHER)


# --- Karil's: dark green leather, a few spikes, a ragged cloak -----------------------------------------
KARIL, KARIL_CLOAK = (54, 62, 42), (42, 50, 34)


def karil_chest(c):
    def body(f, name):
        plate(f, KARIL, 41, 8)
        if name == "front":
            f.line([(0, 0), (31, 46)], (84, 62, 38), 2)
    faces(c, BODY, SIDES, body)
    faces(c, BODY, ("top",), lambda f, n: plate(f, KARIL, 42))

    def arm(f, name):
        plate(f, KARIL_CLOAK, 43)
        f.rect(0, 0, f.w, 10, KARIL)
        f.fray(5, 44 + len(name))
        if name == "outer":
            f.sprite(5, 0, SPIKE, SPIKES)
    faces(c, ARM, LIMB_SIDES, arm)
    faces(c, ARM, ("top",), lambda f, n: plate(f, KARIL, 45).sprite(5, 5, SPIKE, SPIKES))


def karil_legs(c):
    def leg(f, name):
        # dark leggings below a skirt of leather strips
        plate(f, (40, 44, 34), 53)
        legging = f.rgb.copy()
        plate(f, KARIL, 51)
        f.rgb[(f.xx % 6) == 5] *= 0.7
        f.rgb[KNEE:] = legging[KNEE:]
        f.rgb[KNEE - 1] *= 0.6
    faces(c, LEG, LIMB_SIDES, leg)
    belt(c, (66, 48, 30))


# --- Torag's: riveted grey plate, a belt and gold buckle ----------------------------------------------
TORAG, BRASS = (100, 100, 94), (176, 146, 84)


def torag_chest(c):
    def body(f, name):
        plate(f, TORAG, 61, 12)
        f.rivets(2, BRASS, 8, 3)
        f.rect(0, 34, f.w, 39, (70, 52, 34))
        if name == "front":
            f.rect(13, 33, 19, 40, (212, 172, 62))
    faces(c, BODY, SIDES, body)
    faces(c, BODY, ("top",), lambda f, n: plate(f, TORAG, 62))

    def arm(f, name):
        plate(f, (78, 78, 74), 63)
        f.rect(0, 0, f.w, 18, TORAG)
        f.rivets(3, BRASS, 8, 3)
    faces(c, ARM, LIMB_SIDES, arm)
    faces(c, ARM, ("top",), lambda f, n: plate(f, TORAG, 64))


def torag_legs(c):
    def leg(f, name):
        plate(f, TORAG, 71, 16)
        if name == "front":
            f.rect(3, 13, 13, 20, (132, 132, 124))
    faces(c, LEG, LIMB_SIDES, leg)
    faces(c, LEG, ("top",), lambda f, n: plate(f, TORAG, 72))

    def belt(f, name):
        f.clear(0, 0, f.w, 38)
        f.alpha[38:46] = True
        f.base((70, 52, 34), 0.02, 73)
    faces(c, BODY, SIDES, belt)


# --- Verac's: a bare chest, a strap and a red sash, one plate skirt -----------------------------------
VERAC, STRAP, SASH = (72, 74, 50), (100, 70, 40), (128, 34, 28)


def verac_chest(c):
    def body(f, name):
        f.alpha[:] = False
        if name in ("front", "back"):
            a = (f.xx - 2) * 40 / 27 if name == "front" else (29 - f.xx) * 40 / 27
            strap = (abs(a - f.yy) < 3)
            f.alpha |= strap
            f.base(STRAP, 0.02, 81)
        f.alpha[40:46] = True
        f.rgb[40:46] = SASH
    faces(c, BODY, SIDES, body)

    def arm(f, name):
        f.clear(0, 0, f.w, f.h)
        f.alpha[:20] = True
        plate(f, VERAC, 82)
        f.rgb[:20] = VERAC
        f.rgb[19] = tuple(v * 0.7 for v in VERAC)
    faces(c, ARM, LIMB_SIDES, arm)
    faces(c, ARM, ("top",), lambda f, n: plate(f, VERAC, 83))


def verac_legs(c):
    def skirt(f, name):
        plate(f, (82, 80, 54), 91, 9)
        f.clear(0, KNEE, f.w, f.h)
    faces(c, LEG, LIMB_SIDES, skirt)
    belt(c, SASH)


# --- Ahrim's: an olive robe in soft chevrons, frayed ---------------------------------------------------
AHRIM, AHRIM_DARK = (82, 80, 54), (66, 64, 42)


def ahrim_robe(f, seed):
    f.base(AHRIM, 0.02, seed).light(1.06, 0.9).chevrons(AHRIM_DARK, 10, 2)


def ahrim_chest(c):
    def body(f, name):
        ahrim_robe(f, 101)
        f.fray(3, 106 + len(name))
    faces(c, BODY, SIDES, body)
    faces(c, BODY, ("top",), lambda f, n: f.base(AHRIM_DARK))

    def arm(f, name):
        ahrim_robe(f, 103)
        f.fray(3, 104 + len(name))
    faces(c, ARM, LIMB_SIDES, arm)
    faces(c, ARM, ("top",), lambda f, n: f.base(AHRIM))


def ahrim_legs(c):
    def skirt(f, name):
        ahrim_robe(f, 111)
        f.fray(4, 112 + len(name))
    faces(c, LEG, LIMB_SIDES, skirt)
    belt(c, AHRIM_DARK)


CHESTS = {"dharok": dharok_chest, "guthan": guthan_chest, "karil": karil_chest, "torag": torag_chest,
          "verac": verac_chest, "ahrim": ahrim_chest}
LEGGINGS = {"dharok": dharok_legs, "guthan": guthan_legs, "karil": karil_legs, "torag": torag_legs,
            "verac": verac_legs, "ahrim": ahrim_legs}
