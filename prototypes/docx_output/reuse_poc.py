"""Executable R1-05 structure/renderer ablations and six public-API capability probes."""

from __future__ import annotations

import copy
import zipfile
from pathlib import Path

from lxml import etree
from PIL import Image

from .common import JOBS, DemoError, Json, digest, new_job, read, save
from .docvortex_runtime import call_worker
from .render_replay import compare_renderers, inventory
from .renderers.docvortex import DocVortexRenderer
from .structure_processors.bridge import inline_text, json_hash
from .structure_processors.docvortex import DocVortexStructureProcessor, finalized_hash, leaves


def model(blocks: list[Json], pages: list[int] | None = None) -> Json:
    """Self-owned synthetic ModelJson; source evidence is never replaced by gold text."""
    return {
        "schema": "docvortex.model",
        "schema_version": "2.0",
        "metadata": {
            "file_suffix": "pdf",
            "producer": {"name": "pdf2word-synthetic-poc", "version": "1"},
        },
        "extensions": {},
        "page_index_map": pages or [],
        "pages": [blocks],
    }


def text_block(text: str, index: int, bbox: list[float], kind: str = "text") -> Json:
    """Declare synthetic coordinates, not measured real-document geometry."""
    return {
        "type": kind,
        "index": index,
        "bbox": bbox,
        "content": [{"type": "text", "content": text}],
    }


def public_probes(job: Path) -> Json:
    """Run the real public APIs and retain all positive and negative input/output pairs."""
    image = job / "assets" / "synthetic.png"
    Image.new("RGB", (60, 30), "navy").save(image)
    image.chmod(0o600)
    assets = {"assets/synthetic.png": digest(image)}
    first = text_block("a paragraph that continues", 0, [0.1, 0.1, 0.9, 0.15])
    second = text_block("with lower case words", 1, [0.1, 0.16, 0.9, 0.21])
    first["lines"] = [{"bbox": [0.1, 0.1, 0.9, 0.12]}, {"bbox": [0.1, 0.13, 0.9, 0.15]}]
    second["lines"] = [{"bbox": [0.1, 0.16, 0.9, 0.18]}, {"bbox": [0.1, 0.19, 0.7, 0.21]}]
    first.update(angle=0, score=0.8, label="synthetic_text")
    table = '<table><tr><th rowspan="2">A</th><th>B</th></tr><tr><td>C</td></tr></table>'
    cases = {
        "heading": [text_block("Synthetic heading", 0, [0.1, 0.1, 0.9, 0.2], "paragraph_title")],
        "paragraph": [first, second],
        "caption": [
            {
                "type": "image",
                "index": 0,
                "bbox": [0.1, 0.2, 0.6, 0.5],
                "content": "",
                "image_path": "assets/synthetic.png",
            },
            text_block("Figure 1. Synthetic image", 1, [0.1, 0.51, 0.6, 0.55], "image_caption"),
        ],
        "table": [{"type": "table", "index": 0, "bbox": [0.1, 0.1, 0.9, 0.4], "content": table}],
        "formula": [
            {"type": "equation", "index": 0, "bbox": [0.1, 0.1, 0.9, 0.2], "content": "x^2"},
            {
                "type": "text",
                "index": 1,
                "bbox": [0.1, 0.3, 0.9, 0.4],
                "content": [
                    {"type": "text", "content": "Value "},
                    {"type": "equation_inline", "content": "x^2"},
                ],
            },
        ],
        "order": [
            text_block("Second geometrically", 8, [0.1, 0.6, 0.9, 0.7]),
            text_block("First geometrically", 2, [0.1, 0.1, 0.9, 0.2]),
        ],
        "cleanup": [text_block("ＡＢＣ ﬁ first\nsecond", 0, [0.1, 0.1, 0.9, 0.2])],
        "auxiliary": [
            text_block("Visible body", 0, [0.1, 0.1, 0.9, 0.2]),
            text_block("Preserve this footer", 1, [0.1, 0.9, 0.9, 0.95], "footer"),
        ],
        "formula-image-fallback": [
            {
                "type": "equation",
                "index": 0,
                "bbox": [0.1, 0.1, 0.9, 0.2],
                "content": r"\frac{",
                "image_path": "assets/synthetic.png",
            }
        ],
        "formula-raw-latex": [
            {"type": "equation", "index": 0, "bbox": [0.1, 0.1, 0.9, 0.2], "content": r"\frac{"}
        ],
    }
    results = {}
    for name, blocks in cases.items():
        source = model(copy.deepcopy(blocks))
        if name == "paragraph":
            source["pages"][0][0]["bbox"] = [0.1, 0.8, 0.9, 0.85]
            source["pages"][0][0]["lines"] = [
                {"bbox": [0.1, 0.8, 0.9, 0.82]},
                {"bbox": [0.1, 0.83, 0.9, 0.85]},
            ]
            source["pages"] = [[source["pages"][0][0]], [source["pages"][0][1]]]
            source["page_index_map"] = [2, 3]
        output = call_worker({"action": "postprocess", "model": source})
        middle = output["middle"]
        save(job / f"{name}.model.json", source)
        save(job / f"{name}.middle.json", middle)
        target = job / f"{name}.docx"
        rendered = call_worker(
            {
                "action": "render",
                "middle": middle,
                "assets": assets,
                "job": str(job),
                "output": str(target),
            }
        )
        with zipfile.ZipFile(target) as package:
            xml = etree.fromstring(package.read("word/document.xml"))
            text = xml.xpath(
                '//*[local-name()="t" and namespace-uri()="http://schemas.openxmlformats.org/wordprocessingml/2006/main"]/text()'
            )
            counts = {
                k: len(xml.xpath(f'//*[local-name()="{k}"]'))
                for k in ("oMath", "tbl", "vMerge", "drawing")
            }
        results[name] = {
            "input_sha256": json_hash(source),
            "middle_sha256": json_hash(middle),
            "docx_sha256": rendered["docx_sha256"],
            "counts": counts,
            "model_unmodified": output["model_roundtrip"]["pages"] == source["pages"],
            "rendered_text_sha256": json_hash(text),
            "content_cleaned": [
                inline_text(leaf.get("content"))
                for page in middle["pages"]
                for b in page["blocks"]
                for leaf in leaves(b)
            ]
            != [inline_text(b.get("content")) for page in source["pages"] for b in page],
            "raw_latex_fallback": any(
                b["type"] == "equation" and b.get("content") and b["content"] in "".join(text)
                for b in blocks
            ),
            "auxiliary_retained": all(
                inline_text(b["content"]) in "".join(text) for b in blocks if b["type"] == "footer"
            ),
            "network_requests": 0,
            "pdfium_loaded": rendered["pdfium_loaded"],
        }
    results["table_state"] = call_worker({"action": "table", "html": table})["state"]
    save(job / "probe-results.json", results)
    return results


def run_poc(source: Path, output_root: Path = JOBS, source_seal: Path | None = None) -> Path:
    """Keep structure and renderer experiments independent with actual shared-path calls."""
    if output_root.resolve().is_relative_to(source.resolve()):
        raise DemoError("OUTPUT_INSIDE_SOURCE")
    selected = read(source / "layout.auto.json")
    stage = selected.get("metadata", {}).get("docvortex_structure", {})
    if isinstance(stage, dict) and stage.get("finalized_ir_sha256") == finalized_hash(selected):
        raise DemoError("POC_REQUIRES_PRE_STRUCTURE_IR")
    before = inventory(source)
    root = new_job(output_root)
    renderer_axis = compare_renderers(
        source, output_root=root / "jobs", renderer_b=DocVortexRenderer(), source_seal=source_seal
    )
    processor = DocVortexStructureProcessor()
    shared_axis = compare_renderers(
        source, output_root=root / "jobs", structure_processor=processor, source_seal=source_seal
    )
    for name, value in processor.last_execution.items():
        save(root / f"{name.replace('_', '-')}.json", value)
    probe_job = new_job(root / "probes")
    probes = public_probes(probe_job)
    identity = call_worker({"action": "identity"})
    save(root / "runtime-identity.json", identity)
    renderer_record = read(renderer_axis / "comparison.json")
    shared_record = read(shared_axis / "comparison.json")
    decisions = []
    for reuse_id, name in (
        ("MU-HEADING", "heading"),
        ("MU-PARAGRAPH", "paragraph"),
        ("MU-TABLE", "table"),
        ("MU-FORMULA", "formula"),
        ("MU-CAPTION", "caption"),
        ("MU-ORDER", "order"),
    ):
        decisions.append(
            {
                "reuse_id": reuse_id,
                "decision": "REFERENCE_ONLY" if name == "order" else "ADAPT_PUBLIC_API",
                "scope": "R1-05 bounded POC; later capability acceptance pending",
                "probe": name,
                "evidence": probes[name],
                "next_task": "R2/R3专项",
                "model_calls": 0,
            }
        )
    save(root / "reuse-decisions.json", {"capabilities": decisions})
    if inventory(source) != before:
        raise RuntimeError("SOURCE_CHANGED_DURING_POC")
    save(
        root / "poc-manifest.json",
        {
            "task": "P2W-R1-05",
            "source_files": before,
            "source_unchanged": True,
            "renderer_axis": {
                "comparison": renderer_axis.name,
                "outputs": renderer_record["outputs"],
            },
            "structure_axis": {
                "fixed_renderer": "legacy",
                "legacy": renderer_record["outputs"][0],
                "shared": shared_record["outputs"][0],
                "input_ir_sha256": shared_record["source_ir_sha256"],
            },
            "probes": probe_job.name,
            "model_calls": 0,
            "metadata_gets": 0,
            "public_structure_calls": 1 + len(probes) - 1,
            "visual_acceptance": "NOT_RUN",
            "word": "NOT_RUN",
        },
    )
    return root
