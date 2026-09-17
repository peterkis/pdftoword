"""Bounded region HTTP adapter using frozen service contracts, with no implicit retries."""

from __future__ import annotations

import base64
import hashlib
import os
import time
import uuid
from pathlib import Path

import httpx
from jsonschema import Draft202012Validator

from .common import ROOT, DemoError, Json, digest, job_path, read, save
from .raster_bridge import PP_PARAMETERS, PROMPTS, endpoint
from .structure import chat_content


def request_region(job: Path, source: Path, region: Json, provider: str, manifest: Json) -> Json:
    """Send at most one request per authorized region/provider and persist STARTED first."""
    if not manifest.get("authorized") or manifest["model_call_count"] >= manifest["budget"]:
        raise DemoError("REGION_BUDGET_EXCEEDED")
    url, model = endpoint(provider)
    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    payload = (
        {"file": encoded, **PP_PARAMETERS}
        if provider == "pp"
        else {
            "model": model,
            "max_tokens": 8192,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPTS["ovis"]},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        },
                    ],
                }
            ],
        }
    )
    contract = read(ROOT / "tests/fixtures/model_contracts/pp.openapi.normalized.json")[
        "observation"
    ]
    operation = contract["paths"]["/layout-parsing"]["post"]
    if provider == "pp":
        Draft202012Validator(
            operation["requestBody"]["content"]["application/json"]["schema"]
        ).validate(payload)
    entry = {
        "request_id": uuid.uuid4().hex,
        "job_id": job.name,
        "page_index": region["page_index"],
        "region_id": region["region_id"],
        "provider": provider,
        "task_type": "region_layout" if provider == "pp" else "region_content",
        "input_sha256": digest(source),
        "status": "STARTED",
    }
    if any(
        r["region_id"] == entry["region_id"] and r["provider"] == provider
        for r in manifest["requests"]
    ):
        raise DemoError("REGION_ALREADY_ATTEMPTED")
    if manifest.get("reuse_job_id"):
        previous = job_path(manifest["reuse_job_id"], job.parent)
        prior = read(previous / "request-manifest.json")
        cached = next(
            (
                r
                for r in prior["requests"]
                if r["provider"] == provider
                and r["region_id"] == region["region_id"]
                and r["input_sha256"] == entry["input_sha256"]
                and r["status"] == "COMPLETE"
            ),
            None,
        )
        if cached:
            path = previous / f"response-{region['region_id']}-{provider}.json"
            stored_hash = digest(path)
            if cached.get("stored_response_sha256", stored_hash) != stored_hash:
                raise DemoError("CACHED_RESPONSE_CHANGED")
            body = read(path)
            entry.update(
                status="COMPLETE",
                http_attempted=False,
                reused_from={
                    "job_id": previous.name,
                    "request_id": cached["request_id"],
                    "response_sha256": stored_hash,
                    "hash_basis": "stored_normalized_json",
                },
            )
            manifest["requests"].append(entry)
            target = job / path.name
            save(target, body)
            entry["stored_response_sha256"] = digest(target)
            save(job / "request-manifest.json", manifest)
            return body
    manifest["requests"].append(entry)
    manifest["model_call_count"] += 1
    save(job / "request-manifest.json", manifest)
    started = time.monotonic()
    try:
        with httpx.Client(
            timeout=httpx.Timeout(600, connect=10), trust_env=False, follow_redirects=False
        ) as client:
            response = client.post(url, json=payload)
        raw_path = job / f"response-{region['region_id']}-{provider}.raw"
        fd = os.open(raw_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(response.content)
        entry["raw_response_path"] = raw_path.name
        entry["http_attempted"] = True
        entry["http_status"] = response.status_code
        entry["response_sha256"] = hashlib.sha256(response.content).hexdigest()
        if response.status_code != 200:
            raise DemoError("PROVIDER_HTTP_ERROR")
        body = response.json()
        if not isinstance(body, dict):
            raise DemoError("INVALID_CANDIDATE_WIRE_TYPE")
        if provider == "pp":
            schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
            if list(Draft202012Validator(schema).iter_errors(body)) or body.get("errorCode", 0):
                raise DemoError("CONTRACT_DRIFT")
        else:
            chat_content(body)
            if body.get("model") != model:
                raise DemoError("MODEL_IDENTITY_DRIFT")
        entry["status"] = "COMPLETE"
        stored = job / f"response-{region['region_id']}-{provider}.json"
        save(stored, body)
        entry["stored_response_sha256"] = digest(stored)
        return body
    except (httpx.HTTPError, ValueError) as exc:
        entry["status"] = str(exc) if isinstance(exc, DemoError) else "PROVIDER_UNAVAILABLE"
        raise DemoError(entry["status"]) from exc
    finally:
        entry["duration_ms"] = round((time.monotonic() - started) * 1000, 3)
        save(job / "request-manifest.json", manifest)


def layout_purpose(body: Json, pixel_size: list[int]) -> str:
    """Use PP labels/geometry only; never consume its recognized words as content."""
    try:
        raw = body["result"]["layoutParsingResults"][0]["prunedResult"]
        if [raw["width"], raw["height"]] != pixel_size or raw.get("model_settings", {}).get(
            "use_doc_preprocessor"
        ):
            raise DemoError("COORDINATE_MAPPING_UNRESOLVED")
        labels = {r["block_label"] for r in raw["parsing_res_list"]}
        if not labels:
            return "unknown"
        figure = {"image", "figure", "chart", "seal"}
        text = {
            "text",
            "paragraph",
            "doc_title",
            "paragraph_title",
            "formula",
            "table",
            "header",
            "footer",
            "number",
            "reference",
            "content",
        }
        if labels <= figure:
            return "figure"
        if labels <= text:
            return "text"
        if labels <= (text | figure) and labels & text:
            return "mixed"
        return "unknown"
    except (KeyError, TypeError, IndexError) as exc:
        raise DemoError("INVALID_REGION_LAYOUT") from exc
