"""Make the repository root importable for the world-engine tests.

pytest only puts the repo root on ``sys.path`` as a side effect of collecting
other packaged tests; when this directory is run on its own (single file,
PyCharm, a pre-commit hook), ``import services`` / ``import tests`` would fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

# tests/unit/world/conftest.py -> repo root is three levels up.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
