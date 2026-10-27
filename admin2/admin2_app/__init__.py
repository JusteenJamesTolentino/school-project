"""Admin 2 package.

Admin 2 reuses Admin 1's persistence layer and theme palettes. Importing this
package puts the sibling admin1 directory on sys.path so its scheduling_system
package can be imported.
"""

import sys
from pathlib import Path

_ADMIN1 = Path(__file__).resolve().parents[2] / "admin1"
if _ADMIN1.is_dir() and str(_ADMIN1) not in sys.path:
    sys.path.insert(0, str(_ADMIN1))
