"""pytest config — makes the `app` and `ingestion` packages importable.

Living at the `backend/` root, this file gets pytest to add the backend
directory to sys.path so tests can do `from app.models import Player`
without needing an editable install or an explicit PYTHONPATH=.
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
