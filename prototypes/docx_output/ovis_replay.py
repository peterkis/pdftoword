"""Ovis-only reconstruction: literal content, declared figure geometry, no PP inputs."""

from __future__ import annotations

import re
from pathlib import Path

from .common import DemoError, Json, block, candidate, crop, issue, relation, transform
from .formula import to_omml
from .structure import CAPTION, MATH, OPTION, QUESTION, chat_content, image_content

IMAGE = re.compile(r'<img\s+src="images/bbox_(\d+)_(\d+)_(\d+)_(\d+)\.jpg"\s*/?>')


def recover_ovis(job: Path, ir: Json, p: Json, body: Json, request_id: str) -> None:
    """Build IR exclusively from one complete Ovis Markdown response.

    Figure coordinates follow the official normalized_1000 convention. Text has
    no precise bbox in this wire format: full-page source bounds are explicitly
    marked unknown and are never interpreted as a detected text rectangle.
    """
    content = chat_content(body)
    ir["metadata"]["content_provider"] = "ovis"
    ir["provenance"].setdefault("ovis_content", {})[str(p["page_index"])] = content
    ir["provenance"]["ovis_coordinate_contract"] = {
        "unit": "normalized_1000",
        "scope": "figure_tags_only",
        "source": "https://huggingface.co/ATH-MaaS/OvisOCR2",
        "text_bbox": "unknown; full-page source reference only",
    }
    page_box = [0.0, 0.0, p["width_pt"], p["height_pt"]]
    for token in re.split(r"(<img\b[^>]*>)", content):
        if not token.strip():
            continue
        if token.startswith("<img"):
            match = IMAGE.fullmatch(token)
            if not match:
                raise DemoError("OVIS_UNSUPPORTED_IMAGE_TAG")
            raw = [float(x) for x in match.groups()]
            if any(x > 1000 for x in raw):
                raise DemoError("OVIS_IMAGE_COORDINATES_OUT_OF_RANGE")
            bbox = transform(raw, p["width_pt"] / 1000, p["height_pt"] / 1000)
            bid = f"p{p['page_index']}-ovis{len(p['blocks'])}"
            b = block(
                bid,
                p["page_index"],
                bbox,
                "",
                "ovis_ocr2",
                "figure",
                {
                    "request_id": request_id,
                    "raw_image_tag": token,
                    "raw_bbox": raw,
                    "raw_unit": "normalized_1000",
                },
            )
            aid = crop(job, ir, p, bbox, bid + "-figure")
            b.update(content=image_content(aid), render_policy="preserve_image")
            ir["provenance"][bid] = {"request_id": request_id, "raw_image_tag": token}
            p["blocks"].append(b)
            continue
        if re.search(r"<[A-Za-z!/][^>]*>", token):
            raise DemoError("OVIS_UNSUPPORTED_HTML_REGION")
        for paragraph in re.split(r"\n\s*\n", token):
            original = paragraph
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            heading = bool(re.match(r"^#{1,6}\s+", paragraph))
            paragraph = re.sub(r"^#{1,6}\s+", "", paragraph)
            # Only split explicit option markers at whitespace boundaries,
            # outside math delimiters; never split decimals or formula tokens.
            markers = [
                m.start()
                for m in re.finditer(r"(?<!\S)[A-D][.．、]\s*", paragraph)
                if not any(f.start() <= m.start() < f.end() for f in MATH.finditer(paragraph))
            ]
            starts = [0, *[i for i in markers if i > 0]]
            ends = [*starts[1:], len(paragraph)]
            for start, end in zip(starts, ends, strict=True):
                text = paragraph[start:end].strip()
                if not text:
                    continue
                kind = (
                    "heading"
                    if heading
                    else "question"
                    if QUESTION.match(text)
                    else "option"
                    if OPTION.match(text)
                    else "caption"
                    if CAPTION.match(text)
                    else "footer"
                    if re.fullmatch(r".*第|\d+页", text)
                    else "paragraph"
                )
                bid = f"p{p['page_index']}-ovis{len(p['blocks'])}"
                b = block(
                    bid,
                    p["page_index"],
                    list(page_box),
                    text,
                    "ovis_ocr2",
                    kind,
                    {
                        "request_id": request_id,
                        "raw_markdown_paragraph": original,
                        "split_reason": "explicit_whitespace_delimited_option_marker",
                        "text_geometry": "not_provided_by_provider",
                    },
                )
                b["geometry_source"] = "inferred"
                b["flags"].append("text_geometry_unknown_full_page_reference")
                ir["provenance"][bid] = {
                    "request_id": request_id,
                    "raw_markdown_paragraph": original,
                    "geometry_scope": "page_reference_not_detected_bbox",
                }
                parts: list[Json] = []
                cursor = 0
                for m in MATH.finditer(text):
                    parts.append({"text": text[cursor : m.start()]})
                    try:
                        parts.append({"latex": m[1], "source_text": m[0], "omml": to_omml(m[1])})
                    except DemoError as exc:
                        issue(
                            ir,
                            "OVIS_FORMULA_GEOMETRY_REQUIRED",
                            "不支持的公式缺少精确源框；不能猜坐标或伪装成可编辑结果。",
                            [bid],
                            p["page_index"],
                        )
                        raise DemoError("OVIS_FORMULA_GEOMETRY_REQUIRED") from exc
                    cursor = m.end()
                if parts:
                    parts.append({"text": text[cursor:]})
                    ir["metadata"].setdefault("inline_parts", {})[bid] = parts
                    b["render_policy"] = "hybrid"
                    b["flags"].append("editable_formulas")
                p["blocks"].append(b)
    # A split page-number phrase has explicit syntax, not inferred document text.
    compact: list[Json] = []
    for b in p["blocks"]:
        if (
            compact
            and b["type"] == "footer"
            and compact[-1]["type"] == "footer"
            and compact[-1]["content"]["plain_text"].endswith("第")
            and re.fullmatch(r"\d+页", b["content"]["plain_text"])
        ):
            previous = compact[-1]
            text = previous["content"]["plain_text"] + b["content"]["plain_text"]
            supersedes = [previous["selected_candidate_id"], b["selected_candidate_id"]]
            previous["content_candidates"].extend(b["content_candidates"])
            for old in previous["content_candidates"]:
                old["selected"] = False
            selected = candidate(
                previous["id"] + "-joined",
                "ovis_ocr2",
                text,
                {
                    "request_id": request_id,
                    "source_blocks": [previous["id"], b["id"]],
                    "supersedes": supersedes,
                    "reason": "adjacent_page_number_phrase_whitespace_join",
                },
            )
            previous["content"]["plain_text"] = text
            previous["content_candidates"].append(selected)
            previous["selected_candidate_id"] = selected["id"]
            previous["provenance_refs"].append(b["id"])
        else:
            compact.append(b)
    p["blocks"] = compact
    unlocated = [b["id"] for b in p["blocks"] if b["geometry_source"] == "inferred"]
    issue(
        ir,
        "TEXT_GEOMETRY_NOT_PROVIDED",
        "Ovis未提供文字行/公式精确框；文字点击显示整页来源，不能作为精确定位。",
        unlocated,
        p["page_index"],
    )
    ir["metrics"]["unlocated_text_block_count"] = len(unlocated)
    associate_ovis(ir, p)
    p["routing_decision"] = "OVIS_CONTENT_AND_FIGURE_REPLAY"
    p["reading_order"] = [b["id"] for b in p["blocks"]]


def associate_ovis(ir: Json, p: Json) -> None:
    """Use explicit adjacent labels/captions and model sequence, not invented text boxes."""
    blocks = p["blocks"]
    questions = {
        m[1]: b for b in blocks if (m := QUESTION.match(b["content"].get("plain_text", "")))
    }
    option_groups: dict[str, list[Json]] = {}
    shared: list[Json] = []
    question_id = ""
    associated = set()
    for index, b in enumerate(blocks):
        if b["type"] == "question":
            question_id = b["id"]
        if b["type"] != "figure":
            continue
        previous = blocks[index - 1] if index else None
        following = blocks[index + 1] if index + 1 < len(blocks) else None
        if previous and re.fullmatch(r"[A-D][.．、]", previous["content"].get("plain_text", "")):
            relation(
                ir,
                "label_of",
                previous["id"],
                b["id"],
                {"reason": "adjacent_Ovis_label_image_tokens"},
            )
            option_groups.setdefault(question_id, []).append(
                {"label": previous["id"], "figure": b["id"]}
            )
            associated.add(b["id"])
            if question_id:
                relation(
                    ir, "anchored_to", b["id"], question_id, {"reason": "explicit_option_sequence"}
                )
        if following and (m := CAPTION.match(following["content"].get("plain_text", ""))):
            relation(
                ir,
                "caption_of",
                following["id"],
                b["id"],
                {"reason": "adjacent_Ovis_image_caption"},
            )
            if b["id"] not in associated:
                shared.append({"label": following["id"], "figure": b["id"]})
            associated.add(b["id"])
            if m[1] in questions:
                relation(
                    ir,
                    "references",
                    b["id"],
                    questions[m[1]]["id"],
                    {"explicit_question": m[1], "placement": "source_figure_row"},
                )
            else:
                issue(
                    ir,
                    "target_not_in_input",
                    "图题指向的题干不在输入中，保留独立图组。",
                    [b["id"], following["id"]],
                    p["page_index"],
                )
    groups = ir["metadata"].setdefault("figure_groups", [])
    positions = {b["id"]: index for index, b in enumerate(blocks)}
    for pairs in option_groups.values():
        contiguous: list[Json] = []
        for pair in pairs:
            if contiguous and positions[pair["label"]] != positions[contiguous[-1]["figure"]] + 1:
                groups.append(
                    {"page_index": p["page_index"], "kind": "option_grid", "pairs": contiguous}
                )
                contiguous = []
            contiguous.append(pair)
        if contiguous:
            groups.append(
                {"page_index": p["page_index"], "kind": "option_grid", "pairs": contiguous}
            )
    # Captioned figures may share a row only when consecutive in reading order.
    by_id = {b["id"]: b for b in blocks}
    rows: list[list[Json]] = []
    for pair in shared:
        box = by_id[pair["figure"]]["bbox"]
        if rows:
            prior = by_id[rows[-1][-1]["figure"]]["bbox"]
            overlap = min(box[3], prior[3]) - max(box[1], prior[1])
        else:
            overlap = 0
        adjacent = bool(rows) and (
            positions[pair["figure"]] == positions[rows[-1][-1]["label"]] + 1
        )
        if rows and overlap > 0 and adjacent:
            rows[-1].append(pair)
        else:
            rows.append([pair])
    for pairs in rows:
        groups.append({"page_index": p["page_index"], "kind": "shared_row", "pairs": pairs})
    for b in blocks:
        if b["type"] == "figure" and b["id"] not in associated:
            issue(
                ir, "FIGURE_ASSOCIATION_REVIEW", "独立图域待复核关联。", [b["id"]], p["page_index"]
            )
