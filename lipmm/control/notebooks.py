"""Theo notebooks — modular dashboard widgets contributed by theo providers.

Each provider (or any plugin) registers a `TheoNotebook` with a
`NotebookRegistry` at bot startup. The dashboard renders a
`Notebooks` drawer tab that lists every registered notebook and
polls the selected one for live HTML on a 5s cadence.

A notebook is a self-contained renderable: it returns an HTML
fragment string. No Jinja involvement from the framework side —
each notebook can choose its own rendering approach. This keeps
provider-specific UI fully decoupled from the dashboard's core
templates.

To add a new notebook:

    class MyNotebook:
        key = "my-feed"
        label = "My data feed"

        async def render(self) -> str:
            return "<div>hello</div>"

    registry.register(MyNotebook())
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TheoNotebook(Protocol):
    """A provider-contributed dashboard widget.

    Implementations supply a URL-safe `key`, a human-readable
    `label`, and an async `render()` returning an HTML fragment.
    """

    key: str
    label: str

    async def render(self) -> str:
        """Return an HTML fragment for this notebook's current state.

        Called fresh on each poll (~5s). Should be fast (< 50ms) —
        cache expensive computations internally if the underlying
        state changes slowly.
        """
        ...


class NotebookRegistry:
    """Insertion-ordered registry of notebooks keyed by URL-safe slug."""

    def __init__(self) -> None:
        self._by_key: dict[str, TheoNotebook] = {}

    def register(self, notebook: TheoNotebook) -> None:
        """Add a notebook. Raises ValueError on duplicate key."""
        key = notebook.key
        if not key:
            raise ValueError("notebook.key must be non-empty")
        if key in self._by_key:
            raise ValueError(f"notebook key {key!r} already registered")
        self._by_key[key] = notebook

    def get(self, key: str) -> TheoNotebook | None:
        """Return the notebook for `key`, or None if not registered."""
        return self._by_key.get(key)

    def list(self) -> list[tuple[str, str]]:
        """Return [(key, label), ...] in insertion order."""
        return [(nb.key, nb.label) for nb in self._by_key.values()]

    def __len__(self) -> int:
        return len(self._by_key)
