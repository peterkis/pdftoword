"""Explainable raster structure recovery from real PP lines and candidate evidence."""

from __future__ import annotations

import ast
import copy
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .common import (
    DemoError,
    Json,
    area,
    block,
    candidate,
    crop,
    intersection,
    invalid_xml_text,
    issue,
    relation,
    transform,
    union,
)
from .formula import MathSpans, to_omml, unrendered_math

QUESTION = re.compile(r"^\s*(\d+)[.．、](?!\d)\s*")
OPTION = re.compile(r"^\s*([A-D])[.．、]\s*")
CAPTION = re.compile(r"^\s*第\s*(\d+)\s*题\s*$")
MATH = MathSpans()


def chat_content(body: Json) -> str:
    """Require the frozen string wire type and complete finish reason."""
    choices = body.get("choices", [])
    if (
        not isinstance(choices, list)
        or len(choices) != 1
        or not isinstance(choices[0], dict)
        or not isinstance(choices[0].get("message"), dict)
        or choices[0].get("finish_reason") != "stop"
        or not isinstance(choices[0].get("message", {}).get("content"), str)
    ):
        raise DemoError("INVALID_CANDIDATE_WIRE_TYPE")
    return str(choices[0]["message"]["content"])


def image_content(aid: str, internal: str = "") -> Json:
    """Keep figure OCR as metadata only."""
    return {
        "kind": "image",
        "asset_id": aid,
        "content_mode": "figure_with_internal_text",
        "render_mode": "preserve_as_image",
        "ocr_mode": "metadata_only",
        "placement_hint": "inline",
        "internal_text": [internal] if internal else [],
    }


def recover(job: Path, ir: Json, p: Json, responses: Json, requests: Json) -> None:
    """Normalize PP, recover line boundaries, preserve all alternate candidates."""
    body = responses.get("pp")
    if not body or body.get("errorCode", 0) != 0:
        raise DemoError("PP_RESULT_MISSING")
    results = body.get("result", {}).get("layoutParsingResults", [])
    if len(results) != 1:
        raise DemoError("PP_PAGE_CONTRACT")
    raw = results[0]["prunedResult"]
    info = ir["provenance"]["pages"][str(p["page_index"])]
    data_info = body["result"].get("dataInfo", {})
    if (
        [raw.get("width"), raw.get("height")] != info["pixel_size"]
        or [data_info.get("width"), data_info.get("height")] != info["pixel_size"]
        or raw.get("model_settings", {}).get("use_doc_preprocessor", False)
    ):
        raise DemoError("COORDINATE_MAPPING_UNRESOLVED")
    sx, sy = info["pixel_to_point"]
    pp_request = next(
        (
            r["request_id"]
            for r in requests.get("requests", [])
            if r["provider"] == "pp" and r.get("page_index", p["page_index"]) == p["page_index"]
        ),
        "pp",
    )
    ocr = raw.get("overall_ocr_res", {})
    if len(ocr.get("rec_boxes", [])) != len(ocr.get("rec_texts", [])):
        raise DemoError("OCR_ARRAY_MISMATCH")
    lines = [
        {"bbox": transform(b, sx, sy), "text": t}
        for b, t in zip(ocr.get("rec_boxes", []), ocr.get("rec_texts", []), strict=True)
    ]
    formulas = [
        {"bbox": transform(f["dt_polys"], sx, sy), "latex": f["rec_formula"]}
        for f in raw.get("formula_res_list", [])
    ]
    all_boxes = [r["bbox"] for r in [*lines, *formulas]]
    all_boxes += [transform(r["block_bbox"], sx, sy) for r in raw["parsing_res_list"]]
    for bbox in all_boxes:
        if not (
            0 <= bbox[0] < bbox[2] <= p["width_pt"] and 0 <= bbox[1] < bbox[3] <= p["height_pt"]
        ):
            raise DemoError("PP_REGION_OUT_OF_PAGE")
    prefix = f"p{p['page_index']}-"
    figures = [
        transform(b["block_bbox"], sx, sy)
        for b in raw["parsing_res_list"]
        if b["block_label"] in {"image", "chart"}
    ]
    for index, source in enumerate(raw["parsing_res_list"]):
        bbox = transform(source["block_bbox"], sx, sy)
        text = source["block_content"]
        label = source["block_label"]
        bid = prefix + f"b{index}"
        b = block(
            bid,
            p["page_index"],
            bbox,
            text,
            "pp_structure",
            evidence={
                "request_id": pp_request,
                "raw_bbox": source["block_bbox"],
                "raw_unit": "returned_image_pixel",
                "selection_reason": "fixed_demo_PP_baseline",
            },
        )
        ir["provenance"][bid] = {"parent_parsing_block": source, "request_id": pp_request}
        if invalid_xml_text(text) and label not in {"image", "chart", "table"}:
            aid = crop(job, ir, p, bbox, bid + "-xml-fallback")
            b.update(content=image_content(aid), render_policy="preserve_image")
            issue(
                ir,
                "INVALID_XML_TEXT_FALLBACK",
                "候选含非法XML字符，保留原候选并降级源图。",
                [bid],
                p["page_index"],
            )
            p["blocks"].append(b)
            continue
        if label in {"image", "chart", "table"}:
            aid = crop(job, ir, p, bbox, bid + "-image")
            b.update(
                type="table" if label == "table" else "figure",
                content=image_content(aid, text),
                render_policy="preserve_image",
            )
            if label == "table":
                b["flags"].append("table_image_fallback")
                issue(ir, "TABLE_NOT_EDITABLE", "复杂表格保留为区域图片。", [bid], p["page_index"])
            p["blocks"].append(b)
            continue
        if any(intersection(bbox, f) / area(bbox) > 0.85 for f in figures):
            issue(
                ir,
                "IMAGE_TEXT_OVERLAP_REVIEW",
                "正文与图片相交，不能仅凭包含关系认定图内文字；保留正文待复核。",
                [bid],
                p["page_index"],
            )
        if label in {"doc_title", "paragraph_title"}:
            b["type"] = "heading"
        elif label in {"number", "footer"}:
            b["type"] = "footer"
        elif label == "figure_title":
            b["type"] = "caption"
        # Only split a merged parsing block when the SAME textual suffix begins
        # an actual OCR line. Never search for arbitrary "3." substrings.
        children = []
        owned = [
            line for line in lines if intersection(line["bbox"], bbox) / area(line["bbox"]) > 0.75
        ]
        owned.sort(key=lambda x: (x["bbox"][1], x["bbox"][0]))
        boundaries = []
        for line in owned:
            m = QUESTION.match(line["text"])
            if m and not text.lstrip().startswith(line["text"].strip()):
                needle = line["text"].strip()
                pos = text.find(needle)
                if pos > 0 and text.count(needle) == 1:
                    boundaries.append((pos, line))
        if len(boundaries) == 1:
            ir["provenance"][bid]["original_block"] = copy.deepcopy(b)
            pos, start = boundaries[0]
            for n, part in enumerate((text[:pos].strip(), text[pos:].strip())):
                chosen = [
                    line["bbox"]
                    for line in owned
                    if (line["bbox"][1] >= start["bbox"][1] - 1) == (n == 1)
                ]
                child = block(
                    bid + f"-s{n}",
                    p["page_index"],
                    union(chosen) if chosen else bbox,
                    part,
                    "pp_structure",
                    evidence={
                        "parent_id": bid,
                        "reason": "exact_suffix_at_OCR_line_start",
                        "supersedes": b["selected_candidate_id"],
                    },
                )
                ir["provenance"][child["id"]] = {"parent_id": bid, "reason": "OCR_line_boundary"}
                children.append(child)
        else:
            children = [b]
            if re.search(r"\S\d+[.．、]\s*\D", text):
                issue(
                    ir,
                    "SPLIT_REVIEW_REQUIRED",
                    "疑似合并题目；缺少可靠行首证据，请拆分。",
                    [bid],
                    p["page_index"],
                )
        if len(children) > 1:
            for item in ir["issues"]:
                item["block_ids"] = [
                    new_id
                    for old_id in item["block_ids"]
                    for new_id in ([c["id"] for c in children] if old_id == bid else [old_id])
                ]
        for child in children:
            t = child["content"]["plain_text"]
            if QUESTION.match(t):
                child["type"] = "question"
            elif OPTION.match(t):
                child["type"] = "option"
            if len(re.findall(r"[A-D][.．、]", t)) > 1:
                issue(
                    ir,
                    "OPTION_SPLIT_REVIEW",
                    "多个选项仍在同一段；可按源图人工拆分。",
                    [child["id"]],
                    p["page_index"],
                )
            matches = list(MATH.finditer(t))
            if matches:
                parts: list[Json] = []
                last = 0
                available = list(formulas)
                reliable = not unrendered_math(MATH.sub("", t))
                for mi, match in enumerate(matches):
                    compatible = [
                        f
                        for f in available
                        if f["latex"] == match[1]
                        and intersection(f["bbox"], child["bbox"]) / area(f["bbox"]) > 0.6
                    ]
                    if len(compatible) != 1:
                        reliable = False
                        break
                    f = compatible[0]
                    available.remove(f)
                    parts.append({"text": t[last : match.start()]})
                    aid = crop(
                        job, ir, p, f["bbox"], child["id"] + f"-formula{mi}", "formula_image"
                    )
                    part = {"asset_id": aid, "latex": match[1], "source_text": match[0]}
                    try:
                        # Known critical relation operators stay as source imagery until reviewed.
                        if re.search(r"\\(?:leq|geq)|[≤≥]", match[1]):
                            raise DemoError("CRITICAL_SYMBOL_REVIEW")
                        part["omml"] = to_omml(match[1])
                    except DemoError:
                        pass  # Explicit formula fallback issue is recorded below.
                    parts.append(part)
                    last = match.end()
                if reliable:
                    parts.append({"text": t[last:]})
                    ir["metadata"].setdefault("inline_parts", {})[child["id"]] = parts
                    child["render_policy"] = "hybrid"
                    if any("asset_id" in part and "omml" not in part for part in parts):
                        child["flags"].append("formula_images")
                        issue(
                            ir,
                            "FORMULA_IMAGE_FALLBACK",
                            "不支持或有关键符号冲突的公式保留原图；其余为可编辑Word公式。",
                            [child["id"]],
                            p["page_index"],
                        )
                    else:
                        child["flags"].append("editable_formulas")
                else:
                    aid = crop(job, ir, p, child["bbox"], child["id"] + "-fallback")
                    child.update(content=image_content(aid), render_policy="preserve_image")
                    child["flags"].append("region_fallback")
                    issue(
                        ir,
                        "FORMULA_REGION_FALLBACK",
                        "公式无法逐一定位；保留完整局部区域，正文不重复。",
                        [child["id"]],
                        p["page_index"],
                    )
            if not matches and unrendered_math(t):
                aid = crop(job, ir, p, child["bbox"], child["id"] + "-unparsed-formula")
                child.update(content=image_content(aid), render_policy="preserve_image")
                child["flags"].append("region_fallback")
                issue(
                    ir,
                    "FORMULA_REGION_FALLBACK",
                    "公式语法无法安全排版，保留源区域。",
                    [child["id"]],
                    p["page_index"],
                )
            p["blocks"].append(child)
    recover_monkey(ir, p, responses)
    if "ovis" in responses:
        content = chat_content(responses["ovis"])
        ir["provenance"].setdefault("ovis_content", {})[str(p["page_index"])] = content
        paragraphs = [
            s.strip().lstrip("#").strip()
            for s in content.split("\n\n")
            if s.strip() and not s.strip().startswith("<img")
        ]
        for b in p["blocks"]:
            if b["content"]["kind"] != "text":
                continue
            t = b["content"]["plain_text"]
            windows = [
                " ".join(paragraphs[start : start + length])
                for start in range(len(paragraphs))
                for length in (1, 2, 3)
                if start + length <= len(paragraphs)
            ]
            scores = [(SequenceMatcher(None, t, s).ratio(), s) for s in windows]
            if not scores:
                continue
            score, alt = max(scores)
            if score > 0.55 and alt != t:
                b["content_candidates"].append(
                    candidate(
                        b["id"] + "-ovis",
                        "ovis_ocr2",
                        alt,
                        {"alignment": "text_similarity_candidate_only", "similarity": score},
                        False,
                    )
                )
                issue(
                    ir,
                    "CONTENT_CONFLICT",
                    "PP与Ovis候选不同；请对照原图，未自动替换。",
                    [b["id"]],
                    p["page_index"],
                )
        if (
            "\\leq" in str(raw["parsing_res_list"]) or "≤" in str(raw["parsing_res_list"])
        ) and "<" in content:
            issue(
                ir,
                "CRITICAL_SYMBOL_CONFLICT",
                "PP包含≤候选，Ovis包含<候选；须逐处对照原图。",
                [b["id"] for b in p["blocks"] if "\\leq" in b["content"].get("plain_text", "")],
                p["page_index"],
            )
    associate(ir, p)


def associate(ir: Json, p: Json) -> None:
    """Associate explicit captions, and keep missing targets independent of placement."""
    blocks = p["blocks"]
    questions: dict[str, list[Json]] = {}
    for b in blocks:
        if m := QUESTION.match(b["content"].get("plain_text", "")):
            questions.setdefault(m[1], []).append(b)
    figures = [b for b in blocks if b["type"] == "figure"]
    groups = ir["metadata"].setdefault("figure_groups", [])
    used = set()
    # Labels must sit next to a figure, not merely precede it in model order.
    pairs = []
    for b in blocks:
        text = b["content"].get("plain_text", "").strip()
        if re.fullmatch(r"[A-D][.．、]", text):
            candidates = [
                f
                for f in figures
                if f["id"] not in used
                and 0 <= f["bbox"][0] - b["bbox"][2] < 30
                and f["bbox"][1] <= b["bbox"][1] <= f["bbox"][3]
            ]
            if len(candidates) == 1:
                f = candidates[0]
                used.add(f["id"])
                relation(ir, "label_of", b["id"], f["id"], {"reason": "adjacent_label"})
                pairs.append({"label": b["id"], "figure": f["id"]})
    positions = {b["id"]: i for i, b in enumerate(blocks)}
    contiguous: list[Json] = []
    for pair in pairs:
        if positions[pair["figure"]] != positions[pair["label"]] + 1:
            if contiguous:
                groups.append(
                    {"page_index": p["page_index"], "kind": "option_grid", "pairs": contiguous}
                )
                contiguous = []
            continue
        if contiguous and positions[pair["label"]] != positions[contiguous[-1]["figure"]] + 1:
            groups.append(
                {"page_index": p["page_index"], "kind": "option_grid", "pairs": contiguous}
            )
            contiguous = []
        contiguous.append(pair)
    if contiguous:
        groups.append({"page_index": p["page_index"], "kind": "option_grid", "pairs": contiguous})
    caption_pairs = []
    for b in blocks:
        text = b["content"].get("plain_text", "")
        m = CAPTION.match(text)
        if not m:
            continue
        candidates = [
            f
            for f in figures
            if f["id"] not in used
            and 0 <= b["bbox"][1] - f["bbox"][3] < 35
            and f["bbox"][0] <= (b["bbox"][0] + b["bbox"][2]) / 2 <= f["bbox"][2]
        ]
        if len(candidates) == 1:
            f = candidates[0]
            used.add(f["id"])
            relation(ir, "caption_of", b["id"], f["id"], {"explicit_caption": text})
            caption_pairs.append({"label": b["id"], "figure": f["id"]})
            if len(questions.get(m[1], [])) == 1:
                relation(
                    ir,
                    "references",
                    f["id"],
                    questions[m[1]][0]["id"],
                    {"explicit_question": m[1], "placement": "original_shared_row"},
                )
            else:
                issue(
                    ir,
                    "AMBIGUOUS_QUESTION_NUMBER" if m[1] in questions else "target_not_in_input",
                    "重复题号无法唯一关联，保留图组待复核。"
                    if m[1] in questions
                    else "图题指向的题干不在输入中；保留原共享图行，不挂到邻题。",
                    [f["id"], b["id"]],
                    p["page_index"],
                )
    by_id = {b["id"]: b for b in blocks}
    rows: list[list[Json]] = []
    for pair in caption_pairs:
        if positions[pair["label"]] != positions[pair["figure"]] + 1:
            continue
        adjacent = bool(rows) and positions[pair["figure"]] == positions[rows[-1][-1]["label"]] + 1
        box = by_id[pair["figure"]]["bbox"]
        prior = by_id[rows[-1][-1]["figure"]]["bbox"] if rows else box
        overlap = min(box[3], prior[3]) - max(box[1], prior[1])
        if adjacent and overlap > 0:
            rows[-1].append(pair)
        else:
            rows.append([pair])
    for row in rows:
        groups.append({"page_index": p["page_index"], "kind": "shared_row", "pairs": row})
    for f in figures:
        if f["id"] not in used:
            issue(
                ir,
                "FIGURE_ASSOCIATION_REVIEW",
                "独立图域待关联，可人工选择题目或图题。",
                [f["id"]],
                p["page_index"],
            )
    p["reading_order"] = [b["id"] for b in blocks]


def recover_monkey(ir: Json, p: Json, responses: Json) -> None:
    """Normalize optional geometry consistently without replacing primary content."""
    if "monkey" in responses:
        try:
            try:
                monkey: Any = ast.literal_eval(chat_content(responses["monkey"]))
            except (ValueError, SyntaxError) as exc:
                raise DemoError("MONKEY_PARSE_FAILED") from exc
            if not isinstance(monkey, list):
                raise DemoError("INVALID_CANDIDATE_WIRE_TYPE")
            alternatives = []
            for m in monkey:
                if (
                    not isinstance(m, dict)
                    or not isinstance(m.get("label"), str)
                    or not isinstance(m.get("bbox"), list)
                    or any(
                        not isinstance(v, int | float) or isinstance(v, bool) or not 0 <= v <= 1000
                        for v in m["bbox"]
                    )
                ):
                    raise DemoError("MONKEY_INVALID_GEOMETRY")
                alternatives.append(
                    {
                        "label": m["label"],
                        "raw_bbox": m["bbox"],
                        "raw_unit": "normalized_1000",
                        "bbox_pt": transform(
                            m["bbox"], p["width_pt"] / 1000, p["height_pt"] / 1000
                        ),
                    }
                )
            ir["provenance"].setdefault("monkey_geometry", {})[str(p["page_index"])] = alternatives
            issue(
                ir,
                "GEOMETRY_ALTERNATIVES",
                "Monkey几何仅作为可见候选，未覆盖主结果。",
                [],
                p["page_index"],
            )
        except (ValueError, SyntaxError, TypeError, KeyError, AttributeError, RecursionError):
            issue(
                ir,
                "MONKEY_CANDIDATE_REJECTED",
                "可选Monkey几何无法解析或校验，保留主结果；不自动重试。",
                [],
                p["page_index"],
            )
