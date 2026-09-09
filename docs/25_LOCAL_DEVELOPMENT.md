# macOS 本机调试与 FRP 接入

当前仓库包含领域配置、契约发现工具和测试骨架；Core API、桌面 UI、完整 PDF → DOCX 转换尚未实现。本文帮助启动开发和 Gate 调试，不代表转换产品已就绪。

## 环境

在仓库根目录执行（macOS zsh；这些 uv 命令也兼容 PowerShell）：

```sh
uv sync --locked
uv run python --version
uv run pytest
uv run ruff check .
uv run mypy .
uv run python scripts/validate_model_baseline.py
uv run python scripts/validate_task_catalog.py
```

Python 固定为 3.12 系列，依赖使用现有 `uv.lock`。不要从其他机器复制 `.venv`、`__pycache__` 或工具缓存。当前迁移已重建环境；原始样本、`tmp/` 探测证据和已有未提交工作保留。

## 已有 FRP 连接

用户已配置并连接 FRP，本项目无需安装或修改 frpc/frps。Mac visitor 的回环端口经 FRP/TLS 转发至 LLM 服务器的同名端口；公网中继只承载隧道，不是模型 API 地址。

| 本机配置 | 服务 | HTTP 路径 |
| --- | --- | --- |
| `MONKEY_BASE_URL=http://127.0.0.1:9000` | MonkeyOCRv2 | `/v1/models`、`/v1/chat/completions` |
| `OVIS_BASE_URL=http://127.0.0.1:8000` | OvisOCR2 | `/v1/models`、`/v1/chat/completions` |
| `PP_BASE_URL=http://127.0.0.1:8080` | PP-StructureV3 | `/layout-parsing`（既有契约） |

地址是 `127.0.0.1`。FRP 使用的是既有服务端口，不意味着目标统一网关 `8100` 已部署。生产 UI/Core 仍只面向网关，T0015–T0017 Gate 工具可以直连上述服务。

首次克隆且不存在 `.env.local` 时，将 `.env.example` 复制为 `.env.local`。已有文件请原位修改地址，保留凭据，避免覆盖。当前迁移已完成本地配置。

- 短变量名接收服务根 URL；工具自动为 Monkey/Ovis 补齐 `/v1`。
- 兼容 `MONKEY_OPENAI_BASE_URL`、`OVIS_OPENAI_BASE_URL`、`PP_STRUCTURE_BASE_URL`。
- 优先级：进程环境变量 > `.env.local`；同一来源中短名 > 兼容名。避免重复定义。
- 支持简单 `KEY=value` 及成对引号，不执行 shell 展开。
- API Key 使用既有 `MONKEY_API_KEY`、`OVIS_API_KEY`、`PADDLE_API_KEY`，仅保存在忽略配置中。
- `config/example.env` 的 `PDF2WORD_*` 是未来业务应用的配置示例，不是 Gate 工具的配置入口。

## Gate 调试

查看参数不会调用模型：

```sh
uv run python scripts/discover_model_contracts.py --help
```

准备好样本并需要真实推理时，在根目录执行，输出目录每次使用新名称：

```sh
uv run python scripts/discover_model_contracts.py --output-dir tmp/model-contract-discovery/local-run-001
```

原始样本不随公开仓库分发。当前本机保留了 `scripts/test-page.jpg`；新克隆需自行提供有权使用的样本，并通过 `--test-image /path/to/sample.jpg` 指定。

该命令会向模型服务器发送指定样本并运行契约探测，可能耗时数分钟。正常调试不要加 `--promote-artifacts`；该参数会更新契约和测试夹具，应在审查结果后按 Gate 流程使用。

端口监听只证明 visitor 可达；HTTP 成功只证明对应端点可用。真实识别质量、题图关系和黄金样本通过需另行验收。PP 没有 OpenAPI 不等于推理服务不可用，参见已有 ADR-007。发生鉴权/超时错误时保留状态码和错误类别，不打印凭据或文档正文。

## Agent 文档维护

根 `AGENTS.md` 保存日常操作、关键约束与按任务阅读索引。完整产品与模型规则迁入 [产品与模型约束](24_PRODUCT_AND_MODEL_RULES.md)，部署清单留在 [模型部署基线](23_MODEL_DEPLOYMENT_BASELINE_V1_1.md)。迁移没有改变模型权威、阶段顺序或数据契约。

依据 2026-09-09 核对的 [GPT-6 Astra 指导](https://developers.openai.com/api/docs/guides/latest-model)与 [AGENTS.md 指导](https://learn.chatgpt.com/docs/agent-configuration/agents-md)：明确授权范围、减少指令冲突，按变更风险验证，根规则与专题信息分层。Astra 用于开发协作，本项目不增加公网识别依赖。
