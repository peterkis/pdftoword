# 10. Layout IR 1.1

## 1. 作用

Layout IR 是 PDF 解析、模型识别、结构恢复、DOCX、QA 和人工审校之间的唯一稳定契约。Markdown 不是主中间格式。

## 2. 坐标

- 单位：PDF point；
- 原点：左上；
- bbox：`[x0, y0, x1, y1]`；
- 旋转在 Adapter 内归一化；
- Word EMU 只在 DOCX Builder 内产生。

## 3. Block 关键字段

```json
{
  "id": "blk-p3-q12-stem",
  "type": "paragraph",
  "page_index": 2,
  "bbox": [72, 110, 510, 180],
  "geometry_source": "monkeyocrv2",
  "source_type": "fused",
  "engine_confidence": null,
  "system_confidence": 0.94,
  "content_candidates": [],
  "selected_candidate_id": "cand-ppocr-1",
  "render_policy": "editable",
  "children": [],
  "relations": ["rel-anchor-1"]
}
```

## 4. 置信度分离

- `engine_confidence`：模型原始值，允许 `null`；
- `system_confidence`：本系统综合评分；
- 不得将两者混写。

## 5. 来源

主要来源：

```text
native_pdf
pdf_image
pdf_vector_render
pp_doclayout
pp_ocr_v6
pp_structure
pp_formula
monkeyocrv2
ovis_ocr2
manual_correction
fused
inferred
```

## 6. 关系

- `contains`
- `precedes`
- `follows`
- `anchored_to`
- `caption_of`
- `continuation_of`
- `supersedes`
- `derived_from`
- `same_content_as`
- `fallback_for`
- `references`

## 7. Render Policy

- `editable`
- `preserve_image`
- `hybrid`
- `review_required`

DOCX Builder 只根据 IR 和 Render Policy 输出，不自行重新调用模型或改变候选。

## 8. 版本迁移

V1.0 的单一 `confidence` 在 V1.1 中拆分；新增 Monkey 来源、候选数组和几何来源。迁移规则见 `docs/21_MIGRATION_V1_0_TO_V1_1.md`。

完整 Schema：`specs/layout-ir.schema.json`。
