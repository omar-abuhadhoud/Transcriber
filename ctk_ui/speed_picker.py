import customtkinter as ctk


class Tooltip:
    """Hover text for a widget. Used to explain why a speed tier is unavailable."""

    def __init__(self, widget, text, wraplength=280):
        self.widget = widget
        self.text = text
        self.wraplength = wraplength
        self.window = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _show(self, _event=None):
        if self.window is not None or not self.text:
            return

        self.window = ctk.CTkToplevel(self.widget)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)

        label = ctk.CTkLabel(
            self.window,
            text=self.text,
            wraplength=self.wraplength,
            justify="left",
            font=("Arial", 11),
            fg_color=("gray85", "gray20"),
            corner_radius=6,
            padx=10,
            pady=8,
        )
        label.pack()

        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.window.geometry(f"+{x}+{y}")

    def _hide(self, _event=None):
        if self.window is not None:
            self.window.destroy()
            self.window = None


class SpeedPicker(ctk.CTkFrame):
    """Button that opens a list of speed tiers, with unaffordable ones disabled.

    CTkOptionMenu cannot disable individual entries, so the list is drawn as rows in a
    popup: each row is a frame of labels, which still receive hover events when disabled.
    """

    def __init__(self, master, on_change, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self.on_change = on_change
        self.statuses = []
        self.current = None
        self.popup = None

        self.button = ctk.CTkButton(
            self,
            text="Speed",
            command=self.toggle,
            width=150,
            height=35,
            font=("Arial", 12),
        )
        self.button.pack()

    def set_statuses(self, statuses, current):
        """Refresh the offered tiers. Called at startup and whenever the engine changes."""
        self.statuses = statuses
        self.current = current
        self.close()

        status = next((s for s in statuses if s.tier.name == current), None)
        if status is not None:
            self.button.configure(text=f"Speed: {status.tier.label}")

    def set_enabled(self, enabled):
        self.button.configure(state="normal" if enabled else "disabled")
        if not enabled:
            self.close()

    def toggle(self):
        if self.popup is not None:
            self.close()
        else:
            self.open()

    def close(self, _event=None):
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None

    def open(self):
        if not self.statuses:
            return

        self.popup = ctk.CTkToplevel(self)
        self.popup.overrideredirect(True)
        self.popup.attributes("-topmost", True)
        self.popup.bind("<FocusOut>", self.close)

        frame = ctk.CTkFrame(self.popup, corner_radius=8)
        frame.pack(fill="both", expand=True)

        for status in self.statuses:
            self._build_row(frame, status)

        self.popup.update_idletasks()
        x = self.button.winfo_rootx()
        y = self.button.winfo_rooty() + self.button.winfo_height() + 4
        self.popup.geometry(f"+{x}+{y}")
        self.popup.focus_set()

    def _build_row(self, parent, status):
        selected = status.tier.name == self.current
        row = ctk.CTkFrame(
            parent,
            fg_color=("gray75", "gray25") if selected else "transparent",
            corner_radius=6,
        )
        row.pack(fill="x", padx=6, pady=2)

        if status.available:
            name_color = ("gray10", "gray90")
            detail_color = "gray"
        else:
            name_color = detail_color = ("gray60", "gray45")

        name = ctk.CTkLabel(
            row,
            text=status.tier.label,
            anchor="w",
            width=70,
            font=("Arial", 12, "bold"),
            text_color=name_color,
        )
        name.pack(side="left", padx=(10, 4), pady=6)

        detail = ctk.CTkLabel(
            row,
            text=f"{status.tier.batch_size} at a time  ·  ~{status.estimate_gb:.1f} GB",
            anchor="w",
            font=("Arial", 11),
            text_color=detail_color,
        )
        detail.pack(side="left", padx=(0, 8))

        if status.recommended:
            badge = ctk.CTkLabel(
                row,
                text="recommended",
                font=("Arial", 10),
                fg_color=("#2ecc71", "#1e8449"),
                text_color="white",
                corner_radius=4,
                padx=6,
            )
            badge.pack(side="right", padx=(0, 10))

        widgets = [row, name, detail]

        if status.available:
            for widget in widgets:
                widget.configure(cursor="hand2")
                widget.bind("<Button-1>", lambda _e, s=status: self._select(s))
                widget.bind("<Enter>", lambda _e, r=row, s=status: self._hover(r, s, True))
                widget.bind("<Leave>", lambda _e, r=row, s=status: self._hover(r, s, False))
        else:
            for widget in widgets:
                Tooltip(widget, status.reason)

    def _hover(self, row, status, entering):
        if status.tier.name == self.current:
            return
        row.configure(fg_color=("gray85", "gray30") if entering else "transparent")

    def _select(self, status):
        self.current = status.tier.name
        self.button.configure(text=f"Speed: {status.tier.label}")
        self.close()
        self.on_change(status.tier.name)
