"""The popup a tile opens: paste a link, press Download.

Validation happens as you type rather than on submit, because the useful thing to say
about a wrong link is which tile it belongs to. Pasting a TikTok link into the YouTube
box is the mistake people actually make, and the registry can recognise it, so the box
says so instead of letting the download fail a minute later with a worse message.
"""

import customtkinter as ctk

from ctk_ui import theme
from ctk_ui.theme import ui_font
from downloader import registry
from downloader.base import DownloadOptions

# Browsers yt-dlp can lift a session from. Firefox is first because it is the one that
# reliably works: Chrome and Edge encrypt their cookie store while running, and the
# read fails with a decryption error until they are closed.
BROWSERS = ["Firefox", "Chrome", "Edge", "Brave", "Opera", "Vivaldi"]


class UrlDialog(ctk.CTkToplevel):
    """Modal link box for one provider."""

    def __init__(self, parent, info, on_submit):
        super().__init__(parent)

        self.info = info
        self.on_submit = on_submit
        self.result = None

        self.title("Download from " + info.label)
        self.resizable(False, False)
        self.transient(parent)

        self._build()
        self._centre_on(parent)
        self._prefill_from_clipboard()

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _e: self._cancel())
        self.bind("<Return>", lambda _e: self._submit())

        # Deferred: a CTkToplevel is not yet mapped in __init__, and grabbing an
        # unmapped window raises. The same delay is why the icon is set here.
        self.after(120, self._take_over)

    # ------------------------------------------------------------------- building

    def _build(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=20)

        header = ctk.CTkFrame(body, fg_color="transparent")
        header.pack(fill="x", pady=(0, 14))

        # The same mark as the tile, so it is obvious which one was clicked.
        from ctk_ui.provider_icons import icon_for

        icon = icon_for(self.info, 36)
        if icon is not None:
            ctk.CTkLabel(header, text="", image=icon).pack(side="left", padx=(0, 12))

        ctk.CTkLabel(
            header,
            text=self.info.label + " link",
            font=ui_font(16, "bold"),
        ).pack(side="left")

        self.entry = ctk.CTkEntry(
            body,
            width=440,
            height=38,
            font=ui_font(12),
            placeholder_text=self.info.example_url,
        )
        self.entry.pack(fill="x")
        self.entry.bind("<KeyRelease>", lambda _e: self._validate())
        # <<Paste>> does not fire for a right-click paste from Tk's own menu, so the
        # entry is also polled briefly after the window opens.
        self.entry.bind("<<Paste>>", lambda _e: self.after(10, self._validate))

        self.lbl_hint = ctk.CTkLabel(
            body,
            text="",
            font=ui_font(11),
            text_color=theme.MUTED,
            anchor="w",
            justify="left",
            wraplength=440,
        )
        self.lbl_hint.pack(fill="x", pady=(6, 0))

        self._build_login(body)
        self._build_buttons(body)

    def _build_login(self, body):
        login = ctk.CTkFrame(body, fg_color="transparent")
        login.pack(fill="x", pady=(16, 0))

        self.use_cookies = ctk.BooleanVar(value=False)
        self.chk_cookies = ctk.CTkCheckBox(
            login,
            text="Use my browser login",
            variable=self.use_cookies,
            font=ui_font(12),
            checkbox_width=18,
            checkbox_height=18,
            command=self._toggle_cookies,
        )
        self.chk_cookies.pack(side="left")

        self.browser_menu = theme.option_menu(
            login,
            values=BROWSERS,
            width=130,
            height=30,
        )
        self.browser_menu.set(BROWSERS[0])
        self.browser_menu.configure(state="disabled")
        self.browser_menu.pack(side="left", padx=(12, 0))

        hint = self.info.login_hint or "Needed for posts that are not public."
        ctk.CTkLabel(
            body,
            text=hint + "  Chrome and Edge encrypt their cookies while open, so close "
                        "them first or pick Firefox.",
            font=ui_font(11),
            text_color=theme.MUTED,
            anchor="w",
            justify="left",
            wraplength=440,
        ).pack(fill="x", pady=(6, 0))

    def _build_buttons(self, body):
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", pady=(20, 0))

        ctk.CTkButton(
            buttons,
            text="Cancel",
            width=100,
            height=34,
            fg_color="transparent",
            border_width=1,
            text_color=("gray20", "gray85"),
            command=self._cancel,
        ).pack(side="right")

        self.btn_download = ctk.CTkButton(
            buttons,
            text="Download",
            width=120,
            height=34,
            font=ui_font(13, "bold"),
            fg_color=self.info.accent,
            hover_color=self.info.hover,
            state="disabled",
            command=self._submit,
        )
        self.btn_download.pack(side="right", padx=(0, 10))

    # ------------------------------------------------------------------- behaviour

    def _take_over(self):
        try:
            self.grab_set()
        except Exception:
            # Another modal already holds the grab. The dialog still works.
            pass
        self.entry.focus_set()
        self.lift()

    def _centre_on(self, parent):
        self.update_idletasks()
        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - height) // 3
        self.geometry("+{0}+{1}".format(max(0, x), max(0, y)))

    def _prefill_from_clipboard(self):
        """Fill the box when the clipboard already holds a link for this platform.

        Only when it matches this provider. Pasting an unrelated clipboard into the
        box would be worse than leaving it empty.
        """
        try:
            text = self.clipboard_get().strip()
        except Exception:
            return

        if text and len(text) < 500 and self.info.name == _provider_name_of(text):
            self.entry.insert(0, text)
            self._validate()

    def _toggle_cookies(self):
        self.browser_menu.configure(state="normal" if self.use_cookies.get() else "disabled")

    def _validate(self):
        url = self.entry.get().strip()

        if not url:
            self._set_hint("", theme.MUTED)
            self.btn_download.configure(state="disabled")
            return False

        provider = registry.provider_for_url(url)

        if provider is not None and provider.name == self.info.name:
            self._set_hint("Looks like a " + self.info.label + " link.", theme.SUCCESS)
            self.btn_download.configure(state="normal")
            return True

        if provider is not None:
            self._set_hint(
                "That is a " + provider.label + " link. Close this and use the "
                + provider.label + " tile instead.",
                theme.DANGER,
            )
        elif not url.lower().startswith(("http://", "https://")):
            self._set_hint("That is not a web link. Paste the full address.", theme.DANGER)
        else:
            self._set_hint(
                "That does not look like a " + self.info.label + " link.", theme.DANGER
            )

        self.btn_download.configure(state="disabled")
        return False

    def _set_hint(self, text, color):
        self.lbl_hint.configure(text=text, text_color=color)

    def _submit(self):
        if not self._validate():
            return

        options = DownloadOptions(
            cookies_from_browser=(
                self.browser_menu.get().lower() if self.use_cookies.get() else None
            )
        )
        self.result = (self.entry.get().strip(), options)

        self._close()
        if self.on_submit:
            self.on_submit(*self.result)

    def _cancel(self):
        self.result = None
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


def _provider_name_of(text):
    provider = registry.provider_for_url(text)
    return provider.name if provider else None
