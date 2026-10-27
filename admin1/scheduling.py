import tkinter as tk
import sys
from pathlib import Path

_ADMIN1_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _ADMIN1_ROOT.parent
sys.path.insert(0, str(_ADMIN1_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT))
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
