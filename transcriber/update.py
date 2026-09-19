"""Finds newer releases and hands them to the wizard to install.

The app never patches itself. It downloads the same setup exe a person would download
by hand and runs it, so there is exactly one install path to reason about and one place
where "what is already installed?" is decided. Because the install is per-user, that
runs without an administrator prompt.

Everything here is best-effort: no network, a rate-limited API, a malformed tag or a
release with no setup exe attached must all end as "no update found", never as an error
in front of someone who only wanted to transcribe a file.
"""

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

from transcriber.version import (
    GITHUB_REPO,
    INSTALLER_ASSET,
    __version__,
    is_newer,
)

RELEASES_API = "https://api.github.com/repos/{repo}/releases/latest"
RELEASES_PAGE = "https://github.com/{repo}/releases"

# GitHub rejects API requests without one.
USER_AGENT = "Transcriber/{version} (+https://github.com/{repo})".format(
    version=__version__, repo=GITHUB_REPO
)

# Refuse anything that is not plausibly an installer, so a compromised or mistaken
# release cannot get an arbitrary file executed on the user's machine.
MAX_INSTALLER_BYTES = 200 * 1024 * 1024


def releases_page():
    return RELEASES_PAGE.format(repo=GITHUB_REPO)


def _request(url, timeout):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check_for_update(timeout=6.0):
    """The newest release if it is newer than this build, otherwise None.

    Returns a dict of {version, asset_url, asset_name, size, page}.
    """
    if os.environ.get("TRANSCRIBER_NO_UPDATE_CHECK"):
        return None

    try:
        payload = _request(RELEASES_API.format(repo=GITHUB_REPO), timeout)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None

    if not isinstance(payload, dict) or payload.get("draft"):
        return None

    tag = payload.get("tag_name") or payload.get("name") or ""
    if not is_newer(tag):
        return None

    version = str(tag).lstrip("vV")
    wanted = INSTALLER_ASSET.format(version=version).lower()

    chosen = None
    for asset in payload.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        if name.lower() == wanted:
            chosen = asset
            break
        # Fall back to any setup exe, so a release named slightly differently still
        # updates rather than silently offering nothing.
        if chosen is None and name.lower().endswith(".exe") and "setup" in name.lower():
            chosen = asset

    if chosen is None:
        return None

    return {
        "version": version,
        "asset_url": chosen.get("browser_download_url"),
        "asset_name": chosen.get("name"),
        "size": chosen.get("size") or 0,
        "page": releases_page(),
    }


def download_installer(update, progress_callback=None, timeout=30.0):
    """Fetch the setup exe to a temp file and return its path.

    progress_callback(downloaded_bytes, total_bytes) is called as it streams; total is
    0 when the server does not say.
    """
    url = update.get("asset_url")
    if not url:
        raise RuntimeError("That release has no installer attached.")

    name = update.get("asset_name") or INSTALLER_ASSET.format(version=update["version"])
    if not name.lower().endswith(".exe"):
        raise RuntimeError("That release's download is not an installer.")

    target_dir = tempfile.mkdtemp(prefix="transcriber-update-")
    target = os.path.join(target_dir, os.path.basename(name))

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        total = int(response.headers.get("Content-Length") or 0)
        if total > MAX_INSTALLER_BYTES:
            raise RuntimeError("The download is unexpectedly large; refusing it.")

        downloaded = 0
        with open(target, "wb") as file:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > MAX_INSTALLER_BYTES:
                    raise RuntimeError("The download is unexpectedly large; refusing it.")
                file.write(chunk)
                if progress_callback:
                    progress_callback(downloaded, total)

    return target


def launch_installer(installer_path, silent=False):
    """Start the wizard and return, so the caller can close the app.

    The app must exit promptly afterwards: the wizard waits on the app's mutex before
    replacing any file, and a still-running copy would stall it on a "close the
    application" prompt.
    """
    if not os.path.exists(installer_path):
        raise RuntimeError("The downloaded installer is missing.")

    arguments = [installer_path]
    if silent:
        # Progress is still shown; only the question pages are skipped.
        arguments += ["/SILENT", "/SUPPRESSMSGBOXES", "/NOCANCEL"]

    subprocess.Popen(
        arguments,
        close_fds=True,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
    )


def is_managed_install():
    """Whether this copy was installed by the wizard.

    A checkout being run from source has no installer to hand an update to, so the app
    should point at the releases page rather than offer to update itself.
    """
    if not getattr(sys, "frozen", False):
        from transcriber import install_state

        return bool(install_state.installed_app_version())
    return True
