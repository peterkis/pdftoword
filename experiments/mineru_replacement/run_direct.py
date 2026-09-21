"""Opt-in MinerU experiment: one local parse, sealed bundle, offline public DOCX export.

No dependency installation, remote client, route registration or automatic retry.
Run this module in a NEW isolated runtime after explicit user authorization.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import socket
import sys
import time
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from unittest.mock import patch
from xml.etree import ElementTree as ET

PINS = {"mineru": "4.0.4", "docvortex": "0.4.17"}
SCHEMA = "p2w-mineru-bundle/1"
Json = dict[str, Any]


class ExperimentError(ValueError):
    """A stable diagnostic code, never a source-bearing exception message."""


def digest(path: Path) -> str:
    """Hash without loading a full PDF into memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value: Any) -> None:
    """Write a private receipt atomically within a newly reserved run directory."""
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def relative_path(name: str) -> PurePosixPath:
    """Reject URLs, traversal, platform-specific paths and ambiguous spelling."""
    if not isinstance(name, str) or not name or any(c in name for c in "\\:%?#\x00"):
        raise ExperimentError("ASSET_PATH_INVALID")
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in {"", ".", ".."} for p in name.split("/")):
        raise ExperimentError("ASSET_PATH_INVALID")
    return path


def safe_path(root: Path, name: str) -> Path:
    """Reject symlinks and escapes, including parents of registered assets."""
    parts = relative_path(name).parts
    candidate = root
    for part in parts:
        candidate /= part
        if candidate.is_symlink():
            raise ExperimentError("ASSET_SYMLINK")
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ExperimentError("ASSET_OUTSIDE_BUNDLE")
    return candidate


class BundleWriter:
    """Implement public DataWriter's protocol with confined, no-overwrite writes."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def write(self, path: str, data: bytes) -> None:
        """Persist upstream bytes without recropping or reencoding images."""
        target = safe_path(self.root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)

    def write_string(self, path: str, data: str) -> None:
        """Persist upstream text verbatim as UTF-8."""
        self.write(path, data.encode("utf-8"))


def inventory(root: Path) -> dict[str, str]:
    """Seal every saved upstream file; never follow symlinks."""
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ExperimentError("ASSET_SYMLINK")
        if path.is_file():
            name = path.relative_to(root).as_posix()
            safe_path(root, name)
            result[name] = digest(path)
    return result


def read_json(path: Path) -> Json:
    """Read object JSON with sanitized errors and duplicate-key rejection."""

    def unique(pairs: list[tuple[str, Any]]) -> Json:
        result: Json = {}
        for key, value in pairs:
            if key in result:
                raise ExperimentError("JSON_DUPLICATE_KEY")
            result[key] = value
        return result

    try:
        value = json.loads(path.read_text(), object_pairs_hook=unique)
    except (OSError, ValueError) as exc:
        raise ExperimentError("JSON_INVALID") from exc
    if not isinstance(value, dict):
        raise ExperimentError("JSON_OBJECT_REQUIRED")
    return value


class AssetResolver:
    """Resolve only sealed, local registered images; missing assets never disappear."""

    def __init__(self, root: Path, files: dict[str, str]) -> None:
        self.root, self.files = root, files

    def __call__(self, name: str) -> bytes:
        path = safe_path(self.root, name)
        if not name.startswith("images/") or name not in self.files:
            raise ExperimentError("ASSET_NOT_REGISTERED")
        if not path.is_file():
            raise ExperimentError("ASSET_MISSING")
        if digest(path) != self.files[name]:
            raise ExperimentError("ASSET_HASH_MISMATCH")
        return path.read_bytes()


@contextmanager
def offline() -> Iterator[None]:
    """Deny Python network sockets during export and local-only inference.

    This is an in-process guard, not an OS firewall for native libraries. Use an
    OS/container network boundary for the actual disconnected acceptance run.
    """

    def denied(*args: Any, **kwargs: Any) -> Any:
        raise ExperimentError("NETWORK_DISABLED")

    with patch.object(socket, "socket", denied):
        yield


@contextmanager
def quiet_upstream() -> Iterator[None]:
    """Discard source-bearing third-party Python/native logs, retaining only codes."""
    saved = [os.dup(1), os.dup(2)]
    try:
        with open(os.devnull, "w") as sink, redirect_stdout(sink), redirect_stderr(sink):
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
            yield
    finally:
        for target, fd in zip((1, 2), saved, strict=True):
            os.dup2(fd, target)
            os.close(fd)


def runtime() -> Json:
    """Read installed versions without importing inference or modifying environments."""
    installed = {}
    for name in PINS:
        try:
            installed[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            installed[name] = "NOT_INSTALLED"
    return {"python": sys.version.split()[0], "packages": installed}


def require_runtime() -> Json:
    """Refuse the legacy environments and enforce explicit experiment version pins."""
    repo = Path(__file__).resolve().parents[2]
    prefix = Path(sys.prefix).resolve()
    if prefix in {
        (repo / ".venv").resolve(),
        (repo / "tmp/docx-demo/docvortex-runtime/.venv").resolve(),
    }:
        raise ExperimentError("ISOLATED_RUNTIME_REQUIRED")
    info = runtime()
    if info["packages"] != PINS:
        raise ExperimentError("PINNED_RUNTIME_NOT_INSTALLED")
    if sys.version_info[:2] != (3, 12):
        raise ExperimentError("PYTHON_312_REQUIRED")
    return info


def inspect_docx(data: bytes) -> Json:
    """Check ZIP/XML and count actual objects; counts are not content accuracy."""
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            if archive.testzip() is not None:
                raise ExperimentError("DOCX_ZIP_INVALID")
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ExperimentError("DOCX_DUPLICATE_PART")
            for name in ("[Content_Types].xml", "_rels/.rels", "word/document.xml"):
                if name not in names:
                    raise ExperimentError("DOCX_PART_MISSING")
            for name in names:
                if name.endswith((".xml", ".rels")):
                    ET.fromstring(archive.read(name))
            document = ET.fromstring(archive.read("word/document.xml"))
            ns = {
                "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
                "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
            }
            return {
                "zip_xml": "VERIFIED",
                "paragraphs": len(document.findall(".//w:p", ns)),
                "text_nodes": len(document.findall(".//w:t", ns)),
                "tables": len(document.findall(".//w:tbl", ns)),
                "omml": len(document.findall(".//m:oMath", ns)),
                "drawings": len(document.findall(".//w:drawing", ns)),
                "image_parts": sum(n.startswith("word/media/") for n in names),
            }
    except (zipfile.BadZipFile, ET.ParseError, KeyError) as exc:
        raise ExperimentError("DOCX_INVALID") from exc


def load_bundle(bundle: Path) -> tuple[Json, Json, AssetResolver]:
    """Verify the full saved package before restoring its public typed schema."""
    if bundle.is_symlink() or not bundle.is_dir():
        raise ExperimentError("BUNDLE_PATH_INVALID")
    manifest = read_json(safe_path(bundle, "bundle-manifest.json"))
    if manifest.get("schema") != SCHEMA or not isinstance(manifest.get("files"), dict):
        raise ExperimentError("BUNDLE_SCHEMA_INVALID")
    root = safe_path(bundle, "result")
    files = manifest["files"]
    for name, expected in files.items():
        path = safe_path(root, name)
        if not path.is_file():
            raise ExperimentError("BUNDLE_FILE_MISSING")
        if digest(path) != expected:
            raise ExperimentError("BUNDLE_HASH_MISMATCH")
    if inventory(root) != files:
        raise ExperimentError("BUNDLE_FILE_SET_MISMATCH")
    if not {"middle_json.json", "markdown.md", "structured_content.json"} <= files.keys():
        raise ExperimentError("RESULT_BUNDLE_INCOMPLETE")
    middle = read_json(root / "middle_json.json")
    if middle.get("schema") != "docvortex.middle" or middle.get("schema_version") != "2.0":
        raise ExperimentError("MIDDLE_SCHEMA_INVALID")
    return manifest, middle, AssetResolver(root, files)


def export_bundle(bundle: Path, output: Path, receipt: Json) -> None:
    """Use only the saved MiddleJson and assets; never import a parser."""
    manifest, middle, resolver = load_bundle(bundle)
    receipt["source"] = manifest.get("source", {})
    receipt["parse_configuration"] = manifest.get("parse_configuration", {})
    receipt["bundle_manifest_sha256"] = digest(bundle / "bundle-manifest.json")
    with offline():
        shared = importlib.import_module("docvortex.schema")
        try:
            document = shared.MiddleJson.from_dict(middle)
        except (ValueError, TypeError) as exc:
            raise ExperimentError("MIDDLE_SCHEMA_INVALID") from exc
        # Upstream validates references, including images embedded in visual HTML.
        assets = {name: resolver(name) for name in resolver.files if name.startswith("images/")}
        try:
            importlib.import_module("docvortex.export").validate_materialized_assets(
                document, assets
            )
        except (ValueError, TypeError) as exc:
            raise ExperimentError("ASSET_VALIDATION_FAILED") from exc
        renderer = importlib.import_module("mineru.render")
        data = renderer.render_docx(document, asset_resolver=resolver)
    receipt["docx_inventory"] = inspect_docx(data)
    target = output / "B.docx"
    with target.open("xb") as stream:
        stream.write(data)
    receipt.update(
        {
            "status": "DOCX_EXPORTED_NOT_ACCEPTED",
            "docx": "B.docx",
            "docx_sha256": digest(target),
            "renderer": "mineru.render.render_docx",
        }
    )


def parse_once(args: argparse.Namespace, output: Path, receipt: Json) -> Path:
    """Perform exactly one explicitly authorized LOCAL SDK parse, with no retry."""
    if not args.allow_local_parse:
        raise ExperimentError("LOCAL_PARSE_AUTHORIZATION_REQUIRED")
    if not args.input.is_file() or args.input.suffix.lower() not in {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
    }:
        raise ExperimentError("INPUT_INVALID")
    if args.input.suffix.lower() != ".pdf" and args.page != 1:
        raise ExperimentError("IMAGE_PAGE_MUST_BE_ONE")
    source = {
        "sha256": digest(args.input),
        "physical_page": args.page,
        "input_suffix": args.input.suffix.lower(),
        "evidence_kind": args.evidence_kind,
    }
    receipt["source"] = source
    bundle = output / "bundle"
    result_root = bundle / "result"
    result_root.mkdir(parents=True)
    config = {
        "tier_requested": args.tier,
        "tier_actual": "unknown",
        "backend": "unknown",
        "device": "unknown",
        "model_revision": "unknown",
        "model_file_hashes": "unknown",
        "transport": "local_sdk",
        "ocr_mode": "auto",
        "image_analysis": True,
    }
    receipt["parse_configuration"] = config
    write_json(output / "run-receipt.json", receipt)
    # Environment flags prevent the common hub clients from attempting downloads.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    with offline():
        parser = importlib.import_module("mineru.parser")
        receipt["parse_calls"] = 1
        receipt["remote_requests"] = "NOT_INSTRUMENTED_NATIVE_RUNTIME"
        write_json(output / "run-receipt.json", receipt)
        result = parser.parse(
            str(args.input.resolve()),
            tier=args.tier,
            page_range=str(args.page),
            ocr_mode="auto",
            image_analysis=True,
        )
        result.save(BundleWriter(result_root))
    middle = read_json(result_root / "middle_json.json")
    config["tier_actual"] = middle.get("extensions", {}).get("mineru", {}).get("tier", "unknown")
    config["producer"] = middle.get("metadata", {}).get("producer", {})
    write_json(
        bundle / "bundle-manifest.json",
        {
            "schema": SCHEMA,
            "files": inventory(result_root),
            "source": source,
            "parse_configuration": config,
            "runtime": runtime(),
        },
    )
    if config["tier_actual"] != args.tier:
        raise ExperimentError("TIER_NOT_CONFIRMED")
    return bundle


def cli() -> argparse.ArgumentParser:
    """Expose isolated explicit commands; default app routes remain untouched."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inspect-env")
    parse = sub.add_parser("parse")
    parse.add_argument("--input", required=True, type=Path)
    parse.add_argument("--page", required=True, type=int)
    parse.add_argument("--tier", choices=["standard", "flash"], default="standard")
    parse.add_argument("--allow-local-parse", action="store_true")
    parse.add_argument("--evidence-kind", choices=["real", "synthetic"], required=True)
    export = sub.add_parser("export")
    export.add_argument("--bundle", required=True, type=Path)
    for command in (parse, export):
        command.add_argument("--output", required=True, type=Path, help="NEW private run directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Persist failed/partial runs and emit only sanitized status codes."""
    args = cli().parse_args(argv)
    if args.command == "inspect-env":
        print(json.dumps(runtime()))
        return 0
    if args.command == "parse" and args.page < 1:
        print(json.dumps({"status": "BLOCKED", "error": "PAGE_MUST_BE_POSITIVE"}))
        return 2
    if args.command == "export" and args.output.resolve().is_relative_to(args.bundle.resolve()):
        print(json.dumps({"status": "BLOCKED", "error": "OUTPUT_OVERLAPS_BUNDLE"}))
        return 2
    started = time.monotonic()
    try:
        args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    except OSError:
        print(json.dumps({"status": "BLOCKED", "error": "NEW_OUTPUT_REQUIRED"}))
        return 2
    receipt: Json = {
        "task": "P2W-U1-01",
        "status": "STARTED",
        "command": args.command,
        "started_at": datetime.now(UTC).isoformat(),
        "runtime": runtime(),
        "parse_calls": 0,
        "remote_requests": 0,
        "retries": 0,
        "word_open": "NOT_RUN",
        "agent_visual": "NOT_RUN",
        "human_acceptance": "PENDING",
        "local_image_formula_fallbacks": "NOT_REVIEWED",
        "quality": "NOT_VERIFIED",
    }
    code = 0
    try:
        if args.command == "parse" and not args.allow_local_parse:
            raise ExperimentError("LOCAL_PARSE_AUTHORIZATION_REQUIRED")
        require_runtime()
        receipt["dependencies"] = dict(
            sorted(
                (d.metadata["Name"], d.version)
                for d in importlib.metadata.distributions()
                if d.metadata["Name"]
            )
        )
        with quiet_upstream():
            bundle = (
                parse_once(args, args.output, receipt) if args.command == "parse" else args.bundle
            )
            export_bundle(bundle, args.output, receipt)
    except Exception as exc:
        code = 1
        receipt.update(
            {
                "status": "PARTIAL" if (args.output / "bundle").exists() else "BLOCKED",
                "error": str(exc) if isinstance(exc, ExperimentError) else "UPSTREAM_FAILED",
                "exception_type": type(exc).__name__,
            }
        )
    finally:
        receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
        write_json(args.output / "run-receipt.json", receipt)
    print(
        json.dumps(
            {k: receipt[k] for k in ("status", "parse_calls", "word_open")}
            | ({"error": receipt["error"]} if "error" in receipt else {})
        )
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
