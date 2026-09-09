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

当前用户确认模型服务无需 API Key，旧配置值未使用。`.env.local` 中 API Key 项为空且权限 0600；不发送 Authorization。如果部署以后增加鉴权，必须先撤销/轮换旧值，新密钥仅存在本机忽略配置。

完整运行 `t0015-mac-20260909T061855Z` 已通过：Monkey/Ovis verified，PP verified_from_openapi。PP OpenAPI 3.1.0 提供 `/health` 与 `/layout-parsing`；primary 为 JSON `POST /layout-parsing`，alternatives 为空。成功/错误响应和 fingerprint 见同次自动生成的 Spec 与 T0015 报告。

```sh
uv run python scripts/discover_model_contracts.py --help
export NO_PROXY=127.0.0.1,localhost
export no_proxy="$NO_PROXY"
RUN_ID="t0015-mac-$(date -u +%Y%m%dT%H%M%SZ)"
uv run python scripts/discover_model_contracts.py \
  --confirm-no-auth \
  --test-image "$T0015_TEST_IMAGE" \
  --output-dir "tmp/model-contract-discovery/$RUN_ID" \
  --promote-artifacts
```

请先将 `T0015_TEST_IMAGE` 设置为有权使用且允许发送至现有模型服务的本地图片。原始样本不随公开仓库分发；实际路径不写入报告。`--confirm-no-auth` 与 `--confirm-key-rotation` 二选一，不能省略安全确认。

命令执行一次串行契约探测，可能耗时数分钟；不会测试 JPG/PNG 质量差异、旋转、UVDoc、表格/公式专项，也不会实现生产 Adapter。需要再次运行时使用新的 run 目录，不能覆盖旧证据。

`--promote-artifacts` 仅在完整 ACCEPTED 时产生公开 Spec/Fixture，失败不推广。所有产物以相同 source_run_id、输入 SHA-256 和响应 fingerprint 关联；原始详细证据只在被忽略的 tmp 目录。详细行为见 [脚本说明](../scripts/README.md)。

## Agent 文档维护

根 `AGENTS.md` 保存日常操作、关键约束与按任务阅读索引。完整产品与模型规则迁入 [产品与模型约束](24_PRODUCT_AND_MODEL_RULES.md)，部署清单留在 [模型部署基线](23_MODEL_DEPLOYMENT_BASELINE_V1_1.md)。迁移没有改变模型权威、阶段顺序或数据契约。

依据 2026-09-09 核对的 [GPT-6 Astra 指导](https://developers.openai.com/api/docs/guides/latest-model)与 [AGENTS.md 指导](https://learn.chatgpt.com/docs/agent-configuration/agents-md)：明确授权范围、减少指令冲突，按变更风险验证，根规则与专题信息分层。Astra 用于开发协作，本项目不增加公网识别依赖。
