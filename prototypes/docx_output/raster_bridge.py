"""DEMO-only frozen FRP bridge: loopback, no auth, sequential, zero retries."""

from __future__ import annotations

import base64
import hashlib
import os
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from jsonschema import Draft202012Validator

from .common import ROOT, DemoError, Json, digest, issue, read, safe_path, save
from .structure import chat_content

PP_PARAMETERS = {
    "fileType": 1,
    "useDocOrientationClassify": False,
    "useDocUnwarping": False,
    "useTextlineOrientation": False,
    "useSealRecognition": False,
    "useTableRecognition": False,
    "useFormulaRecognition": True,
    "useChartRecognition": False,
    "returnMarkdownImages": False,
    "visualize": False,
}
PROMPTS = {
    "monkey": (
        "Please output the categories and coordinates of the document elements in reading order."
    ),
    "ovis": (
        "Extract readable content in reading order as Markdown. "
        "Preserve original text, numbers, "
        "units and symbols. Do not translate, correct, summarize or infer."
    ),
}


def endpoint(provider: str) -> tuple[str, str]:
    """Accept configured existing loopback ports only; never use secrets or remote URLs."""
    port = {"pp": 8080, "ovis": 8000, "monkey": 9000}[provider]
    name = provider.upper()
    base = os.environ.get(name + "_BASE_URL", f"http://127.0.0.1:{port}").rstrip("/")
    parsed = urlsplit(base)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.port != port
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/v1"}
    ):
        raise DemoError("LOOPBACK_ENDPOINT_REQUIRED")
    model = os.environ.get(
        name + "_MODEL", {"pp": "", "ovis": "ovis-ocr2", "monkey": "MonkeyOCRv2"}[provider]
    )
    expected = {"pp": "", "ovis": "ovis-ocr2", "monkey": "MonkeyOCRv2"}[provider]
    if model != expected:
        raise DemoError("FROZEN_MODEL_REQUIRED")
    if provider == "pp":
        if parsed.path:
            raise DemoError("FROZEN_PP_PATH_REQUIRED")
        return base + "/layout-parsing", model
    return base + ("" if parsed.path == "/v1" else "/v1") + "/chat/completions", model


def recognize(
    job: Path,
    ir: Json,
    page: Json,
    manifest: Json,
    ovis: bool = False,
    monkey: bool = False,
    primary: str = "pp",
) -> Json:
    """Make at most one selected-provider request per page, caching even failures."""
    if not manifest.get("authorized") or not manifest.get("confirm_no_auth"):
        raise DemoError("EXPLICIT_MODEL_AUTHORIZATION_REQUIRED")
    source = safe_path(job, ir["provenance"]["pages"][str(page["page_index"])]["image_path"])
    mime = "image/jpeg" if source.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    responses: Json = {}
    for key in ("NO_PROXY", "no_proxy"):
        os.environ[key] = ",".join(
            dict.fromkeys([*os.environ.get(key, "").split(","), "localhost", "127.0.0.1"])
        )
    if primary not in {"pp", "ovis", "ovis-pp"}:
        raise DemoError("INVALID_CONTENT_PROVIDER")
    providers = (
        ["ovis", "pp"]
        if primary == "ovis-pp"
        else ["ovis"]
        if primary == "ovis"
        else ["pp", *(["ovis"] if ovis else [])]
    )
    providers += ["monkey"] if monkey else []
    with httpx.Client(
        timeout=httpx.Timeout(600, connect=10), trust_env=False, follow_redirects=False
    ) as client:
        for provider in providers:
            cache = job / f"cache-p{page['page_index']}-{provider}.json"
            if cache.exists():
                cached = read(cache)
                if cached["input_sha256"] != digest(source):
                    raise DemoError("CACHE_INPUT_MISMATCH")
                if cached["status"] == "COMPLETE":
                    responses[provider] = cached["response"]
                if provider == "ovis" and primary != "pp" and provider not in responses:
                    break
                continue
            url, model = endpoint(provider)
            payload = (
                {"file": encoded, **PP_PARAMETERS}
                if provider == "pp"
                else {
                    "model": model,
                    "max_tokens": 8192 if provider == "ovis" else 2048,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": PROMPTS[provider]},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{mime};base64,{encoded}"},
                                },
                            ],
                        }
                    ],
                }
            )
            if provider == "pp":
                frozen = read(ROOT / "tests/fixtures/model_contracts/pp.openapi.normalized.json")[
                    "observation"
                ]
                schema = frozen["paths"]["/layout-parsing"]["post"]["requestBody"]["content"][
                    "application/json"
                ]["schema"]
                Draft202012Validator(schema).validate(payload)
            rid = uuid.uuid4().hex
            entry: Json = {
                "request_id": rid,
                "job_id": job.name,
                "page_index": page["page_index"],
                "region_id": None,
                "provider": provider,
                "task_type": (
                    "layout"
                    if provider != "ovis"
                    else "content_review"
                    if primary == "pp"
                    else "content_recognition"
                ),
                "input_sha256": digest(source),
                "status": "STARTED",
            }
            manifest["requests"].append(entry)
            manifest["model_call_count"] += 1
            ir["metrics"]["model_call_count"] = manifest["model_call_count"]
            page["model_calls"].append(rid)
            save(job / "request-manifest.json", manifest)
            # STARTED cache prevents implicit retry after uncertain process interruption.
            save(cache, {"status": "STARTED", "input_sha256": digest(source)})
            start = time.monotonic()
            body: Json = {}
            try:
                response = client.post(url, json=payload)
                entry["http_status"] = response.status_code
                entry["response_sha256"] = hashlib.sha256(response.content).hexdigest()
                if response.status_code != 200:
                    raise DemoError("PROVIDER_HTTP_ERROR")
                body = response.json()
                if not isinstance(body, dict):
                    raise DemoError("INVALID_CANDIDATE_WIRE_TYPE")
                if provider == "pp":
                    if body.get("errorCode", 0) != 0:
                        raise DemoError("PROVIDER_APPLICATION_ERROR")
                    response_schema = frozen["paths"]["/layout-parsing"]["post"]["responses"][
                        "200"
                    ]["content"]["application/json"]["schema"]
                    if list(Draft202012Validator(response_schema).iter_errors(body)):
                        raise DemoError("CONTRACT_DRIFT")
                else:
                    chat_content(body)
                    if body.get("model") != model:
                        raise DemoError("MODEL_IDENTITY_DRIFT")
                entry["status"] = "COMPLETE"
                responses[provider] = body
            except (httpx.HTTPError, ValueError) as exc:
                entry["status"] = str(exc) if isinstance(exc, DemoError) else "PROVIDER_UNAVAILABLE"
                issue(
                    ir,
                    entry["status"],
                    "模型调用失败，无隐式重试，已保留其他结果。",
                    [],
                    page["page_index"],
                )
            entry["duration_ms"] = round((time.monotonic() - start) * 1000, 3)
            save(
                cache, {"status": entry["status"], "input_sha256": digest(source), "response": body}
            )
            save(job / "request-manifest.json", manifest)
            if provider == "ovis" and primary != "pp" and provider not in responses:
                break
    return responses
