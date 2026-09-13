"""Private storage, strict geometry and Layout IR construction helpers."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import re
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from PIL import Image

from . import VERSION

Json = dict[str, Any]
ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / "tmp/docx-demo"
JOBS = PRIVATE / "jobs"
MAX_BYTES = 25 * 1024 * 1024


class DemoError(ValueError):
    """An explicit safe diagnostic code, never a provider body."""


def digest(path: Path) -> str:
    """Hash exact bytes, without interpreting evidence."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    """Resolve a registered relative path and reject traversal and symlinks."""
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise DemoError("INVALID_PATH")
    p = root
    for part in rel.parts:
        p = p / part
        if p.is_symlink():
            raise DemoError("SYMLINK_REJECTED")
    if not p.resolve().is_relative_to(root.resolve()):
        raise DemoError("INVALID_PATH")
    return p


def private_dir(path: Path) -> None:
    """Create private storage only beneath the dedicated ignored directory."""
    absolute = path.absolute()
    if not absolute.is_relative_to(PRIVATE) or ".." in absolute.parts:
        raise DemoError("PRIVATE_STORAGE_REQUIRED")
    safe_path(ROOT, str(absolute.relative_to(ROOT)))
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    for p in [path, *path.parents]:
        if p == PRIVATE.parent:
            break
        p.chmod(0o700)


def save(path: Path, value: Any) -> None:
    """Write UTF-8 private JSON with owner-only access."""
    private_dir(path.parent)
    safe_path(PRIVATE, str(path.absolute().relative_to(PRIVATE)))
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode(
        "utf-8", errors="backslashreplace"
    )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    path.chmod(0o600)


def read(path: Path) -> Json:
    """Read a JSON object, retaining candidate wire types."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DemoError("JSON_OBJECT_REQUIRED")
    return value


def secure_tree(path: Path) -> None:
    """Seal files produced by third-party writers."""
    for item in [path, *path.rglob("*")]:
        if item.is_symlink():
            raise DemoError("SYMLINK_REJECTED")
        item.chmod(0o700 if item.is_dir() else 0o600)


def new_job(output_root: Path = JOBS) -> Path:
    """Allocate a unique private job; never reuse a previous job."""
    output_root = output_root.absolute()
    private_dir(output_root)
    job = output_root / ("demo-" + uuid.uuid4().hex)
    job.mkdir(mode=0o700)
    private_dir(job / "assets")
    save(job / "state.json", {"state": "准备"})
    return job


def job_path(job_id: str, output_root: Path = JOBS) -> Path:
    """Resolve only opaque job identifiers."""
    if not re.fullmatch(r"demo-[a-f0-9]{32}", job_id):
        raise DemoError("INVALID_JOB_ID")
    p = safe_path(output_root, job_id)
    if not p.is_dir():
        raise DemoError("JOB_NOT_FOUND")
    return p


def validate_input(path: Path) -> None:
    """Reject empty, oversized, unsupported or symlinked authorized inputs."""
    absolute = path.absolute()
    safe_path(Path(absolute.anchor), str(absolute.relative_to(absolute.anchor)))
    if not path.is_file():
        raise DemoError("INPUT_MISSING")
    if not 0 < path.stat().st_size <= MAX_BYTES:
        raise DemoError("INPUT_SIZE_LIMIT")
    if path.suffix.lower() not in {".pdf", ".jpg", ".jpeg", ".png"}:
        raise DemoError("UNSUPPORTED_FORMAT")


def image_size(path: Path) -> tuple[int, int]:
    """Validate raster dimensions before decoding large images."""
    with Image.open(path) as im:
        w, h = im.size
        if max(w, h) > 4000 or min(w, h) < 1 or im.format not in {"JPEG", "PNG"}:
            raise DemoError("IMAGE_RESOURCE_LIMIT")
        if im.getexif().get(274, 1) != 1:
            raise DemoError("ORIENTATION_REVIEW_REQUIRED")
    with Image.open(path) as verified:
        verified.verify()
    return w, h


def box_valid(box: Sequence[float]) -> bool:
    """Test finite non-empty geometry; outside-page evidence is retained."""
    return (
        len(box) == 4
        and all(
            isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) for v in box
        )
        and box[2] > box[0]
        and box[3] > box[1]
    )


def transform(box: list[float], sx: float, sy: float) -> list[float]:
    """Scale top-left coordinates at the adapter boundary."""
    if not box_valid(box) or sx <= 0 or sy <= 0:
        raise DemoError("INVALID_GEOMETRY")
    return [box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy]


def union(boxes: list[list[float]]) -> list[float]:
    """Return an enclosing region without inventing sub-line coordinates."""
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def intersection(a: list[float], b: list[float]) -> float:
    """Return overlap area."""
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def area(b: list[float]) -> float:
    """Return nonnegative rectangle area."""
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def union_area(boxes: list[list[float]]) -> float:
    """Measure rectangle union by a sweep; overlapping fallbacks count once."""
    xs = sorted({x for b in boxes for x in (b[0], b[2])})
    result = 0.0
    for left, right in itertools.pairwise(xs):
        intervals = sorted((b[1], b[3]) for b in boxes if b[0] < right and b[2] > left)
        end = -math.inf
        length = 0.0
        for lo, hi in intervals:
            length += max(0.0, hi - max(lo, end))
            end = max(end, hi)
        result += (right - left) * length
    return result


def text_content(text: str) -> Json:
    """Create schema-native text content, not Markdown."""
    return {"kind": "text", "plain_text": text, "runs": [], "language_hints": ["zh", "en"]}


def candidate(cid: str, provider: str, text: str, evidence: Json, selected: bool = True) -> Json:
    """Retain literal candidate text and unknown engine probability."""
    return {
        "id": cid,
        "provider": provider,
        "model_id": {
            "pp_structure": "PP-StructureV3",
            "ovis_ocr2": "ovis-ocr2",
            "native_pdf": "PDFium",
        }.get(provider, provider),
        "model_version": "unknown",
        "content_kind": "text",
        "text": text,
        "engine_confidence": None,
        "system_score": 0,
        "selected": selected,
        "evidence": evidence,
    }


def block(
    bid: str,
    page: int,
    bbox: list[float],
    text: str,
    source: str,
    kind: str = "paragraph",
    evidence: Json | None = None,
) -> Json:
    """Create the minimum legal Layout IR block."""
    c = candidate(bid + "-c0", source, text, evidence or {})
    return {
        "id": bid,
        "type": kind,
        "page_index": page,
        "bbox": bbox,
        "rotation": 0,
        "source_type": source,
        "engine": source,
        "engine_version": "unknown",
        "content": text_content(text),
        "children": [],
        "relations": [],
        "provenance_refs": [bid],
        "flags": [],
        "engine_confidence": None,
        "system_confidence": 0,
        "geometry_source": source,
        "content_candidates": [c],
        "selected_candidate_id": c["id"],
        "render_policy": "editable",
    }


def page(index: int, w: float, h: float, source: str) -> Json:
    """Create a page with explicit unscored system values required by schema."""
    return {
        "page_index": index,
        "width_pt": w,
        "height_pt": h,
        "rotation": 0,
        "page_type": source,
        "classification_confidence": 0,
        "complexity_score": 0,
        "blocks": [],
        "reading_order": [],
        "source_refs": [],
        "routing_decision": "DEMO_REVIEW",
        "model_calls": [],
    }


def layout(job: Path, source: Path, count: int) -> Json:
    """Create a production-schema document with demo metadata."""
    return {
        "schema_version": "layout-ir/1.1",
        "document_id": job.name,
        "source": {"filename": source.name, "sha256": digest(source), "page_count": count},
        "metadata": {
            "demo_version": VERSION,
            "score_semantics": "0 = unscored sentinel required by schema; not confidence",
        },
        "pages": [],
        "styles": {},
        "assets": [],
        "relations": [],
        "issues": [],
        "provenance": {
            "demo_source_hashes": {
                str(p.relative_to(ROOT)): digest(p)
                for p in [
                    *Path(__file__).parent.glob("*.py"),
                    ROOT / "scripts/docx_demo.py",
                    ROOT / "uv.lock",
                ]
            }
        },
        "metrics": {},
        "model_registry": {},
    }


def issue(ir: Json, code: str, message: str, blocks: list[str], page_index: int = 0) -> None:
    """Append a traceable unresolved review issue."""
    existing = {i["id"] for i in ir["issues"]}
    index = len(ir["issues"])
    while f"issue-{index}" in existing:
        index += 1
    ir["issues"].append(
        {
            "id": f"issue-{index}",
            "severity": "warning",
            "type": code,
            "page_index": page_index,
            "block_ids": blocks,
            "message": message,
            "status": "open",
            "suggested_actions": ["compare_source", "manual_review"],
        }
    )


def relation(ir: Json, kind: str, origin: str, target: str, evidence: Json) -> None:
    """Separate semantic references from physical placement evidence."""
    existing = {r["id"] for r in ir["relations"]}
    index = len(existing)
    while f"rel-{index}" in existing:
        index += 1
    rid = f"rel-{index}"
    ir["relations"].append(
        dict(
            id=rid,
            type=kind,
            **{"from": origin, "to": target},
            confidence=0,
            method="demo_rule",
            evidence=evidence,
        )
    )


def validate(ir: Json) -> None:
    """Validate every exported IR against the unchanged public schema."""
    Draft202012Validator(read(ROOT / "specs/layout-ir.schema.json")).validate(ir)


def crop(
    job: Path,
    ir: Json,
    page_data: Json,
    bbox: list[float],
    aid: str,
    asset_type: str = "image",
    padding: float = 2.0,
) -> str:
    """Crop the source image using recorded transforms; clamp only crop boundaries."""
    info = ir["provenance"]["pages"][str(page_data["page_index"])]
    sx, sy = info["point_to_pixel"]
    pixels = transform(bbox, sx, sy)
    source = safe_path(job, info["image_path"])
    with Image.open(source) as im:
        bound = [
            max(0, math.floor(pixels[0] - padding)),
            max(0, math.floor(pixels[1] - padding)),
            min(im.width, math.ceil(pixels[2] + padding)),
            min(im.height, math.ceil(pixels[3] + padding)),
        ]
        if not box_valid(bound):
            raise DemoError("CROP_OUTSIDE_PAGE")
        image = im.crop((bound[0], bound[1], bound[2], bound[3]))
        path = safe_path(job, f"assets/{aid}-{uuid.uuid4().hex}.png")
        image.save(path)
        image.close()
    path.chmod(0o600)
    ir["assets"].append(
        {
            "id": aid,
            "type": asset_type,
            "path": str(path.relative_to(job)),
            "sha256": digest(path),
            "mime_type": "image/png",
            "pixel_width": bound[2] - bound[0],
            "pixel_height": bound[3] - bound[1],
            "source_page_index": page_data["page_index"],
            "source_bbox": bbox,
            "extraction_method": "source_crop",
        }
    )
    ir["provenance"][aid] = {"raw_bbox_pt": bbox, "padding_px": padding, "crop_bbox_px": bound}
    return aid


def invalid_xml_text(text: str) -> bool:
    """Identify XML 1.0 incompatible characters without altering source text."""
    return any(
        not (
            ord(c) in {9, 10, 13}
            or 32 <= ord(c) <= 0xD7FF
            or 0xE000 <= ord(c) <= 0xFFFD
            or 0x10000 <= ord(c) <= 0x10FFFF
        )
        for c in text
    )


def prune_preview_assets(job: Path, candidates: set[Path]) -> None:
    """Remove only preview-owned files unreferenced by every persisted layout."""
    registered = set()
    for layout_path in job.glob("layout.*.json"):
        for asset in read(layout_path).get("assets", []):
            registered.add(safe_path(job, asset["path"]))
    for path in candidates - registered:
        if path.parent == job / "assets" and path.is_file() and not path.is_symlink():
            path.unlink()


def finish_preview(job: Path) -> None:
    """End a preview only after a saved revision exists and reclaim its unused assets."""
    path = job / "layout.preview.json"
    if path.exists():
        assets = {safe_path(job, a["path"]) for a in read(path).get("assets", [])}
        path.unlink()
        prune_preview_assets(job, assets)
