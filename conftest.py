"""Root pytest conftest — puts the monorepo packages on sys.path.

Layout:
  ml/            -> importable as `ml.*`
  apps/api/app/  -> importable as `app.*`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in (str(ROOT), str(ROOT / "ml"), str(ROOT / "apps" / "api")):
    if p not in sys.path:
        sys.path.insert(0, p)
