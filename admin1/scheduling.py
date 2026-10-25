"""Backward-compatible launcher for the scheduling application."""

import tkinter as tk

from scheduling_system.ui import SchedulingApp


def main() -> None:
    root = tk.Tk()
    SchedulingApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
