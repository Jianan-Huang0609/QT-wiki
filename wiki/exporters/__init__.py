from __future__ import annotations

__all__ = ["sync_to_obsidian"]


def __getattr__(name):
    if name == "sync_to_obsidian":
        from wiki.exporters.obsidian import sync_to_obsidian

        return sync_to_obsidian
    raise AttributeError(name)
