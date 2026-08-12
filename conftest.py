import sys
from pathlib import Path

# Add the project root (where app.py lives) to sys.path, so
# "import core...", "import mathlib...", etc. work from within the
# tests regardless of where pytest was started from.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
