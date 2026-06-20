"""Shared JSON read/write helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON atomically via a same-directory temp file + replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
