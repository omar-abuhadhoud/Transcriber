"""Single source of truth for the app version and its release channel.

Read by the app (window title and update check), by installer/build_installer.ps1
(which stamps the setup exe) and by installer/provision.py (which records what it
installed), so a build can always be identified from the outside.

Bump __version__ for every release. The updater compares this value with the newest
GitHub release tag, so a release whose tag does not match what shipped inside the app
will offer itself forever.
"""

__version__ = "1.0.0"

# Windows file-version resources need exactly four integers.
VERSION_TUPLE = tuple(int(part) for part in __version__.split(".")) + (0,)

# Where the updater looks for newer builds, and where the installer's own update
# check points. "owner/name" as GitHub's API spells it.
GITHUB_REPO = "omar-abuhadhoud/Transcriber"

# The setup exe attached to every release, formatted with the release version.
INSTALLER_ASSET = "TranscriberSetup-{version}.exe"


def parse_version(text):
    """Turn "v1.2.3" or "1.2.3" into (1, 2, 3) for comparison.

    Non-numeric parts sort as 0 rather than raising, so a malformed tag on the
    releases page can never crash the app's startup update check.
    """
    cleaned = str(text or "").strip().lstrip("vV")
    parts = []
    for chunk in cleaned.split(".")[:3]:
        digits = ""
        for char in chunk:
            if not char.isdigit():
                break
            digits += char
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer(candidate, current=__version__):
    """True when `candidate` is a strictly newer release than `current`."""
    return parse_version(candidate) > parse_version(current)
