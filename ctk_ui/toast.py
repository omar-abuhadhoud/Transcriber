"""Corner notifications, for things that finish while you are looking elsewhere.

A download can land while the queue page is on screen, or while the window is behind
something else. A message box would steal focus and demand a click for news that needs
neither, so these appear in the bottom-right, say what happened, and leave on their own.

Placed inside the main window rather than as separate toplevels: an override-redirect
toplevel on Windows takes focus unpredictably, floats above other applications even
when Transcriber is not the active window, and has to be moved by hand whenever the
main window moves. A frame placed in the root does none of that.

There is deliberately no container frame holding the stack. An earlier version had one,
with fg_color="transparent", and it left a dark rectangle sitting over the page after
the last notification expired. Tk has no real transparency: CustomTkinter resolves
"transparent" to the *master's* colour, which here is the dark root window, while the
page underneath is a lighter grey -- so the container painted a dark patch wherever it
overlapped, and it stayed placed, at the size of its last contents, once they were gone.

Each notification is therefore placed in the window on its own and positioned by
_relayout(). When the last one is dismissed there is simply no widget left to paint
anything, which is the only way for this to leave nothing behind.
"""

import customtkinter as ctk

from ctk_ui import theme
from ctk_ui.theme import ui_font

# Long enough to read a filename, short enough not to sit over the queue.
DEFAULT_TIMEOUT_MS = 6000

# Beyond this the stack starts covering the page it is meant to sit beside, so the
# oldest goes to make room.
MAX_VISIBLE = 4

KIND_COLORS = {
    "success": theme.SUCCESS,
    "error": theme.DANGER,
    "info": theme.ACCENT,
}


class ToastHost:
    """The stack in the corner. One per window.

    Not a widget. It owns a list of notifications and decides where each one sits;
    the notifications themselves are placed directly in the window.
    """

    def __init__(self, master, margin=20, gap=8):
        self.master = master
        self.margin = margin
        self.gap = gap
        self.toasts = []

    def place_in_corner(self, margin=None):
        """Kept for the caller's benefit; there is nothing to place until a toast exists."""
        if margin is not None:
            self.margin = margin

    def show(self, title, detail="", kind="info", timeout=DEFAULT_TIMEOUT_MS, on_click=None):
        """Add a notification. Returns it, mostly so a test can dismiss it."""
        if not self._alive():
            return None

        while len(self.toasts) >= MAX_VISIBLE:
            self._dismiss(self.toasts[0])

        toast = _Toast(self, title, detail, kind, on_click=on_click)
        self.toasts.append(toast)
        self._relayout()

        if timeout:
            toast.after(timeout, lambda: self._dismiss(toast))
        return toast

    def lift(self):
        """Raise every notification above the page.

        The pages are gridded into the same window, so one shown after a notification
        was placed would otherwise be drawn over it.
        """
        for toast in self.toasts:
            try:
                toast.lift()
            except Exception:
                pass

    # ------------------------------------------------------------------- internals

    def _alive(self):
        try:
            return bool(self.master.winfo_exists())
        except Exception:
            return False

    def _dismiss(self, toast):
        if toast in self.toasts:
            self.toasts.remove(toast)
        try:
            # place_forget before destroy so the window reclaims the area even if the
            # destroy itself is what is racing with the window closing.
            toast.place_forget()
            toast.destroy()
        except Exception:
            # Already gone, because the window is closing.
            pass
        self._relayout()

    def _relayout(self):
        """Stack the notifications upward from the bottom-right corner."""
        if not self._alive():
            return

        try:
            self.master.update_idletasks()
        except Exception:
            return

        offset = self.margin
        # Newest nearest the corner, which is where the eye already is.
        for toast in reversed(self.toasts):
            if not toast.winfo_exists():
                continue
            toast.place(relx=1.0, rely=1.0, anchor="se", x=-self.margin, y=-offset)
            toast.lift()
            offset += toast.winfo_reqheight() + self.gap


class _Toast(ctk.CTkFrame):
    """One notification: a coloured edge, a line of what happened, and a close cross."""

    def __init__(self, host, title, detail, kind, on_click=None):
        # Placed in the window itself, not inside the host, so that nothing but the
        # notification is ever drawn over the page.
        super().__init__(
            host.master,
            fg_color=theme.TOAST_FG,
            border_color=theme.TOAST_BORDER,
            border_width=1,
            corner_radius=8,
            width=330,
            height=1,
        )
        self.host = host
        self.on_click = on_click

        stripe = ctk.CTkFrame(
            self,
            fg_color=KIND_COLORS.get(kind, theme.ACCENT),
            width=4,
            # Without this the stripe asks for a CTkFrame's default 200px and, being
            # filled vertically, drags the whole notification to that height. It is
            # stretched to the real height by fill="y" regardless.
            height=1,
            corner_radius=2,
        )
        stripe.pack(side="left", fill="y", padx=(6, 0), pady=6)

        close = ctk.CTkButton(
            self,
            text="×",
            width=22,
            height=22,
            corner_radius=4,
            fg_color="transparent",
            hover_color=theme.TAB_HOVER,
            text_color=theme.TOAST_DETAIL,
            font=ui_font(15),
            command=lambda: host._dismiss(self),
        )
        close.pack(side="right", padx=(0, 6), pady=6)

        text = ctk.CTkFrame(self, fg_color="transparent", width=1, height=1)
        text.pack(side="left", fill="both", expand=True, padx=10, pady=8)

        self.lbl_title = ctk.CTkLabel(
            text,
            text=title,
            font=ui_font(12, "bold"),
            text_color=theme.TOAST_TEXT,
            anchor="w",
            justify="left",
            wraplength=250,
        )
        self.lbl_title.pack(anchor="w", fill="x")

        self.lbl_detail = None
        if detail:
            self.lbl_detail = ctk.CTkLabel(
                text,
                text=detail,
                font=ui_font(11),
                text_color=theme.TOAST_DETAIL,
                anchor="w",
                justify="left",
                wraplength=250,
            )
            self.lbl_detail.pack(anchor="w", fill="x", pady=(2, 0))

        if on_click:
            # Bound on the children too, because they cover the frame entirely and a
            # click never reaches it.
            for widget in (self, text, self.lbl_title, self.lbl_detail):
                if widget is not None:
                    widget.bind("<Button-1>", self._clicked)
                    widget.configure(cursor="hand2")

    def _clicked(self, _event=None):
        self.host._dismiss(self)
        if self.on_click:
            self.on_click()
