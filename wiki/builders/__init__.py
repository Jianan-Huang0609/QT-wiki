__all__ = ["PAGE_BLUEPRINTS", "bootstrap_pages"]


def __getattr__(name):
    if name in __all__:
        from wiki.builders.bootstrap import PAGE_BLUEPRINTS, bootstrap_pages
        return {"PAGE_BLUEPRINTS": PAGE_BLUEPRINTS, "bootstrap_pages": bootstrap_pages}[name]
    raise AttributeError(name)
