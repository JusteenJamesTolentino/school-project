"""Authentication helpers shared by the admin applications."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk


USERS = {
    "admin1": "group4",
    "admin2": "group4",
}


def require_login(root: tk.Tk, application: str) -> bool:
    """Block application startup until the configured administrator logs in with a dark-themed UI centered on screen."""
    dialog = tk.Toplevel(root)
    dialog.title(f"{application.title()} Login")
    dialog.grab_set()
    dialog.attributes("-topmost", True)
    dialog.resizable(False, False)

    # Dark theme color palette matching app standards
    bg_color = "#1f1e1d"
    panel_color = "#171616"
    text_color = "#e8e6e3"
    entry_bg = "#292626"
    accent_color = "#2563eb"
    accent_hover = "#1d4ed8"

    dialog.configure(bg=bg_color)

    style = ttk.Style(dialog)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("Dark.TFrame", background=panel_color)
    style.configure("Dark.TLabel", background=panel_color, foreground=text_color, font=("Segoe UI", 10))
    style.configure("Title.TLabel", background=panel_color, foreground=text_color, font=("Segoe UI", 16, "bold"))
    style.configure("Subtitle.TLabel", background=panel_color, foreground="#94a3b8", font=("Segoe UI", 9))

    outer_frame = tk.Frame(dialog, bg=bg_color, padx=20, pady=20)
    outer_frame.pack(fill="both", expand=True)

    frame = ttk.Frame(outer_frame, style="Dark.TFrame", padding=24)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text=f"{application.title()} Login", style="Title.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Label(frame, text="Enter your administrator credentials to continue.", style="Subtitle.TLabel").pack(
        anchor="w", pady=(0, 20)
    )

    ttk.Label(frame, text="Username", style="Dark.TLabel").pack(anchor="w")
    username = tk.StringVar()
    username_entry = tk.Entry(
        frame,
        textvariable=username,
        bg=entry_bg,
        fg=text_color,
        insertbackground=text_color,
        relief="flat",
        font=("Segoe UI", 11),
        highlightthickness=1,
        highlightbackground="#475569",
        highlightcolor=accent_color,
    )
    username_entry.pack(fill="x", pady=(4, 16), ipady=6, ipadx=6)

    ttk.Label(frame, text="Password", style="Dark.TLabel").pack(anchor="w")
    password = tk.StringVar()
    password_entry = tk.Entry(
        frame,
        textvariable=password,
        show="*",
        bg=entry_bg,
        fg=text_color,
        insertbackground=text_color,
        relief="flat",
        font=("Segoe UI", 11),
        highlightthickness=1,
        highlightbackground="#475569",
        highlightcolor=accent_color,
    )
    password_entry.pack(fill="x", pady=(4, 24), ipady=6, ipadx=6)

    result = {"authenticated": False}

    def submit() -> None:
        if username.get().strip() == application and password.get() == USERS.get(application):
            result["authenticated"] = True
            dialog.destroy()
        else:
            password.set("")
            messagebox.showerror("Login Failed", "Invalid username or password.", parent=dialog)
            password_entry.focus_set()

    buttons = ttk.Frame(frame, style="Dark.TFrame")
    buttons.pack(fill="x", pady=(4, 0))

    login_btn = tk.Button(
        buttons,
        text="Login",
        command=submit,
        bg=accent_color,
        fg="#ffffff",
        activebackground=accent_hover,
        activeforeground="#ffffff",
        relief="flat",
        font=("Segoe UI", 10, "bold"),
        padx=16,
        pady=6,
        cursor="hand2"
    )
    login_btn.pack(side="right", padx=(8, 0))

    exit_btn = tk.Button(
        buttons,
        text="Exit",
        command=dialog.destroy,
        bg="#334155",
        fg=text_color,
        activebackground="#475569",
        activeforeground="#ffffff",
        relief="flat",
        font=("Segoe UI", 10),
        padx=16,
        pady=6,
        cursor="hand2"
    )
    exit_btn.pack(side="right")

    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    
    # Center the dialog on screen
    dialog.update_idletasks()
    width = dialog.winfo_reqwidth()
    height = dialog.winfo_reqheight()
    screen_width = dialog.winfo_screenwidth()
    screen_height = dialog.winfo_screenheight()
    x = (screen_width - width) // 2
    y = (screen_height - height) // 2
    dialog.geometry(f"{width}x{height}+{x}+{y}")

    dialog.deiconify()
    dialog.lift()
    dialog.focus_force()
    dialog.after(250, lambda: dialog.attributes("-topmost", False))
    username_entry.focus_set()
    dialog.bind("<Return>", lambda _event: submit())
    root.wait_window(dialog)
    return result["authenticated"]
