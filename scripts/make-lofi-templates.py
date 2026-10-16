#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Jareer and Concat contributors
"""Writes the ten soft lo-fi template bundles into a templates/ folder.

    scripts/make-lofi-templates.py [OUT_DIR [function_name ...]]

OUT_DIR defaults to the app's own library, so `template.list` finds them:
macOS ~/Library/Application Support/app.concat.editor/templates, Linux
~/.config/app.concat.editor/templates, Windows %APPDATA%/app.concat.editor/templates.

Each bundle is a `template.json` (see concat-host/src/templates.rs): placeholder
media for the user's photos or clips, and everything else the design: a blurred
copy of each scene that fills the frame behind it, the scene itself with a slow
camera move, colour looks laid as Layer clips over everything beneath, a
light-catching transition between scenes, a fade in and out, and a few accents
that give each template its own face (a spinning record, a photo card, a tape
label, a progress bar, cinema bars...). The styles are original: they borrow the
mood of the lo-fi edits that trend elsewhere, none of their assets, and no music -
the music is the user's own.

Lanes are listed bottom to top: the first is drawn first and the last is on top.

Fonts are ones a stock macOS or Windows install has, because a template cannot
ship a font family it merely names.
"""

import json
import os
import re
import sys
import unicodedata
from pathlib import Path

FPS = 30
SIZES = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
EASE_OUT = (0.16, 0.84, 0.44, 1.0)
EASE_IN_OUT = (0.42, 0.0, 0.58, 1.0)
LINEAR = (0.0, 0.0, 1.0, 1.0)
ORDER = ["scale", "offsetX", "offsetY", "rotation", "opacity", "volume"]

# Every id here is a package under concat-effects/packages; `check_catalogue`
# refuses to write if one has gone missing or changed kind.
KINDS = {}


def check_catalogue():
    root = Path(__file__).resolve().parent.parent / "src/crates/concat-effects/packages"
    for package in root.glob("*/effect.toml"):
        text = package.read_text()
        eid = re.search(r'^id = "([^"]+)"', text, re.M).group(1)
        KINDS[eid] = re.search(r'^kind = "([^"]+)"', text, re.M).group(1)


def want(eid, *kinds):
    assert eid in KINDS, f"{eid} is not in the catalogue"
    assert KINDS[eid] in kinds, f"{eid} is a {KINDS[eid]}, not {kinds}"


# Fonts a stock install has.
SERIF = "Georgia"
MONO = "Courier New"
SANS = "Trebuchet MS"
BOLD = "Arial Black"
SCRIPT = "Brush Script MT"
CLASSIC = "Times New Roman"


def key(prop, at, value, ease=EASE_IN_OUT):
    return dict(property=prop, at=round(at, 4), value=value, ease=list(ease))


def fade_keys(inn=0.12, out=0.88, peak=1.0):
    return [key("opacity", 0.0, 0.0, LINEAR), key("opacity", inn, peak, EASE_OUT),
            key("opacity", out, peak, LINEAR), key("opacity", 1.0, 0.0, LINEAR)]


class Doc:
    """One template's lanes, media and clips, assembled from the bottom up."""

    def __init__(self, name, ratio, total):
        self.name = name
        self.width, self.height = SIZES[ratio]
        self.total = total
        self.media, self.clips, self.lanes = [], [], []
        self.n = 0

    def lane(self, base, start=0.0, end=0.0):
        """The lane for a clip over [start, end]: `base`, or the next lane of its group
        that is free then. Two clips overlapping on one lane draw only one of them."""
        n = 1
        while True:
            name = base if n == 1 else f"{base}.{n}"
            busy = any(c["trackId"] == name and c["start"] < end - 1e-6
                       and start < c["start"] + c["duration"] - 1e-6 for c in self.clips)
            if not busy:
                break
            n += 1
        if name not in self.lanes:
            group = [i for i, lane in enumerate(self.lanes)
                     if lane == base or lane.startswith(base + ".")]
            self.lanes.insert(group[-1] + 1 if group else len(self.lanes), name)
        return name

    def add(self, lane, kind, name, start, duration, media_id="", **extra):
        self.n += 1
        c = dict(
            id=f"c{self.n}", trackId=self.lane(lane, start, start + duration), mediaId=media_id, name=name,
            kind=kind, start=round(start, 3), duration=round(duration, 3),
            sourceStart=0.0, volume=1.0, fadeIn=0.0, fadeOut=0.0, scale=1.0,
            offsetX=0.0, offsetY=0.0, rotation=0.0, opacity=1.0, speed=1.0,
            preservePitch=True, filters=[], videoEffects=[],
        )
        c.update(extra)
        if "keys" in c:
            # The document keeps a clip's keys sorted by property, then by time.
            c["keys"] = sorted(c["keys"], key=lambda k: (ORDER.index(k["property"]), k["at"]))
        self.clips.append(c)
        return c

    def effect(self, eid, **params):
        want(eid, "filter", "effect")
        return dict(id=eid, params=params, enabled=True)

    def look(self, lane, eid, strength, start=0.0, duration=None):
        c = self.add(lane, "layer", eid.removeprefix("concat."), start,
                     duration or self.total, opacity=strength)
        c["videoEffects"] = [self.effect(eid)]
        return c

    def shape(self, lane, kind, size, fill, start, duration, name="shape", stroke="",
              stroke_width=0.0, **extra):
        return self.add(lane, "shape", name, start, duration,
                        shape=dict(kind=kind, size=size, fill=fill, stroke=stroke,
                                   strokeWidth=stroke_width), **extra)

    def text(self, lane, words, start, duration, y, size, color, font, weight=400,
             italic=False, tracking=0.0, plate="", slide=0.035, hold=True, align="center",
             x=0.0, stroke=0.0, stroke_color="#000000", shadow=False, radius=0.0,
             pad=(0.0, 0.0), max_width=0.0):
        # `tracking` is in frame-height fractions, so the figures below are written in
        # hundredths of the type size's own scale and brought down to that here.
        style = dict(content=words, fontFamily=font, fontSize=size, fontWeight=weight,
                     italic=italic, color=color, align=align, opacity=1.0, shadow=shadow,
                     tracking=round(tracking * 0.22, 5), maxWidth=max_width, background=plate,
                     strokeWidth=stroke, strokeColor=stroke_color)
        if plate:
            style.update(backgroundRadius=radius, backgroundPaddingX=pad[0],
                         backgroundPaddingY=pad[1])
        keys = [key("opacity", 0.0, 0.0, LINEAR), key("opacity", min(0.3, 0.6 / duration), 1.0, EASE_OUT)]
        if hold:
            keys += [key("opacity", 1 - min(0.3, 0.6 / duration), 1.0, LINEAR),
                     key("opacity", 1.0, 0.0, LINEAR)]
        if slide:
            # A title eases up out of a slightly smaller size as it fades in. (A keyed
            # `offsetY` on a title drops it out of the frame in this build, so it is
            # the size that moves, not the position.)
            keys += [key("scale", 0.0, 0.93, EASE_OUT),
                     key("scale", min(0.45, 1.0 / duration), 1.0, EASE_OUT)]
        return self.add(lane, "text", words, start, duration, offsetX=x, offsetY=y,
                        text=style, keys=keys)

    def bars(self, thickness, color="#050505"):
        """Cinema bars: a thick rule along the top and one along the bottom, each
        `thickness` of the frame's height."""
        for sign in (-1, 1):
            self.shape("BARS", "line", 2.0, color, 0.0, self.total, name="bar", stroke=color,
                       stroke_width=thickness, offsetY=sign * (0.5 - thickness / 2))

    def border(self, color, inset=0.03, width=0.003, opacity=0.9):
        """A thin outline laid inside the frame's edge, `inset` of each side in. A landscape
        frame gets the whole outline; an upright one gets a rule above and one below, which
        reads as the same thing and is drawn the same way every time."""
        aspect = self.width / self.height
        if aspect >= 1:
            h = 1.0 - 2 * inset
            w = aspect * (1.0 - 2 * inset)
            self.shape("DECO", "square", 1.0, "", 0.0, self.total, name="frame", stroke=color,
                       stroke_width=width, opacity=opacity, scale=h, stretchX=w / h)
            return
        for y in (-(0.5 - inset), 0.5 - inset):
            self.shape("DECO", "line", aspect * (1 - 2 * inset), color, 0.0, self.total,
                       name="frame", stroke=color, stroke_width=width, opacity=opacity, offsetY=y)

    def fades(self, color="#050505", seconds=1.4):
        self.shape("FADE", "square", 1.0, color, 0.0, seconds, name="fade in", scale=3.0,
                   keys=[key("opacity", 0.0, 1.0, LINEAR), key("opacity", 1.0, 0.0, EASE_IN_OUT)])
        self.shape("FADE", "square", 1.0, color, self.total - seconds, seconds, name="fade out",
                   scale=3.0,
                   keys=[key("opacity", 0.0, 0.0, LINEAR), key("opacity", 1.0, 1.0, EASE_IN_OUT)])

    def stacked(self):
        """The lanes bottom to top: backdrop, what sits behind the picture, the picture, the
        looks, decoration, cinema bars, titles, fades; lanes of one group keep their order."""
        order = ["BG", "CARD", "FG", "L", "DECO", "BARS", "T", "FADE"]
        group = lambda lane: order.index(re.match(r"[A-Z]+", lane).group(0))
        return sorted(self.lanes, key=group)

    def document(self):
        return {
            "concat": "0.1.0", "version": 1, "name": self.name,
            "video": dict(width=self.width, height=self.height, rateNum=FPS, rateDen=1),
            "media": self.media,
            "tracks": [dict(id=t, name=t, visible=True, muted=False) for t in self.stacked()],
            "clips": self.clips,
        }


def scenes(doc, slot_kind, count, seconds, transition, fg_scale=0.9, blur=36, backdrop=0.9,
           glow=None, aberration=None, drift=0.05, trans_seconds=0.9, shift_x=0.0, shift_y=0.0):
    """The picture: for each slot a blurred copy that fills the frame behind it, and the
    slot itself with a slow camera move."""
    want(transition, "transition")
    noun = "Photo" if slot_kind == "image" else "Clip"
    for i in range(count):
        doc.media.append(dict(id=f"m{i + 1}", path="", name=f"{noun} {i + 1}", duration=seconds,
                              kind=slot_kind, hasAudio=False, placeholder=True))
    for i in range(count):
        mid, start = f"m{i + 1}", i * seconds
        # The backdrop: the same slot, enlarged past any shape of frame and blurred.
        bg = doc.add("BG", slot_kind, f"{noun} {i + 1} backdrop", start, seconds, mid,
                     scale=3.4, opacity=backdrop,
                     keys=[key("scale", 0.0, 3.4), key("scale", 1.0, 3.7)])
        bg["videoEffects"] = [doc.effect("concat.gaussian-blur", radius=blur)]
        a, b = (fg_scale, fg_scale + drift) if i % 2 == 0 else (fg_scale + drift, fg_scale)
        sway = 0.012 if i % 2 == 0 else -0.012
        fg = doc.add("FG", slot_kind, f"{noun} {i + 1}", start, seconds, mid, scale=a,
                     offsetX=shift_x, offsetY=shift_y,
                     keys=[key("scale", 0.0, a), key("scale", 1.0, b),
                           key("offsetX", 0.0, shift_x - sway), key("offsetX", 1.0, shift_x + sway),
                           key("offsetY", 0.0, shift_y), key("offsetY", 1.0, shift_y)])
        effects = []
        if glow:
            effects.append(doc.effect("concat.glow", **glow))
        if aberration:
            effects.append(doc.effect("concat.chromatic-aberration", **aberration))
        fg["videoEffects"] = effects
        if i > 0:
            for c in (bg, fg):
                c["transitionIn"] = dict(id=transition, duration=trans_seconds)


def looks(doc, stack):
    for n, (eid, strength) in enumerate(stack):
        doc.look(f"L{n + 1}", eid, strength)


# ── the ten ──────────────────────────────────────────────────────────────

def dusk_drive():
    d = Doc("Dusk Drive", "9:16", 4 * 4.0)
    scenes(d, "video", 4, 4.0, "concat.light-leak-transition", glow={})
    looks(d, [("concat.golden-hour", 1.0), ("concat.film-grain", 0.5), ("concat.vignette", 0.6)])
    d.shape("DECO", "line", 0.34, "#ffb86b", 0.9, 5.2, name="accent line", stroke="#ffb86b",
            stroke_width=0.004, offsetY=0.255, keys=fade_keys())
    d.text("T1", "dusk drive", 0.9, 5.2, 0.31, 0.09, "#fff1dc", SERIF, italic=True,
           tracking=0.01, shadow=True)
    d.text("T2", "ROAD TRIP  ·  LOFI", 1.3, 4.8, 0.37, 0.022, "#2a1408", SANS, weight=700,
           tracking=0.012, plate="#ffb86b", radius=0.5, pad=(0.018, 0.008))
    d.fades()
    return d


def rainy_window():
    d = Doc("Rainy Window", "16:9", 3 * 5.0)
    scenes(d, "video", 3, 5.0, "concat.blur-dissolve", fg_scale=0.86, blur=40, glow={})
    looks(d, [("concat.moody", 1.0), ("concat.rain", 0.7), ("concat.soft-light", 0.5),
              ("concat.film-grain", 0.4)])
    d.bars(0.12)
    d.text("T1", "rainy day", 1.2, 5.5, 0.28, 0.12, "#e8f0f6", SERIF, italic=True,
           tracking=0.012, shadow=True)
    d.text("T2", "STAY IN  ·  PRESS PLAY", 1.7, 5.0, 0.36, 0.03, "#9fb6c6", SANS, weight=700,
           tracking=0.03)
    d.fades()
    return d


def cozy_room():
    d = Doc("Cozy Room", "9:16", 5 * 3.5)
    scenes(d, "image", 5, 3.5, "concat.light-leak-flash", fg_scale=0.88, glow={},
           trans_seconds=0.7)
    looks(d, [("concat.warm", 0.9), ("concat.milk", 0.55), ("concat.film-grain", 0.35),
              ("concat.vignette", 0.45)])
    d.border("#fff3e0", 0.035)
    d.text("T1", "night in", 0.7, 4.6, 0.295, 0.12, "#fff3e0", SCRIPT, shadow=True)
    d.text("T2", "cozy  ·  slow  ·  warm", 1.2, 4.1, 0.395, 0.022, "#3b2414", SANS, weight=700,
           tracking=0.015, plate="#ffd9a8", radius=0.5, pad=(0.016, 0.007))
    d.fades()
    return d


def vinyl_night():
    d = Doc("Vinyl Night", "1:1", 3 * 4.5)
    # The picture sits left of centre and a record turns out from behind it.
    scenes(d, "image", 3, 4.5, "concat.zoom-transition", fg_scale=0.58, blur=44, drift=0.04,
           shift_x=-0.13)
    d.shape("CARD", "circle", 0.62, "#121212", 0.0, d.total, name="record", offsetX=0.17,
            stroke="#2c2c2c", stroke_width=0.006)
    d.shape("CARD", "line", 0.58, "#3a3a3a", 0.0, d.total, name="record glint", offsetX=0.17,
            stroke="#3d3d3d", stroke_width=0.006,
            keys=[key("rotation", 0.0, -70, LINEAR), key("rotation", 1.0, 110, LINEAR)])
    d.shape("CARD", "circle", 0.2, "#ff8f6b", 0.0, d.total, name="label", offsetX=0.17)
    d.shape("CARD", "circle", 0.025, "#121212", 0.0, d.total, name="spindle", offsetX=0.17)
    looks(d, [("concat.vintage", 1.0), ("concat.film-grain", 0.55), ("concat.vignette", 0.8)])
    d.text("T1", "slow down", 0.8, 5.0, -0.36, 0.085, "#ffc9a8", SERIF, italic=True, shadow=True)
    d.text("T2", "SIDE A  ·  33 RPM", 1.3, 4.5, -0.29, 0.02, "#241006", MONO, weight=700,
           tracking=0.0, plate="#ff8f6b", radius=0.3, pad=(0.014, 0.007))
    d.fades()
    return d


def polaroid_memory():
    captions = ["good days", "slow mornings", "golden hour", "us", "just because",
                "remember this"]
    d = Doc("Polaroid Memory", "9:16", 6 * 3.0)
    scenes(d, "image", 6, 3.0, "concat.light-leak-flash", fg_scale=0.8, blur=40, drift=0.03,
           trans_seconds=0.6, shift_y=-0.04)
    # A white card behind each photo, a little crooked, with its caption under it.
    for i, words in enumerate(captions):
        tilt = -2.0 if i % 2 == 0 else 2.0
        d.shape("CARD", "square", 0.52, "#fbf7ef", i * 3.0, 3.0, name="card", stretchY=1.52,
                offsetY=-0.0, rotation=tilt,
                keys=[key("rotation", 0.0, tilt - 0.6), key("rotation", 1.0, tilt + 0.6)])
        d.text("T1", words, i * 3.0 + 0.25, 2.5, 0.31, 0.075, "#3a2a1c", SCRIPT, slide=0.02)
    looks(d, [("concat.polaroid", 0.9), ("concat.fair", 0.45), ("concat.film-grain", 0.3)])
    d.text("T2", "10.14.26", 0.6, 17.0, -0.44, 0.024, "#ffb15c", MONO, weight=700,
           tracking=0.04, hold=False, slide=0, shadow=True)
    d.fades()
    return d


def sleepy_sunday():
    d = Doc("Sleepy Sunday", "16:9", 4 * 4.5)
    scenes(d, "video", 4, 4.5, "concat.blur-dissolve", fg_scale=0.88, glow={}, blur=44)
    looks(d, [("concat.peach", 0.95), ("concat.dreamy", 0.8), ("concat.film-grain", 0.3),
              ("concat.vignette", 0.4)])
    d.border("#fff5ea", 0.035)
    d.text("T1", "sleepy sunday", 1.0, 5.4, 0.3, 0.12, "#fff5ea", SERIF, italic=True, shadow=True)
    d.text("T2", "NO ALARMS  ·  NO PLANS", 1.5, 4.9, 0.385, 0.03, "#4a2b18", SANS, weight=700,
           tracking=0.025, plate="#ffe2b8", radius=0.5, pad=(0.016, 0.008))
    d.fades()
    return d


def study_girl():
    d = Doc("Study Girl", "9:16", 3 * 5.0)
    scenes(d, "video", 3, 5.0, "concat.dissolve", fg_scale=0.9, blur=36)
    looks(d, [("concat.matcha", 0.9), ("concat.sage", 0.7), ("concat.film-grain", 0.35),
              ("concat.vignette", 0.4)])
    # A progress bar along the foot: a dim rule across the frame and a bright one sliding in
    # from the left edge, so it fills as the piece plays.
    wide = d.width / d.height
    d.shape("DECO", "line", wide, "#ffffff", 0.0, d.total, name="progress track", opacity=0.25,
            stroke="#ffffff", stroke_width=0.004, offsetY=0.46)
    d.shape("DECO", "line", wide, "#d8f0a8", 0.0, d.total, name="progress",
            stroke="#d8f0a8", stroke_width=0.004, offsetY=0.46,
            keys=[key("offsetX", 0.0, -1.0, LINEAR), key("offsetX", 1.0, 0.0, LINEAR)])
    d.text("T1", "25:00", 0.6, d.total - 1.2, -0.43, 0.07, "#f3f8e6", MONO, weight=700,
           tracking=0.04, hold=False, shadow=True)
    d.text("T2", "study with me", 0.9, 5.2, 0.3, 0.075, "#f4f8e8", SANS, weight=700,
           tracking=0.01, shadow=True)
    d.text("T2", "FOCUS  ·  BREATHE  ·  REPEAT", 1.3, 4.8, 0.37, 0.02, "#1e2a10", SANS,
           weight=700, tracking=0.015, plate="#d8f0a8", radius=0.5, pad=(0.016, 0.007))
    d.fades()
    return d


def tape_hiss():
    d = Doc("Tape Hiss", "16:9", 3 * 4.5)
    scenes(d, "video", 3, 4.5, "concat.glitch-transition", fg_scale=0.92, blur=30,
           aberration={}, trans_seconds=0.5)
    looks(d, [("concat.vhs", 0.9), ("concat.super-8", 0.6), ("concat.film-grain", 0.7),
              ("concat.vignette", 0.5)])
    blink = []
    for n in range(0, 16):
        blink.append(key("opacity", n * 0.03, 1.0 if n % 2 == 0 else 0.0, LINEAR))
    d.shape("DECO", "circle", 0.032, "#ff3b30", 0.0, d.total, name="rec", offsetX=-0.4,
            offsetY=-0.4, keys=blink)
    d.text("T1", "REC  ● SP", 0.0, d.total, -0.43, 0.04, "#ffffff", MONO, weight=700,
           tracking=0.04, x=-0.33, hold=False, slide=0, shadow=True)
    d.text("T1", "PLAY ▶", 0.0, d.total, -0.43, 0.04, "#ffffff", MONO, weight=700,
           tracking=0.04, x=0.36, hold=False, slide=0, shadow=True)
    d.text("T2", "lo-fi tape", 0.8, 5.2, 0.34, 0.12, "#ffe8d6", MONO, weight=700, tracking=0.02,
           shadow=True, stroke=0.004, stroke_color="#ff3b6b")
    d.text("T2", "SIDE B  ·  NO SIGNAL", 1.3, 4.7, 0.42, 0.03, "#1a0a10", MONO, weight=700,
           tracking=0.03, plate="#ffd9c0", radius=0.15, pad=(0.016, 0.008))
    d.fades()
    return d


def falling_dust():
    d = Doc("Falling Dust", "9:16", 5 * 3.5)
    scenes(d, "image", 5, 3.5, "concat.light-leak-transition", fg_scale=0.9, glow={},
           trans_seconds=0.9)
    looks(d, [("concat.umber", 0.95), ("concat.falling-dust", 0.9), ("concat.film-grain", 0.4),
              ("concat.vignette", 0.55)])
    d.shape("DECO", "line", 0.5, "#ffe0a8", 0.7, 4.4, name="rule", stroke="#ffe0a8",
            stroke_width=0.0025, offsetY=-0.325, keys=fade_keys(0.15, 0.85, 0.9))
    d.border("#ffe0a8", 0.035)
    d.text("T1", "golden dust", 0.7, 4.4, -0.37, 0.085, "#fff0d6", SERIF, italic=True, shadow=True)
    d.text("T2", "AUTUMN  ·  SLOW LIGHT", 1.1, 4.0, -0.285, 0.021, "#ffe0a8", SANS, weight=700,
           tracking=0.03, shadow=True)
    d.fades()
    return d


def midnight_city():
    d = Doc("Midnight City", "16:9", 4 * 4.5)
    scenes(d, "video", 4, 4.5, "concat.zoom-blur-transition", fg_scale=0.9, blur=38,
           glow={}, aberration={}, trans_seconds=0.7)
    looks(d, [("concat.midnight", 1.0), ("concat.cool-blue", 0.55), ("concat.bloom-pulse", 0.5),
              ("concat.film-grain", 0.35), ("concat.vignette", 0.6)])
    d.bars(0.11)
    d.shape("DECO", "square", 1.0, "#38e1ff", 1.0, 5.0, name="neon bar", scale=0.07,
            stretchX=0.16, stretchY=3.2, offsetX=-0.285, offsetY=0.3, keys=fade_keys())
    d.border("#38e1ff", 0.03, 0.002, 0.7)
    d.text("T1", "midnight city", 1.0, 5.0, 0.285, 0.1, "#e6f4ff", SANS, weight=700,
           tracking=0.03, align="left", x=-0.1, shadow=True)
    d.text("T2", "AFTER HOURS  ·  NEON  ·  RAIN", 1.4, 4.6, 0.36, 0.026, "#031a22", SANS,
           weight=700, tracking=0.03, align="left", x=-0.04, plate="#38e1ff", radius=0.2,
           pad=(0.014, 0.007))
    d.fades()
    return d


def tho_tram():
    """A page of verse on warm paper for a poetry page: no footage, only words, so there
    are no slots. The poem, its title and its author are placeholders to retype; the
    page's own name is fixed. Centred, with an ornament and a hairline frame, in
    Georgia italic (a soft face a stock install has that carries Vietnamese tone marks)."""
    d = Doc("Thơ Trạm 1990s", "9:16", 10.0)
    paper, ink, soft = "#efe5d0", "#33261a", "#6d5a43"
    d.shape("BG", "square", 1.0, paper, 0.0, d.total, name="paper", scale=3.0)
    looks(d, [("concat.film-grain", 0.35), ("concat.vignette", 0.3)])
    d.border(soft, 0.045, 0.0018, 0.55)
    # An ornament over the verse: a dot above a short rule.
    d.shape("DECO", "circle", 0.011, soft, 0.3, 9.4, name="dot", offsetY=-0.2,
            keys=fade_keys(0.1, 0.9, 0.9))
    d.shape("DECO", "line", 0.06, soft, 0.5, 9.2, name="ornament rule", stroke=soft,
            stroke_width=0.0016, offsetY=-0.175, keys=fade_keys(0.1, 0.9, 0.9))
    d.text("T1", "Dòng thơ thứ nhất\nDòng thơ thứ hai\nDòng thơ thứ ba\nDòng thơ thứ tư",
           0.6, 9.0, -0.03, 0.031, ink, SERIF, italic=True, hold=False, slide=0.02)
    d.text("T2", "\u201cTên bài thơ\u201d", 1.5, 8.2, 0.13, 0.019, soft, SERIF,
           italic=True, hold=False, slide=0)
    d.text("T2", "TÊN TÁC GIẢ", 1.8, 7.9, 0.165, 0.0165, ink, SERIF, weight=700,
           tracking=0.04, hold=False, slide=0)
    d.shape("DECO", "line", 0.04, soft, 2.2, 7.5, name="page rule", stroke=soft,
            stroke_width=0.0016, offsetY=0.395, keys=fade_keys(0.1, 0.9, 0.9))
    d.text("T3", "TRẠM 1990s", 2.2, 7.5, 0.425, 0.0185, soft, SERIF, weight=700,
           tracking=0.035, hold=False, slide=0)
    d.fades(paper, 1.0)
    return d


# A verse wraps inside this share of the frame's width: centred, that leaves about 120px
# clear on each side of 1080 (the right hand one less, the buttons being lower), inside the edge the right-hand buttons of TikTok and Reels take.
WRAP = 0.78


def tho_over_video(name, total, pages=None):
    """The poem set over the footage itself, which is dimmed so the words stand clear; the
    footage's own blurred copy shows at the edges of a frame that is not upright. The verse
    sits just above the middle with room to run long, its title and author below it and the
    page's name above it, all inside the frame TikTok and Reels leave clear: about 250px
    from the top, 480px from the bottom and 180px from the right of a 1080x1920 frame. One video slot; the verse, title and author are placeholders to retype.

    `pages` is None for a verse that stands still, or a list of verses that follow one another
    in the same place, each one's words arriving in reading order as the page's clip plays:
    Word Reveal's Progress rides from 0 to 100 across the clip, so a page is timed by its
    clip, and trimming or stretching the clip to a voice's length times the words to it."""
    d = Doc(name, "9:16", total)
    scenes(d, "video", 1, total, "concat.dissolve", fg_scale=0.96, blur=36, drift=0.04)
    for n, (eid, params, strength) in enumerate([
            ("concat.vintage", dict(age=70.0, tint=55.0), 1.0), ("concat.warm", {}, 0.35),
            ("concat.film-grain", {}, 0.4), ("concat.vignette", {}, 0.7)]):
        want(eid, "filter", "effect")
        c = d.add("L", "layer", eid.removeprefix("concat."), 0.0, d.total, opacity=strength)
        c["videoEffects"] = [d.effect(eid, **params)]
    # The way in: a cascade of blurs, each a veil over the one before it, that thin out
    # one after another and with eased ends, so the picture comes into focus in small steps
    # rather than one or two visible ones. Three, not more: every layer is a full-frame blur
    # on each frame, and past three the preview starts to drop frames. (Pixelating it first read as blocks
    # fading, not as focus arriving.)
    for n, (radius, seconds) in enumerate([(3, 3.6), (9, 3.0), (24, 2.4)]):
        c = d.add("L", "layer", f"focus {n + 1}", 0.0, seconds, opacity=1.0,
                  keys=[key("opacity", 0.0, 1.0, LINEAR), key("opacity", 0.12, 1.0, EASE_IN_OUT),
                        key("opacity", 1.0, 0.0, EASE_IN_OUT)])
        c["videoEffects"] = [d.effect("concat.gaussian-blur", radius=float(radius))]
    # The dimming: black over the picture and its backdrop, under the words.
    d.shape("DECO", "square", 1.0, "#000000", 0.0, d.total, name="dim", scale=3.0, opacity=0.5)
    cream, soft = "#f6ecd9", "#d6c4a3"
    d.text("T1", "TRẠM 1990s", 0.8, total - 1.0, -0.335, 0.0165, soft, SERIF, weight=700,
           tracking=0.035, hold=False, slide=0, shadow=True)
    d.shape("DECO", "line", 0.04, soft, 0.8, total - 1.0, name="page rule", stroke=soft,
            stroke_width=0.0016, offsetY=-0.31, keys=fade_keys(0.1, 0.9, 0.9))
    if pages is None:
        d.text("T2", "Dòng thơ thứ nhất\nDòng thơ thứ hai\nDòng thơ thứ ba\nDòng thơ thứ tư",
               1.2, 8.6, -0.05, 0.028, cream, SERIF, italic=True, hold=False, slide=0, shadow=True, max_width=WRAP)
    else:
        want("concat.word-reveal", "effect")
        span = (total - 2.2) / len(pages)
        for n, verse in enumerate(pages):
            start = 1.2 + n * span
            length = span - 0.4
            c = d.text("T2", verse, start, length, -0.05, 0.028, cream, SERIF, italic=True,
                       hold=False, slide=0, shadow=True, max_width=WRAP)
            # Each page is whole at once, then leaves; its words come in with Progress.
            c["keys"] = [key("opacity", 0.0, 1.0, LINEAR), key("opacity", 1.0 - 0.4 / length, 1.0, LINEAR),
                         key("opacity", 1.0, 0.0, LINEAR)]
            reveal = d.effect("concat.word-reveal", progress=100.0)
            reveal["keys"] = {"progress": [
                {k: v for k, v in key("progress", at, value, LINEAR).items() if k != "property"}
                for at, value in ((0.0, 0.0), (0.9, 100.0), (1.0, 100.0))]}
            c["videoEffects"] = [reveal]
    d.text("T3", "\u201cTên bài thơ\u201d", 2.0, total - 2.2, 0.2, 0.018, soft, SERIF, italic=True,
           hold=False, slide=0, shadow=True)
    d.text("T3", "TÊN TÁC GIẢ", 2.3, total - 2.5, 0.226, 0.0155, cream, SERIF, weight=700,
           tracking=0.04, hold=False, slide=0, shadow=True)
    d.fades("#0c0805", 1.0)
    return d


def tho_hoai_co():
    return tho_over_video("Thơ Hoài Cổ", 10.0)


def tho_chay_chu_2():
    """A verse of up to eight lines on two pages of four, its words arriving as they are read:
    each placeholder page is timed for a voice of about nine seconds, and trimming a page's
    clip to the read times the words to it."""
    pages = [f"Trang {n}, dòng thứ {w}" for n in ("một", "hai") for w in ("nhất", "hai", "ba", "tư")]
    return tho_over_video("Thơ Hoài Cổ Chạy Chữ 2 Trang", 20.0,
                          ["\n".join(pages[i:i + 4]) for i in (0, 4)])


def tho_chay_chu():
    """A verse of more than eight lines on three pages of up to six, its words arriving as they
    are read; a verse of fewer pages needs only the others deleted."""
    pages = [f"Trang {n}, dòng thứ {w}" for n in ("một", "hai", "ba")
             for w in ("nhất", "hai", "ba", "tư", "năm", "sáu")]
    return tho_over_video("Thơ Hoài Cổ Chạy Chữ Nhiều Trang", 30.0,
                          ["\n".join(pages[i:i + 6]) for i in (0, 6, 12)])


TEMPLATES = [tho_tram, tho_hoai_co, tho_chay_chu_2, tho_chay_chu]


def slug(name):
    name = unicodedata.normalize("NFD", name.replace("đ", "d").replace("Đ", "D"))
    name = "".join(ch for ch in name if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def default_out():
    if sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    elif sys.platform.startswith("win"):
        base = Path(os.environ["APPDATA"])
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "app.concat.editor/templates"


def main():
    check_catalogue()
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else default_out()
    only = sys.argv[2:]
    for build in TEMPLATES:
        if only and build.__name__ not in only:
            continue
        doc = build()
        root = out / slug(doc.name)
        (root / "assets").mkdir(parents=True, exist_ok=True)
        (root / "template.json").write_text(json.dumps(doc.document(), indent=2) + "\n")
        print(f"{doc.name:18} {doc.width}x{doc.height}  {len(doc.media)} slots  -> {root}")


if __name__ == "__main__":
    main()
