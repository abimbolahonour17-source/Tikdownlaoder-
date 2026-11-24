"""Catch-all Vercel Python function for the FastAPI routes under /api/*.

Vercel's api/index.py entrypoint only handles the /api/index route. The frontend
calls nested paths such as /api/v1/download, so expose the same ASGI app through
a catch-all function as well.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.main import app
