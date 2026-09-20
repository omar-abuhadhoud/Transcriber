"""How each platform looks and reads on screen.

The downloader package knows how to fetch from Instagram; it has no opinion about what
colour Instagram is. That split is on purpose:

  * downloader/ is imported by the installer, which has no Tk and no window, so a
    colour sitting on an adapter class is dead weight there;
  * the same adapter should be usable from a script or a future different front end
    without dragging a palette along;
  * and when the UI is restyled, nothing under downloader/ should need touching.

So an adapter declares only what it *is* -- name, label, folder, which links are its
own -- and everything about how it is presented is decided here.

A platform with no entry below still works. It gets DEFAULT_STYLE, so registering an
adapter is enough to put a usable tile on the page, and adding its colours here is a
separate, optional step.
"""

from dataclasses import dataclass

from ctk_ui import theme
from downloader import registry


@dataclass(frozen=True)
class ProviderStyle:
    """The presentation half of a provider."""

    accent: str
    hover: str
    # Which mark provider_icons draws. Generic shapes, never a platform's own logo.
    glyph: str
    example_url: str
    login_hint: str


# Each platform's familiar colour, which together with the name under the tile is what
# people actually recognise. The marks themselves are generic -- see provider_icons.
STYLES = {
    "youtube": ProviderStyle(
        accent="#c4302b",
        hover="#9c2622",
        glyph="play",
        example_url="https://www.youtube.com/watch?v=...",
        login_hint="Needed for members-only, private or age-restricted videos.",
    ),
    "instagram": ProviderStyle(
        accent="#c13584",
        hover="#9d2a6a",
        glyph="camera",
        example_url="https://www.instagram.com/reel/...",
        login_hint="Instagram blocks most posts from logged-out clients.",
    ),
    "tiktok": ProviderStyle(
        accent="#2b2b33",
        hover="#3d3d47",
        glyph="note",
        example_url="https://www.tiktok.com/@user/video/...",
        login_hint="Needed for posts from private accounts you follow.",
    ),
    "facebook": ProviderStyle(
        accent="#1877f2",
        hover="#125fc4",
        glyph="bubble",
        example_url="https://www.facebook.com/reel/...",
        login_hint="Needed for posts limited to friends, or to a group you are in.",
    ),
}

DEFAULT_STYLE = ProviderStyle(
    accent=theme.ACCENT,
    hover=theme.ACCENT_HOVER,
    glyph="play",
    example_url="https://...",
    login_hint="Needed for posts that are not public.",
)


@dataclass(frozen=True)
class ProviderView:
    """One provider as the widgets see it: its identity plus its styling.

    Flat on purpose. A tile should read `view.accent`, not `view.style.accent`, and
    nothing in ctk_ui should have to hold both an adapter and a style side by side.
    """

    name: str
    label: str
    accent: str
    hover: str
    glyph: str
    example_url: str
    login_hint: str


def style_for(name):
    return STYLES.get(name, DEFAULT_STYLE)


def view_for(provider):
    """Combine an adapter with its styling. Takes an adapter or a provider name."""
    if isinstance(provider, str):
        provider = registry.get_provider(provider)

    style = style_for(provider.name)
    return ProviderView(
        name=provider.name,
        label=provider.label,
        accent=style.accent,
        hover=style.hover,
        glyph=style.glyph,
        example_url=style.example_url,
        login_hint=style.login_hint,
    )


def all_views():
    """Every registered provider, in tile order."""
    return [view_for(provider) for provider in registry.all_providers()]
