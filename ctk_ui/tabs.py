"""The strip that switches between the queue and the download page.

Hand-built rather than a CTkTabview, for the same reason the dropdowns are hand-built:
CTkTabview owns the frames it shows and draws its own header, which cannot be styled to
match the buttons beside it, and the pages here need to outlive being switched away
from -- a download must keep running while the queue is on screen, and the queue's
worker must keep going while someone is pasting a link.

So this widget only draws buttons and reports clicks. The app owns the pages and
decides which one is gridded.
"""

import customtkinter as ctk

from ctk_ui import theme
from ctk_ui.theme import ui_font


class TabBar(ctk.CTkFrame):
    """A row of pill buttons, one of which is active."""

    def __init__(self, master, tabs, command, **kwargs):
        super().__init__(master, fg_color=theme.TAB_BAR_FG, corner_radius=10, **kwargs)

        self.command = command
        self.buttons = {}
        self.active = None

        for key, label in tabs:
            button = ctk.CTkButton(
                self,
                text=label,
                font=ui_font(13, "bold"),
                height=34,
                width=150,
                corner_radius=8,
                fg_color="transparent",
                text_color=theme.TAB_INACTIVE_TEXT,
                hover_color=theme.TAB_HOVER,
                command=lambda k=key: self.select(k),
            )
            button.pack(side="left", padx=4, pady=4)
            self.buttons[key] = button

        if tabs:
            self.select(tabs[0][0])

    def select(self, key):
        """Show `key` as active and tell the app to raise its page."""
        if key not in self.buttons:
            return

        self.active = key
        for name, button in self.buttons.items():
            if name == key:
                button.configure(
                    fg_color=theme.ACCENT,
                    hover_color=theme.ACCENT_HOVER,
                    text_color="white",
                )
            else:
                button.configure(
                    fg_color="transparent",
                    hover_color=theme.TAB_HOVER,
                    text_color=theme.TAB_INACTIVE_TEXT,
                )

        if self.command:
            self.command(key)

    def set_badge(self, key, count):
        """Append a running count to a tab's label, e.g. "Downloads  2".

        This is how a download in progress stays visible from the queue page, which is
        where someone waiting for a transcription will be sitting.
        """
        button = self.buttons.get(key)
        if button is None:
            return

        base = button.cget("text").split("  ")[0]
        button.configure(text=base + ("  " + str(count) if count else ""))
