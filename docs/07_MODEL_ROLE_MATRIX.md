# 07. 模型职责矩阵

**重要说明**：本文档已根据 V1.1 部署基线更新。旧模型名称（PP-DocLayout-M、PP-OCRv6 Small 等）已升级为新版本，详见 `docs/23_MODEL_DEPLOYMENT_BASELINE_V1_1.md`。

| 组件 | 默认任务 | 不承担 | 是否常驻 |
|---|---|---|---|
| pdf-inspector | 页面分类、原生文字、编码质量 | OCR、DOCX | 本地轻量 |
| pypdfium2 | 渲染、对象、图片、裁剪 | 语义识别 | 本地轻量 |
| PP-DocLayout_plus-L | 全局布局分析 | 最终文字、复杂页终局 | 可按需 |
| PP-DocBlockLayout | 块级布局 | 最终文字、复杂页终局 | 可按需 |
| MonkeyOCRv2-B-Parsing | 复杂页几何候选、阅读顺序候选 | 细粒度 OCR、表格/公式终局 | GPU 重模型 |
| PP-OCRv6_medium_det/rec | 栅格文字 OCR | 表格结构、公式 | 可常用 |
| RT-DETR-L + SLANeXt/SLANet_plus | 表格主解析 | 普通正文 | 按需 |
| PP-FormulaNet_plus-L | 公式主解析 | 化学结构图 | 按需 |
| OvisOCR2 | 高风险内容与完整性复核 | 复杂几何终局、默认全页 OCR | GPU 重模型 |

**历史名称对照**：
- PP-DocLayout-M → 已升级为 PP-DocLayout_plus-L / PP-DocBlockLayout
- PP-OCRv6 Small → 当前部署为 PP-OCRv6_medium
- PP-FormulaNet-S → 已升级为 PP-FormulaNet_plus-L

**几何权威关系（临时，见 ADR-006）**：
- PP 新版布局和 MonkeyOCRv2 **均为独立几何候选**
- 不预设永久唯一权威
- Gate B 完成后再决定终局 ADR

## 1. 默认调用策略

### fast

- 原生优先；
- PP-DocLayout_plus-L / PP-DocBlockLayout 快速布局；
- PP-OCRv6_medium 文字 OCR；
- Monkey 和 Ovis 默认关闭，只有阻断性异常才允许升级。

### balanced

- PP-DocLayout_plus-L / PP-DocBlockLayout 初筛；
- 复杂页调用 Monkey 几何候选；
- PP-OCRv6_medium 文字 OCR；
- 表格/公式专项；
- Ovis 只处理冲突复核。

### accurate

- 扫描复杂页使用 PP 和 Monkey 几何仲裁；
- 所有文字块由 PP-OCRv6_medium 复识别；
- 表格/公式专项；
- 高风险页调用 Ovis 复核；
- 开启回渲染 QA。

## 2. 模型替换原则

任何新模型必须通过 Adapter 接入，并在真实测试集影子运行。不能因为单一排行榜领先就替换所有组件。替换评估必须覆盖：

- 中文 CER；
- 英文 WER；
- 数字/单位；
- 公式；
- 表格；
- 阅读顺序；
- 块几何；
- 题图归属；
- 延迟和显存；
- 幻觉、遗漏和静默修正。
