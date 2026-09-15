"""Maps the `FORUM_ADAPTER` config string to a `ForumAdapter`
implementation.

This is the one place in the codebase that needs to know every adapter
that ships with the app. Adding support for a new forum platform means
writing its adapter class (implementing `forum_adapter.ForumAdapter`) and
adding one line to `_ADAPTERS` below - `ingest.py`, the API layer, and
config never need to change.
"""
from __future__ import annotations

from app.crawler.forum_adapter import ForumAdapter
from app.crawler.smf_adapter import SMFForumAdapter
from app.crawler.xenforo_adapter import XenForoForumAdapter

_ADAPTERS: dict[str, type[ForumAdapter]] = {
    "smf": SMFForumAdapter,
    "xenforo": XenForoForumAdapter,
    # Add new platforms here, e.g. "phpbb": PhpBBForumAdapter.
}


def get_adapter(name: str) -> ForumAdapter:
    """Instantiate the registered adapter for `name` (e.g. "smf")."""
    try:
        adapter_cls = _ADAPTERS[name]
    except KeyError:
        available = ", ".join(sorted(_ADAPTERS)) or "(none registered)"
        raise ValueError(f"Unknown forum adapter {name!r}. Available: {available}") from None
    return adapter_cls()
