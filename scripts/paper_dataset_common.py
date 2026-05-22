from __future__ import annotations

import sys
from pathlib import Path


def get_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_api_root() -> Path:
    return get_repo_root() / "apps" / "api"


def bootstrap_api_path() -> Path:
    api_root = get_api_root()
    api_root_text = str(api_root)
    if api_root_text not in sys.path:
        sys.path.insert(0, api_root_text)
    return api_root
