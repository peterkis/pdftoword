"""Escaped offline review and auditable manual overrides."""

from __future__ import annotations

import copy
import html
import re
from pathlib import Path

from .common import (
    DemoError,
    Json,
    block,
    box_valid,
    candidate,
    crop,
    issue,
    private_dir,
    relation,
    text_content,
    union,
    validate,
)
from .formula import to_omml, unrendered_math
from .structure import CAPTION, MATH, OPTION, QUESTION, image_content


def write_preview(job: Path, ir: Json, revision: str) -> None:
    """Write a safe, no-script offline source/reconstruction view."""
    private_dir(job / "review")
    chunks = [
        '<!doctype html><html lang="zh"><meta charset="utf-8">',
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "img-src 'self'; style-src 'unsafe-inline'\">",
        "<title>DEMO-001 本地对照</title><style>body{font:16px sans-serif;max-width:1200px;"
        "margin:auto}section{display:grid;grid-template-columns:1fr 1fr;gap:24px}"
        "img{max-width:100%}article{border:1px solid #aaa;padding:12px;white-space:pre-wrap}"
        "</style><h1>重建内容对照（不是 DOCX 渲染）</h1>",
        "<p>交互修正请启动本机 demo 服务；实际 Word 文件：",
        f'<a href="../{revision}.docx">{revision}.docx</a></p>',
    ]
    assets = {a["id"]: a for a in ir["assets"]}
    for p in ir["pages"]:
        source = ir["provenance"]["pages"][str(p["page_index"])]["image_path"]
        chunks.append(f'<section><div><img src="../{html.escape(source, quote=True)}"></div><div>')
        by_id = {b["id"]: b for b in p["blocks"]}
        for bid in p["reading_order"]:
            b = by_id[bid]
            chunks.append(
                "<article><b>" + html.escape(b["id"] + " / " + b["render_policy"]) + "</b><br>"
            )
            c = b["content"]
            if c["kind"] == "image":
                chunks.append(
                    '<img src="../' + html.escape(assets[c["asset_id"]]["path"], quote=True) + '">'
                )
            else:
                chunks.append(html.escape(c.get("plain_text", "")))
            chunks.append("</article>")
        chunks.append("</div></section>")
    chunks.append("<h2>待复核</h2>")
    for i in ir["issues"]:
        if i["status"] != "open":
            continue
        chunks.append("<p>" + html.escape(i["type"] + ": " + i["message"]) + "</p>")
    chunks.append("</html>")
    target = job / "review" / ("index.html" if revision == "auto" else "reviewed.html")
    target.write_text("".join(chunks), encoding="utf-8")
    target.chmod(0o600)


def apply_overrides(job: Path, automatic: Json, overrides: Json) -> Json:
    """Apply deterministic explicit edits to a copy; all operations require a reason."""
    ir = copy.deepcopy(automatic)
    operations = overrides.get("operations")
    if not isinstance(operations, list) or len(operations) > 200:
        raise DemoError("INVALID_OVERRIDES")
    ir["provenance"]["manual_overrides"] = copy.deepcopy(overrides)
    for n, op in enumerate(operations):
        if (
            not isinstance(op, dict)
            or not isinstance(op.get("reason"), str)
            or not op["reason"].strip()
        ):
            raise DemoError("OVERRIDE_REASON_REQUIRED")
        if op.get("action") == "resolve_issue":
            chosen = [i for i in ir["issues"] if i["id"] == op.get("issue_id")]
            if len(chosen) != 1:
                raise DemoError("ISSUE_NOT_FOUND")
            item = chosen[0]
            if (item["block_ids"] and op.get("block_id") not in item["block_ids"]) or op.get(
                "page_index", item["page_index"]
            ) != item["page_index"]:
                raise DemoError("ISSUE_NOT_FOUND")
            before_issue = copy.deepcopy(item)
            item["status"] = "resolved"
            ir["provenance"][f"manual-{n}"] = {
                "operation": op,
                "before_issue": before_issue,
                "after_issue": copy.deepcopy(item),
            }
            continue
        matches = [
            (p, b) for p in ir["pages"] for b in p["blocks"] if b["id"] == op.get("block_id")
        ]
        if len(matches) != 1:
            raise DemoError("BLOCK_NOT_FOUND")
        p, b = matches[0]
        action = op.get("action")
        old = copy.deepcopy(b)
        merged_before: Json | None = None
        if action in {"split", "merge", "move"}:
            affected = {b["id"]}
            if action == "merge":
                order = p["reading_order"]
                index = order.index(b["id"])
                if index + 1 < len(order):
                    affected.add(order[index + 1])
            ir["metadata"]["text_groups"] = [
                g
                for g in ir["metadata"].get("text_groups", [])
                if not any(bid in affected for row in g["rows"] for bid in row)
            ]
        if action in {"text", "candidate"}:
            if action == "candidate":
                choices = [
                    c
                    for c in b["content_candidates"]
                    if c["id"] == op.get("candidate_id")
                    and c["evidence"].get("review_selectable", True)
                ]
                if len(choices) != 1 or choices[0]["provider"] != "ovis_ocr2":
                    raise DemoError("CANDIDATE_NOT_FOUND")
                text = choices[0]["text"]
            else:
                text = op.get("text")
            if not isinstance(text, str) or len(text) > 50000:
                raise DemoError("INVALID_TEXT")
            c = candidate(
                f"{b['id']}-manual{n}",
                "manual_correction",
                text,
                {"reason": op["reason"], "supersedes": b["selected_candidate_id"]},
            )
            for previous in b["content_candidates"]:
                previous["selected"] = False
            b["content_candidates"].append(c)
            b.update(
                content=text_content(text), selected_candidate_id=c["id"], render_policy="editable"
            )
            replan_text(job, ir, p, b, text, old, n)
            ir["metadata"]["figure_groups"] = [
                g
                for g in ir["metadata"].get("figure_groups", [])
                if all(b["id"] not in pair.values() for pair in g["pairs"])
            ]
        elif action == "split":
            text = b["content"].get("plain_text")
            offset = op.get("offset")
            if (
                not isinstance(text, str)
                or not isinstance(offset, int)
                or not 0 < offset < len(text)
            ):
                raise DemoError("INVALID_SPLIT")
            if any(m.start() < offset < m.end() for m in MATH.finditer(text)):
                raise DemoError("SPLIT_INSIDE_FORMULA")
            old_parts = ir["metadata"].get("inline_parts", {}).get(b["id"])
            b["content"] = text_content(text[:offset])
            for prior in b["content_candidates"]:
                prior["evidence"]["review_selectable"] = False
                prior["evidence"]["selection_blocked_reason"] = (
                    "parent_candidate_exceeds_split_scope"
                )
            c = block(
                b["id"] + f"-manual{n}",
                p["page_index"],
                b["bbox"],
                text[offset:],
                "manual_correction",
                "question"
                if QUESTION.match(text[offset:])
                else "option"
                if OPTION.match(text[offset:])
                else "caption"
                if CAPTION.match(text[offset:])
                else "paragraph",
                evidence={
                    "parent": b["id"],
                    "reason": op["reason"],
                    "supersedes": old["selected_candidate_id"],
                },
            )
            if old_parts:
                left, right = split_parts(old_parts, offset)
                ir["metadata"]["inline_parts"][b["id"]] = left
                ir["metadata"]["inline_parts"][c["id"]] = right
                b["render_policy"] = c["render_policy"] = "hybrid"
            c["flags"].append("geometry_approximate_parent_bbox")
            b["flags"].append("geometry_approximate_parent_bbox")
            ir["provenance"][c["id"]] = {"parent_id": b["id"], "operation": op}
            p["blocks"].append(c)
            p["reading_order"].insert(p["reading_order"].index(b["id"]) + 1, c["id"])
            relation(ir, "derived_from", c["id"], b["id"], {"reason": op["reason"]})
        elif action == "merge":
            order = p["reading_order"]
            idx = order.index(b["id"])
            if idx + 1 == len(order):
                raise DemoError("NO_NEXT_BLOCK")
            other = next(x for x in p["blocks"] if x["id"] == order[idx + 1])
            if any(x["content"]["kind"] != "text" for x in (b, other)):
                raise DemoError("MERGE_REQUIRES_PLAIN_TEXT")
            merged_before = copy.deepcopy(other)
            b["content_candidates"].extend(copy.deepcopy(other["content_candidates"]))
            b["provenance_refs"] = list(
                dict.fromkeys([*b["provenance_refs"], *other["provenance_refs"]])
            )
            parts = ir["metadata"].get("inline_parts", {})
            if b["id"] in parts or other["id"] in parts:
                combined = parts.get(b["id"], [{"text": b["content"]["plain_text"]}])
                combined = [
                    *combined,
                    {"text": "\n"},
                    *parts.get(other["id"], [{"text": other["content"]["plain_text"]}]),
                ]
                ir["metadata"].setdefault("inline_parts", {})[b["id"]] = combined
                parts.pop(other["id"], None)
                b["render_policy"] = "hybrid"
            b["content"] = text_content(
                b["content"]["plain_text"] + "\n" + other["content"]["plain_text"]
            )
            b["bbox"] = union([b["bbox"], other["bbox"]])
            b["geometry_source"] = "manual_correction"
            for item in ir["issues"]:
                item["block_ids"] = list(
                    dict.fromkeys(
                        b["id"] if bid == other["id"] else bid for bid in item["block_ids"]
                    )
                )
            p["blocks"].remove(other)
            order.remove(other["id"])
            original_relations = copy.deepcopy(ir["relations"])
            for rel in ir["relations"]:
                for endpoint in ("from", "to"):
                    if rel[endpoint] == other["id"]:
                        rel[endpoint] = b["id"]
            by_id = {x["id"]: x for pg in ir["pages"] for x in pg["blocks"]}
            collapsed = [
                r
                for r in ir["relations"]
                if b["id"] in (r["from"], r["to"])
                and (
                    r["from"] == r["to"]
                    or (
                        r["type"] in {"references", "caption_of", "label_of"}
                        and not valid_relation(r["type"], by_id[r["from"]], by_id[r["to"]])
                    )
                )
            ]
            if collapsed:
                ir["provenance"][f"merge-collapsed-{n}"] = {
                    "before": original_relations,
                    "rejected": copy.deepcopy(collapsed),
                }
                issue(
                    ir,
                    "MERGED_RELATION_REVIEW",
                    "合并后关系折叠或端点类型不适用，原关系已记录待复核。",
                    [b["id"]],
                    p["page_index"],
                )
                ir["relations"] = [r for r in ir["relations"] if r not in collapsed]
            ir["metadata"]["figure_groups"] = [
                g
                for g in ir["metadata"].get("figure_groups", [])
                if all(other["id"] not in pair.values() for pair in g["pairs"])
            ]
        elif action == "move":
            order = p["reading_order"]
            idx = order.index(b["id"])
            delta = op.get("delta")
            if delta not in (-1, 1) or not 0 <= idx + delta < len(order):
                raise DemoError("INVALID_MOVE")
            order[idx], order[idx + delta] = order[idx + delta], order[idx]
            ir["metadata"]["figure_groups"] = [
                g
                for g in ir["metadata"].get("figure_groups", [])
                if all(b["id"] not in pair.values() for pair in g["pairs"])
            ]
        elif action in {"crop", "policy"}:
            policy = "preserve_image" if action == "crop" else op.get("policy", b["render_policy"])
            if policy not in {"editable", "preserve_image", "review_required"}:
                raise DemoError("INVALID_RENDER_POLICY")
            bbox = op.get("bbox", b["bbox"])
            if (
                not isinstance(bbox, list)
                or not box_valid(bbox)
                or not (
                    0 <= bbox[0] < bbox[2] <= p["width_pt"]
                    and 0 <= bbox[1] < bbox[3] <= p["height_pt"]
                )
            ):
                raise DemoError("INVALID_CROP")
            if action == "crop" or policy == "preserve_image":
                aid = crop(job, ir, p, bbox, f"{b['id']}-review{n}")
                b.update(content=image_content(aid), render_policy="preserve_image")
                ir["metadata"]["figure_groups"] = [
                    g
                    for g in ir["metadata"].get("figure_groups", [])
                    if all(b["id"] not in pair.values() for pair in g["pairs"])
                ]
                ir["metadata"]["text_groups"] = [
                    g
                    for g in ir["metadata"].get("text_groups", [])
                    if all(b["id"] not in row for row in g["rows"])
                ]
                ir["metadata"].get("inline_parts", {}).pop(b["id"], None)
                b["bbox"] = bbox
                b["geometry_source"] = "manual_correction"
            elif policy == "editable" and b["content"]["kind"] != "text":
                raise DemoError("EDITABLE_REQUIRES_TRANSCRIPTION")
            else:
                b["render_policy"] = policy
        elif action == "relation":
            target = op.get("target_id")
            kind = op.get("relation_type", "references")
            if (
                not isinstance(target, str)
                or kind not in {"references", "caption_of", "label_of"}
                or target not in {x["id"] for pg in ir["pages"] for x in pg["blocks"]}
            ):
                raise DemoError("INVALID_RELATION_TARGET")
            target_block = next(x for pg in ir["pages"] for x in pg["blocks"] if x["id"] == target)
            valid = valid_relation(kind, b, target_block)
            if not valid:
                raise DemoError("INVALID_RELATION_TARGET")
            ir["relations"] = [
                r for r in ir["relations"] if not (r["from"] == b["id"] and r["type"] == kind)
            ]
            relation(ir, kind, b["id"], target, {"reason": op["reason"], "manual": True})
        else:
            raise DemoError("UNKNOWN_OVERRIDE_ACTION")
        by_id = {x["id"]: x for pg in ir["pages"] for x in pg["blocks"]}
        invalid_relations = [
            r
            for r in ir["relations"]
            if b["id"] in (r["from"], r["to"])
            and r["type"] in {"references", "caption_of", "label_of"}
            and not valid_relation(r["type"], by_id[r["from"]], by_id[r["to"]])
        ]
        if invalid_relations:
            ir["provenance"][f"manual-invalid-relations-{n}"] = copy.deepcopy(invalid_relations)
            ir["relations"] = [r for r in ir["relations"] if r not in invalid_relations]
            issue(
                ir,
                "MANUAL_RELATION_REVIEW",
                "内容变更后关联端点不适用，原关系保留待复核。",
                [b["id"]],
                p["page_index"],
            )
        b["source_type"] = "manual_correction"
        ir["provenance"][f"manual-{n}"] = {
            "operation": op,
            "before": old,
            "after": copy.deepcopy(b),
        }
        if merged_before is not None:
            ir["provenance"][f"manual-{n}"]["merged_before"] = merged_before
        b["provenance_refs"].append(f"manual-{n}")
        if action in {"split", "merge"}:
            c = candidate(
                f"{b['id']}-manual{n}",
                "manual_correction",
                b["content"]["plain_text"],
                {
                    "reason": op["reason"],
                    "supersedes": (
                        [old["selected_candidate_id"], merged_before["selected_candidate_id"]]
                        if merged_before is not None
                        else b["selected_candidate_id"]
                    ),
                },
            )
            for previous in b["content_candidates"]:
                previous["selected"] = False
            b["content_candidates"].append(c)
            b["selected_candidate_id"] = c["id"]
        issue(
            ir,
            "MANUAL_CHANGE_REVIEW",
            "已记录人工操作；不自动宣称内容验收通过。",
            [b["id"]],
            p["page_index"],
        )
    ir["metrics"]["manual_override_count"] = len(operations)
    validate(ir)
    return ir


def split_parts(parts: list[Json], offset: int) -> tuple[list[Json], list[Json]]:
    """Split display parts at a text boundary without repeating formula images."""
    left: list[Json] = []
    right: list[Json] = []
    cursor = 0
    for part in parts:
        length = (
            len(part["source_text"] if "source_text" in part else part["text"])
            if "text" in part
            else len(part.get("source_text", "$" + part["latex"] + "$"))
        )
        if cursor + length <= offset:
            left.append(part)
        elif cursor >= offset:
            right.append(part)
        elif "text" in part:
            left.append({"text": part["text"][: offset - cursor]})
            right.append({"text": part["text"][offset - cursor :]})
        else:
            raise DemoError("SPLIT_INSIDE_FORMULA")
        cursor += length
    return left, right


def replan_text(job: Path, ir: Json, p: Json, b: Json, text: str, old: Json, n: int) -> None:
    """Rebuild explicitly reviewed formulas; reuse source images only when unsupported.

    Editable OMML needs no inferred image geometry. Unsupported unmatched syntax
    falls back to the original local block without guessing a formula coordinate.
    """
    mapping = ir["metadata"].setdefault("inline_parts", {})
    previous = mapping.pop(b["id"], [])
    if not unrendered_math(text):
        return
    matches = list(MATH.finditer(text))
    result: list[Json] = []
    cursor = 0
    supported = bool(matches)
    for m in matches:
        result.append({"text": text[cursor : m.start()]})
        candidates = [
            part
            for part in previous
            if "latex" in part and re.sub(r"\s+", "", part["latex"]) == re.sub(r"\s+", "", m[1])
        ]
        try:
            # This path runs only after an explicit, reason-bearing review operation.
            # Rebuild even if the automatic version deliberately retained an image.
            part = {**candidates[0]} if len(candidates) == 1 else {}
            part.update(latex=m[1], source_text=m[0], omml=to_omml(m[1]))
            result.append(part)
        except DemoError:
            if len(candidates) == 1:
                result.append({**candidates[0], "latex": m[1], "source_text": m[0]})
            else:
                supported = False
                break
        cursor = m.end()
    if supported:
        result.append({"text": text[cursor:]})
        mapping[b["id"]] = result
        b["render_policy"] = "hybrid"
    else:
        aid = crop(job, ir, p, old["bbox"], f"{b['id']}-candidate-fallback{n}")
        b.update(content=image_content(aid), render_policy="preserve_image")
        b["flags"].append("region_fallback")
        issue(
            ir,
            "ACCEPTED_CANDIDATE_FORMULA_REVIEW",
            "已接受候选；新公式无可靠坐标，原区域图片保留，候选文字仍可审校。",
            [b["id"]],
            p["page_index"],
        )


def valid_relation(kind: str, source: Json, target: Json) -> bool:
    """Validate the semantic endpoints of an authored or redirected relation."""
    if source["id"] == target["id"]:
        return False
    if kind == "references":
        return bool(source["type"] == "figure" and target["type"] == "question")
    allowed = {"caption", "paragraph"} if kind == "caption_of" else {"option", "paragraph"}
    return (
        source["type"] in allowed
        and source["content"]["kind"] == "text"
        and target["type"] == "figure"
        and source["page_index"] == target["page_index"]
    )
