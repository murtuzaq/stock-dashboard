"""Where saved portfolios and strategies live: the repo root, or the folder in STOCK_DASHBOARD_DATA if it is set.

Setting it lets you run the app against a throwaway data set (for example the git-ignored example/ folder)
without touching your real portfolios/ and strategies/.
"""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ['STOCK_DASHBOARD_DATA']).resolve() if os.environ.get('STOCK_DASHBOARD_DATA') else REPO_ROOT
