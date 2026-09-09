# scripts — T0015 契约发现与验证

`scripts/model_contract_discovery.py` 是唯一发现实现：配置、URL、受限 HTTP、身份检查、OpenAPI、PP 有界回退、Wire 分析、脱敏、来源关联、Promotion 与运行状态都在此模块。

`scripts/discover_model_contracts.py` 只处理参数、调用 core、打印非敏感摘要及退出码。不得在 CLI 再实现 `discover_*` / `run_full_discovery`。

## 真实运行

在仓库根目录执行，先确认图片有权使用、服务无需鉴权或旧密钥已撤销。当前用户已确认服务无需 API Key，旧值未使用，本机配置已清空旧值。

```sh
export NO_PROXY=127.0.0.1,localhost
export no_proxy="$NO_PROXY"
RUN_ID="t0015-mac-$(date -u +%Y%m%dT%H%M%SZ)"
uv run python scripts/discover_model_contracts.py \
  --confirm-no-auth \
  --test-image "$T0015_TEST_IMAGE" \
  --output-dir "tmp/model-contract-discovery/$RUN_ID" \
  --promote-artifacts
```

`T0015_TEST_IMAGE` 由操作人设置为本地自有 JPEG 或 PNG 路径；不要将实际路径写入仓库。`--confirm-no-auth` 是操作人对无需 API Key 的明确确认，不是探测或绕过鉴权。若服务以后改为需要密钥，先撤销旧值，再使用 `--confirm-key-rotation`；新值仅放 0600 的 `.env.local`。

每次先查询两个 `/v1/models`，身份不符即停止所有推理。之后串行执行两个 chat、各一次错误 model 请求、PP OpenAPI 与成功/三类错误请求。只验证 HTTP 契约，不评估识别质量。无重试、无重定向、不修改 FRP。Monkey max_tokens=2048、Ovis max_tokens=8192，实际参数保存在运行契约；避免将 Monkey 全部上下文分配给输出。

PP OpenAPI 完整时只验证文档化上传候选，不对 Path/Transport 做无依据的笛卡尔扩展。不可用或不完整时才执行 ADR-007 的四种有限组合。文档化成功请求与 Schema 不一致时为 `CONTRACT_RUNTIME_DIVERGENCE`，不得强行选择旧端点。

## 证据与 Promotion

运行目录必须位于忽略的 `tmp/model-contract-discovery/`，非空目录禁止复用。

- `*.raw.redacted.json`：本地详细证据（不提交），含原始 HTTP 字节摘要、脱敏结果摘要和请求元数据；文档内容只保留类型/长度/摘要。
- `discovered-model-contracts.json`：本次最终状态与契约；失败也写入。
- `run-metadata.json`、`run-results.sha256`：执行环境、输入摘要和结果完整性校验。
- fingerprint 算法：单响应采用原始 HTTP response bytes 的 SHA-256；多个来源的汇总摘要采用其摘要列表的 canonical JSON SHA-256，列表同时保留。

仅完整真实运行 ACCEPTED 时可自动生成公开 Spec 及 8 个 observed/provenance Fixture。Promotion 先验证全部证据、结果摘要和来源，再写入公开产物。MockTransport 运行只生成 synthetic_example，不能称为 verified 实测。

旧 `*.schema.json` / `*.normalized.json` 等静态夹具是 `synthetic_example`，用于示例与负例，不能冻结当前契约。

## 离线验证

```sh
uv sync --locked
uv run pytest
uv run ruff check .
uv run mypy .
uv run python scripts/validate_task_catalog.py
uv run python scripts/validate_model_baseline.py
```

默认 pytest 禁止真实 HTTPTransport，只允许 MockTransport。`smoke_models.py` 是历史手工工具，不纳入本轮 Gate；新流程统一使用上述 CLI。
