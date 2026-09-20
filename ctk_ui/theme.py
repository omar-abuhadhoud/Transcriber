"""One place for the app's typeface and the styling CustomTkinter does not expose.

Every widget asks for its font through ui_font(), so the app cannot drift back into a
mix of families, and switching typeface is one edit rather than fourteen.
"""

import customtkinter as ctk

# Segoe UI is the Windows system typeface and is what every other application on the
# machine uses; Arial is the fallback for anywhere it is missing.
PREFERRED_FAMILIES = ("Segoe UI", "Inter", "Arial", "Helvetica")

_family = None


def _resolve_family():
    """Pick the first installed family. Cached, and safe before a Tk root exists."""
    global _family
    if _family is not None:
        return _family

    try:
        from tkinter import font as tkfont

        available = set(tkfont.families())
    except Exception:
        # Called before a root window, or on a stripped Tk: decide later.
        available = set()

    for name in PREFERRED_FAMILIES:
        if name in available:
            _family = name
            return _family

    if available:
        _family = "Arial"
        return _family

    # No font list yet, so do not cache a guess -- ask again once Tk is up.
    return "Arial"


def ui_font(size=13, weight=None):
    family = _resolve_family()
    return (family, size) if weight is None else (family, size, weight)


# --- dropdown lists ----------------------------------------------------------------
#
# A CTkOptionMenu's list is a tkinter.Menu, which CustomTkinter styles only partly. Left
# alone it renders a raised border and draws disabled entries in the Tk default, a murky
# yellow that reads as a rendering fault rather than "unavailable".

DROPDOWN_FG = ("gray96", "gray17")
DROPDOWN_HOVER = ("gray86", "gray28")
DROPDOWN_TEXT = ("gray10", "gray90")
DROPDOWN_DISABLED_TEXT = ("gray55", "gray45")
# A quiet edge, where Tk's own menu draws a near-white 3D frame that glares on a dark
# window. The selected row is tinted with the accent the buttons already use.
DROPDOWN_BORDER = ("gray75", "gray30")
DROPDOWN_ROW_SELECTED = ("gray82", "gray32")

# Matched across every dropdown so they open into the same shape.
DROPDOWN_FONT_SIZE = 13


def option_menu(master, **kwargs):
    """A dropdown with the app's shared size, font and list styling."""
    from ctk_ui.dropdown import StyledOptionMenu

    settings = dict(width=190, height=35, corner_radius=8, font=ui_font(13))
    settings.update(kwargs)
    return StyledOptionMenu(master, **settings)


# --- accents -----------------------------------------------------------------------
#
# The blues CustomTkinter's own theme uses for a button, named so the tab strip and the
# notifications can match the buttons rather than approximating them.

ACCENT = "#1f6aa5"
ACCENT_HOVER = "#144870"

SUCCESS = "#2ecc71"
SUCCESS_DIM = "#27ae60"
DANGER = "#c0392b"
MUTED = "gray"

# --- tab strip ---------------------------------------------------------------------

TAB_BAR_FG = ("gray86", "gray17")
TAB_INACTIVE_TEXT = ("gray35", "gray70")
TAB_HOVER = ("gray78", "gray25")

# --- notifications -----------------------------------------------------------------
#
# The toast sits over the page, so it needs its own surface colour rather than the
# frame grey it would otherwise blend into.

TOAST_FG = ("gray92", "gray20")
TOAST_BORDER = ("gray70", "gray32")
TOAST_TEXT = ("gray10", "gray92")
TOAST_DETAIL = ("gray35", "gray65")
