"""Application entry point.

This module is the direct-launch entry point for Admin 1.
Login is enforced here the same way admin1/scheduling.py does it.
"""

import sys
import tkinter as tk
from pathlib import Path

# Make sure the project root (which contains authentication.py) is on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from authentication import require_login
from scheduling_system.ui import SchedulingApp


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    if not require_login(root, "admin1"):
        root.destroy()
        return
    root.deiconify()
    SchedulingApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
