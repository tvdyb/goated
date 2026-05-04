"""Filesystem paths to the web package's bundled templates and static
assets. Centralized so the renderer and router agree on the same dirs."""

from __future__ import annotations

from pathlib import Path

_HERE = Path(__file__).resolve().parent
TEMPLATES_DIR = _HERE / "templates"
STATIC_DIR = _HERE / "static"
