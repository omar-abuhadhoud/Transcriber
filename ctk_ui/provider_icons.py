"""The mark on each download tile.

These are original glyphs, not the platforms' logos. The real Instagram, Facebook,
TikTok and YouTube marks are registered trademarks, and shipping redrawn copies of
them inside an application is not something this project should do. What is drawn here
is a plain generic symbol for the kind of thing the platform holds -- a play triangle,
a camera outline, a music note, a speech bubble -- on that platform's familiar colour,
with the platform's name printed underneath it on the tile. In practice the colour and
the name are what a person recognises anyway.

If you hold a licence for the official assets, drop a square PNG at

    ctk_ui/assets/providers/<provider name>.png      e.g. .../instagram.png

and it is used instead, with no code change. That folder is checked first every time.

Everything is drawn at four times the final size and scaled down, because Pillow's
shape primitives do not antialias and a 64 px circle drawn directly has visibly ragged
edges on a dark background.
"""

import os

from transcriber.paths import resource_path

SUPERSAMPLE = 4

# Squares of transparent margin around the glyph, as a fraction of the icon, so the
# marks sit at a consistent visual weight rather than each filling its own box.
PADDING = 0.16

_cache = {}


def icon_for(info, size=64):
    """A CTkImage for one provider, cached.

    Returns None when Pillow is unavailable, which lets the tile fall back to drawing
    a plain coloured square rather than failing to build.
    """
    key = (info.name, size)
    if key in _cache:
        return _cache[key]

    try:
        import customtkinter as ctk
        from PIL import Image
    except Exception:
        return None

    try:
        image = _custom_image(info.name, size) or _drawn_image(info, size)
        icon = ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))
    except Exception:
        return None

    _cache[key] = icon
    return icon


def _custom_image(name, size):
    """A PNG the user supplied, if there is one."""
    from PIL import Image

    path = resource_path(os.path.join("ctk_ui", "assets", "providers", name + ".png"))
    if not os.path.exists(path):
        return None

    try:
        with Image.open(path) as handle:
            return handle.convert("RGBA").resize((size, size), Image.LANCZOS)
    except Exception:
        # A corrupt or unreadable drop-in file falls back to the drawn glyph rather
        # than taking the whole page down with it.
        return None


def _drawn_image(info, size):
    from PIL import Image, ImageDraw

    scale = size * SUPERSAMPLE
    image = Image.new("RGBA", (scale, scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # A rounded square in the platform's colour, with the mark knocked out in white.
    radius = scale * 0.26
    draw.rounded_rectangle([0, 0, scale - 1, scale - 1], radius=radius, fill=info.accent)

    inset = scale * PADDING
    box = (inset, inset, scale - inset, scale - inset)

    # Keyed by the style's glyph name, not the provider's, so two platforms can share
    # a mark and a new platform can pick an existing one.
    painter = _GLYPHS.get(getattr(info, "glyph", ""), _glyph_play)
    painter(draw, box)

    return image.resize((size, size), Image.LANCZOS)


# --------------------------------------------------------------------- the glyphs
#
# Each takes the drawing surface and the box to fill. All white, because they are
# knocked out of a saturated colour.

WHITE = (255, 255, 255, 255)


def _glyph_play(draw, box):
    """A play triangle. Video, generically."""
    left, top, right, bottom = box
    width = right - left
    height = bottom - top

    # Nudged right of centre: a triangle centred on its bounding box reads as sitting
    # too far left, because its visual mass is at the blunt end.
    x = left + width * 0.30
    draw.polygon(
        [
            (x, top + height * 0.16),
            (x, bottom - height * 0.16),
            (left + width * 0.84, top + height * 0.5),
        ],
        fill=WHITE,
    )


def _glyph_camera(draw, box):
    """A camera body with a viewfinder bump and a lens. Photo and video, generically.

    Drawn as the familiar wide camera silhouette rather than a rounded square around a
    circle, which is a shape too close to a mark this project has no licence to use.
    """
    left, top, right, bottom = box
    width = right - left
    height = bottom - top

    body_top = top + height * 0.26
    body_bottom = bottom - height * 0.08

    # The viewfinder bump, over the left of the body.
    draw.rounded_rectangle(
        [left + width * 0.14, top + height * 0.10, left + width * 0.44, body_top + height * 0.08],
        radius=width * 0.05,
        fill=WHITE,
    )

    draw.rounded_rectangle(
        [left, body_top, right, body_bottom],
        radius=width * 0.12,
        fill=WHITE,
    )

    # The lens, punched out so it takes the tile's colour.
    centre_x = left + width * 0.5
    centre_y = body_top + (body_bottom - body_top) * 0.52
    lens = width * 0.20
    draw.ellipse(
        [centre_x - lens, centre_y - lens, centre_x + lens, centre_y + lens],
        fill=(0, 0, 0, 0),
    )


def _glyph_note(draw, box):
    """A music note. Sound, generically."""
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    stroke = max(2, int(width * 0.10))

    stem_x = left + width * 0.66
    stem_top = top + height * 0.06

    # Stem.
    draw.line([(stem_x, stem_top), (stem_x, bottom - height * 0.20)], fill=WHITE, width=stroke)

    # Flag, as two strokes rather than a curve: at this size a drawn bezier reads as
    # a smudge, while two straight segments stay crisp.
    flag_x = left + width * 0.96
    draw.line([(stem_x, stem_top), (flag_x, top + height * 0.20)], fill=WHITE, width=stroke)
    draw.line(
        [(stem_x, stem_top + height * 0.20), (flag_x, top + height * 0.40)],
        fill=WHITE,
        width=stroke,
    )

    # Note head.
    head = width * 0.20
    head_x = stem_x - head
    head_y = bottom - height * 0.20
    draw.ellipse([head_x - head, head_y - head * 0.78, head_x + head, head_y + head * 0.78], fill=WHITE)


def _glyph_bubble(draw, box):
    """A speech bubble with a play triangle in it. Shared video, generically."""
    left, top, right, bottom = box
    width = right - left
    height = bottom - top

    body_bottom = bottom - height * 0.22
    draw.rounded_rectangle(
        [left, top, right, body_bottom],
        radius=width * 0.22,
        fill=WHITE,
    )

    # Tail, sitting under the left of the body.
    draw.polygon(
        [
            (left + width * 0.22, body_bottom - height * 0.04),
            (left + width * 0.48, body_bottom - height * 0.04),
            (left + width * 0.26, bottom),
        ],
        fill=WHITE,
    )

    # The triangle is punched out of the bubble, so it takes the tile's own colour.
    centre_y = top + (body_bottom - top) * 0.5
    draw.polygon(
        [
            (left + width * 0.38, centre_y - height * 0.15),
            (left + width * 0.38, centre_y + height * 0.15),
            (left + width * 0.66, centre_y),
        ],
        fill=(0, 0, 0, 0),
    )


# Named by shape, not by platform: these are generic marks, and which platform uses
# which is decided in provider_style.py.
_GLYPHS = {
    "play": _glyph_play,
    "camera": _glyph_camera,
    "note": _glyph_note,
    "bubble": _glyph_bubble,
}
