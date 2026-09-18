# AGENTS.md — PDF2Word Reconstruction Engine V2.1

## 项目定位

本项目目标：

构建一个可靠的 PDF → DOCX Document Reconstruction Engine。

目标不是简单 OCR 转 Word，而是：

PDF 内容理解
→ 几何分析
→ 文档结构恢复
→ 可编辑 DOCX 重建。

核心质量目标：

* 主要文字可编辑；
* 普通表格可编辑；
* 复杂表格明确降级；
* 题目与图片关系正确；
* 阅读顺序正确；
* 来源可追溯；
* 不静默修改原文。

当前阶段：

* S1：废弃，不再执行。
* S2-01～06：已完成。
* 当前进入 S2 Reconstruction 主线。
* 后续执行以 `~/Plans/PDF2Word_Development_Plan_v2.1` 为准。

---

# Agent 工作原则

## 1. 开始任何任务前

必须：

1. 查看：

```bash
git status --short --branch
```

2. 保留：

* 未提交修改；
* 本地样本；
* 历史证据；
* 临时实验结果。

禁止：

* git reset --hard；
* git clean；
* 覆盖用户修改。

---

## 2. 执行顺序

严格遵守：

理解计划
↓
读取相关代码
↓
制定最小修改范围
↓
实现
↓
测试
↓
报告

禁止：

* 看到问题立即重构整个系统；
* 跳过设计直接编码；
* 跨阶段提前实现未来功能。

---

# 当前架构原则

## PDF 输入层

保持：

* pdf-inspector：

  * 分类；
  * 原生文字；
  * 基础结构。

* PDFium：

  * 页面渲染；
  * 几何；
  * 对象边界。

有效原生 PDF：

优先于 OCR。

禁止默认：

整页 OCR 替代有效原生文字。

---

# Geometry Architecture

当前不是单一几何权威。

候选：

Native PDF Geometry

PP-Structure

MonkeyOCRv2

必须：

统一进入 Geometry Candidate。

禁止：

Monkey 只保存 provenance 而不参与选择。

最终：

GeometryArbitrator

负责：

* 覆盖率；
* 几何合理性；
* 阅读顺序；
* 模型一致性；
* 图文关系。

禁止伪造：

engine_confidence。

---

# Document Structure Architecture

不要重新造轮子。

优先复用：

* MinerU 文档结构思想；
* DocVortex MiddleJson；
* DocVortex Renderer。

优先复用：

* 标题；
* 段落；
* 列表；
* 表格；
* 公式；
* 图片说明；
* 阅读顺序。

但必须保留本项目特殊能力：

* 题目关系；
* 选项关系；
* 图题关系；
* 人工修订锁定；
* 来源追踪。

禁止：

直接复制上游内部模块作为长期依赖。

必须通过：

Adapter / Bridge。

---

# Layout IR

所有模型输出必须经过 Layout IR。

禁止：

模型 JSON

直接进入：

DOCX Writer。

Block 必须保留：

* geometry_source；
* content_candidates；
* selected_candidate_id；
* engine_confidence；
* system_confidence；
* render_policy；
* provenance。

---

# DOCX 输出原则

Word 输出目标：

可编辑优先。

允许：

自然分页。

禁止：

大量绝对定位文本框模拟 PDF。

优先：

* Paragraph；
* Table；
* OMML；
* Inline Figure。

复杂区域：

可以：

preserve_as_image。

但必须：

记录原因。

---

# 模型使用原则

新增模型前必须回答：

1. 当前模块为什么无法解决？
2. 新模型解决哪个明确问题？
3. 增加什么维护成本？
4. 是否影响已有契约？

禁止：

因为 DOCX 效果差，
直接增加 OCR 模型。

当前角色：

MonkeyOCRv2：

Geometry Candidate。

OvisOCR2：

内容复核。

PP：

文字、表格、公式候选。

TrOCR：

不属于当前生产链。

---

# MinerU / DocVortex 使用原则

优先评估：

公共结构能力。

包括：

* 文档层级；
* 表格结构；
* 公式转换；
* 图片关系；
* DOCX Renderer。

不要：

重新实现成熟能力。

但：

不能无条件信任上游结果。

必须：

保留：

source evidence。

---

# 数据安全

PDF 内容属于敏感数据。

禁止：

日志输出：

* 正文；
* 图片；
* API Key。

禁止：

默认调用公网模型。

模型服务：

必须经过配置网关。

---

# 开发规范

Python:

* 3.12；
* uv；
* 类型标注；
* docstring。

执行：

```bash
uv sync --locked
uv run pytest
uv run ruff check .
uv run mypy .
```

行为修改：

必须新增回归测试。

---

# 验证原则

区分：

代码测试

模型测试

真实推理

人工验收

测试通过：

不代表：

产品质量通过。

DOCX 验证必须包含：

* 内容；
* 阅读顺序；
* 来源；
* 题图关系；
* 图片完整性；
* 降级行为；
* 文件可打开。

---

# Agent 汇报格式

每次完成任务必须报告：

## 修改

文件：

原因：

## 验证

命令：

结果：

## 证据

日志：

测试：

产物：

## 风险

已知限制：

下一步建议：

禁止：

使用：

“完成”
“通过”

描述未经验证的产品效果。

---

# 当前开发重点

优先：

1. Geometry Candidate；
2. Geometry Arbitrator；
3. Layout IR；
4. Structure Bridge；
5. Flow Layout Planner；
6. Docx Renderer。

不要提前开发：

* 新 UI；
* 新模型；
* 大规模部署；
* 非核心优化。

目标：

把 PDF 页面可靠转换为结构化文档资产。
