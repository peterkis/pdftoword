"""Ovis-only output must not borrow PP content, geometry or corrections."""

import zipfile
from pathlib import Path

import pytest
from lxml import etree
from prototypes.docx_output.common import DemoError, read
from prototypes.docx_output.pipeline import finish
from tests.demo.test_output import setup_ir


def test_ovis_content_formulas_and_explicit_relations(private_case: Path) -> None:
    from prototypes.docx_output.ovis_replay import recover_ovis

    job, ir, p = setup_ir(private_case)
    content = (
        "# Synthetic exam\n\n1. Choose a figure\n\nA.\n\n"
        '<img src="images/bbox_100_100_200_200.jpg" />\n\n'
        "2. Choose a relation\n\nC. $x>0$ decreases\n\nD. $x<0$ increases\n\n"
        '<img src="images/bbox_100_500_250_650.jpg" />\n\n第99题'
    )
    body = {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}
    recover_ovis(job, ir, p, body, "ovis-request")
    finish(job, ir)
    qa = read(job / "qa.json")
    assert qa["model_call_count"] == 0
    assert qa["omml_formula_count"] == 2 and qa["formula_image_count"] == 0
    assert qa["placed_figure_count"] == 2
    assert any(i["type"] == "target_not_in_input" for i in ir["issues"])
    assert any(r["type"] == "label_of" for r in ir["relations"])
    assert all(b["source_type"] == "ovis_ocr2" for b in p["blocks"])
    with zipfile.ZipFile(job / "auto.docx") as z:
        root = etree.fromstring(z.read("word/document.xml"))
        assert "x<0" in "".join(root.xpath('//*[local-name()="oMath"]//*[local-name()="t"]/text()'))


@pytest.mark.parametrize(
    "content",
    [
        '<img src="https://evil.test/image.png" />',
        '<img src="images/bbox_0_0_1100_50.jpg" />',
        "1. $\\unsupported{x}$",
    ],
)
def test_ovis_rejects_unknown_geometry_or_syntax(private_case: Path, content: str) -> None:
    from prototypes.docx_output.ovis_replay import recover_ovis

    job, ir, p = setup_ir(private_case)
    body = {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}
    if "unsupported" in content:
        recover_ovis(job, ir, p, body, "ovis-request")
        assert finish(job, ir)["fallback_area_ratio"] == pytest.approx(1)
    else:
        with pytest.raises(DemoError):
            recover_ovis(job, ir, p, body, "ovis-request")


def test_ovis_import_does_not_open_other_provider_evidence(
    private_case: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from prototypes.docx_output import replay as importer
    from prototypes.docx_output.common import digest
    from prototypes.docx_output.pipeline import replay
    from tests.demo.test_output import raster

    source = raster(private_case)
    monkeypatch.setattr(importer, "EXPECTED_JPG", digest(source))
    run = private_case / "run"
    run.mkdir()
    for folder in ["inputs.private", "responses.private", "predictions.private"]:
        (run / folder).mkdir()
    (run / "inputs.private/source.png").write_bytes(source.read_bytes())
    body = {
        "choices": [{"finish_reason": "stop", "message": {"content": "# Ovis only\n\n1. $x<0$"}}]
    }
    (run / "responses.private/ovis-rid.json").write_text(json.dumps(body))
    (run / "predictions.private/ovis-rid.json").write_text("{}")
    row = {
        "provider": "ovis",
        "variant_id": "jpg",
        "repeat_index": 1,
        "request_id": "ovis-rid",
        "status": "COMPLETE",
        "input_file_sha256": digest(source),
        "pruned_response_sha256": digest(run / "responses.private/ovis-rid.json"),
        "prediction_sha256": digest(run / "predictions.private/ovis-rid.json"),
    }
    files = {
        "requests.json": {
            "requests": [
                row,
                {"provider": "pp", "variant_id": "jpg", "repeat_index": 1, "request_id": "poison"},
            ]
        },
        "run-metadata.json": {
            "execution_status": "COMPLETE",
            "run_id": "synthetic",
            "tool_source_hashes": {},
        },
        "input-manifest.snapshot.json": {
            "variants": {"jpg": {"filename": "source.png", "file_sha256": digest(source)}}
        },
    }
    for name, data in files.items():
        (run / name).write_text(json.dumps(data))
    seal = {str(p.relative_to(run)): digest(p) for p in run.rglob("*") if p.is_file()}
    (run / "evidence-manifest.private.json").write_text(json.dumps(seal))
    seen = []
    original = Path.read_bytes

    def guarded(path: Path) -> bytes:
        assert "poison" not in path.name and "ground-truth" not in path.name
        seen.append(path)
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    job = replay(run, output_root=private_case / "jobs", content_provider="ovis")
    assert [r["provider"] for r in read(job / "request-manifest.json")["requests"]] == ["ovis"]
    assert read(job / "qa.json")["omml_formula_count"] == 1


def test_adjacent_page_footer_fragments_join_without_text_loss(private_case: Path) -> None:
    from prototypes.docx_output.ovis_replay import recover_ovis

    job, ir, p = setup_ir(private_case)
    body = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": "1. Question\n\nA. Answer\n\n试卷第\n\n1页"},
            }
        ]
    }
    recover_ovis(job, ir, p, body, "ovis-request")
    footers = [b for b in p["blocks"] if b["type"] == "footer"]
    assert len(footers) == 1 and footers[0]["content"]["plain_text"] == "试卷第1页"
    finish(job, ir)
    with zipfile.ZipFile(job / "auto.docx") as z:
        root = etree.fromstring(z.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        question = next(
            p for p in root.xpath("//w:p", namespaces=ns) if "1. Question" in "".join(p.itertext())
        )
        assert question.xpath("./w:pPr/w:keepNext", namespaces=ns)
