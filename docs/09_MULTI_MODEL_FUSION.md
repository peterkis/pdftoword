# 09. 多模型融合规范

## 1. 不覆盖原则

每次识别生成 `content_candidate`。Fusion Engine 负责选择，不允许 Adapter 直接覆盖已有结果。

## 2. 候选字段

- provider/model/version；
- 内容类型；
- text/latex/html/otsl；
- source bbox；
- 原始置信度；
- 系统评分；
- 输入资产；
- 证据；
- 风险标签；
- 是否被选择和理由。

## 3. 内容选择

### 原生文字

原生质量通过时直接选择。OCR/VLM 仅用于遗漏检测和审校提示。

### 栅格文字

PP-OCRv6_medium 为主。以下情况升级或复核：

- 平均置信度低；
- 关键字符风险；
- 不同预处理/裁剪结果差异大；
- Monkey 候选差异大；
- 视觉覆盖不足。

### 表格

PP-StructureV3 的网格和单元格坐标优先。Ovis/Monkey 可补内容和结构证据。低可信不强制可编辑。

### 公式

PP-FormulaNet 优先。Ovis/Monkey 作为候选。最终以渲染一致性决定 OMML 或图片。

## 4. 系统评分示例

```text
system_score =
  source_authority
+ engine_confidence_component
+ cross_model_agreement
+ geometry_validity
+ language_character_validity
+ coverage_score
+ render_similarity
- hallucination_risk
- overlap_penalty
- unsupported_transform_penalty
```

权重必须集中配置和版本化，不得散落代码。

## 5. 冲突类型

- `content_conflict`
- `geometry_conflict`
- `reading_order_conflict`
- `table_structure_conflict`
- `formula_conflict`
- `native_ocr_conflict`
- `candidate_missing`

## 6. 自动选择与审校

- 高分且无高风险：自动选择；
- 分数接近或关键内容冲突：创建 Issue；
- 所有候选低可信：图片降级；
- 人工选择：写入 `manual_correction` 候选并锁定。

## 7. 再处理

重新识别不能删除旧候选。新候选追加，并重新运行 Fusion；人工锁定结果默认不被自动替换。
