"""Fingerprint concrete extension code without publishing its local paths."""
from __future__ import annotations

import hashlib
import inspect
import marshal
from pathlib import Path

from .common import Json, digest


def implementation_identity(instance: object, method: str) -> Json:
    """Identify concrete class, inherited source modules and the executed method code."""
    cls = type(instance)
    sources: dict[str, str] = {}
    for base in cls.__mro__:
        if base is object:
            continue
        try:
            filename = inspect.getsourcefile(base)
        except TypeError:
            filename = None
        if filename and Path(filename).is_file():
            sources[base.__module__] = digest(Path(filename))
    function = getattr(instance, method)
    code = getattr(function, "__code__", None)
    return {
        "class": f"{cls.__module__}.{cls.__qualname__}", "source_sha256": sources,
        "source_status": "RECORDED" if cls.__module__ in sources else "UNAVAILABLE",
        "method_code_sha256": hashlib.sha256(marshal.dumps(code)).hexdigest() if code else None,
    }
