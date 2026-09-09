# 产品、模型与输出约束 — V1.1

从根 AGENTS.md 分类迁入的规范，保留原有产品边界与模型职责。涉及识别、融合、Layout IR 或 DOCX 的任务必须阅读本文。当前 Mac 连接配置见 [本机调试](25_LOCAL_DEVELOPMENT.md)。

## 1. 最终任务

开发一个 PDF → DOCX 转换应用，生成：

- 内容准确、可追溯；
- 主要文字和普通表格可编辑；
- 标题、段落、题目、选项、图片、表格和公式关系正确；
- 图片稳定归属于对应题目或段落；
- 版式高度相似但允许 Word 自然重分页；
- 对低可信区域保留原图并生成审校项。

## 2. 不可违反的产品决策

1. 不要求 DOCX 与 PDF 页数相同。
2. 不要求逐行断行、字符坐标或分页完全一致。
3. 正常电子文字必须原生提取，禁止默认整页 OCR。
4. PDF 有图片不等于需要 OCR。几何图、实验装置图、化学结构图和普通配图默认整体保留。
5. 局部 OCR 只用于栅格文字、图片表格、公式、编码损坏或低质量隐藏文字层。
6. Markdown 只能作为可选导出，不得作为主中间格式。
7. 所有模型输出必须先归一化到 Layout IR 1.1。
8. 任何模型不得静默修正原文，尤其是试卷选项、数字、单位、英文拼写、公式和化学式。
9. 无法可靠重建时，必须降级为区域图片或人工复核，不得臆测。
10. 生产 UI 和业务 Core 不得直接调用任何 Provider 原始端口；生产目标只调用统一网关 `8100`。Gate 验证阶段（T0015-T0017）允许受控工具按配置直连 `9000`/`8000`/`8080`。`8102`/`8104`/`8106` 为历史端口，不是当前部署。

## 3. V1.1 模型职责，不得混用

### 3.1 非模型组件

- `pdf-inspector`：PDF/页面分类、原生文字、字体与编码质量。
- `pypdfium2 / PDFium`：页面渲染、图片/矢量对象、区域裁剪和坐标转换。

### 3.2 Paddle 专项模型

**当前部署基线（V1.1，详见 [部署基线](23_MODEL_DEPLOYMENT_BASELINE_V1_1.md)）**：

- `PP-DocLayout_plus-L`：全局布局分析。
- `PP-DocBlockLayout`：块级布局。
- `PP-OCRv6_medium_det/rec`：栅格文字检测、识别、行/框坐标和模型置信度。
- `RT-DETR-L_wired_table_cell_det`：有线表格单元格检测。
- `RT-DETR-L_wireless_table_cell_det`：无线表格单元格检测。
- `SLANeXt_wired`：有线表格结构。
- `SLANet_plus`：表格结构增强。
- `PP-FormulaNet_plus-L`：公式识别。
- `PP-LCNet_x1_0_doc_ori`：文档方向（按需）。
- `UVDoc`：文档去扭曲（按需）。

**历史名称对照**：
- PP-DocLayout-M → 已升级为 PP-DocLayout_plus-L / PP-DocBlockLayout
- PP-OCRv6 Small → 当前部署为 PP-OCRv6_medium
- PP-FormulaNet-S → 已升级为 PP-FormulaNet_plus-L

### 3.3 MonkeyOCRv2

**重要变更（ADR-006）**：在 T0016 / P0-GATE-001B 完成前，PP 新版布局和 MonkeyOCRv2 **均为独立候选**，不预设永久唯一权威。详见 [ADR-006](../adr/ADR-006-MULTI-CANDIDATE-GEOMETRY-UNTIL-GATE.md)。

`MonkeyOCRv2-B-Parsing` 是复杂页面的几何候选：

- 版面块类别；
- 块级坐标；
- 阅读顺序；
- 复杂扫描/拍照页面的结构候选。

它不是：

- 正常电子文字替代品；
- 细粒度文字行/字符坐标主引擎；
- 表格或公式最终权威；
- 题图归属最终判定器；
- Word 生成器。

MonkeyOCRv2 当前原始结果没有可直接等同于概率的块级置信度时，不得伪造 `engine_confidence`。系统可基于一致性、几何合理性和回渲染计算 `system_confidence`，两者必须分开。

**部署状态**：
- 对外模型名：`MonkeyOCRv2`
- 协议：OpenAI-compatible
- DFlash：服务端透明加速，不是客户端独立模型
- 客户端不得建立 `MonkeyOCRv2-DFlashAdapter`

### 3.4 OvisOCR2

OvisOCR2 只作为：

- 高风险内容完整性复核；
- 复杂公式、表格的第二候选；
- 整页 Markdown 序列化对照；
- PP-OCRv6 与 MonkeyOCRv2 内容冲突时的第三证据。

它不再承担复杂页面几何主职责，也不是默认每页调用的模型。

## 4. 权威优先级

### 4.1 文字内容

```text
有效原生 PDF 文字
  > PP-OCRv6 高置信度结果
  > 多模型一致结果
  > MonkeyOCRv2 单独内容
  > OvisOCR2 单独内容
```

原生文字只有在编码损坏、错位、重复、覆盖率异常或顺序严重错误并有证据时才可替换；必须记录 `supersedes`、原因和原候选。

### 4.2 几何与阅读顺序（临时，Gate B 完成前）

**重要**：此优先级为临时策略，详见 [ADR-006](../adr/ADR-006-MULTI-CANDIDATE-GEOMETRY-UNTIL-GATE.md)。

```text
有效 PDF 原生对象几何（最高优先）
  > Geometry Arbitration {
      PP-DocLayout_plus-L / PP-DocBlockLayout 候选,
      MonkeyOCRv2 布局候选
    }
  > 规则推断
```

**关键约束**：
- PP 新版布局和 MonkeyOCRv2 均为独立候选，不预设永久唯一权威
- 调用顺序不代表权威顺序
- 最终选择必须记录 `geometry_source`、`candidate_ids`、`selection_reason`、`engine_confidence`、`system_confidence`
- 单页回归结果不足以形成永久权威结论
- Gate B 完成后再决定是否形成新的终局 ADR

### 4.3 表格

```text
PP-StructureV3
  > OvisOCR2 复核候选
  > MonkeyOCRv2 候选
  > 区域图片降级
```

### 4.4 公式

```text
PP-FormulaNet
  > OvisOCR2 复核候选
  > MonkeyOCRv2 候选
  > 原公式图片
```

## 5. 架构约束

必须至少拆分：

```text
preflight
pdf_classifier
native_extractor
page_renderer
region_router
layout_fast_adapter
layout_complex_adapter
ocr_adapter
table_adapter
formula_adapter
content_reviewer_adapter
model_gateway_client
response_normalizer
fusion_engine
layout_ir
document_structure
question_figure_resolver
docx_planner
docx_builder
qa_engine
review_service
```

核心层不得 import 具体模型 SDK。外部能力必须实现协议：

```python
class LayoutEngine(Protocol):
    async def analyze(self, request: LayoutRequest) -> LayoutResult: ...

class TextOcrEngine(Protocol):
    async def recognize(self, request: TextOcrRequest) -> TextOcrResult: ...

class TableEngine(Protocol):
    async def parse(self, request: TableRequest) -> TableResult: ...

class FormulaEngine(Protocol):
    async def parse(self, request: FormulaRequest) -> FormulaResult: ...

class ContentReviewer(Protocol):
    async def review(self, request: ReviewRequest) -> ReviewResult: ...
```

## 6. 坐标和 Layout IR

- 标准坐标：PDF point，`1 pt = 1/72 inch`。
- 原点：左上角。
- `bbox = [x0, y0, x1, y1]`。
- 像素、归一化 `[0,1000]`、PDF point 和 Word EMU 的转换必须在边界 Adapter 内完成。
- 业务层不得混用坐标单位。
- 每个块必须保存 `geometry_source`、`content_candidates`、`selected_candidate_id`、`engine_confidence`、`system_confidence` 和 `render_policy`。

## 7. 模型网关规则

**当前部署状态**：
- **当前直接服务**：MonkeyOCRv2 :9000 / OvisOCR2 :8000 / PP-StructureV3 :8080
- 统一网关 8100 **尚未部署**（目标架构）
- 旧设计端口：8102 / 8104 / 8106（**不是当前部署事实**）

**规则**：
- 主应用只连接 `MODEL_GATEWAY_BASE_URL`，默认示例 `http://MODEL_SERVER_IP:8100`。
- 所有请求携带 `request_id`、`job_id`、`page_index`、`region_id`、任务类型和输入哈希。
- 请求必须有超时、重试上限、幂等键和取消语义。
- 模型调用失败不得导致已完成的原生解析结果丢失。
- GPU 重模型并发必须受网关控制；客户端不得自行并发轰炸模型机。
- 不得把 API Key 写入仓库、日志或 Layout IR。
- Gate 验证阶段（T0015-T0017）允许直连 9000/8000/8080，生产环境必须通过统一网关。

**详细部署基线**：见 [部署基线](23_MODEL_DEPLOYMENT_BASELINE_V1_1.md)。

## 8. Word 输出顺序

```text
Word 原生段落 / 表格 / OMML
  > 行内图片
  > 无边框布局表格
  > 浮动对象
  > 局部区域图片
  > 整页图片
```

默认禁止大量绝对定位文本框。右侧题图优先使用无边框 1×2 布局表格；选项图优先使用 1×N 或 2×2 布局表格。
