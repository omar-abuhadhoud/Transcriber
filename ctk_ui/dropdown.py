import tkinter as tk

import customtkinter as ctk

from ctk_ui.theme import (
    DROPDOWN_BORDER,
    DROPDOWN_DISABLED_TEXT,
    DROPDOWN_FG,
    DROPDOWN_HOVER,
    DROPDOWN_ROW_SELECTED,
    DROPDOWN_TEXT,
    ui_font,
)


class StyledOptionMenu(ctk.CTkOptionMenu):
    """A CTkOptionMenu whose list the app draws itself.

    Only the list is replaced. The closed button is still CustomTkinter's, so these sit
    beside any other option menu and look identical shut.

    Tk's own menu cannot be styled past a point: it paints a light 3D frame whatever
    borderwidth and relief say, which on a dark theme reads as a bright rectangle around
    the list, and it offers no control over row height or padding. Drawing the list as a
    frame of rows gives all of that back, and lets a single row be greyed out -- which a
    CTkOptionMenu cannot do at all.

    Dismissal has several independent routes on purpose: click outside, click the button
    again, Escape, or move the window. The widget this replaced relied on <FocusOut>
    alone, and when that event did not arrive the list sat on screen with nothing able
    to close it.
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._popup = None
        self._row_font = ui_font(13)

    # ------------------------------------------------------------------ hooks

    def _row_enabled(self, value):
        """Whether this entry can be chosen. Override to grey individual rows out."""
        return True

    def _row_text(self, value):
        return value

    # ------------------------------------------------------------- open/close

    def _open_dropdown_menu(self):
        """Replaces CustomTkinter's call to the Tk menu."""
        if self._popup is not None:
            self._close_popup()
            return
        self._open_popup()

    def _open_popup(self):
        if not self._values:
            return

        popup = tk.Toplevel(self)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        # The window itself is square; the border is drawn by the frame inside it, so
        # the toplevel background must match or a light seam shows at the edges.
        popup.configure(background=self._apply_appearance_mode(DROPDOWN_BORDER))
        self._popup = popup

        frame = ctk.CTkFrame(
            popup,
            corner_radius=0,
            fg_color=DROPDOWN_FG,
            border_width=1,
            border_color=DROPDOWN_BORDER,
        )
        frame.pack(fill="both", expand=True)

        for value in self._values:
            self._build_row(frame, value)

        popup.update_idletasks()
        self._place_popup(popup)
        popup.deiconify()

        # Every one of these can close the list on its own.
        popup.bind("<Escape>", lambda _e: self._close_popup())
        popup.bind("<FocusOut>", lambda _e: self._close_popup())
        popup.bind("<Button-1>", self._maybe_close_from_click)
        self._bind_dismissers()

        try:
            popup.grab_set()
        except tk.TclError:
            # A grab can be refused if another window holds one; the list still works,
            # it simply leans on the other dismissal routes.
            pass
        popup.focus_set()

    def _place_popup(self, popup):
        """Below the button, flipped above it when there is no room underneath."""
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 2
        height = popup.winfo_reqheight()

        if y + height > self.winfo_screenheight():
            y = max(0, self.winfo_rooty() - height - 2)

        width = max(popup.winfo_reqwidth(), self.winfo_width())
        popup.geometry(f"{width}x{height}+{x}+{y}")

    def _bind_dismissers(self):
        """Close if the window moves, resizes or goes away underneath the list."""
        root = self.winfo_toplevel()
        self._dismiss_binds = [
            (root, "<Configure>", root.bind("<Configure>", self._on_root_changed, add="+")),
            (root, "<Unmap>", root.bind("<Unmap>", self._on_root_changed, add="+")),
        ]

    def _unbind_dismissers(self):
        for widget, sequence, funcid in getattr(self, "_dismiss_binds", []):
            try:
                widget.unbind(sequence, funcid)
            except Exception:
                pass
        self._dismiss_binds = []

    def _on_root_changed(self, _event=None):
        if self._popup is not None:
            self._close_popup()

    def _maybe_close_from_click(self, event):
        """With a grab held, clicks anywhere in the app arrive here."""
        popup = self._popup
        if popup is None:
            return
        inside = (
            0 <= event.x_root - popup.winfo_rootx() < popup.winfo_width()
            and 0 <= event.y_root - popup.winfo_rooty() < popup.winfo_height()
        )
        if not inside:
            self._close_popup()

    def _close_popup(self):
        popup, self._popup = self._popup, None
        if popup is None:
            return

        self._unbind_dismissers()
        try:
            popup.grab_release()
        except Exception:
            pass
        try:
            popup.destroy()
        except Exception:
            pass

    def destroy(self):
        self._close_popup()
        super().destroy()

    # ------------------------------------------------------------------ rows

    def _build_row(self, parent, value):
        enabled = self._row_enabled(value)
        selected = value == self._current_value

        row = ctk.CTkLabel(
            parent,
            text=self._row_text(value),
            anchor="w",
            height=30,
            font=self._row_font,
            corner_radius=4,
            fg_color=DROPDOWN_ROW_SELECTED if selected else "transparent",
            text_color=DROPDOWN_TEXT if enabled else DROPDOWN_DISABLED_TEXT,
        )
        row.pack(fill="x", padx=4, pady=1)

        if not enabled:
            return

        row.configure(cursor="hand2")
        row.bind("<Button-1>", lambda _e, v=value: self._pick(v))
        row.bind("<Enter>", lambda _e, r=row, s=selected: r.configure(
            fg_color=DROPDOWN_ROW_SELECTED if s else DROPDOWN_HOVER))
        row.bind("<Leave>", lambda _e, r=row, s=selected: r.configure(
            fg_color=DROPDOWN_ROW_SELECTED if s else "transparent"))

    def _pick(self, value):
        self._close_popup()
        # Same path CustomTkinter uses for a Tk menu choice, so subclasses and the
        # command callback see no difference.
        self._dropdown_callback(value)
