# 从这里开始：PDF2Word Local V1.1 Agent 开发包

本包是 **PDF → Word 高保真流式重建应用** 的开发依据。它不是模型演示项目，也不是“PDF 转 Markdown”项目。

## 第一次交给 Coding Agent 时

先读 `AGENTS.md` 与 `README.md`，按根文件的任务表读取相关规范、当前阶段与 Ticket 依赖。
本机安装与 FRP 连接见 [本机调试](docs/25_LOCAL_DEVELOPMENT.md)。

## 推荐启动指令

将 `prompts/IMPLEMENTATION_START_PROMPT.md` 原样交给 Codex、Claude Code 或其他 Coding Agent。

## V1.1 的关键变化

**部署基线已升级**：详见 `docs/23_MODEL_DEPLOYMENT_BASELINE_V1_1.md`。

- PP 子模型已升级为新版本：
  - PP-DocLayout_plus-L / PP-DocBlockLayout（全局与块级布局）
  - PP-OCRv6_medium（文字检测与识别）
  - RT-DETR-L（有线/无线表格单元格检测）
  - SLANeXt_wired / SLANet_plus（表格结构）
  - PP-FormulaNet_plus-L（公式识别）
  - PP-LCNet_x1_0_doc_ori / UVDoc（按需预处理）
- `MonkeyOCRv2-B-Parsing` 作为复杂页面几何候选（**不预设永久唯一权威**，见 `adr/ADR-006-MULTI-CANDIDATE-GEOMETRY-UNTIL-GATE.md`）。
- `OvisOCR2` 作为高风险内容、公式、表格和整页完整性复核器，不承担复杂版面几何主职责。
- 本地应用只访问 GPU 模型机统一网关 `8100`（目标架构，尚未部署），不得直接依赖各模型的原始接口。

**Gate 任务（T0014-T0017）**：
- T0014 / P0-BASELINE-001：模型部署基线与架构文档对齐（本文档更新）
- T0015 / P0-GATE-001A：服务契约发现（冻结 HTTP 端点和 Schema）
- T0016 / P0-GATE-001B：JPG/PNG 与数学试卷回归（几何权威验证）
- T0017 / P0-GATE-001C：旋转、UVDoc、多栏、表格和公式专项能力矩阵

## 第一个开发目标

先完成 `P0` 和 `P1`：在不依赖任何 OCR/VLM 的情况下，把正常电子 PDF 转成结构正确、主要内容可编辑的 DOCX。模型链路从 `P2` 开始接入。
