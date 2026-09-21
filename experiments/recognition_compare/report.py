"""Static private evidence browser; no JavaScript, model access, or public source payloads."""

from __future__ import annotations

import html
import os
from pathlib import Path

from .common import ARMS, GROUPS, Json, offline, read, write


def aggregate(summary: Json) -> Json:
    """Four source-document macro averages, split by owner/agent reference evidence."""
    result: Json = {}
    for arm in ARMS:
        result[arm] = {}
        for evidence in ("owner", "agent"):
            sources: Json = {}
            for group, (source, _, _) in GROUPS.items():
                rows = [r for r in summary["rows"] if r["arm"] == arm and r["group"] == group]
                for row in rows:
                    for metric in row.get(evidence + "_cer_records", []):
                        totals = sources.setdefault(source, {"distance": 0, "reference_chars": 0})
                        totals["distance"] += metric["distance"]
                        totals["reference_chars"] += metric["reference_chars"]
            for values in sources.values():
                values["cer"] = (
                    values["distance"] / values["reference_chars"]
                    if values["reference_chars"]
                    else None
                )
            values = [s["cer"] for s in sources.values() if s["cer"] is not None]
            result[arm][evidence] = {
                "sources": sources,
                "macro_cer": sum(values) / len(values) if values else None,
                "represented_source_count": len(values),
                "required_source_count": 4,
                "complete_four_source_macro": len(values) == 4,
            }
    return result


def report(run: Path, evaluation: Path, output: Path) -> None:
    """Write a new local report that links original DOCX and all available render evidence."""
    with offline():
        summary = read(evaluation / "summary.json")
        audit_path = run / "word-audit/final/word-verification.json"
        audit = read(audit_path)["records"] if audit_path.exists() else []
        output.mkdir(parents=True, exist_ok=False)
        write(output / "aggregate.json", aggregate(summary))

        def link(path: Path, label: str) -> str:
            if not path.exists():
                return "NOT_RUN"
            rel = html.escape(os.path.relpath(path, output), quote=True)
            return f'<a href="{rel}">{html.escape(label)}</a>'

        parts = [
            '<!doctype html><meta charset="utf-8"><title>三路 PDF 与 Word 对比</title>',
            "<style>body{font:16px system-ui;margin:32px;color:#17202a;background:#f8fafc} "
            "table{border-collapse:collapse;width:100%}"
            "td,th{border:1px solid #ccd5df;padding:10px;vertical-align:top} "
            "img{width:100%;height:auto}a{color:#175ca4}"
            "details{margin:16px 0}pre{white-space:pre-wrap}</style>",
            "<h1>29 页三路识别与 Word 对比</h1><p>原始产物保留。用户确认项与辅助初标分别评分。"
            "无加权总分；模型与服务失败、未评分和未验证项均保留。</p>",
            "<p>状态：PARTIAL。原始识别、Word 实际打开、代理视觉检查和用户接受分开记录。"
            "各路线可评分覆盖不同，禁止直接用各自 CER 排名。"
            "Word 图为实际 Word 本地导出 PDF；辅助渲染器结果单独保留。</p>",
            "<p>"
            + link(run / "conclusion.md", "结论与限制")
            + " · "
            + link(run / "analysis/final/comparison.json", "识别能力：共同分母比较")
            + " · "
            + link(run / "analysis/final/metrics.csv", "识别能力明细 CSV")
            + " · "
            + link(audit_path, "Word 保真与可编辑性检查")
            + " · "
            + link(run / "visual-review.json", "逐页视觉缺陷与未验证项")
            + "</p>",
            "<p>"
            + link(evaluation / "summary.json", "完整评分汇总")
            + " · "
            + link(output / "aggregate.json", "按源文档宏平均及覆盖数")
            + "</p>",
        ]
        for group, (source, original_pages, _) in GROUPS.items():
            parts.append(f"<h2>{group} · {source} · 原物理页 {original_pages}</h2>")
            parts.append("<table><tr><th>路线</th><th>状态与对象清单</th><th>产物与证据</th></tr>")
            for arm in ARMS:
                row = next(r for r in summary["rows"] if r["group"] == group and r["arm"] == arm)
                artifacts = run / "runs" / group / arm / "artifacts"
                docx = artifacts / ("A.docx" if arm == "A" else "B.docx")
                inv = row.get("docx_inventory", {})
                word: Json = next((w for w in audit if w["group"] == group and w["arm"] == arm), {})
                links = [
                    link(docx, "原始 Word"),
                    link(run / "runs" / group / arm / "receipt.json", "运行收据"),
                    link(evaluation / group / f"{arm}-scoring.json", "识别逐项评分"),
                    link(evaluation / group / f"{arm}-word.json", "Word 对齐与对象证据"),
                    link(run / word.get("word_pdf", "missing.pdf"), "实际 Word PDF"),
                    link(
                        run / "word-audit/final" / f"{group}-{arm}-geometry.json",
                        "原页与输出页映射",
                    ),
                    link(run / "renders" / group / arm, "辅助渲染（存在字体环境差异）"),
                ]
                parts.append(
                    f"<tr><td>{arm} {ARMS[arm]}</td><td>{html.escape(str(row['status']))}"
                    f"<br>{html.escape(str(inv))}<br>Word: "
                    f"{html.escape(word.get('word_status', 'NOT_RUN'))}"
                    f"<br>源页 {len(original_pages)} → Word 页 {word.get('word_pages', '?')}"
                    "</td><td>" + "<br>".join(links) + "</td></tr>"
                )
            parts.append(
                "</table><details><summary>原页与各路线渲染图（输出页码不等于源页码）</summary>"
            )
            parts.append("<table><tr><th>原页</th><th>A</th><th>B</th><th>C</th></tr><tr>")
            collections = [run / "frozen" / group / "source-pages"] + [
                run / "word-render-pristine" / group / a for a in ARMS
            ]
            for folder in collections:
                pictures = sorted(
                    folder.glob("page-*.png"), key=lambda p: int(p.stem.split("-")[-1])
                )
                parts.append("<td>")
                if not pictures:
                    parts.append("NOT_RUN")
                for pic in pictures:
                    rel = html.escape(os.path.relpath(pic, output), quote=True)
                    parts.append(
                        f'<p>{html.escape(pic.stem)}</p><a href="{rel}">'
                        f'<img loading="lazy" src="{rel}"></a>'
                    )
                parts.append("</td>")
            parts.append("</tr></table></details>")
        (output / "index.html").write_text("\n".join(parts))
