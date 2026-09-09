"""Evidence-chain, network-budget and privacy tests with synthetic content only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

import evaluate_raster_models as cli
import raster_regression as core
from model_contract_discovery import DiscoveryConfig, ModelConfig, Timeouts


def synthetic_case(tmp_path: Path) -> Path:
    """Prepare and review a tiny synthetic case through real public functions."""
    source = tmp_path / "source.jpg"
    Image.new("RGB", (100, 100), "white").save(source)
    case = tmp_path / "case"
    m = core.prepare(source, "synthetic", case)
    core.write_private(
        case / "ground-truth.private.json",
        {
            "case_id": "synthetic",
            "source_sha256": m["variants"]["jpg"]["file_sha256"],
            "pixel_sha256": m["variants"]["jpg"]["decoded_pixel_sha256"],
            "page_width": 100,
            "page_height": 100,
            "annotation_version": "1",
            "reviewer_type": "agent_visual",
            "reviewer_id": "synthetic",
            "reviewed_at": core.now(),
            "review_status": "REVIEWED",
            "regions": [
                {
                    "id": "r1",
                    "type": "text",
                    "bbox": [0, 0, 50, 50],
                    "reference": "PRIVATE_SENTINEL",
                    "status": "confirmed",
                    "uncertainty": None,
                    "notes": "synthetic",
                    "layer": "paragraph",
                }
            ],
            "reading_order_constraints": [],
            "critical_text_checks": [
                {
                    "id": "c1",
                    "region_id": "r1",
                    "reference": "PRIVATE_SENTINEL",
                    "status": "confirmed",
                }
            ],
        },
    )
    core.validate_ground_truth(case)
    return case


def config() -> DiscoveryConfig:
    """Local test configuration, without credentials."""
    return DiscoveryConfig(
        monkey=ModelConfig("http://127.0.0.1:9000", "MonkeyOCRv2"),
        ovis=ModelConfig("http://127.0.0.1:8000", "ovis-ocr2"),
        pp=ModelConfig("http://127.0.0.1:8080"),
        timeouts=Timeouts(1, 1),
    )


def service(request: httpx.Request) -> httpx.Response:
    """Synthetic wire data matching frozen structure, including removable media."""
    assert "authorization" not in request.headers
    port = request.url.port
    if request.url.path.endswith("/models"):
        return httpx.Response(
            200, json={"data": [{"id": "MonkeyOCRv2" if port == 9000 else "ovis-ocr2"}]}
        )
    if request.url.path == "/openapi.json":
        fixture = core.read_json(
            core.ROOT / "tests/fixtures/model_contracts/pp.openapi.normalized.json"
        )["observation"]
        paths = fixture["paths"]
        return httpx.Response(
            200,
            json={"openapi": fixture["openapi_version"], "info": fixture["info"], "paths": paths},
        )
    body = json.loads(request.content)
    if port != 8080:
        assert body["max_tokens"] == (2048 if port == 9000 else 8192)
        return httpx.Response(
            200,
            json={
                "model": body["model"],
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": "[{'label':'text','bbox':[0,0,500,500]}]"
                            if port == 9000
                            else "PRIVATE_SENTINEL"
                        },
                    }
                ],
            },
        )
    assert body["fileType"] == 1
    return httpx.Response(
        200,
        json={
            "logId": "synthetic",
            "errorCode": 0,
            "result": {
                "dataInfo": {"width": 100, "height": 100, "type": "image"},
                "layoutParsingResults": [
                    {
                        "prunedResult": {
                            "width": 100,
                            "height": 100,
                            "parsing_res_list": [
                                {
                                    "block_label": "text",
                                    "block_bbox": [0, 0, 50, 50],
                                    "block_content": "PRIVATE_SENTINEL",
                                    "block_order": None,
                                }
                            ],
                            "layout_det_res": {
                                "boxes": [
                                    {"label": "text", "coordinate": [0, 0, 50, 50], "score": 0.8}
                                ]
                            },
                        },
                        "outputImages": {"image": "A" * 400},
                        "inputImage": "https://third-party.invalid/private.jpg",
                        "markdown": {
                            "text": "PRIVATE_SENTINEL",
                            "isStart": True,
                            "isEnd": True,
                            "images": {"private.jpg": "A" * 400},
                        },
                    }
                ],
            },
        },
    )


@pytest.fixture
def collected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run the complete real collector with synthetic transport."""
    case = synthetic_case(tmp_path)
    monkeypatch.setattr(core, "load_config", config)
    monkeypatch.setattr(core, "assert_live_preconditions", lambda *a, **k: None)
    run_dir = tmp_path / "run"
    status = core.run(
        case,
        core.ROOT / "specs/t0016-evaluation-protocol.json",
        "synthetic",
        run_dir,
        confirm_no_auth=True,
        confirm_local_quality_evidence=True,
        transport=httpx.MockTransport(service),
    )
    assert status["inference_complete"] == 14
    return run_dir


def test_offline_recompute_and_public_privacy(collected: Path) -> None:
    gt = collected / "ground-truth.snapshot.private.json"
    a = core.evaluate(collected, gt)
    b = core.evaluate(collected, gt)
    assert a == b
    public = core.public_summary(collected)
    text = json.dumps(public)
    for forbidden in ("PRIVATE_SENTINEL", "third-party", "AAAAAA", str(collected)):
        assert forbidden not in text
    for path in (collected / "responses.private").glob("*"):
        assert "third-party" not in path.read_text()
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in collected.rglob("*") if p.is_file())
    assert all(p.stat().st_mode & 0o777 == 0o700 for p in collected.rglob("*") if p.is_dir())


@pytest.mark.parametrize(
    "name",
    [
        "protocol.snapshot.json",
        "inputs.private/source.jpg",
        "ground-truth.snapshot.private.json",
        "requests.json",
    ],
)
def test_tampered_evidence_rejected(collected: Path, name: str) -> None:
    path = collected / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        core.evaluate(collected, collected / "ground-truth.snapshot.private.json")


def test_external_ground_truth_rejected(collected: Path, tmp_path: Path) -> None:
    path = tmp_path / "wrong.json"
    gt = core.read_json(collected / "ground-truth.snapshot.private.json")
    gt["annotation_version"] = "2"
    core.write_private(path, gt)
    with pytest.raises(ValueError, match="GROUND_TRUTH_HASH_MISMATCH"):
        core.evaluate(collected, path)


@pytest.mark.parametrize("failure", ["network", "identity", "contract"])
def test_preflight_blocks_sample_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    case = synthetic_case(tmp_path)
    monkeypatch.setattr(core, "load_config", config)
    monkeypatch.setattr(core, "assert_live_preconditions", lambda *a, **k: None)
    calls = []

    def broken(req: httpx.Request) -> httpx.Response:
        calls.append(req.method)
        if failure == "network":
            raise httpx.ConnectError("private endpoint", request=req)
        if failure == "identity":
            return httpx.Response(200, json={"data": [{"id": "wrong"}]})
        if req.url.path == "/openapi.json":
            return httpx.Response(200, json={"openapi": "3.1.0", "paths": {}})
        return service(req)

    status = core.run(
        case,
        core.ROOT / "specs/t0016-evaluation-protocol.json",
        "blocked",
        tmp_path / "run",
        confirm_no_auth=True,
        confirm_local_quality_evidence=True,
        transport=httpx.MockTransport(broken),
    )
    assert status["inference_attempted"] == 0
    assert "POST" not in calls
    assert len(calls) == (3 if failure == "contract" else 1)


@pytest.mark.parametrize("failure", ["length", "http", "disconnect", "parse", "application"])
def test_failure_not_retried_or_scored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    case = synthetic_case(tmp_path)
    monkeypatch.setattr(core, "load_config", config)
    monkeypatch.setattr(core, "assert_live_preconditions", lambda *a, **k: None)
    posts = []

    def broken(req: httpx.Request) -> httpx.Response:
        if req.method == "GET":
            return service(req)
        posts.append(req)
        if failure == "disconnect":
            raise httpx.ReadError("sensitive", request=req)
        if failure == "http":
            return httpx.Response(503, json={})
        body: dict[str, Any] = service(req).json()
        if req.url.port != 8080:
            if failure == "length":
                body["choices"][0]["finish_reason"] = "length"
            elif failure == "parse":
                body["choices"][0]["message"]["content"] = None
        elif failure == "application":
            body["errorCode"] = 900
        return httpx.Response(200, json=body)

    out = tmp_path / "run"
    status = core.run(
        case,
        core.ROOT / "specs/t0016-evaluation-protocol.json",
        "failures",
        out,
        confirm_no_auth=True,
        confirm_local_quality_evidence=True,
        transport=httpx.MockTransport(broken),
    )
    assert len(posts) == 14
    assert status["inference_complete"] < 14
    metrics = core.evaluate(out, out / "ground-truth.snapshot.private.json")
    assert any(r.get("not_scored") for r in metrics["results"])


def test_cli_calls_actual_core(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core, "PRIVATE_ROOT", tmp_path)
    source = tmp_path / "source.jpg"
    Image.new("RGB", (10, 10)).save(source)
    assert (
        cli.main(
            [
                "prepare",
                "--source",
                str(source),
                "--case-id",
                "synthetic",
                "--case-dir",
                str(tmp_path / "cases/synthetic"),
            ]
        )
        == 0
    )
    assert (tmp_path / "cases/synthetic/input-manifest.private.json").exists()
    assert str(tmp_path) not in capsys.readouterr().out


def test_readonly_baseline() -> None:
    """Accepted core and fixture sources remain aligned with accepted T0015 evidence."""
    spec = core.read_json(core.ROOT / "specs/discovered-model-contracts.json")
    provenance = core.read_json(core.ROOT / "tests/fixtures/model_contracts/run.provenance.json")
    assert (
        core.compute_file_hash(core.ROOT / "scripts/model_contract_discovery.py")
        == provenance["observation"]["tool_source_sha256"]
    )
    assert provenance["source_run_id"] == core.BASELINE_RUN
    assert spec["run_id"] == core.BASELINE_RUN


def test_openapi_prose_and_key_order_do_not_cause_drift() -> None:
    a = {
        "description": "before",
        "required": ["file", "kind"],
        "properties": {"file": {"type": "string"}},
    }
    b = {
        "properties": {"file": {"type": "string", "description": "after"}},
        "required": ["kind", "file"],
    }
    assert core.structural_contract(a) == core.structural_contract(b)


def test_frozen_annotation_changes_need_new_version(tmp_path: Path) -> None:
    case = synthetic_case(tmp_path)
    gt = core.read_json(case / "ground-truth.private.json")
    gt["regions"][0]["reference"] = "changed"
    core.write_private(case / "ground-truth.private.json", gt)
    with pytest.raises(ValueError, match="GROUND_TRUTH_FROZEN_MISMATCH"):
        core.validate_ground_truth(case)


def test_prepare_and_run_refuse_nonempty_directories(
    collected: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Exercise run refusal with the original input case and no additional requests.
    case = collected.parent / "case"
    with pytest.raises(ValueError, match="OUTPUT_NOT_EMPTY"):
        core.run(
            case,
            core.ROOT / "specs/t0016-evaluation-protocol.json",
            "second",
            collected,
            confirm_no_auth=True,
            confirm_local_quality_evidence=True,
            transport=httpx.MockTransport(service),
        )


def test_public_metrics_tamper_rejected(collected: Path) -> None:
    core.evaluate(collected, collected / "ground-truth.snapshot.private.json")
    path = collected / "metrics.private.json"
    path.write_text("{}")
    with pytest.raises(ValueError, match="EVALUATION_HASH_MISMATCH"):
        core.public_summary(collected)


def test_cli_rejects_public_evidence_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        cli.main(
            [
                "prepare",
                "--source",
                str(tmp_path / "source.jpg"),
                "--case-id",
                "synthetic",
                "--case-dir",
                str(tmp_path / "public"),
            ]
        )
        == 1
    )
    assert "PRIVATE_STORAGE_REQUIRED" in capsys.readouterr().out


def test_malformed_choices_metadata_safe() -> None:
    values: list[Any] = [None, [], ["bad"], {}, "bad"]
    for value in values:
        assert core.safe_finish_reason({"choices": value}) is None
