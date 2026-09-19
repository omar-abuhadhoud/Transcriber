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
