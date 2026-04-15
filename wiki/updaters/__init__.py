__all__ = ["conflict_scan", "incremental_update", "publish"]


def __getattr__(name):
    if name == "incremental_update":
        from wiki.updaters.incremental import incremental_update
        return incremental_update
    if name == "conflict_scan":
        from wiki.updaters.conflict_scan import conflict_scan
        return conflict_scan
    if name == "publish":
        from wiki.updaters.publish import publish
        return publish
    raise AttributeError(name)
