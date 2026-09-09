# 03. 技术架构 V1.1

## 1. 总体分层

```text
┌───────────────────────────────────────────────────────────┐
│ Desktop UI / CLI                                          │
│ Tauri 2 + React + TypeScript                              │
└──────────────────────┬────────────────────────────────────┘
                       │ local IPC / HTTP
┌──────────────────────▼────────────────────────────────────┐
│ Python Core                                               │
│ Job Engine / Routing / Fusion / Layout IR / DOCX / QA     │
├───────────────────────────────────────────────────────────┤
│ Native Layer                                              │
│ pdf-inspector + pypdfium2 / PDFium                        │
├───────────────────────────────────────────────────────────┤
│ Model Gateway Client                                      │
│ timeout / retry / idempotency / cache / cancellation      │
└──────────────────────┬────────────────────────────────────┘
                       │ HTTPS + API Key
┌──────────────────────▼────────────────────────────────────┐
│ GPU Model Gateway :8100（目标架构，尚未部署）              │
│ auth / queue / routing / normalized response / metrics    │
├───────────────────┬───────────────────┬───────────────────┤
│ Paddle :8080      │ OvisOCR2 :8000   │ Monkey :9000      │
│ layout/OCR/table/ │ content reviewer │ complex geometry  │
│ formula           │                  │ candidate         │
└───────────────────┴───────────────────┴───────────────────┘
```

**端口说明**：
- **当前部署**：Paddle :8080 / OvisOCR2 :8000 / Monkey :9000
- **目标架构**：统一网关 :8100（尚未部署）
- **历史设计**：8102/8104/8106（不是当前部署事实，仅在 `CHANGELOG.md` 或已标记 `Historical/Superseded` 的 ADR 中出现）

## 2. 本地核心组件

### 2.1 Preflight

校验 PDF、生成哈希、读取页数/尺寸/旋转/加密状态，创建只读输入副本和作业目录。

### 2.2 Native Extractor

从 PDF 获取文字、字体、样式、坐标、图片和矢量信息；计算原生文字质量和视觉覆盖。

### 2.3 Region Router

基于页面类型、原生覆盖、图像覆盖、版面复杂度和模型置信度，决定每个区域的处理引擎。

### 2.4 Model Gateway Client

只实现统一业务任务，不暴露具体推理框架：

- `paddle.layout_global`
- `paddle.layout_block`
- `paddle.text_ocr`
- `paddle.table_parse`
- `paddle.formula_parse`
- `monkey.layout_complex`
- `ovis.content_review`

### 2.5 Response Normalizer

将 Paddle、MonkeyOCRv2、OvisOCR2 输出转成统一候选、几何和证据结构。

### 2.6 Fusion Engine

根据来源权威、模型置信度、多模型一致性、几何合理性和回渲染结果选择最终内容。

### 2.7 Layout IR 1.1

核心数据层。DOCX、审校、QA 和可选知识库导出均只读取 IR。

### 2.8 Structure Engine

恢复章节、题目、选项、题图、图题、表格、公式和跨页关系。

### 2.9 DOCX Planner / Builder

Planner 决定流式段落、表格、图片或局部降级；Builder 生成 OOXML/OMML。

### 2.10 QA / Review

执行数据、结构、DOCX 包、回渲染和人工审校。

## 3. 模型端组件

### 3.1 Paddle 服务 `8080`（当前部署）

同一服务封装多个专项模型，使用 LRU 或任务级加载策略，防止显存长期堆积。

**当前端口**：8080

### 3.2 MonkeyOCRv2 `9000`（当前部署）

服务 `MonkeyOCRv2-B-Parsing`。输入页面或复杂区域图像，返回布局或端到端结构。

**当前端口**：9000

**重要**：MonkeyOCRv2 为几何候选，不预设永久唯一权威（见 ADR-006）。

### 3.3 OvisOCR2 `8000`（当前部署）

高风险内容复核。默认不与 Monkey 重模型高并发运行；由网关或部署 profile 控制。

**当前端口**：8000

### 3.4 统一网关 `8100`（目标架构，尚未部署）

- API Key；
- 来源 IP 限制；
- 最大上传尺寸；
- 幂等；
- 单 GPU 队列；
- 任务级超时；
- 统一错误；
- 统一结果 Schema；
- 模型版本和哈希回传。

## 4. 三类 PDF 数据流

### 4.1 纯电子

```text
Preflight → Native Extractor → 简单阅读顺序 → Layout IR → DOCX
                         └─ 复杂时可调用 layout_global / layout_complex
```

### 4.2 混合

```text
原生文字 + 页面对象
   ↓
PP-DocLayout_plus-L / PP-DocBlockLayout 快速分区
   ↓
普通配图保留 / 栅格文字 OCR / 表格 / 公式 / 复杂组合 Monkey 几何候选
   ↓
融合与去重 → 结构 → DOCX
```

### 4.3 扫描

快速模式：

```text
PP-DocLayout_plus-L / PP-DocBlockLayout → 专项 OCR/表格/公式 → 融合
```

高精度模式：

```text
PP 与 Monkey 几何仲裁
   ↓
文字块 PP-OCRv6_medium 精识别
表格块 PP-StructureV3
公式块 PP-FormulaNet_plus-L
图片块保留
   ↓
Ovis 仅在冲突或遗漏风险时复核
```

## 5. 故障和降级

- 模型网关不可达：纯电子作业继续；需要模型的页面进入 `waiting_model` 或失败可重试。
- Monkey 不可用：回退 PP-DocLayout_plus-L / PP-DocBlockLayout + 规则，复杂页标记复核。
- Ovis 不可用：不阻断主流程，只减少复核证据。
- 表格/公式模型失败：区域图片降级。
- DOCX 生成失败：保留 IR、资产和错误报告，支持修复后重建。

## 6. 不允许的耦合

- UI 直接调用模型机；
- DOCX Builder 直接读取模型原始 JSON；
- 模型 Adapter 直接修改最终结构；
- 提示词包含业务硬编码样本文字；
- 业务层依赖具体 vLLM、Paddle 或 Transformers 对象。