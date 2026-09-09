"""T0016 development-only raster evidence; no production Layout IR or adapters.

Only run() performs HTTP. Everything else is reproducible from private local evidence.
EvalRegion coordinates are raster pixels, never PDF points.
"""

from __future__ import annotations

import base64
import hashlib
import html
import itertools
import json
import math
import re
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from jsonschema import Draft202012Validator
from PIL import Image, ImageDraw
from PIL import __version__ as pillow_version

from model_contract_discovery import (
    DiscoveryConfig,
    HttpClient,
    assert_live_preconditions,
    compute_file_hash,
    compute_json_fingerprint,
    load_config,
    normalize_openapi,
    openai_endpoint_url,
    safe_parse_monkey_content,
)

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = ROOT / "tmp/raster-regression"
BASELINE_SHA = "74f619b8ebea1ce75cf07629022bf60728d00a3d"
BASELINE_RUN = "t0015-mac-20260909T061855Z"
Json = dict[str, Any]


def require_storage(path: Path, collection: str) -> None:
    """Keep real CLI evidence under the ignored cases/runs collections."""
    base = (PRIVATE_ROOT / collection).resolve()
    if path.is_symlink() or not path.resolve().is_relative_to(base) or path.resolve() == base:
        raise ValueError("PRIVATE_STORAGE_REQUIRED")


def now() -> str:
    """UTC timestamp for evidence chronology."""
    return datetime.now(UTC).isoformat()


def read_json(path: Path) -> Json:
    """Read a UTF-8 evidence object."""
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("EVIDENCE_OBJECT_REQUIRED")
    return obj


def private_dir(path: Path, *, empty: bool = False) -> None:
    """Create restricted directories, refusing links and nonempty run reuse."""
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError("SYMLINK_FORBIDDEN")
    if empty and path.exists() and any(path.iterdir()):
        raise ValueError("OUTPUT_NOT_EMPTY")
    missing = []
    parent = path
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for item in reversed(missing):
        item.mkdir(mode=0o700)
    path.chmod(0o700)


def write_private(path: Path, value: Any) -> None:
    """Write JSON with restricted permissions, no body logging."""
    private_dir(path.parent)
    if path.is_symlink():
        raise ValueError("SYMLINK_FORBIDDEN")
    with path.open("w", encoding="utf-8") as stream:
        path.chmod(0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def pixel_hash(image: Image.Image) -> str:
    """Hash width, height, mode and decoded RGB bytes with a fixed separator."""
    rgb = image.convert("RGB")
    header = f"{rgb.width},{rgb.height},RGB\0".encode("ascii")
    return hashlib.sha256(header + rgb.tobytes()).hexdigest()


def prepare(source: Path, case_id: str, case_dir: Path) -> Json:
    """Keep JPEG bytes unchanged; create a pixel-identical lossless PNG control."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", case_id):
        raise ValueError("INVALID_CASE_ID")
    private_dir(case_dir, empty=True)
    original = source.read_bytes()
    with Image.open(source) as im:
        info = {
            "format": im.format,
            "mode": im.mode,
            "width": im.width,
            "height": im.height,
            "exif_orientation": im.getexif().get(274, 1),
            "icc_sha256": hashlib.sha256(im.info["icc_profile"]).hexdigest()
            if im.info.get("icc_profile")
            else None,
        }
        if (
            im.format != "JPEG"
            or im.mode not in {"RGB", "L"}
            or info["exif_orientation"] != 1
            or info["icc_sha256"]
        ):
            write_private(
                case_dir / "preparation-blocked.private.json",
                {"status": "SIMPLE_COMPARISON_CONDITIONS_NOT_MET", **info},
            )
            raise ValueError("SIMPLE_COMPARISON_CONDITIONS_NOT_MET")
        rgb = im.convert("RGB")
    jpg = case_dir / "source.jpg"
    jpg.write_bytes(original)
    jpg.chmod(0o600)
    png = case_dir / "decoded-equivalent.png"
    rgb.save(png, format="PNG", compress_level=6, optimize=False)
    png.chmod(0o600)
    with Image.open(png) as decoded:
        if decoded.size != rgb.size or decoded.convert("RGB").tobytes() != rgb.tobytes():
            raise ValueError("PIXEL_EQUIVALENCE_FAILED")
    if source.read_bytes() != original or jpg.read_bytes() != original:
        raise ValueError("SOURCE_CHANGED")
    variants = {
        key: {
            "filename": path.name,
            "mime": mime,
            "file_sha256": compute_file_hash(path),
            "size_bytes": path.stat().st_size,
            "decoded_pixel_sha256": pixel_hash(rgb),
        }
        for key, path, mime in [("jpg", jpg, "image/jpeg"), ("png", png, "image/png")]
    }
    manifest = {
        "case_id": case_id,
        **info,
        "variants": variants,
        "decoder": {"pillow": pillow_version, "jpeg": Image.core.jpeglib_version},
        "png_encoder": {"compress_level": 6, "optimize": False},
        "conversion": f"{info['mode']} decoded to RGB; no EXIF transpose or ICC transform",
        "source_unchanged": True,
        "pixel_equivalence_verified": True,
        "prepared_at": now(),
    }
    write_private(case_dir / "input-manifest.private.json", manifest)
    return manifest


def verify_inputs(case_dir: Path, manifest: Json) -> None:
    """Reject input bytes, content formats, dimensions or pixel identity drift."""
    for variant, value in manifest["variants"].items():
        if value["filename"] != {"jpg": "source.jpg", "png": "decoded-equivalent.png"}[variant]:
            raise ValueError("INPUT_FILENAME_MISMATCH")
        path = case_dir / value["filename"]
        with Image.open(path) as image:
            valid = (
                image.format == {"jpg": "JPEG", "png": "PNG"}[variant]
                and list(image.size) == [manifest["width"], manifest["height"]]
                and pixel_hash(image) == value["decoded_pixel_sha256"]
            )
        if compute_file_hash(path) != value["file_sha256"] or not valid:
            raise ValueError("INPUT_HASH_MISMATCH")
    if (
        manifest["variants"]["jpg"]["decoded_pixel_sha256"]
        != manifest["variants"]["png"]["decoded_pixel_sha256"]
    ):
        raise ValueError("PIXEL_HASH_MISMATCH")


def bbox_error(box: Any, width: int, height: int) -> str | None:
    """Classify invalid geometry without clamping or rounding it."""
    if not isinstance(box, list) or len(box) != 4:
        return "INVALID_BBOX_SHAPE"
    if not all(
        isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) for v in box
    ):
        return "NONFINITE_BBOX"
    if box[0] >= box[2] or box[1] >= box[3]:
        return "NONPOSITIVE_BBOX"
    if box[0] < 0 or box[1] < 0 or box[2] > width or box[3] > height:
        return "OUT_OF_BOUNDS_BBOX"
    return None


def region(opaque_id: str, label: str, box: list[float], **extra: Any) -> Json:
    """Construct a development EvalRegion, preserving raw labels and coordinates."""
    common = {
        "image": "visual",
        "picture": "visual",
        "chart": "visual",
        "figure": "visual",
        "doc_title": "title",
        "paragraph_title": "title",
        "figure_title": "caption",
        "image_caption": "caption",
        "page_number": "footer",
        "inline_formula": "formula",
        "formula": "formula",
    }
    return {
        "id": opaque_id,
        "type": common.get(label, label),
        "raw_label": label,
        "bbox": box,
        "order": None,
        "coordinate_space": "raster_pixel",
        **extra,
    }


def validate_ground_truth(case_dir: Path) -> Json:
    """Validate visual annotation and freeze its hash in a separate manifest."""
    manifest = read_json(case_dir / "input-manifest.private.json")
    verify_inputs(case_dir, manifest)
    path = case_dir / "ground-truth.private.json"
    gt = read_json(path)
    required = {
        "case_id",
        "source_sha256",
        "pixel_sha256",
        "page_width",
        "page_height",
        "annotation_version",
        "reviewer_type",
        "reviewer_id",
        "reviewed_at",
        "review_status",
        "regions",
        "reading_order_constraints",
        "critical_text_checks",
    }
    if not required <= gt.keys():
        raise ValueError("GROUND_TRUTH_FIELDS_MISSING")
    if (
        gt["case_id"] != manifest["case_id"]
        or gt["source_sha256"] != manifest["variants"]["jpg"]["file_sha256"]
        or gt["pixel_sha256"] != manifest["variants"]["jpg"]["decoded_pixel_sha256"]
        or [gt["page_width"], gt["page_height"]] != [manifest["width"], manifest["height"]]
    ):
        raise ValueError("GROUND_TRUTH_INPUT_MISMATCH")
    if gt["reviewer_type"] not in {"human", "agent_visual"} or gt["review_status"] != "REVIEWED":
        raise ValueError("BLOCKED_GROUND_TRUTH")
    if (
        not all(gt[k] for k in ("annotation_version", "reviewer_id", "reviewed_at"))
        or not gt["regions"]
    ):
        raise ValueError("BLOCKED_GROUND_TRUTH")
    ids = [r["id"] for r in gt["regions"]]
    if len(ids) != len(set(ids)):
        raise ValueError("DUPLICATE_REGION_ID")
    if any(
        not isinstance(i, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", i) for i in ids
    ):
        raise ValueError("OPAQUE_REGION_ID_REQUIRED")
    for r in gt["regions"]:
        if (
            not {"type", "bbox", "status", "uncertainty", "notes", "reference", "layer"} <= r.keys()
            or r["status"] not in {"confirmed", "uncertain"}
            or bbox_error(r["bbox"], gt["page_width"], gt["page_height"])
        ):
            raise ValueError("INVALID_GROUND_TRUTH_REGION")
    confirmed = {r["id"] for r in gt["regions"] if r["status"] == "confirmed"}
    if not confirmed or not any(c.get("status") == "confirmed" for c in gt["critical_text_checks"]):
        raise ValueError("BLOCKED_GROUND_TRUTH")
    for pair in gt["reading_order_constraints"]:
        if len(pair) != 2 or any(i not in confirmed for i in pair) or pair[0] == pair[1]:
            raise ValueError("INVALID_ORDER_CONSTRAINT")
    for check in gt["critical_text_checks"]:
        if (
            not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", str(check.get("id", "")))
            or check.get("region_id") not in ids
            or check.get("status") not in {"confirmed", "uncertain"}
            or not isinstance(check.get("reference"), str)
        ):
            raise ValueError("INVALID_TEXT_CHECK")
    frozen = {
        "ground_truth_sha256": compute_file_hash(path),
        "annotation_version": gt["annotation_version"],
        "input_manifest_sha256": compute_file_hash(case_dir / "input-manifest.private.json"),
    }
    lock = case_dir / "ground-truth-manifest.private.json"
    if lock.exists() and read_json(lock) != frozen:
        raise ValueError("GROUND_TRUTH_FROZEN_MISMATCH_NEW_VERSION_REQUIRED")
    write_private(lock, frozen)
    return frozen


def matrix() -> list[Json]:
    """Fixed 14 inference schedule, alternating the first format by repetition."""
    return [
        {"provider": provider, "variant_id": variant, "repeat_index": repeat}
        for provider, repeats in [("monkey", 3), ("pp", 3), ("ovis", 1)]
        for repeat in range(1, repeats + 1)
        for variant in (["jpg", "png"] if repeat % 2 else ["png", "jpg"])
    ]


def strip_media(value: Any) -> Any:
    """Remove image payloads and URLs without fetching; retain private scoring content."""
    if isinstance(value, dict):
        return {
            k: strip_media(v)
            for k, v in value.items()
            if k.lower() not in {"images", "outputimages", "inputimage", "image", "base64"}
        }
    if isinstance(value, list):
        return [strip_media(v) for v in value]
    if isinstance(value, str):
        if value.startswith(("http://", "https://", "data:")) or (
            len(value) > 256 and re.fullmatch(r"[A-Za-z0-9+/=\r\n]+", value)
        ):
            return "[MEDIA_REMOVED]"
        return re.sub(r"!\[[^\]]*\]\([^)]*\)", "[IMAGE_REFERENCE_REMOVED]", value)
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite_original": repr(value)}
    return value


def safe_finish_reason(body: Json) -> str | None:
    """Read finish metadata without trusting a malformed choices container."""
    choices = body.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        value = choices[0].get("finish_reason")
        return value if isinstance(value, str) else None
    return None


def parse_prediction(provider: str, body: Json, width: int, height: int) -> Json:
    """Normalize real responses into separate raster evaluation layers."""
    output: Json = {
        "layers": {"macro": [], "paragraph": [], "fine": []},
        "content": "",
        "model_settings": {},
        "coordinate_mapping": "identity_raster_pixels",
    }
    if provider in {"monkey", "ovis"}:
        choices = body.get("choices", [])
        if len(choices) != 1 or not isinstance(choices[0].get("message", {}).get("content"), str):
            raise ValueError("PARSE_FAILED")
        if choices[0].get("finish_reason") != "stop":
            raise ValueError(
                "INCOMPLETE_LENGTH"
                if choices[0].get("finish_reason") == "length"
                else "INCOMPLETE_FINISH_REASON"
            )
        content = choices[0]["message"]["content"]
        if provider == "ovis":
            output["content"] = content
            return output
        blocks, _ = safe_parse_monkey_content(content)
        output["coordinate_mapping"] = {
            "source": "normalized_1000",
            "scale_x": width / 1000,
            "scale_y": height / 1000,
        }
        for index, block in enumerate(blocks):
            raw = block.get("bbox")
            error = bbox_error(raw, 1000, 1000)
            box = (
                [
                    raw[0] * width / 1000,
                    raw[1] * height / 1000,
                    raw[2] * width / 1000,
                    raw[3] * height / 1000,
                ]
                if not error
                else raw
            )
            label = block.get("label", "unknown")
            item = region(
                f"m{index:03}",
                label,
                box,
                raw_bbox=raw,
                raw_unit="normalized_1000",
                order=index,
                error=error,
                score=None,
            )
            output["layers"]["macro"].append(item)
            output["layers"]["paragraph"].append(item.copy())
        return output
    result = body.get("result", {})
    pages = result.get("layoutParsingResults", [])
    if len(pages) != 1 or not isinstance(pages[0].get("prunedResult"), dict):
        raise ValueError("PARSE_FAILED")
    page = pages[0]["prunedResult"]
    size = [page.get("width"), page.get("height")]
    data_info = result.get("dataInfo", {})
    if size != [width, height] or [data_info.get("width"), data_info.get("height")] != size:
        raise ValueError("COORDINATE_MAPPING_UNRESOLVED")
    output["returned_size"] = size
    output["model_settings"] = page.get("model_settings", {})
    output["preprocessor_settings"] = page.get("doc_preprocessor_res", {})
    output["ocr_settings"] = page.get("overall_ocr_res", {}).get("model_settings", {})
    for index, block in enumerate(page.get("parsing_res_list", [])):
        box = block.get("block_bbox")
        output["layers"]["paragraph"].append(
            region(
                f"p{index:03}",
                block.get("block_label", "unknown"),
                box,
                raw_bbox=box,
                raw_unit="returned_image_pixel",
                order=block.get("block_order"),
                content=block.get("block_content", ""),
                error=bbox_error(box, width, height),
                score=None,
            )
        )
    for index, block in enumerate(page.get("layout_det_res", {}).get("boxes", [])):
        box = block.get("coordinate")
        output["layers"]["macro"].append(
            region(
                f"l{index:03}",
                block.get("label", "unknown"),
                box,
                raw_bbox=box,
                raw_unit="returned_image_pixel",
                score=block.get("score"),
                error=bbox_error(box, width, height),
            )
        )
    ocr = page.get("overall_ocr_res", {})
    boxes, texts, scores = (
        ocr.get("rec_boxes", []),
        ocr.get("rec_texts", []),
        ocr.get("rec_scores", []),
    )
    if not (len(boxes) == len(texts) == len(scores)):
        raise ValueError("PARSE_FAILED_OCR_ARRAY_LENGTH")
    for index, (box, text, score) in enumerate(zip(boxes, texts, scores, strict=True)):
        output["layers"]["fine"].append(
            region(
                f"f{index:03}",
                "text",
                box,
                raw_bbox=box,
                raw_unit="returned_image_pixel",
                content=text,
                score=score,
                error=bbox_error(box, width, height),
            )
        )
    # Formula candidates retained for private diagnosis, not added again to content counts.
    output["formula_candidates"] = page.get("formula_res_list", [])
    return output


def intersection(a: list[float], b: list[float]) -> float:
    """Intersection area of valid axis-aligned raster rectangles."""
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def area(box: list[float]) -> float:
    """Rectangle area; callers validate boxes first."""
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def iou(a: list[float], b: list[float]) -> float:
    """Intersection over union, with zero union explicitly zero."""
    overlap = intersection(a, b)
    union = area(a) + area(b) - overlap
    return overlap / union if union > 0 else 0.0


def evaluation_type(item: Json) -> str:
    """Correct case/aliases for scoring only; immutable collected regions stay intact."""
    label = str(item["type"]).casefold()
    return {
        "picture": "visual",
        "image": "visual",
        "chart": "visual",
        "list-item": "text",
        "section-header": "title",
        "page-footer": "footer",
    }.get(label, label)


def geometry_metrics(gt: list[Json], predictions: list[Json], threshold: float) -> Json:
    """Deterministic descending-IoU greedy one-to-one matches within the same class.

    This diagnostic matching rule is frozen; merges/splits never increase TP.
    """
    targets = [r for r in gt if r.get("status", "confirmed") == "confirmed" and not r.get("error")]
    valid = [r for r in predictions if not r.get("error")]
    edges = sorted(
        (-iou(g["bbox"], p["bbox"]), str(g["id"]), str(p["id"]))
        for g in targets
        for p in valid
        if evaluation_type(g) == evaluation_type(p) and iou(g["bbox"], p["bbox"]) >= threshold
    )
    used_g: set[str] = set()
    used_p: set[str] = set()
    matches: list[Json] = []
    for negative, gid, pid in edges:
        if gid not in used_g and pid not in used_p:
            used_g.add(gid)
            used_p.add(pid)
            matches.append({"gt_id": gid, "prediction_id": pid, "iou": -negative})
    merges = [
        {
            "prediction_id": p["id"],
            "gt_ids": [
                g["id"]
                for g in targets
                if intersection(g["bbox"], p["bbox"]) / area(g["bbox"]) >= 0.5
            ],
        }
        for p in valid
    ]
    splits = [
        {
            "gt_id": g["id"],
            "prediction_ids": [
                p["id"]
                for p in valid
                if intersection(g["bbox"], p["bbox"]) / area(p["bbox"]) >= 0.5
            ],
        }
        for g in targets
    ]
    values = [m["iou"] for m in matches]
    count = len(matches)
    return {
        "gt_count": len(targets),
        "prediction_count": len(predictions),
        "invalid_count": len(predictions) - len(valid),
        "uncertain_count": sum(r.get("status") == "uncertain" for r in gt),
        "reference_invalid_count": sum(bool(r.get("error")) for r in gt),
        "tp": count,
        "fp": len(predictions) - count,
        "fn": len(targets) - count,
        "precision": count / len(predictions) if predictions else None,
        "recall": count / len(targets) if targets else None,
        "iou_mean": statistics.mean(values) if values else None,
        "iou_median": statistics.median(values) if values else None,
        "matches": matches,
        "missing_gt_ids": sorted({r["id"] for r in targets} - used_g),
        "unmatched_prediction_ids": sorted({r["id"] for r in predictions} - used_p),
        "merges": [m for m in merges if len(m["gt_ids"]) > 1],
        "splits": [s for s in splits if len(s["prediction_ids"]) > 1],
    }


def normalize_text(text: str) -> str:
    """Frozen light normalization: whitespace and LaTeX display wrappers only."""
    for token in ("$", "\\(", "\\)", "\\[", "\\]"):
        text = text.replace(token, "")
    return re.sub(r"\s+", "", text)


def compare_text(reference: str, candidate: str) -> Json:
    """Preserve raw comparison and never collapse mathematical symbol differences."""
    return {
        "raw_equal": reference == candidate,
        "normalized_equal": normalize_text(reference) == normalize_text(candidate),
    }


def order_metrics(gt: Json, pred: Json) -> Json:
    """Use visual anchors and model orders, leaving null PP order missing."""
    targets = [r for r in gt["regions"] if r["layer"] == "paragraph"]
    blocks = pred["layers"]["paragraph"]
    matching = geometry_metrics(targets, blocks, 0.5)["matches"]
    orders = {b["id"]: b.get("order") for b in blocks}
    anchors = {m["gt_id"]: orders[m["prediction_id"]] for m in matching}
    counts: Json = {"correct": 0, "incorrect": 0, "missing": 0, "pairs": []}
    for a, b in gt["reading_order_constraints"]:
        left, right = anchors.get(a), anchors.get(b)
        status = (
            "missing"
            if left is None or right is None
            else ("correct" if left < right else "incorrect")
        )
        counts[status] += 1
        counts["pairs"].append({"before": a, "after": b, "status": status})
    total = len(gt["reading_order_constraints"])
    counts["coverage"] = (counts["correct"] + counts["incorrect"]) / total if total else None
    return counts


def content_metrics(gt: Json, pred: Json, provider: str) -> Json:
    """Single-count localized PP / whole-page Ovis reference-presence diagnostics.

    Presence is evidence only: it does not prove ownership or complete transcription.
    PP uses blocks intersecting the confirmed check region, never formula duplication.
    """
    if provider == "monkey":
        return {"status": "N/A_LAYOUT_ONLY", "checks": []}
    by_id = {r["id"]: r for r in gt["regions"]}
    checks = []
    for check in gt["critical_text_checks"]:
        if check["status"] != "confirmed":
            checks.append({"id": check["id"], "status": "not_scored"})
            continue
        target = by_id[check["region_id"]]
        if provider == "pp":
            selected = [
                p
                for p in pred["layers"]["paragraph"]
                if not p.get("error")
                and p["type"] != "visual"
                and intersection(target["bbox"], p["bbox"]) / area(p["bbox"]) >= 0.5
            ]
            candidate = "\n".join(p.get("content", "") for p in selected)
        else:
            candidate = pred["content"]
        ref = check["reference"]
        checks.append(
            {
                "id": check["id"],
                "status": "missing_localized_candidate"
                if provider == "pp" and not selected
                else "scored",
                "scope": "localized_block_presence" if provider == "pp" else "page_presence_only",
                "raw_present": ref in candidate,
                "normalized_present": normalize_text(ref) in normalize_text(candidate),
                "raw_comparison": {"reference": ref, "candidate": candidate},
                **compare_text(ref, candidate),
            }
        )
    return {"status": "DIAGNOSTIC_NOT_FULL_OCR_ACCURACY", "checks": checks}


def source_hashes() -> Json:
    """Identify the implementation and dependency lock used by this experiment."""
    paths = [
        "scripts/raster_regression.py",
        "scripts/evaluate_raster_models.py",
        "scripts/model_contract_discovery.py",
        "uv.lock",
    ]
    return {p: compute_file_hash(ROOT / p) for p in paths}


def structural_contract(value: Any) -> Any:
    """Ignore OpenAPI prose and array ordering that has no structural semantics."""
    if isinstance(value, dict):
        return {
            k: structural_contract(v)
            for k, v in value.items()
            if k not in {"description", "summary", "title", "examples", "example", "available"}
        }
    if isinstance(value, list):
        return sorted(
            [structural_contract(v) for v in value], key=lambda v: json.dumps(v, sort_keys=True)
        )
    return value


def preflight(client: HttpClient, config: DiscoveryConfig) -> tuple[list[Json], str | None]:
    """Three metadata GETs only; refuse substantive contract or identity drift."""
    observations = []
    for name in ("monkey", "ovis", "pp"):
        model = getattr(config, name)
        url = (
            model.base_url.rstrip("/") + "/openapi.json"
            if name == "pp"
            else openai_endpoint_url(model.base_url, "models")
        )
        status, body, meta = client.get(url)
        entry: Json = {"provider": name, **meta.to_dict()}
        entry.pop("url", None)
        observations.append(entry)
        if status == 0:
            return observations, "NETWORK_BLOCKED"
        if status != 200 or meta.error:
            return observations, "METADATA_HTTP_ERROR"
        if name != "pp":
            expected = {"monkey": "MonkeyOCRv2", "ovis": "ovis-ocr2"}[name]
            ids = [r.get("id") for r in body.get("data", []) if isinstance(r, dict)]
            if model.model != expected or expected not in ids:
                return observations, "MODEL_IDENTITY_DRIFT"
            entry["expected_model_present"] = True
        else:
            frozen = read_json(ROOT / "tests/fixtures/model_contracts/pp.openapi.normalized.json")
            normalized = normalize_openapi(body)
            entry["normalized_structure_sha256"] = compute_json_fingerprint(
                structural_contract(normalized)
            )
            entry["baseline_raw_sha256"] = frozen["source_response_fingerprint"]
            entry["raw_hash_changed"] = (
                meta.response_fingerprint != frozen["source_response_fingerprint"]
            )
            if structural_contract(normalized) != structural_contract(frozen["observation"]):
                return observations, "CONTRACT_DRIFT"
    return observations, None


def request_payload(provider: str, model: str, encoded: str, mime: str, protocol: Json) -> Json:
    """Use identical provider parameters and prompts across the two formats."""
    settings = protocol["providers"][provider]
    if provider == "pp":
        return {"file": encoded, **settings["parameters"]}
    return {
        "model": model,
        **settings["parameters"],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": settings["prompt"]},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                ],
            }
        ],
    }


def validate_protocol(protocol: Json) -> None:
    """Enforce budget, frozen supported PP controls and accepted chat requests."""
    canonical = read_json(ROOT / "specs/t0016-evaluation-protocol.json")
    if protocol != canonical or protocol["matrix"] != matrix():
        raise ValueError("PROTOCOL_MISMATCH")
    frozen = read_json(ROOT / "tests/fixtures/model_contracts/pp.openapi.normalized.json")[
        "observation"
    ]
    schema = frozen["paths"]["/layout-parsing"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    params = protocol["providers"]["pp"]["parameters"]
    if set(params) - schema["properties"].keys():
        raise ValueError("UNDOCUMENTED_PP_PARAMETER")
    if list(Draft202012Validator(schema).iter_errors({"file": "synthetic", **params})):
        raise ValueError("INVALID_PP_PARAMETERS")


def seal_run(run_dir: Path) -> None:
    """Seal all collected immutable evidence before offline evaluation."""
    names = [
        "run-metadata.json",
        "protocol.snapshot.json",
        "requests.json",
        "input-manifest.snapshot.json",
        "ground-truth.snapshot.private.json",
    ]
    paths = [run_dir / name for name in names]
    for subdir in ("responses.private", "predictions.private", "inputs.private"):
        paths.extend(sorted((run_dir / subdir).glob("*")))
    write_private(
        run_dir / "evidence-manifest.private.json",
        {
            str(path.relative_to(run_dir)): compute_file_hash(path)
            for path in paths
            if path.is_file()
        },
    )


def verify_run(run_dir: Path, ground_truth: Path) -> tuple[Json, Json, Json]:
    """Verify the complete local evidence chain; evaluation makes no network calls."""
    seal = read_json(run_dir / "evidence-manifest.private.json")
    required = {
        "run-metadata.json",
        "protocol.snapshot.json",
        "requests.json",
        "input-manifest.snapshot.json",
        "ground-truth.snapshot.private.json",
        "inputs.private/source.jpg",
        "inputs.private/decoded-equivalent.png",
    }
    if not required <= seal.keys():
        raise ValueError("EVIDENCE_MANIFEST_INCOMPLETE")
    for name, digest in seal.items():
        path = run_dir / name
        if path.is_symlink() or not path.resolve().is_relative_to(run_dir.resolve()):
            raise ValueError("EVIDENCE_PATH_ESCAPE")
        if not path.is_file() or compute_file_hash(path) != digest:
            raise ValueError("EVIDENCE_HASH_MISMATCH")
    meta = read_json(run_dir / "run-metadata.json")
    gt = read_json(ground_truth)
    if (
        compute_file_hash(ground_truth) != meta["ground_truth_sha256"]
        or gt["annotation_version"] != meta["annotation_version"]
    ):
        raise ValueError("GROUND_TRUTH_HASH_MISMATCH")
    protocol = read_json(run_dir / "protocol.snapshot.json")
    if compute_file_hash(run_dir / "protocol.snapshot.json") != meta["protocol_sha256"]:
        raise ValueError("PROTOCOL_HASH_MISMATCH")
    inputs = read_json(run_dir / "input-manifest.snapshot.json")
    verify_inputs(run_dir / "inputs.private", inputs)
    requests = read_json(run_dir / "requests.json")["requests"]
    if len(requests) > len(protocol["matrix"]):
        raise ValueError("REQUEST_MATRIX_MISMATCH")
    ids = [r["request_id"] for r in requests]
    if len(ids) != len(set(ids)):
        raise ValueError("REQUEST_MATRIX_MISMATCH")
    for index, request in enumerate(requests):
        expected = protocol["matrix"][index]
        if (
            any(request[k] != expected[k] for k in expected)
            or request["run_id"] != meta["run_id"]
            or request["case_id"] != meta["case_id"]
        ):
            raise ValueError("REQUEST_MATRIX_MISMATCH")
        if request["status"] == "COMPLETE":
            for directory, hash_key in [
                ("responses.private", "pruned_response_sha256"),
                ("predictions.private", "prediction_sha256"),
            ]:
                name = f"{directory}/{request['request_id']}.json"
                if name not in seal or seal[name] != request[hash_key]:
                    raise ValueError("REQUEST_EVIDENCE_HASH_MISMATCH")
        variant = inputs["variants"][request["variant_id"]]
        if (
            request["input_file_sha256"] != variant["file_sha256"]
            or request["decoded_pixel_sha256"] != variant["decoded_pixel_sha256"]
        ):
            raise ValueError("REQUEST_INPUT_HASH_MISMATCH")
    return meta, gt, protocol


def run(
    case_dir: Path,
    protocol_path: Path,
    run_id: str,
    output_dir: Path,
    *,
    confirm_no_auth: bool,
    confirm_local_quality_evidence: bool,
    transport: httpx.BaseTransport | None = None,
) -> Json:
    """Collect serial controlled model requests, never retry or promote T0015 artifacts."""
    if transport is None:
        require_storage(case_dir, "cases")
        require_storage(output_dir, "runs")
    if not confirm_no_auth or not confirm_local_quality_evidence:
        raise ValueError("EXPLICIT_RUN_CONFIRMATIONS_REQUIRED")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("INVALID_RUN_ID")
    protocol = read_json(protocol_path)
    validate_protocol(protocol)
    truth_lock = validate_ground_truth(case_dir)
    inputs = read_json(case_dir / "input-manifest.private.json")
    config = load_config()
    assert_live_preconditions(config, ROOT, confirmed_no_auth=True)
    private_dir(output_dir, empty=True)
    for directory in (
        "responses.private",
        "predictions.private",
        "inputs.private",
        "overlays.private",
    ):
        private_dir(output_dir / directory)
    for variant in inputs["variants"].values():
        path = output_dir / "inputs.private" / variant["filename"]
        path.write_bytes((case_dir / variant["filename"]).read_bytes())
        path.chmod(0o600)
    write_private(output_dir / "input-manifest.snapshot.json", inputs)
    gt_path = output_dir / "ground-truth.snapshot.private.json"
    gt_path.write_bytes((case_dir / "ground-truth.private.json").read_bytes())
    gt_path.chmod(0o600)
    write_private(output_dir / "protocol.snapshot.json", protocol)
    meta: Json = {
        "run_id": run_id,
        "case_id": inputs["case_id"],
        "started_at": now(),
        "baseline_sha": BASELINE_SHA,
        "baseline_run_id": BASELINE_RUN,
        "ground_truth_sha256": truth_lock["ground_truth_sha256"],
        "annotation_version": truth_lock["annotation_version"],
        "protocol_sha256": compute_file_hash(output_dir / "protocol.snapshot.json"),
        "input_manifest_sha256": compute_file_hash(case_dir / "input-manifest.private.json"),
        "tool_source_hashes": source_hashes(),
        "execution_status": "PARTIAL",
        "annotation_status": "REVIEWED",
        "execution_mode": "synthetic" if transport is not None else "live",
        "reviewer_type": read_json(gt_path)["reviewer_type"],
        "authentication_mode": "none",
        "weight_revision": "unknown",
        "timeout_seconds": {"connect": config.timeouts.connect, "request": config.timeouts.request},
        "retries": 0,
    }
    requests: list[Json] = []
    write_private(output_dir / "run-metadata.json", meta)
    write_private(output_dir / "requests.json", {"requests": requests})
    with HttpClient(config.timeouts, transport=transport) as client:
        observations, error = preflight(client, config)
        meta["preflight"] = observations
        meta["blocking_reason"] = error
        if not error:
            for row in protocol["matrix"]:
                provider = row["provider"]
                model = getattr(config, provider)
                variant = inputs["variants"][row["variant_id"]]
                data = (output_dir / "inputs.private" / variant["filename"]).read_bytes()
                payload = request_payload(
                    provider,
                    model.model,
                    base64.b64encode(data).decode("ascii"),
                    variant["mime"],
                    protocol,
                )
                url = (
                    model.base_url.rstrip("/") + "/layout-parsing"
                    if provider == "pp"
                    else openai_endpoint_url(model.base_url, "chat/completions")
                )
                status, body, http_meta = client.post(url, json_data=payload)
                record: Json = {
                    **row,
                    **http_meta.to_dict(),
                    "run_id": run_id,
                    "case_id": inputs["case_id"],
                    "completed_at": now(),
                    "input_id": f"{inputs['case_id']}-{row['variant_id']}",
                    "input_file_sha256": variant["file_sha256"],
                    "decoded_pixel_sha256": variant["decoded_pixel_sha256"],
                    "mime": variant["mime"],
                    "tool_source_hashes": meta["tool_source_hashes"],
                    "prompt_sha256": hashlib.sha256(
                        protocol["providers"][provider]["prompt"].encode()
                    ).hexdigest(),
                    "parameters_sha256": compute_json_fingerprint(
                        protocol["providers"][provider]["parameters"]
                    ),
                    "http_response_bytes_sha256": http_meta.response_fingerprint,
                    "application_status": body.get("errorCode"),
                    "finish_reason": safe_finish_reason(body),
                    "service_fingerprint": body.get("system_fingerprint"),
                    "status": "COMPLETE",
                }
                record.pop("url", None)
                pruned = strip_media(body)
                response_path = output_dir / "responses.private" / f"{http_meta.request_id}.json"
                write_private(response_path, pruned)
                record["pruned_response_sha256"] = compute_file_hash(response_path)
                try:
                    if status == 0:
                        raise ValueError("NETWORK_BLOCKED")
                    if status != 200:
                        raise ValueError("HTTP_ERROR")
                    if http_meta.error:
                        raise ValueError("PARSE_FAILED")
                    if provider != "pp" and body.get("model") != model.model:
                        raise ValueError("MODEL_IDENTITY_DRIFT")
                    if provider == "pp" and body.get("errorCode", 0) != 0:
                        raise ValueError("APPLICATION_ERROR")
                    if provider == "pp":
                        frozen = read_json(
                            ROOT / "tests/fixtures/model_contracts/pp.openapi.normalized.json"
                        )["observation"]
                        schema = frozen["paths"]["/layout-parsing"]["post"]["responses"]["200"][
                            "content"
                        ]["application/json"]["schema"]
                        if list(Draft202012Validator(schema).iter_errors(body)):
                            raise ValueError("CONTRACT_DRIFT")
                    prediction = parse_prediction(provider, body, inputs["width"], inputs["height"])
                    prediction_path = (
                        output_dir / "predictions.private" / f"{http_meta.request_id}.json"
                    )
                    write_private(prediction_path, strip_media(prediction))
                    record["prediction_sha256"] = compute_file_hash(prediction_path)
                    record["model_settings"] = prediction["model_settings"]
                except (ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
                    safe_codes = {
                        "NETWORK_BLOCKED",
                        "HTTP_ERROR",
                        "PARSE_FAILED",
                        "MODEL_IDENTITY_DRIFT",
                        "APPLICATION_ERROR",
                        "CONTRACT_DRIFT",
                        "INCOMPLETE_LENGTH",
                        "INCOMPLETE_FINISH_REASON",
                        "COORDINATE_MAPPING_UNRESOLVED",
                    }
                    record["status"] = str(exc) if str(exc) in safe_codes else "PARSE_FAILED"
                requests.append(record)
                write_private(output_dir / "requests.json", {"requests": requests})
                if record["status"] in {"MODEL_IDENTITY_DRIFT", "CONTRACT_DRIFT"}:
                    meta["blocking_reason"] = record["status"]
                    break
    meta["completed_at"] = now()
    meta["inference_attempted"] = len(requests)
    meta["inference_complete"] = sum(r["status"] == "COMPLETE" for r in requests)
    meta["execution_status"] = (
        "BLOCKED"
        if meta["blocking_reason"]
        else "COMPLETE"
        if meta["inference_complete"] == 14
        else "PARTIAL"
    )
    write_private(output_dir / "run-metadata.json", meta)
    seal_run(output_dir)
    return {
        "run_id": run_id,
        "execution_status": meta["execution_status"],
        "inference_attempted": len(requests),
        "inference_complete": meta["inference_complete"],
        "blocking_reason": meta["blocking_reason"],
    }


def overlays(run_dir: Path, gt: Json, predictions: dict[str, Json]) -> None:
    """Local-only image overlays and HTML review, with no external references."""
    private_dir(run_dir / "overlays.private")
    links = []
    source = run_dir / "inputs.private/source.jpg"
    for request_id, prediction in [
        ("ground-truth", {"layers": {"macro": gt["regions"]}}),
        *predictions.items(),
    ]:
        with Image.open(source) as image:
            preview = image.convert("RGB")
        draw = ImageDraw.Draw(preview)
        for item in prediction["layers"]["macro"]:
            if not item.get("error"):
                draw.rectangle(item["bbox"], outline="red", width=2)
                draw.text((item["bbox"][0], item["bbox"][1]), item["id"], fill="blue")
        name = f"overlays.private/{request_id}.png"
        preview.save(run_dir / name)
        (run_dir / name).chmod(0o600)
        links.append(f'<h2>{html.escape(request_id)}</h2><img src="{name}" alt="local overlay">')
    metrics = read_json(run_dir / "metrics.private.json")
    links.append(
        "<h2>Private scoring details</h2><pre>"
        + html.escape(json.dumps(metrics, ensure_ascii=False, indent=2))
        + "</pre>"
    )
    document = (
        '<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" '
        "content=\"default-src 'none'; img-src 'self'; style-src 'unsafe-inline'\">"
        "<title>T0016 private visual review</title><h1>Private raster evidence</h1>"
        + "".join(links)
    )
    path = run_dir / "review.private.html"
    path.write_text(document, encoding="utf-8")
    path.chmod(0o600)


def evaluate(run_dir: Path, ground_truth: Path) -> Json:
    """Recompute geometry, agreement, order and content entirely offline."""
    meta, gt, protocol = verify_run(run_dir, ground_truth)
    requests = read_json(run_dir / "requests.json")["requests"]
    predictions = {}
    results = []
    for request in requests:
        rid = request["request_id"]
        if request["status"] != "COMPLETE":
            results.append({"request_id": rid, "status": request["status"], "not_scored": True})
            continue
        # Reparse same-run private responses rather than trusting previously computed predictions.
        body = read_json(run_dir / "responses.private" / f"{rid}.json")
        pred = parse_prediction(request["provider"], body, gt["page_width"], gt["page_height"])
        if compute_json_fingerprint(strip_media(pred)) != compute_json_fingerprint(
            read_json(run_dir / "predictions.private" / f"{rid}.json")
        ):
            raise ValueError("PREDICTION_RECOMPUTE_MISMATCH")
        predictions[rid] = pred
        geometry: Json = {}
        if request["provider"] != "ovis":
            for layer in ("macro", "paragraph", "fine"):
                targets = [
                    r
                    for r in gt["regions"]
                    if r["layer"] == layer or (layer == "macro" and r["layer"] == "paragraph")
                ]
                if not any(r.get("status") == "confirmed" for r in targets):
                    geometry[layer] = {
                        "not_scored": "NO_GROUND_TRUTH_AT_THIS_GRANULARITY",
                        "prediction_count": len(pred["layers"][layer]),
                    }
                else:
                    layer_predictions = [
                        r
                        for r in pred["layers"][layer]
                        if layer != "paragraph" or evaluation_type(r) != "visual"
                    ]
                    geometry[layer] = {
                        str(t): geometry_metrics(targets, layer_predictions, t)
                        for t in protocol["iou_thresholds"]
                    }
            visual_gt = [r for r in gt["regions"] if evaluation_type(r) == "visual"]
            visual_pred = [r for r in pred["layers"]["macro"] if evaluation_type(r) == "visual"]
            geometry["visual"] = {
                str(t): geometry_metrics(visual_gt, visual_pred, t)
                for t in protocol["iou_thresholds"]
            }
        results.append(
            {
                "request_id": rid,
                "provider": request["provider"],
                "variant_id": request["variant_id"],
                "repeat_index": request["repeat_index"],
                "status": "COMPLETE",
                "geometry": geometry,
                "reading_order": order_metrics(gt, pred)
                if request["provider"] != "ovis"
                else {"not_scored": "OVIS_NO_GEOMETRY"},
                "content": content_metrics(gt, pred, request["provider"]),
            }
        )
    agreements = []
    for a, b in itertools.combinations(
        [r for r in requests if r["request_id"] in predictions and r["provider"] != "ovis"], 2
    ):
        kind = "within_format_repeat" if a["variant_id"] == b["variant_id"] else "cross_format"
        if a["provider"] != b["provider"]:
            if a["variant_id"] != b["variant_id"] or a["repeat_index"] != b["repeat_index"]:
                continue
            kind = "inter_provider_agreement"
        left = predictions[a["request_id"]]["layers"]["macro"]
        right = predictions[b["request_id"]]["layers"]["macro"]
        agreements.append(
            {
                "a": a["request_id"],
                "b": b["request_id"],
                "kind": kind,
                "metrics": {
                    str(t): geometry_metrics(left, right, t) for t in protocol["iou_thresholds"]
                },
            }
        )
    durations = {}
    for provider in ("monkey", "pp", "ovis"):
        for variant in ("jpg", "png"):
            times = [
                r["duration_ms"]
                for r in requests
                if r["provider"] == provider and r["variant_id"] == variant
            ]
            durations[f"{provider}_{variant}"] = (
                {
                    "count": len(times),
                    "median_ms": statistics.median(times),
                    "min_ms": min(times),
                    "max_ms": max(times),
                }
                if times
                else {}
            )
    metrics: Json = {
        "run_id": meta["run_id"],
        "execution_status": meta["execution_status"],
        "ground_truth_sha256": meta["ground_truth_sha256"],
        "protocol_sha256": meta["protocol_sha256"],
        "results": results,
        "agreements": agreements,
        "duration_including_frp_transport_service": durations,
        "uncertain_regions": sum(r["status"] == "uncertain" for r in gt["regions"]),
        "uncertain_text_checks": sum(
            r["status"] == "uncertain" for r in gt["critical_text_checks"]
        ),
    }
    write_private(run_dir / "metrics.private.json", metrics)
    write_private(
        run_dir / "evaluation-manifest.private.json",
        {
            "metrics_sha256": compute_file_hash(run_dir / "metrics.private.json"),
            "evidence_manifest_sha256": compute_file_hash(
                run_dir / "evidence-manifest.private.json"
            ),
            "evaluation_tool_hashes": source_hashes(),
            "evaluation_version": "1.1",
            "correction_sha256": compute_file_hash(ROOT / "specs/t0016-evaluation-correction.json"),
        },
    )
    overlays(run_dir, gt, predictions)
    return metrics


def public_summary(run_dir: Path) -> Json:
    """Allowlist numeric results only; never export OCR, raw labels or user paths."""
    meta, gt, _ = verify_run(run_dir, run_dir / "ground-truth.snapshot.private.json")
    evaluation = read_json(run_dir / "evaluation-manifest.private.json")
    if (
        compute_file_hash(run_dir / "metrics.private.json") != evaluation["metrics_sha256"]
        or compute_file_hash(run_dir / "evidence-manifest.private.json")
        != evaluation["evidence_manifest_sha256"]
    ):
        raise ValueError("EVALUATION_HASH_MISMATCH")
    if evaluation["evaluation_tool_hashes"] != source_hashes():
        raise ValueError("EVALUATION_TOOL_CHANGED_REEVALUATE")
    metrics = read_json(run_dir / "metrics.private.json")
    inputs = read_json(run_dir / "input-manifest.snapshot.json")
    requests = read_json(run_dir / "requests.json")["requests"]
    result: Json = {
        k: meta[k]
        for k in (
            "run_id",
            "case_id",
            "baseline_sha",
            "baseline_run_id",
            "ground_truth_sha256",
            "annotation_version",
            "protocol_sha256",
            "tool_source_hashes",
            "execution_status",
            "annotation_status",
            "reviewer_type",
            "inference_attempted",
            "inference_complete",
            "blocking_reason",
            "weight_revision",
        )
    }
    result.update(
        input_file_sha256=inputs["variants"]["jpg"]["file_sha256"],
        png_file_sha256=inputs["variants"]["png"]["file_sha256"],
        decoded_pixel_sha256=inputs["variants"]["jpg"]["decoded_pixel_sha256"],
        width=inputs["width"],
        height=inputs["height"],
        uncertain_regions=metrics["uncertain_regions"],
        uncertain_text_checks=metrics["uncertain_text_checks"],
        evaluation_tool_hashes=evaluation["evaluation_tool_hashes"],
        evaluation_version=evaluation["evaluation_version"],
        correction_sha256=evaluation["correction_sha256"],
    )
    result["requests"] = [
        {
            k: r[k]
            for k in (
                "request_id",
                "provider",
                "variant_id",
                "repeat_index",
                "status",
                "duration_ms",
                "response_status",
                "application_status",
                "finish_reason",
                "http_response_bytes_sha256",
                "prompt_sha256",
                "parameters_sha256",
                "service_fingerprint",
            )
        }
        for r in requests
    ]
    scalar_keys = (
        "gt_count",
        "prediction_count",
        "invalid_count",
        "uncertain_count",
        "reference_invalid_count",
        "tp",
        "fp",
        "fn",
        "precision",
        "recall",
        "iou_mean",
        "iou_median",
    )
    summaries = []
    for row in metrics["results"]:
        if row["status"] != "COMPLETE":
            summaries.append(row)
            continue
        output = {
            k: row[k] for k in ("request_id", "provider", "variant_id", "repeat_index", "status")
        }
        output["geometry"] = {}
        for layer, values in row["geometry"].items():
            if "not_scored" in values:
                output["geometry"][layer] = values
            else:
                output["geometry"][layer] = {
                    threshold: {k: stats[k] for k in scalar_keys}
                    for threshold, stats in values.items()
                }
        output["reading_order"] = {k: v for k, v in row["reading_order"].items() if k != "pairs"}
        output["content"] = {
            "status": row["content"]["status"],
            "checks": [
                {k: v for k, v in check.items() if k not in {"raw_comparison"}}
                for check in row["content"]["checks"]
            ],
        }
        summaries.append(output)
    result["results"] = summaries
    result["agreements"] = [
        {
            **{k: a[k] for k in ("a", "b", "kind")},
            "metrics": {
                threshold: {k: stats[k] for k in scalar_keys}
                for threshold, stats in a["metrics"].items()
            },
        }
        for a in metrics["agreements"]
    ]
    result["durations"] = metrics["duration_including_frp_transport_service"]
    result["annotation_confirmed_count"] = sum(r["status"] == "confirmed" for r in gt["regions"])
    return result


def promote(run_dir: Path) -> Json:
    """Export only a sanitized T0016 summary; never touch T0015 artifacts."""
    summary = public_summary(run_dir)
    target = ROOT / "tasks/reports/T0016_METRICS.json"
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "run_id": summary["run_id"],
        "execution_status": summary["execution_status"],
        "public_artifact": "tasks/reports/T0016_METRICS.json",
    }
