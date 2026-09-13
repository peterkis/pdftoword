"""PP contributes geometry only; every emitted word and formula stays Ovis-owned."""

import copy
from pathlib import Path

from prototypes.docx_output.common import read
from prototypes.docx_output.ovis_replay import recover_ovis
from prototypes.docx_output.pipeline import finish
from tests.demo.test_output import setup_ir


def test_pp_geometry_cannot_replace_ovis_content(private_case: Path) -> None:
    from prototypes.docx_output.pp_layout import apply_pp_layout

    job, ir, page = setup_ir(private_case)
    body = {
        "choices": [
            {"finish_reason": "stop", "message": {"content": "1. Select\n\nA. $x>0$\n\nB. $x<0$"}}
        ]
    }
    recover_ovis(job, ir, page, body, "ovis-request")
    original = copy.deepcopy([b["content"] for b in page["blocks"]])
    raw = {
        "width": 400,
        "height": 600,
        "parsing_res_list": [
            {
                "block_label": "text",
                "block_bbox": [40, 100, 350, 120],
                "block_content": "POISON question",
            },
            {
                "block_label": "text",
                "block_bbox": [55, 145, 350, 170],
                "block_content": "POISON options",
            },
        ],
        "overall_ocr_res": {
            "rec_boxes": [[40, 100, 350, 120], [55, 145, 160, 170], [225, 145, 350, 170]],
            "rec_texts": ["POISON"],
        },
        "formula_res_list": [],
    }
    pp = {"result": {"layoutParsingResults": [{"prunedResult": raw}]}}
    apply_pp_layout(job, ir, page, pp, "pp-request")
    assert [b["content"] for b in page["blocks"]] == original
    assert all(b["source_type"] == "ovis_ocr2" for b in page["blocks"])
    assert all(b["geometry_source"] == "pp_structure" for b in page["blocks"])
    assert ir["metadata"]["text_groups"][0]["rows"] == [
        [page["blocks"][1]["id"], page["blocks"][2]["id"]]
    ]
    finish(job, ir)
    assert read(job / "qa.json")["omml_formula_count"] == 2
    assert "POISON" not in str(ir)


def test_shared_row_and_two_row_layout_are_explicit(private_case: Path) -> None:
    from prototypes.docx_output.pp_layout import apply_pp_layout

    job, ir, page = setup_ir(private_case)
    content = (
        "1. Choose\n\nA. first B. second C. third D. fourth\n\n"
        "2. Choose\n\nA. one B. two C. three D. four"
    )
    recover_ovis(
        job,
        ir,
        page,
        {"choices": [{"finish_reason": "stop", "message": {"content": content}}]},
        "ovis",
    )
    regions = [
        ("text", [40, 100, 350, 120]),
        ("text", [55, 145, 350, 170]),
        ("text", [40, 200, 350, 220]),
        ("text", [55, 245, 350, 300]),
    ]
    boxes = [
        [40, 100, 350, 120],
        [55, 145, 350, 170],
        [40, 200, 350, 220],
        [55, 245, 160, 265],
        [220, 245, 350, 265],
        [55, 280, 160, 300],
        [220, 280, 350, 300],
    ]
    raw = {
        "width": 400,
        "height": 600,
        "parsing_res_list": [{"block_label": t, "block_bbox": b} for t, b in regions],
        "overall_ocr_res": {"rec_boxes": boxes},
        "formula_res_list": [],
    }
    apply_pp_layout(
        job, ir, page, {"result": {"layoutParsingResults": [{"prunedResult": raw}]}}, "pp"
    )
    groups = ir["metadata"]["text_groups"]
    assert [list(map(len, g["rows"])) for g in groups] == [[4], [2, 2]]
    assert groups[0]["distribution_inferred"] and not groups[1]["distribution_inferred"]
    options = [b for b in page["blocks"] if b["type"] == "option"]
    assert len({tuple(b["bbox"]) for b in options[:4]}) == 1
    assert all("geometry_approximate_shared_row" in b["flags"] for b in options[:4])
    from prototypes.docx_output.review import apply_overrides

    changed = apply_overrides(
        job,
        ir,
        {
            "operations": [
                {
                    "block_id": options[0]["id"],
                    "action": "move",
                    "delta": 1,
                    "reason": "Explicit order review",
                }
            ]
        },
    )
    assert len(changed["metadata"]["text_groups"]) == 1
