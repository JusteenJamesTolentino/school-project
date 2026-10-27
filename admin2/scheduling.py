import tkinter as tk
import sys
from pathlib import Path

_ADMIN2_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _ADMIN2_ROOT.parent
sys.path.insert(0, str(_ADMIN2_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT))
from authentication import require_login
from admin2_app.ui import Admin2App


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    if not require_login(root, "admin2"):
        root.destroy()
        return
    root.deiconify()
    Admin2App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
