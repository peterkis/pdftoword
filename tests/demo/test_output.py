"""Offline behavior checks against the real prototype pipeline, not evaluator mocks."""

from __future__ import annotations

import copy
import json
import re
import zipfile
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from lxml import etree
from PIL import Image
from prototypes.docx_output import replay as replay_module
from prototypes.docx_output.common import (
    DemoError,
    Json,
    block,
    crop,
    digest,
    job_path,
    layout,
    new_job,
    read,
    safe_path,
    save,
    transform,
    union_area,
    validate,
)
from prototypes.docx_output.native_pdf import cluster_regions, parse_pages
from prototypes.docx_output.pipeline import convert, export, finish, replay, source_image
from prototypes.docx_output.raster_bridge import endpoint, recognize
from prototypes.docx_output.review import apply_overrides
from prototypes.docx_output.server import create_app
from prototypes.docx_output.structure import chat_content, recover
from prototypes.docx_output.writer import inspect_package
from tests.demo.synthetic import make_pdf


def raster(path: Path) -> Path:
    """Create a self-owned raster."""
    p = path / "input.png"
    Image.new("RGB", (400, 600), "white").save(p)
    p.chmod(0o600)
    return p


def response(
    blocks: list[Json], lines: list[Json] | None = None, formulas: list[Json] | None = None
) -> Json:
    """Use the actual PP wire envelope with synthetic content."""
    return {
        "logId": "synthetic",
        "errorCode": 0,
        "result": {
            "dataInfo": {"width": 400, "height": 600, "type": "image"},
            "layoutParsingResults": [
                {
                    "markdown": {"text": "", "isStart": True, "isEnd": True},
                    "prunedResult": {
                        "width": 400,
                        "height": 600,
                        "parsing_res_list": blocks,
                        "overall_ocr_res": {
                            "rec_boxes": [r["bbox"] for r in lines or []],
                            "rec_texts": [r["text"] for r in lines or []],
                        },
                        "formula_res_list": formulas or [],
                    },
                }
            ],
        },
    }


def pp_block(
    text: str = "1. Synthetic question", label: str = "text", bbox: list[int] | None = None
) -> Json:
    """One synthetic PP parsing block."""
    return {"block_content": text, "block_label": label, "block_bbox": bbox or [20, 20, 300, 40]}


def setup_ir(private_case: Path) -> tuple[Path, Json, Json]:
    """Allocate private source, job and production-schema IR."""
    source = raster(private_case)
    job = new_job(private_case / "jobs")
    ir = layout(job, source, 1)
    p = source_image(job, ir, source)
    return job, ir, p


def test_native_zero_http_and_text(private_case: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("HTTP forbidden")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    source = private_case / "native.pdf"
    original = make_pdf(source)
    job = convert(source, "1", output_root=private_case / "jobs", synthetic=True)
    ir = read(job / "layout.auto.json")
    text = "\n".join(b["content"].get("plain_text", "") for b in ir["pages"][0]["blocks"]).strip()
    assert re.sub(r"\s+", " ", text) == re.sub(r"\s+", " ", original)
    assert ir["pages"][0]["routing_decision"] == "NATIVE_LIMITED_SUPPORTED"
    qa = read(job / "qa.json")
    assert qa["model_call_count"] == 0 and qa["docx_package_valid"]
    assert qa["placed_figure_count"] == 1


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_native_rotation_geometry(private_case: Path, rotation: int) -> None:
    source = private_case / "rotated.pdf"
    make_pdf(source, rotation=rotation)
    job = convert(source, "1", output_root=private_case / "jobs")
    ir = read(job / "layout.auto.json")
    p = ir["pages"][0]
    assert p["routing_decision"] == "NEEDS_ROUTE_REVIEW"
    for b in p["blocks"]:
        x0, y0, x1, y1 = b["bbox"]
        assert 0 <= x0 < x1 <= p["width_pt"] + 1
        assert 0 <= y0 < y1 <= p["height_pt"] + 1


@pytest.mark.parametrize(
    "selection,total", [("1-4", 4), ("1,1", 2), ("0", 2), ("3", 2), ("1-2", 1)]
)
def test_page_limits(selection: str, total: int) -> None:
    with pytest.raises(DemoError):
        parse_pages(selection, total)


def test_point_roundtrip_and_overlap_area() -> None:
    bbox = [10.0, 20.0, 110.0, 160.0]
    assert transform(transform(bbox, 0.5, 0.25), 2, 4) == bbox
    assert union_area([[0, 0, 10, 10], [5, 0, 15, 10]]) == 150
    assert cluster_regions([[0, 0, 10, 10], [12, 1, 20, 10]]) == [[0, 0, 20, 10]]


@pytest.mark.parametrize("wire", [[], {}, 12, None])
def test_candidate_wire_rejected(wire: Any) -> None:
    with pytest.raises(DemoError, match="WIRE_TYPE"):
        chat_content({"choices": [{"finish_reason": "stop", "message": {"content": wire}}]})


def test_real_replay_read_only_zero_http(
    private_case: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = raster(private_case)
    monkeypatch.setattr(replay_module, "EXPECTED_JPG", digest(source))
    run = private_case / "history"
    run.mkdir()
    (run / "inputs.private").mkdir()
    (run / "inputs.private" / "source.png").write_bytes(source.read_bytes())
    inputs = {"variants": {"jpg": {"filename": "source.png", "file_sha256": digest(source)}}}
    requests = []
    for provider in ["pp", "ovis", "monkey"]:
        rid = provider + "-rid"
        body = (
            response([pp_block()])
            if provider == "pp"
            else {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": "1. Synthetic question"
                            if provider == "ovis"
                            else "[{'label':'Text','bbox':[50,30,750,70]}]"
                        },
                    }
                ]
            }
        )
        for folder in ["responses.private", "predictions.private"]:
            (run / folder).mkdir(exist_ok=True)
            (run / folder / f"{rid}.json").write_text(json.dumps(body))
        requests.append(
            {
                "provider": provider,
                "variant_id": "jpg",
                "repeat_index": 1,
                "status": "COMPLETE",
                "request_id": rid,
                "input_file_sha256": digest(source),
                "pruned_response_sha256": digest(run / "responses.private" / f"{rid}.json"),
                "prediction_sha256": digest(run / "predictions.private" / f"{rid}.json"),
            }
        )
    for name, value in {
        "input-manifest.snapshot.json": inputs,
        "requests.json": {"requests": requests},
        "run-metadata.json": {
            "execution_status": "COMPLETE",
            "run_id": "self-owned-synthetic",
            "tool_source_hashes": {"old": "unchanged"},
        },
    }.items():
        (run / name).write_text(json.dumps(value))
    # Poison GT to prove it is never needed or read as JSON by conversion.
    (run / "ground-truth.private.json").write_text("not JSON; never read")
    seal = {str(p.relative_to(run)): digest(p) for p in run.rglob("*") if p.is_file()}
    (run / "evidence-manifest.private.json").write_text(json.dumps(seal))
    before = {str(p): digest(p) for p in run.rglob("*") if p.is_file()}

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("HTTP forbidden")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    job = replay(run, output_root=private_case / "jobs", content_provider="pp")
    assert read(job / "qa.json")["model_call_count"] == 0
    assert before == {str(p): digest(p) for p in run.rglob("*") if p.is_file()}
    (run / "responses.private/pp-rid.json").write_text("{}")
    with pytest.raises(DemoError, match="HASH_MISMATCH"):
        replay(run, output_root=private_case / "jobs", content_provider="pp")


def test_formula_fallback_no_duplicate_and_fig_internal_text(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    pp = response(
        [
            pp_block("1. value $\\unsupported{a}$"),
            pp_block("inside secret", "image", [40, 100, 90, 180]),
            pp_block("inside secret", "text", [45, 110, 80, 130]),
        ],
        formulas=[{"rec_formula": "\\unsupported{a}", "dt_polys": [120, 20, 160, 40]}],
    )
    recover(job, ir, p, {"pp": pp}, {})
    finish(job, ir)
    with zipfile.ZipFile(job / "auto.docx") as z:
        root = etree.fromstring(z.read("word/document.xml"))
        text = "".join(root.itertext())
        assert "inside secret" not in text and "\\frac" not in text
        assert "value" in text
    qa = read(job / "qa.json")
    assert qa["formula_image_count"] == 1 and qa["placed_figure_count"] == 1
    assert qa["docx_package_valid"]


def test_unlocated_formula_preserves_region(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    recover(job, ir, p, {"pp": response([pp_block("1. $\\unknown{x}$")])}, {})
    finish(job, ir)
    assert p["blocks"][0]["content"]["kind"] == "image"
    qa = read(job / "qa.json")
    assert qa["fallback_region_count"] == 1
    assert qa["execution_status"] == "DEMO_OUTPUT_INSUFFICIENT"


def test_split_needs_line_evidence(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    text = "A. value 2.5 D. done3. Next question"
    recover(job, ir, p, {"pp": response([pp_block(text)])}, {})
    assert len(p["blocks"]) == 1
    assert any(i["type"] == "SPLIT_REVIEW_REQUIRED" for i in ir["issues"])
    job2, ir2, p2 = setup_ir(private_case)
    pp = response(
        [pp_block(text, bbox=[20, 20, 300, 80])],
        [
            {"text": "A. value 2.5 D. done", "bbox": [20, 20, 300, 40]},
            {"text": "3. Next question", "bbox": [20, 60, 200, 80]},
        ],
    )
    recover(job2, ir2, p2, {"pp": pp}, {})
    assert len(p2["blocks"]) == 2
    assert p2["blocks"][0]["content"]["plain_text"] == "A. value 2.5 D. done"
    assert p2["blocks"][1]["content"]["plain_text"] == "3. Next question"


def test_missing_caption_target_not_neighbor(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    recover(
        job,
        ir,
        p,
        {
            "pp": response(
                [
                    pp_block("1. Question"),
                    pp_block("", "image", [40, 100, 90, 180]),
                    pp_block("第99题", "figure_title", [45, 185, 85, 195]),
                ]
            )
        },
        {},
    )
    assert any(i["type"] == "target_not_in_input" for i in ir["issues"])
    assert not any(r["type"] == "references" for r in ir["relations"])


def test_crop_clamps_without_mutating_evidence(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    bbox = [-10.0, -20.0, 30.0, 50.0]
    crop(job, ir, p, bbox, "edge")
    assert ir["assets"][-1]["source_bbox"] == bbox
    assert ir["provenance"]["edge"]["crop_bbox_px"][:2] == [0, 0]
    assert bbox == [-10, -20, 30, 50]


def test_reviewed_immutable_auto_and_zero_calls(
    private_case: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = private_case / "source.pdf"
    make_pdf(source)
    job = convert(source, "1", output_root=private_case / "jobs")
    before = digest(job / "auto.docx")
    ir = read(job / "layout.auto.json")
    bid = ir["pages"][0]["blocks"][0]["id"]
    save(
        job / "overrides.json",
        {
            "actor": "synthetic_demo",
            "operations": [
                {
                    "block_id": bid,
                    "action": "text",
                    "text": "Explicit review <safe>",
                    "reason": "Synthetic manual demo",
                },
                {
                    "block_id": bid,
                    "action": "split",
                    "offset": 9,
                    "reason": "Split at reviewed boundary",
                },
            ],
        },
    )

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("HTTP forbidden")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    export(job)
    assert digest(job / "auto.docx") == before
    assert read(job / "qa.reviewed.json")["manual_override_count"] == 2
    assert read(job / "qa.reviewed.json")["model_call_count"] == 0
    assert inspect_package(job / "reviewed.docx")["docx_package_valid"]
    with pytest.raises(DemoError, match="AUTO_IMMUTABLE"):
        finish(job, ir)


def test_missing_image_has_explicit_error(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    recover(
        job, ir, p, {"pp": response([pp_block(), pp_block("", "image", [40, 100, 90, 180])])}, {}
    )
    (job / ir["assets"][0]["path"]).unlink()
    with pytest.raises(DemoError, match="ASSET_MISSING"):
        finish(job, ir)


def test_html_and_path_security(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    p["blocks"] = [block("a", 0, [1, 1, 20, 20], "<script>alert(1)</script>", "native_pdf")]
    p["reading_order"] = ["a"]
    finish(job, ir)
    html = (job / "review/index.html").read_text()
    assert "<script>alert" not in html and "&lt;script&gt;" in html
    with pytest.raises(DemoError):
        safe_path(job, "../private")
    (job / "escape").symlink_to(private_case)
    with pytest.raises(DemoError):
        safe_path(job, "escape/input.png")
    with pytest.raises(DemoError):
        job_path("../other", private_case)


def test_server_session_host_origin_and_assets(private_case: Path) -> None:
    app = create_app(output_root=private_case / "jobs")
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        assert client.get("/api/jobs").status_code == 403
        token = client.get("/api/session").json()["token"]
        assert client.get("/api/jobs").status_code == 200
        assert client.post("/api/replay", json={}).status_code == 403
        assert (
            client.post(
                "/api/replay",
                json={},
                headers={"origin": "http://evil.test", "x-demo-session": token},
            ).status_code
            == 403
        )
        assert client.get("/", headers={"host": "evil.test"}).status_code == 403
        assert client.get("/api/asset/invalid/id").status_code == 400
        assert "default-src 'self'" in client.get("/").headers["content-security-policy"]


def test_live_auth_and_loopback_only(private_case: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(DemoError, match="AUTHORIZATION"):
        convert(raster(private_case), mode="raster", output_root=private_case / "jobs")
    monkeypatch.setenv("PP_BASE_URL", "http://evil.test:8080")
    with pytest.raises(DemoError, match="LOOPBACK"):
        endpoint("pp")


def test_live_failure_cached_no_retry(private_case: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    job, ir, p = setup_ir(private_case)
    calls = []

    def disconnected(self: httpx.Client, url: str, **kwargs: Any) -> httpx.Response:
        calls.append(url)
        assert "Authorization" not in self.headers
        raise httpx.ConnectError("synthetic disconnect")

    monkeypatch.setattr(httpx.Client, "post", disconnected)
    manifest: Json = {
        "authorized": True,
        "confirm_no_auth": True,
        "requests": [],
        "model_call_count": 0,
    }
    recognize(job, ir, p, manifest)
    recognize(job, ir, p, manifest)
    assert len(calls) == 1 and manifest["model_call_count"] == 1
    assert manifest["requests"][0]["status"] == "PROVIDER_UNAVAILABLE"
    assert (job / ir["provenance"]["pages"]["0"]["image_path"]).exists()


def test_override_reason_and_policy_validation(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    p["blocks"] = [block("a", 0, [1, 1, 20, 20], "Original", "native_pdf")]
    p["reading_order"] = ["a"]
    before = copy.deepcopy(ir)
    with pytest.raises(DemoError, match="REASON"):
        apply_overrides(
            job, ir, {"operations": [{"block_id": "a", "action": "text", "text": "new"}]}
        )
    reviewed = apply_overrides(
        job,
        ir,
        {
            "operations": [
                {"block_id": "a", "action": "text", "text": "new", "reason": "source review"}
            ]
        },
    )
    assert ir == before
    validate(reviewed)
    assert reviewed["pages"][0]["blocks"][0]["content_candidates"][0]["text"] == "Original"


def test_review_formula_split_merge_and_candidate(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    t = "C. $x>0$ text D. $x<0$ next"
    pp = response(
        [pp_block(t)],
        formulas=[
            {"rec_formula": "x>0", "dt_polys": [50, 20, 85, 40]},
            {"rec_formula": "x<0", "dt_polys": [200, 20, 235, 40]},
        ],
    )
    recover(job, ir, p, {"pp": pp}, {})
    bid = p["blocks"][0]["id"]
    ops = {
        "operations": [
            {
                "block_id": bid,
                "action": "split",
                "offset": t.index("D."),
                "reason": "Reviewed option boundary",
            }
        ]
    }
    reviewed = apply_overrides(job, ir, ops)
    finish(job, reviewed, "reviewed")
    assert read(job / "qa.reviewed.json")["omml_formula_count"] == 2
    ops["operations"].append({"block_id": bid, "action": "merge", "reason": "Reviewed merge"})
    merged = apply_overrides(job, ir, ops)
    assert len(merged["pages"][0]["blocks"]) == 1
    assert sum("asset_id" in x for x in merged["metadata"]["inline_parts"][bid]) == 2
    original = copy.deepcopy(ir)
    original["pages"][0]["blocks"][0]["content_candidates"].append(
        {
            **original["pages"][0]["blocks"][0]["content_candidates"][0],
            "id": "ovis-review",
            "provider": "ovis_ocr2",
            "selected": False,
            "text": "C. $x > 0$ text D. $x < 0$ next",
        }
    )
    accepted = apply_overrides(
        job,
        original,
        {
            "operations": [
                {
                    "block_id": bid,
                    "action": "candidate",
                    "candidate_id": "ovis-review",
                    "reason": "Explicit candidate acceptance",
                }
            ]
        },
    )
    assert accepted["pages"][0]["blocks"][0]["content"]["plain_text"].startswith("C. $x > 0$")
    assert accepted["pages"][0]["blocks"][0]["selected_candidate_id"] != bid + "-c0"


def test_live_serial_budget_and_frozen_payload(
    private_case: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job, ir, p = setup_ir(private_case)
    calls = []

    def success(self: httpx.Client, url: str, **kwargs: Any) -> httpx.Response:
        payload = kwargs["json"]
        assert "authorization" not in self.headers
        calls.append((url, payload))
        if "layout-parsing" in url:
            from prototypes.docx_output.raster_bridge import PP_PARAMETERS

            assert {k: v for k, v in payload.items() if k != "file"} == PP_PARAMETERS
            value = response([pp_block()])
        else:
            provider = "ovis" if ":8000" in url else "monkey"
            assert payload["max_tokens"] == (8192 if provider == "ovis" else 2048)
            value = {
                "model": payload["model"],
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "text" if provider == "ovis" else "[]"},
                    }
                ],
            }
        return httpx.Response(200, json=value)

    monkeypatch.setattr(httpx.Client, "post", success)
    manifest: Json = {
        "authorized": True,
        "confirm_no_auth": True,
        "requests": [],
        "model_call_count": 0,
    }
    result = recognize(job, ir, p, manifest, ovis=True, monkey=True)
    assert list(result) == ["pp", "ovis", "monkey"]
    assert len(calls) == 3
    recognize(job, ir, p, manifest, ovis=True, monkey=True)
    assert len(calls) == 3


def test_server_preview_save_download_without_reinference(private_case: Path) -> None:
    source = private_case / "source.pdf"
    make_pdf(source)
    job = convert(source, "1", output_root=private_case / "jobs")
    before = digest(job / "auto.docx")
    bid = read(job / "layout.auto.json")["pages"][0]["blocks"][0]["id"]
    app = create_app(output_root=private_case / "jobs")
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        token = client.get("/api/session").json()["token"]
        headers = {"origin": "http://127.0.0.1:8765", "x-demo-session": token}
        changes = {
            "operations": [
                {
                    "block_id": bid,
                    "action": "text",
                    "text": "User edit <safe>",
                    "reason": "Synthetic review",
                }
            ]
        }
        preview = client.post("/api/preview/" + job.name, json=changes, headers=headers)
        assert preview.status_code == 200
        assert not (job / "reviewed.docx").exists()
        saved = client.post("/api/review/" + job.name, json=changes, headers=headers)
        assert saved.status_code == 200
        doc = client.get("/api/download/" + job.name + "/reviewed")
        assert doc.status_code == 200 and doc.content[:2] == b"PK"
        assert client.get("/api/asset/" + job.name + "/not-registered").status_code == 404
        assert digest(job / "auto.docx") == before
        assert read(job / "qa.reviewed.json")["model_call_count"] == 0


@pytest.mark.parametrize(
    "bbox", [[0, 0, 0, 1], [0, 0, float("nan"), 3], [0, "x", 2, 3], [True, 0, 2, 3]]
)
def test_invalid_coordinate_types(bbox: Any) -> None:
    with pytest.raises(DemoError, match="GEOMETRY"):
        transform(bbox, 1, 1)


def test_image_aspect_and_no_external_ooxml(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    recover(
        job, ir, p, {"pp": response([pp_block(), pp_block("", "image", [40, 100, 90, 200])])}, {}
    )
    finish(job, ir)
    with zipfile.ZipFile(job / "auto.docx") as z:
        root = etree.fromstring(z.read("word/document.xml"))
        ext = root.xpath('//*[local-name()="extent"]')[0]
        asset = ir["assets"][0]
        assert int(ext.get("cx")) / int(ext.get("cy")) == pytest.approx(
            asset["pixel_width"] / asset["pixel_height"], rel=0.001
        )
        assert int(ext.get("cx")) <= 505.28 * 12700
        assert b'TargetMode="External"' not in z.read("word/_rels/document.xml.rels")


def test_live_error_response_preserves_native_content(
    private_case: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job, ir, p = setup_ir(private_case)
    p["blocks"] = [block("native-kept", 0, [1, 1, 30, 20], "Native retained", "native_pdf")]
    p["reading_order"] = ["native-kept"]

    def wrong(self: httpx.Client, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(200, json={"errorCode": 0, "result": {}})

    monkeypatch.setattr(httpx.Client, "post", wrong)
    manifest: Json = {
        "authorized": True,
        "confirm_no_auth": True,
        "requests": [],
        "model_call_count": 0,
    }
    recognize(job, ir, p, manifest)
    finish(job, ir)
    assert manifest["requests"][0]["status"] == "CONTRACT_DRIFT"
    assert p["blocks"][0]["content"]["plain_text"] == "Native retained"
    assert read(job / "qa.json")["has_editable_runs"]


def test_supported_formula_written_as_editable_omml(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    pp = response(
        [pp_block(r"1. $y=\frac{k}{x}(k\neq0)$")],
        formulas=[{"rec_formula": r"y=\frac{k}{x}(k\neq0)", "dt_polys": [50, 20, 180, 40]}],
    )
    recover(job, ir, p, {"pp": pp}, {})
    finish(job, ir)
    with zipfile.ZipFile(job / "auto.docx") as z:
        root = etree.fromstring(z.read("word/document.xml"))
        ns = {"m": "http://schemas.openxmlformats.org/officeDocument/2006/math"}
        assert len(root.xpath("//m:oMath/m:f", namespaces=ns)) == 1
        assert "k" in root.xpath("//m:num//m:t/text()", namespaces=ns)
    assert read(job / "qa.json")["omml_formula_count"] == 1


@pytest.mark.parametrize(
    "latex,element",
    [
        (r"\frac{x-y}{x+y}=\frac{x^{2}-y^{2}}{(x+y)^{2}}", "sSup"),
        (r"2\sqrt{3}", "rad"),
        (r"x_i^2", "sSubSup"),
    ],
)
def test_formula_structure_preserved(latex: str, element: str) -> None:
    from prototypes.docx_output.formula import to_omml

    root = etree.fromstring(to_omml(latex).encode())
    assert root.xpath("//*[local-name()=$name]", name=element)


@pytest.mark.parametrize(
    "latex", [r"\unknown{x}", r"\frac{a}", r"x^{2", r"\input{file}", r"\sqrt[3]{x}", "x^^2"]
)
def test_unsupported_formula_not_guessed(latex: str) -> None:
    from prototypes.docx_output.formula import to_omml

    with pytest.raises(DemoError):
        to_omml(latex)


def test_critical_symbol_still_requires_review(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    recover(
        job,
        ir,
        p,
        {
            "pp": response(
                [pp_block(r"D. $x\leq0$")],
                formulas=[{"rec_formula": r"x\leq0", "dt_polys": [50, 20, 90, 40]}],
            )
        },
        {},
    )
    finish(job, ir)
    assert read(job / "qa.json")["formula_image_count"] == 1
    assert read(job / "qa.json")["omml_formula_count"] == 0


@pytest.mark.parametrize("confirmed", [r"x<0", r"x\leq0"])
def test_reviewed_operator_rebuilt_as_omml(private_case: Path, confirmed: str) -> None:
    job, ir, p = setup_ir(private_case)
    recover(
        job,
        ir,
        p,
        {
            "pp": response(
                [pp_block(r"D. $x\leq0$")],
                formulas=[{"rec_formula": r"x\leq0", "dt_polys": [50, 20, 90, 40]}],
            )
        },
        {},
    )
    bid = p["blocks"][0]["id"]
    revised = apply_overrides(
        job,
        ir,
        {
            "operations": [
                {
                    "block_id": bid,
                    "action": "text",
                    "text": f"D. ${confirmed}$",
                    "reason": "Explicit source-verified operator selection",
                }
            ]
        },
    )
    finish(job, revised, "reviewed")
    qa = read(job / "qa.reviewed.json")
    assert qa["omml_formula_count"] == 1
    assert qa["formula_image_count"] == 0
    with zipfile.ZipFile(job / "reviewed.docx") as z:
        root = etree.fromstring(z.read("word/document.xml"))
        paragraph = root.xpath('//*[local-name()="p"][.//*[local-name()="oMath"]]')[0]
        assert not paragraph.xpath('.//*[local-name()="drawing"]')
        text = "".join(paragraph.xpath('.//*[local-name()="oMath"]//*[local-name()="t"]/text()'))
        assert text == ("x<0" if confirmed == "x<0" else "x≤0")
