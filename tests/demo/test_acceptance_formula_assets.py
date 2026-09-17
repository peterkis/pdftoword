"""Only drawn inline assets belong in the DOCX source-image manifest."""

from pathlib import Path

import pytest
from prototypes.docx_output.common import read
from prototypes.docx_output.pipeline import finish
from prototypes.docx_output.structure import image_content, recover
from tests.demo.test_output import pp_block, response, setup_ir

from acceptance.docx_reader import inspect


@pytest.mark.parametrize(
    "formula,editable,whole_image",
    [
        ("x>0", True, False),
        (r"\unsupported{x}", False, False),
        (r"\unsupported{x}", False, True),
    ],
)
def test_source_map_matches_actual_formula_render_branch(
    private_case: Path, formula: str, editable: bool, whole_image: bool
) -> None:
    job, ir, page = setup_ir(private_case)
    pp = response(
        [pp_block(f"1. ${formula}$")],
        formulas=[{"rec_formula": formula, "dt_polys": [50, 20, 180, 40]}],
    )
    recover(job, ir, page, {"pp": pp}, {})
    parts = [part for group in ir["metadata"]["inline_parts"].values() for part in group]
    assert any("asset_id" in part for part in parts)
    assert any("omml" in part and "asset_id" in part for part in parts) is editable
    if whole_image:
        bid = next(iter(ir["metadata"]["inline_parts"]))
        asset_id = next(p["asset_id"] for p in parts if "asset_id" in p)
        next(b for b in page["blocks"] if b["id"] == bid)["content"] = image_content(asset_id)
    finish(job, ir)
    actual = inspect(job / "auto.docx")
    source = read(job / "source-map.auto.json")
    assert actual["errors"] == []
    assert sum(len(p["images"]) for p in actual["paragraphs"]) == (0 if editable else 1)
    assert sum(len(b["images"]) for b in source["blocks"]) == (0 if editable else 1)
    # Reference crops stay available locally even when OMML is the written representation.
    assert all((job / a["path"]).is_file() for a in ir["assets"])
