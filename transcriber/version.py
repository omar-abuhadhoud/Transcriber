"""Single source of truth for the app version.

Read by the app (window title), by Transcriber.spec (exe file properties) and by any
installer script, so a build can always be identified from the outside.
"""

__version__ = "1.0.0"

# Windows file-version resources need exactly four integers.
VERSION_TUPLE = tuple(int(part) for part in __version__.split(".")) + (0,)
