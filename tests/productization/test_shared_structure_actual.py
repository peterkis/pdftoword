"""Actual public DocVortex calls with negative contracts and isolated offline execution."""

from __future__ import annotations

import copy
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from prototypes.docx_output.common import PRIVATE, DemoError, Json, block, new_job, read
from prototypes.docx_output.docvortex_runtime import call_worker
from prototypes.docx_output.reuse_poc import public_probes
from prototypes.docx_output.structure_processors.bridge import bridge
from prototypes.docx_output.structure_processors.docvortex import DocVortexStructureProcessor
from tests.demo.test_output import setup_ir


@pytest.fixture
def case() -> Iterator[Path]:
    """Independent self-owned evidence only; absence of required runtime fails, never mock/skip."""
    root = PRIVATE / ("shared-test-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root)


def text_ir(root: Path, text: str = "Synthetic heading") -> Json:
    """Produce a real schema IR with native-point synthetic evidence."""
    _, ir, page = setup_ir(root)
    b = block("one", 0, [10, 10, 300, 50], text, "native_pdf", "heading")
    page["blocks"], page["reading_order"] = [b], [b["id"]]
    return ir


def test_public_probes_six_capabilities_and_negative_outputs(case: Path) -> None:
    job = new_job(case / "probes")
    results = public_probes(job)
    assert all(v["model_unmodified"] for k, v in results.items() if k != "table_state")
    assert results["formula"]["counts"]["oMath"] == 2
    assert results["table"]["counts"]["tbl"] == 1
    assert results["table"]["counts"]["vMerge"] == 2
    assert results["table_state"]["columns"] == 2
    assert results["formula-image-fallback"]["counts"]["drawing"] == 1
    assert results["formula-raw-latex"]["counts"]["oMath"] == 0
    assert read(job / "heading.middle.json")["pages"][0]["blocks"][0]["level"] == 2
    middle = read(job / "paragraph.middle.json")
    assert middle["pages"][1]["blocks"][0]["continues_prev"] is True
    assert "lines" not in middle["pages"][0]["blocks"][0]
    assert read(job / "caption.middle.json")["pages"][0]["blocks"][0]["type"] == "image"
    order = read(job / "order.middle.json")["pages"][0]["blocks"]
    assert order[0]["content"][0]["content"] == "Second geometrically"
    assert results["cleanup"]["content_cleaned"] is False
    # Missing lines and non-consecutive source pages must not be guessed.
    model = read(job / "paragraph.model.json")
    model["page_index_map"] = [2, 4]
    result = call_worker({"action": "postprocess", "model": model})
    assert not result["middle"]["pages"][1]["blocks"][0].get("continues_prev")
    model["page_index_map"] = [2, 3]
    for page in model["pages"]:
        page[0].pop("lines")
    result = call_worker({"action": "postprocess", "model": model})
    assert not result["middle"]["pages"][1]["blocks"][0].get("continues_prev")
    assert result["network_requests"] == 0 and not result["pdfium_loaded"]


def test_bridge_normalized_contract_identity_and_field_ledger(case: Path) -> None:
    ir = text_ir(case)
    ir["metadata"]["structure_evidence"] = {
        "one": {
            "coordinate_space": "pdf_points",
            "lines": [{"bbox": [10, 10, 300, 50], "text": "Synthetic heading"}],
            "angle": 0,
            "label": "synthetic_heading",
        }
    }
    ir["pages"][0]["blocks"][0]["engine_confidence"] = 0.7
    original = copy.deepcopy(ir)
    value = bridge(ir)
    assert value.model["metadata"]["producer"]["name"] == "pdf2word"
    assert value.model["page_index_map"] == []
    assert value.model["pages"][0][0]["bbox"][2] == 300 / ir["pages"][0]["width_pt"]
    processor = DocVortexStructureProcessor()
    candidate = processor.process(ir)
    assert ir == original and candidate.document["pages"] == original["pages"]
    assert processor.last_execution["source_ledger"]["entries"][0]["evidence"]["lines"]
    assert "lines" not in processor.last_execution["middle"]["pages"][0]["blocks"][0]
    assert candidate.loss_report["proposals"][0]["adopted"]
    assert any("TEMP_FIELDS" in r["code"] for r in candidate.loss_report["losses"])


@pytest.mark.parametrize("fault", ["duplicate", "bbox", "order"])
def test_reject_invalid_source_contract(case: Path, fault: str) -> None:
    ir = text_ir(case)
    page = ir["pages"][0]
    if fault == "duplicate":
        page["blocks"].append(copy.deepcopy(page["blocks"][0]))
    elif fault == "bbox":
        page["blocks"][0]["bbox"][2] = page["width_pt"] + 1
    else:
        page["reading_order"] = []
    with pytest.raises(DemoError):
        bridge(ir)


@pytest.mark.parametrize("text,changed", [("ＡＢＣ ﬁ", False), ("first\nsecond", True)])
def test_cleanup_is_a_candidate_loss_not_a_source_edit(
    case: Path, text: str, changed: bool
) -> None:
    ir = text_ir(case, text)
    candidate = DocVortexStructureProcessor().process(ir)
    assert candidate.document["pages"] == ir["pages"]
    assert (
        any(
            r["code"] == "SHARED_CONTENT_OR_GEOMETRY_CHANGED"
            for r in candidate.loss_report["losses"]
        )
        == changed
    )
    assert candidate.loss_report["proposals"][0]["adopted"] == (not changed)


def test_manual_lock_and_stage_identity(case: Path) -> None:
    ir = text_ir(case)
    ir["pages"][0]["blocks"][0]["source_type"] = "manual_correction"
    processor = DocVortexStructureProcessor()
    candidate = processor.process(ir)
    assert not candidate.loss_report["proposals"][0]["adopted"]
    assert processor.process(candidate.document).loss_report["status"] == "ALREADY_FINALIZED"
    candidate.document["pages"][0]["blocks"][0]["content"]["plain_text"] = "A new human edit"
    assert processor.process(candidate.document).loss_report["status"] == "GUARDED"


def test_same_text_multiple_sources_remain_distinct(case: Path) -> None:
    ir = text_ir(case, "Identical text")
    second = copy.deepcopy(ir["pages"][0]["blocks"][0])
    second["id"] = "two"
    second["bbox"] = [10, 100, 300, 150]
    ir["pages"][0]["blocks"].append(second)
    ir["pages"][0]["reading_order"].append("two")
    processor = DocVortexStructureProcessor()
    result = processor.process(ir)
    assert result.loss_report["mapped_count"] == 2
    assert [p["source_id"] for p in result.loss_report["proposals"]] == ["one", "two"]
    assert result.document["pages"] == ir["pages"]


def test_caption_binding_requires_existing_source_relation(case: Path) -> None:
    from prototypes.docx_output.common import relation
    from tests.productization.test_renderer_boundary import source_job

    _, ir = source_job(case)
    caption = block("caption", 0, [10, 105, 100, 125], "Figure 1", "native_pdf", "caption")
    ir["pages"][0]["blocks"].append(caption)
    ir["pages"][0]["reading_order"].append("caption")
    processor = DocVortexStructureProcessor()
    candidate = processor.process(ir)
    groups = [p for p in candidate.loss_report["proposals"] if p["kind"] == "caption_group"]
    assert groups and not groups[0]["adopted"]
    assert candidate.document["relations"] == ir["relations"]
    assert any(
        r["code"] == "SHARED_CAPTION_OWNERSHIP_UNCONFIRMED" for r in candidate.loss_report["losses"]
    )
    relation(ir, "caption_of", "caption", "figure", {"basis": "synthetic explicit source relation"})
    candidate = processor.process(ir)
    assert next(p for p in candidate.loss_report["proposals"] if p["kind"] == "caption_group")[
        "adopted"
    ]
    assert candidate.document["relations"] == ir["relations"]


@pytest.mark.parametrize("provider", ["native_pdf", "monkeyocrv2", "pp_structure", "ovis_ocr2"])
def test_provider_evidence_is_retained_without_fake_producer(case: Path, provider: str) -> None:
    ir = text_ir(case)
    source = ir["pages"][0]["blocks"][0]
    source["geometry_source"] = provider
    source["engine"] = provider
    value = bridge(ir)
    assert value.ledger["entries"][0]["block"]["geometry_source"] == provider
    assert value.model["metadata"]["producer"]["name"] == "pdf2word"
    assert "score" not in value.model["pages"][0][0]


def test_structure_loss_uses_actual_nonzero_source_page(case: Path) -> None:
    ir = text_ir(case, "first\nsecond")
    ir["source"]["page_count"] = 6
    page = ir["pages"][0]
    page["page_index"] = 5
    page["blocks"][0]["page_index"] = 5
    candidate = DocVortexStructureProcessor().process(ir)
    issues = [
        i for i in candidate.document["issues"] if i["type"] == "SHARED_CONTENT_OR_GEOMETRY_CHANGED"
    ]
    assert issues and issues[0]["page_index"] == 5
    assert issues[0]["block_ids"] == ["one"]


def continuation_ir(root: Path) -> Json:
    """Two source pages with explicit lines satisfying the public continuation contract."""
    ir = text_ir(root, "a paragraph continues")
    first = ir["pages"][0]
    first["blocks"][0]["type"] = "paragraph"
    first["blocks"][0]["bbox"] = [60, 700, 500, 750]
    second = copy.deepcopy(first)
    second["page_index"] = 1
    second["blocks"][0].update(id="two", page_index=1, bbox=[60, 60, 500, 110])
    second["blocks"][0]["content"]["plain_text"] = "with further words"
    second["reading_order"] = ["two"]
    ir["pages"].append(second)
    ir["source"]["page_count"] = 2
    ir["metadata"]["structure_evidence"] = {
        "one": {
            "coordinate_space": "pdf_points",
            "lines": [{"bbox": [60, 700, 500, 720]}, {"bbox": [60, 730, 500, 750]}],
        },
        "two": {
            "coordinate_space": "pdf_points",
            "lines": [{"bbox": [60, 60, 500, 80]}, {"bbox": [60, 90, 400, 110]}],
        },
    }
    return ir


def test_reprocessing_updates_owned_continuations_without_duplicates(case: Path) -> None:
    processor = DocVortexStructureProcessor()
    result = processor.process(continuation_ir(case)).document
    assert len(result["relations"]) == 1
    relation_id = result["relations"][0]["id"]
    for text in ["with an edit", "with another edit"]:
        result["pages"][1]["blocks"][0]["content"]["plain_text"] = text
        result = processor.process(result).document
        assert len(result["relations"]) == 1
        assert result["relations"][0]["id"] == relation_id
    result["pages"][0]["blocks"][0]["content"]["plain_text"] += "."
    result = processor.process(result).document
    assert result["relations"] == []


def test_reprocessing_retains_manual_continuation(case: Path) -> None:
    processor = DocVortexStructureProcessor()
    result = processor.process(continuation_ir(case)).document
    manual = result["relations"][0]
    manual["evidence"]["manual"] = True
    expected = copy.deepcopy(manual)
    result["pages"][1]["blocks"][0]["content"]["plain_text"] = "with a human edit"
    result = processor.process(result).document
    assert result["relations"] == [expected]
    result["pages"][0]["blocks"][0]["content"]["plain_text"] += "."
    result = processor.process(result).document
    assert result["relations"] == [expected]


def test_poc_does_not_claim_a_call_for_cached_finalized_structure(case: Path) -> None:
    from prototypes.docx_output.common import save
    from prototypes.docx_output.reuse_poc import run_poc
    from tests.productization.test_renderer_boundary import source_job

    source, ir = source_job(case)
    ir["metrics"]["model_call_count"] = 0
    finalized = DocVortexStructureProcessor().process(ir).document
    save(source / "layout.auto.json", finalized)
    with pytest.raises(DemoError, match="POC_REQUIRES_PRE_STRUCTURE_IR"):
        run_poc(source, output_root=case / "new-poc")
    assert not (case / "new-poc").exists()


def test_reprocessing_reconciles_owned_issues(case: Path) -> None:
    processor = DocVortexStructureProcessor()
    result = processor.process(text_ir(case, "first\nsecond")).document
    original = copy.deepcopy(result["issues"])
    assert original
    for text in ["changed\nsecond", "another\nsecond"]:
        result["pages"][0]["blocks"][0]["content"]["plain_text"] = text
        result = processor.process(result).document
        assert result["issues"] == original
    result["pages"][0]["blocks"][0]["content"]["plain_text"] = "single line"
    result = processor.process(result).document
    assert result["issues"] == []


def test_reprocessing_preserves_managed_and_unrelated_issues(case: Path) -> None:
    processor = DocVortexStructureProcessor()
    result = processor.process(text_ir(case, "first\nsecond")).document
    result["issues"][0]["status"] = "resolved"
    unrelated = copy.deepcopy(result["issues"][0])
    unrelated.update(id="human-warning", status="open", message="Human review note")
    result["issues"].append(unrelated)
    expected = copy.deepcopy(result["issues"])
    for text in ["changed\nsecond", "single line"]:
        result["pages"][0]["blocks"][0]["content"]["plain_text"] = text
        result = processor.process(result).document
        assert result["issues"] == expected


def test_reassociated_manual_warning_keeps_unique_issue_id(case: Path) -> None:
    processor = DocVortexStructureProcessor()
    result = processor.process(text_ir(case, "first\nsecond")).document
    result["issues"][0]["block_ids"] = []
    manual = copy.deepcopy(result["issues"][0])
    for text in ["changed\nsecond", "another\nsecond"]:
        result["pages"][0]["blocks"][0]["content"]["plain_text"] = text
        result = processor.process(result).document
        assert len(result["issues"]) == 2
        assert len({item["id"] for item in result["issues"]}) == 2
        assert manual in result["issues"]


@pytest.mark.parametrize("action", ["text", "candidate"])
@pytest.mark.parametrize("kind", ["heading", "continuation"])
def test_actual_review_operations_lock_selected_manual_content(
    case: Path, action: str, kind: str
) -> None:
    from prototypes.docx_output.common import candidate
    from prototypes.docx_output.review import apply_overrides

    ir = text_ir(case) if kind == "heading" else continuation_ir(case)
    block = ir["pages"][0]["blocks"][0]
    text = "a manually corrected paragraph"
    operation = {"action": action, "block_id": block["id"], "reason": "Synthetic review"}
    if action == "text":
        operation["text"] = text
    else:
        option = candidate("review-choice", "ovis_ocr2", text, {})
        option["selected"] = False
        block["content_candidates"].append(option)
        operation["candidate_id"] = option["id"]
    reviewed = apply_overrides(case, ir, {"operations": [operation]})
    selected = reviewed["pages"][0]["blocks"][0]
    assert selected["source_type"] == "manual_correction"
    assert selected["geometry_source"] != "manual_correction"
    result = DocVortexStructureProcessor().process(reviewed)
    assert not any(proposal["adopted"] for proposal in result.loss_report["proposals"])
    assert not result.document["relations"]
    assert result.document["pages"][0]["blocks"][0]["content"]["plain_text"] == text


@pytest.mark.parametrize("fault", ["changed", "missing", "duplicate"])
def test_caption_group_requires_preserved_owner(
    case: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    from prototypes.docx_output.common import relation
    from prototypes.docx_output.structure_processors import docvortex as adapter
    from tests.productization.test_renderer_boundary import source_job

    _, ir = source_job(case)
    page = ir["pages"][0]
    caption = page["blocks"][0]
    caption.update(type="caption", bbox=[10, 101, 100, 115])
    caption["content"]["plain_text"] = "Figure 1. Synthetic image"
    page["reading_order"] = ["figure", "question"]
    relation(ir, "caption_of", "question", "figure", {"basis": "synthetic"})
    real_call = adapter.call_worker

    def damaged_response(payload: Json) -> Json:
        result = real_call(payload)
        parent = next(b for b in result["middle"]["pages"][0]["blocks"] if b["type"] == "image")
        body = next(b for b in parent["content"] if b["type"] == "image_body")
        assert any(b["type"] == "image_caption" for b in parent["content"])
        if fault == "changed":
            body["bbox"][0] += 0.01
        elif fault == "missing":
            parent["content"].remove(body)
        else:
            parent["content"].append(copy.deepcopy(body))
        return result

    monkeypatch.setattr(adapter, "call_worker", damaged_response)
    result = DocVortexStructureProcessor().process(ir)
    groups = [p for p in result.loss_report["proposals"] if p["kind"] == "caption_group"]
    assert groups and all(not p["adopted"] for p in groups)
    assert any(loss.get("source_id") == "figure" for loss in result.loss_report["losses"])
