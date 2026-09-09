# AGENTS.md — PDF2Word Local V1.1

## 任务与协作

交付内容准确、来源可追溯、主要文字与普通表格可编辑、题图关系正确的 PDF → DOCX 应用。使用简体中文沟通。

- 根据用户意图完成已授权的工作，包括实现、适当验证和文档更新；常规可逆操作自行推进。
- 用户明确要求优先于仓库工作流和技能指南。不得自行更改产品边界、模型职责、数据契约或阶段顺序。
- 开始时检查 `git status --short --branch`，保留已有暂存、未提交修改、样本和原始证据；不得用 reset/clean 清理用户工作。
- 只在缺失信息影响正确性或操作具有不可逆后果时澄清；先完成不受影响的工作。若技能导致暂停，说明具体文件、规则及原因。
- 汇报结果、验证证据和剩余限制；区分离线测试、服务连通性、真实推理与阶段验收。

## 按任务阅读

先读 [README](README.md) 了解现状，再读当前 Ticket 及依赖；无需为每次小改动加载全部文档。

| 工作范围 | 必读入口 |
| --- | --- |
| 本机安装、FRP、调试 | [本机调试](docs/25_LOCAL_DEVELOPMENT.md) |
| 识别、融合、布局、DOCX | [产品与模型约束](docs/24_PRODUCT_AND_MODEL_RULES.md)，相关 `specs/` 契约 |
| 架构与模块依赖 | [技术架构](docs/03_TECHNICAL_ARCHITECTURE_V1_1.md) |
| 模型与 Gate | [部署基线](docs/23_MODEL_DEPLOYMENT_BASELINE_V1_1.md)、[ADR-006](adr/ADR-006-MULTI-CANDIDATE-GEOMETRY-UNTIL-GATE.md)、[网关契约](specs/model-gateway-contract.md) |
| Layout IR | [Layout IR](docs/10_LAYOUT_IR.md) |
| Ticket 实现与验收 | [阶段](phases/PHASES_OVERVIEW.md)、[任务](tasks/TICKETS.md)、[完成定义](tasks/DEFINITION_OF_DONE.md) |

这些链接中的专题规则仍是规范。遇到冲突先核对当前用户要求、已接受 ADR 和契约；历史报告只是当时证据，不代表本机状态。

## 始终成立的约束

- 正常电子文字原生提取，禁止默认整页 OCR。普通配图整体保留；仅对需要识别的区域 OCR。
- 不得静默修正原文，尤其选项、数字、单位、拼写、公式和化学式。不可靠时保留原图并创建审校项，不得猜测。
- 模型结果先归一化到 Layout IR 1.1；Markdown 仅可选导出。不得向 DOCX Builder 传模型原始 JSON。
- 坐标统一 PDF point、左上原点、`[x0, y0, x1, y1]`；单位转换在边界 Adapter 内完成。
- 块保留 `geometry_source`、`content_candidates`、`selected_candidate_id`、`engine_confidence`、`system_confidence`、`render_policy`。无模型概率时不得伪造置信度。
- 有效原生文字优先；替换必须保留原候选、`supersedes` 与原因。Gate B 前 PP 与 MonkeyOCRv2 均为独立几何候选，不预设唯一权威；OvisOCR2 按需复核。
- Word 允许自然重分页，优先原生段落、表格、OMML；默认禁止大量绝对定位文本框。
- 生产 UI/Core 只连接统一网关 `8100`（尚未部署）。T0015–T0017 Gate 工具允许按配置直连 Monkey `9000` / Ovis `8000` / PP `8080`。FRP 不改变这一边界。
- 核心层不 import 具体模型 SDK；外部能力实现 Protocol。调用保留请求/作业/页面/区域标识、任务类型及输入哈希，有超时、有限重试、幂等和取消；失败不得丢失原生解析结果。
- GPU 重模型并发由网关控制；Gate 请求保守串行。不得默认调用公网模型或外部 API。
- 文档和页面图片视为敏感数据。普通日志不含正文、图片、API Key；秘密仅存本地忽略配置。中间文件按作业隔离、可清理。
- 模型版本、镜像摘要、文件哈希可记录与锁定。`trust_remote_code=True` 仅限固定 commit/hash、禁止外网、最小权限的隔离容器。

## 开发与验证

Python 3.12 + uv；公共 Python 接口有类型标注和 docstring，TypeScript strict，JSON/日志/文件使用 UTF-8。业务规则集中在 Core，错误使用统一错误码，不吞异常。路径使用 `pathlib`，兼容中文与空格；当前开发机为 macOS，保留 Windows 兼容性。

```sh
uv sync --locked
uv run pytest
uv run ruff check .
uv run mypy .
uv run python scripts/validate_model_baseline.py
uv run python scripts/validate_task_catalog.py
```

Ticket 按“规范与依赖 → 测试/夹具 → 最小实现 → 单元/集成/黄金验证 → 文档、错误码、变更记录 → 证据”执行。纯文档和环境清理不造形式化测试；行为变更先补有意义的回归测试。检查通过后，无新变更或疑点不重复扩大测试。

DOCX 验证包含内容、阅读顺序、来源、题图归属、降级、图片完整性和可打开性。空测试目录、Mock 和历史报告不能代替真实模型或黄金验收；既有失败与本次新增失败分别报告。

维护依据：[OpenAI GPT-6 Astra 指导](https://developers.openai.com/api/docs/guides/latest-model)与[AGENTS.md 指导](https://learn.chatgpt.com/docs/agent-configuration/agents-md)（2026-09-09 核对）。详细产品规范迁至专题文档；Astra 是开发代理，不加入本产品识别链路。
