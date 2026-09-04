"""Load project .env into os.environ (no external dependency)."""

from __future__ import annotations

import os
from pathlib import Path

from recovery.paths import PROJECT_ROOT

_LOADED = False


def _load_env_file(env_path: Path) -> None:
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_project_env(project_root: Path | None = None) -> bool:
    """Load KEY=VALUE pairs from .env if present. Returns True if any file was loaded."""
    global _LOADED
    if _LOADED:
        return False

    backend_root = project_root or PROJECT_ROOT
    repo_root = backend_root.parent
    loaded = False
    for candidate in (backend_root / ".env", repo_root / ".env"):
        if candidate.is_file():
            _load_env_file(candidate)
            loaded = True

    _LOADED = True
    return loaded
