"""Isolated, network-denied public DocVortex API worker; JSON over stdin/stdout only."""

from __future__ import annotations

import hashlib
import importlib
import importlib.abc
import importlib.metadata
import json
import sys
from contextlib import ExitStack
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from unittest.mock import patch


class ForbiddenImport(importlib.abc.MetaPathFinder):
    """The deterministic slice never initializes a second PDF or model runtime."""

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> None:
        if fullname.startswith(("pypdfium", "docvortex.document.pdf", "torch", "magika")):
            raise RuntimeError("FORBIDDEN_RUNTIME_IMPORT")


def denied(*args: Any, **kwargs: Any) -> Any:
    """Reject networking and external processes before loading upstream modules."""
    raise RuntimeError("OFFLINE_WORKER_POLICY")


def run(request: dict[str, Any]) -> dict[str, Any]:
    """Invoke only public schema, document, table and DOCX APIs."""
    sys.meta_path.insert(0, ForbiddenImport())
    logger = importlib.import_module("loguru").logger
    logger.remove()
    schema = importlib.import_module("docvortex.schema")
    version = importlib.metadata.version("docvortex")
    if version != "0.4.9":
        raise RuntimeError("DOCVORTEX_VERSION_MISMATCH")
    result: dict[str, Any] = {"version": version, "network_requests": 0}
    action = request["action"]
    if action == "postprocess":
        model = schema.ModelJson.from_dict(request["model"])
        public = importlib.import_module("docvortex.postprocess.document")
        middle = public.model_json_to_middle_json(model)
        result["middle"] = middle.to_dict()
        result["model_roundtrip"] = model.to_dict()
    elif action == "render":
        middle = schema.MiddleJson.from_dict(request["middle"])
        job = Path(request["job"])
        registry = request["assets"]

        def resolve(name: str) -> bytes:
            if name not in registry or Path(name).is_absolute() or ".." in Path(name).parts:
                raise RuntimeError("ASSET_NOT_REGISTERED")
            path = job
            for part in Path(name).parts:
                path /= part
                if path.is_symlink():
                    raise RuntimeError("ASSET_SYMLINK")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != registry[name]:
                raise RuntimeError("ASSET_HASH_MISMATCH")
            return data

        class HtmlAssets(HTMLParser):
            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                if tag == "svg":
                    raise RuntimeError("INLINE_ASSET_REJECTED")
                if tag == "img":
                    name = dict(attrs).get("src")
                    if not name:
                        raise RuntimeError("ASSET_NOT_REGISTERED")
                    resolve(name)

        def check_images(value: Any) -> None:
            if isinstance(value, dict):
                if value.get("type") in {"table", "table_body"} and isinstance(
                    value.get("content"), str
                ):
                    parser = HtmlAssets()
                    parser.feed(value["content"])
                    parser.close()
                if value.get("image_url") or value.get("image_base64"):
                    raise RuntimeError("REMOTE_OR_INLINE_ASSET_REJECTED")
                if value.get("image_path"):
                    resolve(value["image_path"])
                for item in value.values():
                    check_images(item)
            elif isinstance(value, list):
                for item in value:
                    check_images(item)

        check_images(request["middle"])
        public = importlib.import_module("docvortex.render.docx")
        body = public.render_docx(middle, asset_resolver=resolve)
        target = Path(request["output"])
        with target.open("xb") as stream:
            stream.write(body)
        target.chmod(0o600)
        result["docx_sha256"] = hashlib.sha256(body).hexdigest()
    elif action == "table":
        public = importlib.import_module("docvortex.content.table")
        state = public.build_table_state_from_html(request["html"])
        result["state"] = (
            None
            if state is None
            else {
                "columns": state.total_cols,
                "rows": len(state.rows),
                "row_effective_cols": state.row_effective_cols,
                "header_rowspans": [list(row.rowspans) for row in state.front_header_info],
            }
        )
    elif action == "identity":
        result["public_api"] = importlib.import_module("docvortex.public_api").PUBLIC_API
        result["dependencies"] = []
        for d in importlib.metadata.distributions():
            licenses = [
                c for c in d.metadata.get_all("Classifier", []) if c.startswith("License ::")
            ]
            result["dependencies"].append(
                {
                    "name": d.metadata["Name"],
                    "version": d.version,
                    "license": d.metadata.get("License-Expression")
                    or d.metadata.get("License")
                    or (licenses[0] if licenses else "UNKNOWN"),
                    "license_files": [
                        {
                            "name": Path(str(f)).name,
                            "sha256": hashlib.sha256(
                                Path(str(d.locate_file(f))).read_bytes()
                            ).hexdigest(),
                        }
                        for f in d.files or []
                        if "license" in Path(str(f)).name.lower()
                        or "copying" in Path(str(f)).name.lower()
                    ],
                }
            )
    else:
        raise RuntimeError("UNKNOWN_WORKER_ACTION")
    result["implementation_sha256"] = {
        name: hashlib.sha256(Path(str(module.__file__)).read_bytes()).hexdigest()
        for name, module in tuple(sys.modules.items())
        if name.startswith("docvortex")
        and getattr(module, "__file__", None)
        and Path(str(module.__file__)).is_file()
    }
    result["pdfium_loaded"] = any("pdfium" in name for name in sys.modules)
    return result


def main() -> int:
    """Never emit upstream exceptions containing source content."""
    try:
        with ExitStack() as stack:
            for target in (
                "socket.socket.connect",
                "socket.socket.connect_ex",
                "socket.create_connection",
                "socket.getaddrinfo",
                "subprocess.Popen",
                "os.system",
            ):
                stack.enter_context(patch(target, denied))
            result = run(json.load(sys.stdin))
        print(json.dumps({"ok": True, **result}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
