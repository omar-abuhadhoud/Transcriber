# Custom provider icons

Drop a square PNG here named after a provider and it replaces the glyph drawn by
`ctk_ui/provider_icons.py` on that platform's tile, with no code change:

```
youtube.png      instagram.png      tiktok.png      facebook.png
```

The name must match the provider's `name` in `downloader/registry.py`. Anything square
works; 128x128 or larger looks best, and transparency is preserved. A file that cannot
be read is ignored and the drawn glyph is used instead.

This folder is empty on purpose. Transcriber ships original generic marks rather than
the platforms' own logos, because those are registered trademarks the project has no
licence to redraw and distribute. If you hold that licence, this is where the official
assets go.
