"""Shared fullscreen window behavior for the two admin workspaces."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class WindowControls:
    def _configure_window(self, title: str) -> None:
        self.root.title(title)
        self.root.geometry("1280x760")
        self.root.minsize(900, 600)
        self._resume_fullscreen = False
        self._restore_after_id = None
        self.root.attributes("-fullscreen", True)
        self.root.bind("<F11>", self._toggle_fullscreen)
        self.root.bind("<Escape>", self._leave_fullscreen)
        self.root.bind("<Map>", self._restore_window, add="+")

    def _build_window_controls(self, parent: ttk.Frame, title: str) -> None:
        header = ttk.Frame(parent, style="Panel.TFrame", padding=(12, 4))
        header.pack(fill="x", pady=(0, 6))
        self.exit_button = ttk.Button(
            header, text="Exit", style="Danger.TButton", command=self._close,
        )
        self.exit_button.pack(side="right", padx=(6, 0))
        self.minimize_button = ttk.Button(
            header, text="Minimize", style="Action.TButton", command=self._minimize_window,
        )
        self.minimize_button.pack(side="right")
        ttk.Label(header, text=title, style="Header.TLabel").pack(side="left")

    def _toggle_fullscreen(self, _event=None) -> str:
        self.root.attributes("-fullscreen", not self.root.attributes("-fullscreen"))
        return "break"

    def _leave_fullscreen(self, _event=None) -> str:
        self.root.attributes("-fullscreen", False)
        return "break"

    def _minimize_window(self) -> None:
        self._resume_fullscreen = bool(self.root.attributes("-fullscreen"))
        # Windows cannot iconify a fullscreen Tk window until fullscreen is cleared.
        self.root.attributes("-fullscreen", False)
        self.root.iconify()

    def _restore_window(self, event: tk.Event) -> None:
        if event.widget is self.root and self._resume_fullscreen:
            self._resume_fullscreen = False
            self._restore_after_id = self.root.after_idle(self._finish_restore)

    def _finish_restore(self) -> None:
        self._restore_after_id = None
        self.root.attributes("-fullscreen", True)

    def _cancel_window_callbacks(self) -> None:
        if self._restore_after_id is not None:
            self.root.after_cancel(self._restore_after_id)
            self._restore_after_id = None
