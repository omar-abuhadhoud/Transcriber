"""Turning a caption into a filename Windows will actually accept.

Downloaded audio is named after the video's title or caption, because that is the only
thing about a reel a person recognises later. Captions are not filenames, though: they
carry newlines, emoji, colons, slashes and occasionally nothing at all, and on Windows
several perfectly ordinary words are reserved device names.

Non-ASCII is deliberately kept. The app transcribes Arabic, so most titles are Arabic,
and stripping them to ASCII would name every file "".
"""

import os
import re

# Characters Windows forbids in a filename, plus the C0 control range, which a pasted
# caption can genuinely contain.
#
# Built with re.escape from a plain list rather than written out as a character class.
# A backslash inside a hand-written class is one edit away from reading as an escape
# for the character after it -- which is exactly the bug this replaced, where the
# pattern said \| and so matched a pipe while quietly letting backslashes through into
# filenames.
FORBIDDEN = '<>:"/|?*' + chr(92)

ILLEGAL = re.compile("[" + re.escape(FORBIDDEN) + "\\x00-\\x1f]")

# Reserved device names. "CON.m4a" cannot be created at all, and the failure reads as a
# permissions problem rather than the naming problem it is.
RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{n}" for n in range(1, 10)),
    *(f"LPT{n}" for n in range(1, 10)),
}

# Well under MAX_PATH once the provider folder and extension are added, and short
# enough that Explorer shows the whole name.
MAX_STEM = 110


def safe_stem(title, fallback="audio"):
    """A caption reduced to a legal, readable filename stem."""
    stem = ILLEGAL.sub(" ", str(title or ""))

    # Newlines and runs of spaces come from captions written as several lines.
    stem = re.sub(r"\s+", " ", stem).strip()

    # Windows silently drops trailing dots and spaces, so a name ending in one is not
    # the name that ends up on disk. Removed here instead, where it is visible.
    stem = stem.rstrip(". ")

    if len(stem) > MAX_STEM:
        # Cut on a word boundary when there is one near the limit, so the name ends in
        # a word rather than mid-syllable.
        stem = stem[:MAX_STEM]
        cut = stem.rfind(" ")
        if cut > MAX_STEM * 0.6:
            stem = stem[:cut]
        stem = stem.rstrip(". ")

    if stem.split(".")[0].upper() in RESERVED:
        stem = "_" + stem

    # Emoji-only and caption-less posts both land here; Reels frequently have no
    # caption at all.
    return stem or fallback


def unique_path(folder, stem, extension):
    """A path in `folder` that nothing occupies yet.

    Two different reels genuinely can share a caption, and the second must not
    overwrite the first, so a counter is appended rather than the name reused.
    """
    extension = extension if extension.startswith(".") else "." + extension
    candidate = os.path.join(folder, stem + extension)
    if not os.path.exists(candidate):
        return candidate

    for counter in range(2, 1000):
        candidate = os.path.join(folder, f"{stem} ({counter}){extension}")
        if not os.path.exists(candidate):
            return candidate

    # A thousand identical captions is not a real case, but returning None here would
    # surface as a confusing crash much later.
    raise RuntimeError(f"Could not find a free filename for '{stem}' in {folder}")
