from __future__ import annotations

from importlib import import_module


_SERVICE_EXPORTS = {
    "AuditService": ("app.services.audit", "AuditService"),
    "AuthService": ("app.services.auth", "AuthService"),
    "KnowledgeTreeService": ("app.services.knowledge", "KnowledgeTreeService"),
    "PaperService": ("app.services.papers", "PaperService"),
    "SystemService": ("app.services.system", "SystemService"),
}

__all__ = sorted(_SERVICE_EXPORTS)


def __getattr__(name: str):
    module_name, attr_name = _SERVICE_EXPORTS.get(name, (None, None))
    if module_name is None or attr_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + list(_SERVICE_EXPORTS.keys()))
