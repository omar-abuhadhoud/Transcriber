from ctk_ui.dropdown import StyledOptionMenu
from ctk_ui.theme import ui_font


class SpeedPicker(StyledOptionMenu):
    """The speed tier chooser.

    Deliberately the same widget as the engine picker beside it, so the header reads as
    one control strip rather than two unrelated controls.

    It used to be a button that opened a hand-built CTkToplevel. That existed for one
    reason -- CTkOptionMenu offers no way to grey out a single entry, and tiers this GPU
    cannot afford must not be selectable -- but it cost a new toplevel window every time
    it opened, and it closed on <FocusOut>, which an override-redirect window does not
    reliably receive on Windows. Miss that event and the list stayed on screen with
    nothing able to dismiss it.

    CustomTkinter's dropdown is a real tkinter.Menu, so an entry can simply be disabled,
    which removes the reason the popup existed. The reason a tier is out of reach now
    travels in its label, where it is readable without hovering for a tooltip.
    """

    def __init__(self, master, on_change, **kwargs):
        super().__init__(
            master,
            values=[],
            command=self._on_pick,
            # Matched to the engine picker so the two sit level and look alike.
            width=190,
            height=35,
            corner_radius=8,
            font=ui_font(13),
            **kwargs,
        )

        self.on_change = on_change
        self.statuses = []
        self.current = None
        # Entry text -> status, because the menu hands back the label that was clicked.
        self._by_label = {}

    # ------------------------------------------------------------------ building

    @staticmethod
    def _entry_text(status):
        """One row of the list.

        The tier name is padded so the columns line up: the names are short and of
        similar width, so even in a proportional face this reads as a table rather than
        a ragged list.
        """
        name = status.tier.label.ljust(8)
        windows = f"{status.tier.batch_size} windows".ljust(11)

        if not status.available:
            return f"{name}{windows}needs {status.estimate_gb:.1f} GB"

        text = f"{name}{windows}{status.estimate_gb:.1f} GB"
        if status.recommended:
            text += "    recommended"
        return text

    def _button_text(self, status):
        return f"Speed: {status.tier.label}"

    def set_statuses(self, statuses, current):
        """Refresh the offered tiers. Called at startup and whenever the engine changes."""
        self.statuses = list(statuses)
        self.current = current

        self._by_label = {}
        values = []
        for status in self.statuses:
            text = self._entry_text(status)
            self._by_label[text] = status
            values.append(text)

        self.configure(values=values)
        self._show_current()

    def _row_enabled(self, value):
        """The list asks this per row; tiers this GPU cannot afford are greyed out."""
        status = self._by_label.get(value)
        return status is None or status.available

    def set_enabled(self, enabled):
        self.configure(state="normal" if enabled else "disabled")

    # ----------------------------------------------------------------- selection

    def _show_current(self):
        """Put the short form back on the button.

        The menu writes the full entry text onto the button before the command runs;
        the button only has room for the tier's name.
        """
        chosen = next((s for s in self.statuses if s.tier.name == self.current), None)
        if chosen is not None:
            self.set(self._button_text(chosen))

    def _on_pick(self, value):
        status = self._by_label.get(value)
        if status is None:
            self._show_current()
            return

        # Reachable only if the entry could not be disabled above.
        if not status.available or status.tier.name == self.current:
            self._show_current()
            return

        self.current = status.tier.name
        self._show_current()
        self.on_change(status.tier.name)
