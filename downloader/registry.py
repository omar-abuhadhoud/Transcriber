"""Which platforms exist, and how to reach their adapters.

Shaped like transcriber/registry.py on purpose: a table of names to classes, imported
lazily, so the app never depends on a provider module and adding a platform is one
entry here plus one file in providers/.

Order in PROVIDERS is the order the tiles appear on the download page.
"""

import importlib
from collections import namedtuple

ProviderSpec = namedtuple("ProviderSpec", "module class_name")

PROVIDERS = {
    "youtube": ProviderSpec("downloader.providers.youtube", "YouTubeDownloader"),
    "instagram": ProviderSpec("downloader.providers.instagram", "InstagramDownloader"),
    "tiktok": ProviderSpec("downloader.providers.tiktok", "TikTokDownloader"),
    "facebook": ProviderSpec("downloader.providers.facebook", "FacebookDownloader"),
}

# One instance per platform, reused. Adapters are stateless, so this is only to avoid
# re-importing on every click.
_instances = {}


def provider_names():
    return list(PROVIDERS)


def get_provider(name):
    """The adapter for one platform, importing its module on first use."""
    if name in _instances:
        return _instances[name]

    spec = PROVIDERS.get(name)
    if spec is None:
        available = ", ".join(PROVIDERS)
        raise ValueError("Unknown provider '" + str(name) + "'. Available: " + available)

    provider_class = getattr(importlib.import_module(spec.module), spec.class_name)
    _instances[name] = provider_class()
    return _instances[name]


def all_providers():
    """Every adapter, in tile order."""
    return [get_provider(name) for name in PROVIDERS]


def provider_for_url(url):
    """The adapter that recognises this link, or None.

    Used to tell someone who pasted a TikTok link into the YouTube box which tile they
    actually wanted, rather than letting the download fail later with a worse message.
    """
    for provider in all_providers():
        if provider.matches(url):
            return provider
    return None
