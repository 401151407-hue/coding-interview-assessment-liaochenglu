"""Make ``import backend...`` work regardless of the directory pytest is run from."""

from __future__ import annotations

import pathlib
import sys

APP_DIR = pathlib.Path(__file__).resolve().parents[2]  # .../app
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
