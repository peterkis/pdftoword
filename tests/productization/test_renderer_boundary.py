"""Real offline structure/renderer seams, immutable replay and CLI/API coverage."""
from __future__ import annotations

import copy
import json
import shutil
import socket
import sys
import uuid
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from fastapi.testclient import TestClient
from prototypes.docx_output.common import PRIVATE, DemoError, Json, block, digest, read, save
from prototypes.docx_output.pipeline import finish
from prototypes.docx_output.planning.render_plan import RenderPlan
from prototypes.docx_output.render_replay import compare_renderers, inventory
from prototypes.docx_output.renderers.legacy import LegacyRenderer
from prototypes.docx_output.server import create_app
from prototypes.docx_output.structure import image_content
from prototypes.docx_output.structure_processors.base import StructureCandidate
from prototypes.docx_output.structure_processors.legacy import LegacyStructureProcessor
from prototypes.docx_output.writer import build
from tests.demo.test_output import setup_ir

from docx_demo import main


@pytest.fixture
def case(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """All tests deny outbound sockets; only private synthetic inputs are generated."""
    def deny(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("NETWORK_FORBIDDEN")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    root = PRIVATE / ("renderer-test-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root)


def source_job(root: Path) -> tuple[Path, Json]:
    """Build text, image, explicit figure ownership and nested registered assets."""
    from prototypes.docx_output.common import crop, relation

    job, ir, page = setup_ir(root)
    b = block("question", 0, [10, 10, 300, 30], "1. Keep < exact > content", "inferred")
    b["type"] = "question"
    fig = block("figure", 0, [10, 50, 100, 100], "", "inferred")
    aid = crop(job, ir, page, fig["bbox"], "figure")
    fig.update(type="figure", content=image_content(aid), render_policy="preserve_image")
    asset = next(a for a in ir["assets"] if a["id"] == aid)
    old = job / asset["path"]
    nested = job / "regions" / "nested" / "assets" / old.name
    nested.parent.mkdir(parents=True)
    shutil.move(old, nested)
    asset["path"] = nested.relative_to(job).as_posix()
    page["blocks"] = [b, fig]
    page["reading_order"] = [b["id"], fig["id"]]
    relation(ir, "anchored_to", fig["id"], b["id"], {"basis": "synthetic"})
    save(job / "request-manifest.json", {"requests": [], "model_call_count": 0})
    build(job, ir, "auto")  # Baseline bypasses the new seam intentionally.
    save(job / "layout.auto.json", ir)
    save(job / "overrides.json", {"protected": "synthetic human evidence"})
    save(job / "layout.reviewed.json", ir)
    shutil.copyfile(job / "auto.docx", job / "reviewed.docx")
    return job, ir


def xml_parts(path: Path) -> dict[str, bytes]:
    """Compare document semantics, styles and exact embedded images, excluding timestamps."""
    with zipfile.ZipFile(path) as package:
        return {name: package.read(name) for name in package.namelist() if name.startswith("word/")}


def test_same_source_real_docx_and_repeated_export(case: Path) -> None:
    source, ir = source_job(case)
    before = inventory(source)
    comparisons = [compare_renderers(source, "reviewed", case / "jobs") for _ in range(2)]
    children = []
    for comparison in comparisons:
        record = read(comparison / "comparison.json")
        assert record["source_unchanged"] and record["model_call_count"] == 0
        for output in record["outputs"]:
            child = case / "jobs" / output["job_id"]
            children.append(child)
            assert xml_parts(child / "auto.docx") == xml_parts(source / "reviewed.docx")
            current_map = read(child / "source-map.auto.json")
            baseline_map = read(source / "source-map.auto.json")
            assert current_map.pop("docx_sha256") == digest(child / "auto.docx")
            assert baseline_map.pop("docx_sha256") == digest(source / "auto.docx")
            assert current_map == baseline_map
            assert read(child / "layout.auto.json")["relations"] == ir["relations"]
            assert Document(str(child / "auto.docx")).paragraphs[0].text == (
                "1. Keep < exact > content")
            plan = read(child / "render-plan.auto.json")
            assert plan["elements"][0]["source_ids"] == ["question"]
            assert plan["elements"][0]["style_ref"] == "Normal"
    assert len(set(children)) == 4 and inventory(source) == before


def test_independent_processor_and_renderer_execute(case: Path) -> None:
    source, ir = source_job(case)
    calls = []

    class Processor(LegacyStructureProcessor):
        name = "injected-structure"

        def process(self, selected: Json) -> StructureCandidate:
            calls.append("structure")
            selected["pages"][0]["blocks"][0]["content"]["plain_text"] = "Candidate only"
            return super().process(selected)

    class Renderer(LegacyRenderer):
        name = "injected-renderer"

        def render(self, job: Path, plan: RenderPlan, revision: str) -> Json:
            calls.append("renderer")
            assert plan.document["pages"][0]["blocks"][0]["content"]["plain_text"] == (
                "Candidate only")
            return super().render(job, plan, revision)

    comparison = compare_renderers(source, output_root=case / "jobs", renderer_b=Renderer(),
                                   structure_processor=Processor())
    record = read(comparison / "comparison.json")
    assert calls == ["structure", "renderer"]
    assert read(source / "layout.auto.json") == ir
    b = case / "jobs" / record["outputs"][1]["job_id"]
    assert read(b / "render-manifest.auto.json")["structure_processor"]["name"] == (
        "injected-structure")


@pytest.mark.parametrize("fault", ["missing", "tampered", "response", "symlink", "nested"])
def test_reject_bad_evidence_before_output(case: Path, fault: str) -> None:
    source, ir = source_job(case)
    asset = source / ir["assets"][0]["path"]
    if fault == "missing":
        asset.unlink()
    elif fault == "tampered":
        asset.write_bytes(b"altered")
    elif fault == "response":
        (source / "response.raw").write_bytes(b"wire")
        save(source / "request-manifest.json", {"requests": [
            {"raw_response_path": "response.raw", "response_sha256": "0" * 64}]})
    elif fault == "symlink":
        (source / "link").symlink_to(asset)
    before = inventory(source) if fault != "symlink" else None
    target = source / "children" if fault == "nested" else case / "new-jobs"
    with pytest.raises(DemoError):
        compare_renderers(source, output_root=target)
    assert not target.exists()
    if before is not None:
        assert inventory(source) == before


def test_auto_guard_and_plan_rejection(case: Path) -> None:
    source, ir = source_job(case)
    before = inventory(source)
    with pytest.raises(DemoError, match="AUTO_IMMUTABLE"):
        finish(source, ir)
    assert inventory(source) == before
    plan = RenderPlan.from_ir(ir)
    plan.output_layout["mode"] = "unsupported"
    with pytest.raises(DemoError, match="LEGACY_LAYOUT_UNSUPPORTED"):
        LegacyRenderer().render(source, plan, "reviewed")
    assert inventory(source) == before
    candidate = LegacyStructureProcessor().process(ir)
    original = copy.deepcopy(ir)
    candidate.document["pages"].clear()
    assert ir == original


def test_cli_api_use_actual_shared_path(case: Path, monkeypatch: pytest.MonkeyPatch,
                                      capsys: pytest.CaptureFixture[str]) -> None:
    source, _ = source_job(case)
    before = inventory(source)
    monkeypatch.setattr(sys, "argv", ["docx_demo", "compare-renderers", "--source-job",
                                    str(source), "--output-root", str(case / "jobs")])
    assert main() == 0
    cli = read(Path(capsys.readouterr().out.strip()) / "comparison.json")
    with TestClient(create_app(output_root=case / "jobs"),
                    base_url="http://127.0.0.1:8765") as client:
        token = client.get("/api/session").json()["token"]
        headers = {"origin": "http://127.0.0.1:8765", "x-demo-session": token}
        response = client.post(f"/api/compare-renderers/{source.name}", json={}, headers=headers)
        assert response.status_code == 200
        api = response.json()["comparison"]
        assert cli["source_ir_sha256"] == api["source_ir_sha256"]
        assert len(api["outputs"]) == 2
        for out in api["outputs"]:
            child = case / "jobs" / out["job_id"]
            assert xml_parts(child / "auto.docx") == xml_parts(source / "auto.docx")
        rejected = client.post(f"/api/compare-renderers/{source.name}",
                               json={"renderer_b": "unknown"}, headers=headers)
        assert rejected.status_code == 400
    assert inventory(source) == before


def test_sealed_responses_verify_both_wire_and_stored(case: Path) -> None:
    source, _ = source_job(case)
    raw, stored = source / "response.raw", source / "response.json"
    raw.write_bytes(b'{"synthetic":true}')
    save(stored, {"synthetic": True})
    save(source / "request-manifest.json", {"requests": [{"raw_response_path": raw.name,
         "response_sha256": digest(raw), "stored_response_sha256": digest(stored)}]})
    comparison = compare_renderers(source, output_root=case / "jobs")
    assert read(comparison / "comparison.json")["verification"]["verified_stored_responses"] == 1
    stored.write_text(json.dumps({"changed": True}))
    with pytest.raises(DemoError, match="STORED_RESPONSE_HASH"):
        compare_renderers(source, output_root=case / "jobs")


@pytest.mark.parametrize("suffix", [".png", ".jpg", ".jpeg", ".pdf"])
def test_staged_input_hash_all_formats(case: Path, suffix: str) -> None:
    source, ir = source_job(case)
    staged = source / ("input" + suffix)
    staged.write_bytes(b"synthetic original bytes")
    ir["source"]["sha256"] = digest(staged)
    ir["source"]["filename"] = "original" + suffix
    save(source / "layout.auto.json", ir)
    compare_renderers(source, output_root=case / "valid-jobs")
    staged.write_bytes(b"altered staged input")
    with pytest.raises(DemoError, match="INPUT_HASH_MISMATCH"):
        compare_renderers(source, output_root=case / "invalid-jobs")
    assert not (case / "invalid-jobs").exists()


@pytest.mark.parametrize("fault", ["tampered", "missing"])
def test_cached_response_without_wire_path(case: Path, fault: str) -> None:
    source, _ = source_job(case)
    stored = source / "response-p0-region0-pp.json"
    save(stored, {"synthetic": True})
    save(source / "request-manifest.json", {"requests": [{
        "region_id": "p0-region0", "provider": "pp", "status": "COMPLETE",
        "http_attempted": False, "stored_response_sha256": digest(stored),
        "reused_from": {"job_id": "prior", "hash_basis": "stored_normalized_json"},
    }]})
    compare_renderers(source, output_root=case / "valid-jobs")
    if fault == "tampered":
        save(stored, {"changed": True})
    else:
        stored.unlink()
    with pytest.raises(DemoError, match="STORED_RESPONSE_HASH"):
        compare_renderers(source, output_root=case / "invalid-jobs")
    assert not (case / "invalid-jobs").exists()


def test_plan_elements_follow_explicit_reading_order(case: Path) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"].reverse()
    plan = RenderPlan.from_ir(ir)
    assert [e["source_ids"][0] for e in plan.as_dict()["elements"]] == ["question", "figure"]
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(source, output_root=case / "jobs")
    for row in read(comparison / "comparison.json")["outputs"]:
        child = case / "jobs" / row["job_id"]
        assert xml_parts(child / "auto.docx") == xml_parts(source / "auto.docx")


def test_provenance_image_tampering_without_staged_input(case: Path) -> None:
    source, ir = source_job(case)
    image = source / ir["provenance"]["pages"]["0"]["image_path"]
    image.write_bytes(b"tampered preview image")
    with pytest.raises(DemoError, match="SOURCE_IMAGE_HASH"):
        compare_renderers(source, output_root=case / "invalid-jobs")
    assert not (case / "invalid-jobs").exists()


def test_structure_processed_once_for_renderer_comparison(case: Path) -> None:
    source, _ = source_job(case)

    class Stateful(LegacyStructureProcessor):
        calls = 0

        def process(self, selected: Json) -> StructureCandidate:
            self.calls += 1
            candidate = super().process(selected)
            candidate.document["pages"][0]["blocks"][0]["content"]["plain_text"] = str(self.calls)
            return candidate

    processor = Stateful()
    comparison = compare_renderers(source, output_root=case / "jobs", structure_processor=processor)
    outputs = read(comparison / "comparison.json")["outputs"]
    a, b = [case / "jobs" / row["job_id"] for row in outputs]
    assert processor.calls == 1
    assert digest(a / "render-plan.auto.json") == digest(b / "render-plan.auto.json")
    assert xml_parts(a / "auto.docx") == xml_parts(b / "auto.docx")


def test_manifest_identifies_concrete_injected_code(case: Path) -> None:
    source, _ = source_job(case)

    class Alternate(LegacyRenderer):
        name = "alternate"

        def render(self, job: Path, plan: RenderPlan, revision: str) -> Json:
            return super().render(job, plan, revision)

    comparison = compare_renderers(source, output_root=case / "jobs", renderer_b=Alternate())
    outputs = read(comparison / "comparison.json")["outputs"]
    manifests = [read(case / "jobs" / row["job_id"] / "render-manifest.auto.json")
                 for row in outputs]
    assert manifests[0]["renderer"]["implementation"] != manifests[1]["renderer"]["implementation"]
    source_hashes = manifests[1]["renderer"]["implementation"]["source_sha256"]
    assert digest(Path(__file__)) in source_hashes.values()


def test_old_unsealed_page_requires_explicit_prior_seal(case: Path) -> None:
    source, ir = source_job(case)
    ir["provenance"]["pages"]["0"].pop("image_sha256", None)
    ir["source"]["filename"] = "older.pdf"
    save(source / "layout.auto.json", ir)
    seal = case / "prior-comparison.json"
    save(seal, {"source_job_id": source.name, "source_files": inventory(source)})
    with pytest.raises(DemoError, match="SOURCE_IMAGE_HASH_UNAVAILABLE"):
        compare_renderers(source, output_root=case / "invalid-jobs")
    comparison = compare_renderers(source, output_root=case / "jobs", source_seal=seal)
    assert read(comparison / "comparison.json")["source_seal_sha256"] == digest(seal)
    (source / ir["provenance"]["pages"]["0"]["image_path"]).write_bytes(b"tampered")
    with pytest.raises(DemoError, match="SOURCE_SEAL_MISMATCH"):
        compare_renderers(source, output_root=case / "invalid-jobs", source_seal=seal)
    assert not (case / "invalid-jobs").exists()
