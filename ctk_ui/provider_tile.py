"""One square on the download page: a platform's mark, with its name underneath.

The same component for all four. Nothing in it names a platform -- it takes a
ProviderInfo from downloader/registry.py and draws whatever that describes, so a fifth
platform appears on the page as soon as it is registered, with no change here.
"""

import customtkinter as ctk

from ctk_ui import theme
from ctk_ui.provider_icons import icon_for
from ctk_ui.theme import ui_font

TILE_SIZE = 108
ICON_SIZE = 60


class ProviderTile(ctk.CTkFrame):
    """A square button showing a platform's mark, with its label below."""

    def __init__(self, master, info, command, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self.info = info
        self.command = command

        self.icon = icon_for(info, ICON_SIZE)

        self.button = ctk.CTkButton(
            self,
            text="" if self.icon else info.label[0],
            image=self.icon,
            width=TILE_SIZE,
            height=TILE_SIZE,
            corner_radius=16,
            fg_color=info.accent,
            hover_color=info.hover,
            # Only reached when Pillow could not draw the mark; the tile still works
            # and still says which platform it is, in the label underneath.
            font=ui_font(34, "bold"),
            text_color="white",
            command=self._clicked,
        )
        self.button.pack()

        self.label = ctk.CTkLabel(
            self,
            text=info.label,
            font=ui_font(13, "bold"),
            text_color=("gray20", "gray88"),
        )
        self.label.pack(pady=(8, 0))

        # Clicking the name is the same as clicking the square: the two read as one
        # control, so they behave as one.
        self.label.configure(cursor="hand2")
        self.label.bind("<Button-1>", lambda _e: self._clicked())
        self.label.bind("<Enter>", lambda _e: self.label.configure(text_color=info.accent))
        self.label.bind("<Leave>", lambda _e: self.label.configure(
            text_color=("gray20", "gray88")))

    def _clicked(self):
        if self.command:
            self.command(self.info)

    def set_enabled(self, enabled):
        self.button.configure(state="normal" if enabled else "disabled")


def tile_grid(master, infos, command, columns=4, pad=18):
    """Lay every provider out as a responsive grid of tiles.

    Returns the frame holding them, so the caller only has to place one widget.
    """
    grid = ctk.CTkFrame(master, fg_color="transparent")

    tiles = []
    for index, info in enumerate(infos):
        row, column = divmod(index, columns)
        tile = ProviderTile(grid, info, command)
        tile.grid(row=row, column=column, padx=pad, pady=pad, sticky="n")
        tiles.append(tile)

    for column in range(min(columns, max(1, len(infos)))):
        grid.grid_columnconfigure(column, weight=1)

    grid.tiles = tiles
    return grid
