# T0015 / P0-GATE-001A — Mac + FRP 真实契约证据

最终建议状态：**ACCEPTED（HTTP 契约验收）**。本报告以当前一次真实运行及其自动产物为依据。

## 分支、范围与安全前提

- 当前分支：`fix/t0015-reproducible-contract-evidence-macos`。
- 起始公开提交 / 运行 HEAD：`a5f1fd713715e2304432ac3cc9d27544f849e904`。
- 本轮不修改 main；未执行 commit、push、创建 PR 或 merge。通过全部验收后明确暂存 T0015 文件。
- 用户确认三个 LLM 服务无需 API Key，此前填入的值未用于鉴权；旧配置项已清空。未进行、也未声称进行了服务器密钥轮换。
- 当前 authentication_mode=none，请求不携带 Authorization；`.env.local` 未跟踪，权限 0600。
- FRP 已由用户配置并恢复，本轮不修改 frpc/frps，不记录或访问中继/模型机远端地址。
- 图片为用户已确认有权使用并允许发送的本机样本；不提交图片、正文或 Base64。

## 接入和运行身份

- 三个 visitor 端口 `127.0.0.1:9000/8000/8080` TCP 已连通；本轮各服务成功 HTTP 请求均返回 200。
- `access_mode=frp_stcp_loopback`，`NO_PROXY` 与 `no_proxy` 均包含 `127.0.0.1,localhost`。
- run_id：`t0015-mac-20260909T061855Z`。
- started_at：`2026-09-09T06:18:55.452748+00:00`；completed_at：`2026-09-09T06:19:08.469757+00:00`。
- 环境：`macOS`；Python `3.12.13`；httpx `0.28.1`。
- 输入 SHA-256：`fe608629ae8af60890684c77437b3d62facd3a0c27b9fa019692890f96cbcf52`。
- 输入：`image/jpeg`，94410 bytes。
- core 源文件 SHA-256：`f1ccda2cc9cffd7565b232474d26948a91ee496d5ed609086ca171e2c20d05da`；与本轮执行代码一致。
- 未提交代码通过 tool_source_sha256 标识；运行 HEAD 不冒充已包含本轮修改的 commit。

## PP OpenAPI 与最终选择

- OpenAPI：可用，`3.1.0`；info.title=`FastAPI`，info.version=`0.1.0`。
- 文档化 paths：`GET /health`、`POST /layout-parsing`。
- primary：`POST /layout-parsing`，operationId=`infer`，Transport=`json_base64`，Content-Type=`application/json`。
- 文件字段：`file`；Schema required 为 `[file]`。`fileType` 允许 0/1/null，图片探测显式发送 1。query 参数为空。
- Schema 文档化成功响应 200、错误响应 422/500；完整解析后的 Schema 见 `pp.openapi.normalized.json`。
- 实际 JSON 成功请求及成功响应均通过文档化 Schema 验证。
- compatibility alternatives：`[]`。OpenAPI 未提供 multipart 或 `/PP-StructureV3`，未额外探测未文档化候选；不宣称它们一定不可用。
- contract_source=`openapi_with_runtime_verification`；contract_status=`verified_from_openapi`。
- OpenAPI HTTP 字节 SHA-256：`d8fa7c68be55a2ff12e5d01b47e60c15535170318d51814985cf542df3f1a885`。
- 未触发 ADR-007 回退；子模型独立端点未在 T0015 测试。

## Monkey 与 Ovis Wire

| 服务 | 实际 model ID | Wire / serialization | 结果 |
| --- | --- | --- | --- |
| Monkey | `MonkeyOCRv2` | `string` / `python_literal_list` | strict_json=false；ast.literal_eval；array<object>；38 blocks；normalized_1000 |
| Ovis | `ovis-ocr2` | `string` / `markdown` | 内容长度 1171；仅记录长度和 SHA-256，不记录正文 |

- Monkey 坐标单位为已声明的模型契约，本轮检查所有块的范围/合法性，不以“数值小于 1000”独立推断单位，不评价布局质量。
- Monkey 探测 max_tokens=2048；Ovis max_tokens=8192；实际 finish_reason 均为 stop。
- 两个模型的 `/v1/models` 都先于任何推理；错误模型 ID 请求均返回 HTTP 404 / application/json。DFlash 对客户端透明。

| 服务 | system_fingerprint | OpenAPI / 应用版本 | 权重 revision |
| --- | --- | --- | --- |
| monkey | `vllm-0.26.0-7a07b93c` | 3.1.0 / 0.1.0 | 未暴露 |
| ovis | `vllm-0.26.0-1a9933c7` | 3.1.0 / 0.1.0 | 未暴露 |
| PP | 未暴露（null） | 3.1.0 / 0.1.0 | 未暴露 |

这些是实际服务指纹/应用版本，不等同于模型权重或容器镜像锁定。未暴露字段保持 unknown/null，不推测。

## 逐请求证据

所有请求串行、无重试，redirect_count 均为 0。GET 无请求 Content-Type，POST 均为 application/json，所有响应均为 application/json。

| 请求 | 端口 / Path | HTTP | duration_ms | 请求 / 响应 Content-Type |
| --- | --- | ---: | ---: | --- |
| monkey.models | `GET 9000/v1/models` | 200 | 104.064 | — / application/json |
| ovis.models | `GET 8000/v1/models` | 200 | 109.636 | — / application/json |
| monkey.openapi | `GET 9000/openapi.json` | 200 | 390.092 | — / application/json |
| monkey.chat | `POST 9000/v1/chat/completions` | 200 | 1960.491 | application/json / application/json |
| monkey.error | `POST 9000/v1/chat/completions` | 404 | 56.297 | application/json / application/json |
| ovis.openapi | `GET 8000/openapi.json` | 200 | 435.165 | — / application/json |
| ovis.chat | `POST 8000/v1/chat/completions` | 200 | 3375.202 | application/json / application/json |
| ovis.error | `POST 8000/v1/chat/completions` | 404 | 47.929 | application/json / application/json |
| pp.openapi | `GET 8080/openapi.json` | 200 | 104.406 | — / application/json |
| pp.probe-0 | `POST 8080/layout-parsing` | 200 | 6091.264 | application/json / application/json |
| pp.error-missing_file | `POST 8080/layout-parsing` | 422 | 45.721 | application/json / application/json |
| pp.error-invalid_file_type | `POST 8080/layout-parsing` | 422 | 81.057 | application/json / application/json |
| pp.error-invalid_file | `POST 8080/layout-parsing` | 422 | 48.284 | application/json / application/json |

每个 request_id、started_at、响应原始字节 SHA-256 均保存在 Spec 的 requests 与 run.provenance.json，详细本地证据具有相同 metadata。

## PP 三类无害错误

| 类型 | HTTP status | body.errorCode | errorMsg Wire Type | Content-Type | 响应 SHA-256 |
| --- | ---: | ---: | --- | --- | --- |
| missing_file | 422 | 422 | string | application/json | `f75796384d5aaff37c5c38d9ec2cf68afd6087be3ab2d307153b0f3fc7611730` |
| invalid_file_type | 422 | 422 | string | application/json | `2c125bbece0e70549ef2df2e07159c9002c2b088aea9ca290c26b78614d580dc` |
| invalid_file | 422 | 422 | string | application/json | `b494c239445d1c398bb25037ce5fbc6c3547dda9e46c5fdda8ddee4b7cfae44a` |

本次 HTTP status 与 body.errorCode 恰好均为 422；工具分别记录，离线测试覆盖二者不相等及字段缺失的情况。

## 自动生成 Artifact 与 provenance

以下 8 个 Artifact 与 Spec 均来自 `t0015-mac-20260909T061855Z`，fixture_kind=`sanitized_observed_wire`，generated_by=`scripts/model_contract_discovery.py`；每个都含 generated_at、input_file_sha256、access_mode 和 source_response_fingerprint(s)。

| Fixture | 来源摘要数量 |
| --- | ---: |
| `monkey.chat.observed.json` | 2 |
| `monkey.models.observed.json` | 1 |
| `ovis.chat.observed.json` | 2 |
| `ovis.models.observed.json` | 1 |
| `pp.errors.observed.json` | 3 |
| `pp.openapi.normalized.json` | 1 |
| `pp.success.observed.pruned.json` | 1 |
| `run.provenance.json` | 11 |

- 单响应 fingerprint 是原始 HTTP response bytes 的 SHA-256；多响应产物同时保存来源摘要列表，并对 canonical JSON 列表计算汇总 SHA-256。
- 原始 HTTP 字节只用于内存哈希；本地 `*.raw.redacted.json` 保存脱敏事实/结构，另有 redacted_response_fingerprint，避免泄漏正文。
- Promotion 验证完整请求集、脱敏文件摘要、run-results.sha256 后一次生成全部产物。已交叉核对 13 个请求、8 个 Fixture 与当前 core 源哈希。
- 旧 7 个静态夹具保留为 `synthetic_example` / synthetic，仅作历史示例和负例，不能作为当前 verified 证据。
- Spec：schema_version=2.0，execution_mode=live，overall_status=ACCEPTED；monkey/ovis=verified，paddle=verified_from_openapi。

## 全仓质量门禁

| 检查 | 初始基线 | 当前结果 |
| --- | --- | --- |
| uv sync --locked | PASS | PASS |
| pytest | 104 PASS | 147 PASS |
| ruff check . | 6 错误 | PASS，0 错误 |
| mypy . | 17 错误 | PASS，0 错误 |
| validate_task_catalog.py | PASS | PASS，97 个 Ticket 一致 |
| validate_model_baseline.py | PASS | PASS |

测试直接调用 core；MockTransport 模拟正常/错误/身份不匹配/断连，默认 pytest 禁止真实 HTTPTransport。新增真实产物来源一致性离线校验。未通过 ignore、关闭 strict 或删除有意义验证来清零错误；新增 types-jsonschema 类型存根。

## 敏感信息与 Git 审查

- `.env.local`：0600、未跟踪；没有新 API Key，旧值未使用且已从本地配置清空。
- 暂存范围只包含 T0015 源码、测试、规范、报告、脱敏 Artifact 与依赖锁文件。
- 扫描旧凭据、远端拓扑地址、token/Authorization 实值、Base64、原始图片、OCR 正文及本机绝对用户路径；未发现泄漏。
- tmp/ 和测试图片均被 Git 忽略，保留本地；不暂存原始响应或 FRP 配置。
- 未执行 T0016/T0017、质量对比、专项能力测试、生产 Adapter、统一网关或几何权威 ADR 变更。
- 本轮未 commit/push/PR/merge。建议单一提交：`fix(t0015): add reproducible Mac FRP contract evidence`；之后由用户授权推送 feature branch、创建 Draft PR、审查后合并。

## Historical：先前尝试与旧报告

- 2026-08-29 Windows 报告不能证明当前契约；旧 Spec/Fixture 曾错误记录 Monkey 数组/像素坐标及 PP 无 OpenAPI。
- `t0015-mac-20260909T061213Z`：visitor 端口未监听，两个 GET ConnectError，没有发送图片；旧代码误标身份不符，已补测试修正，原失败证据保持不变。
- `t0015-mac-20260909T061721Z`：Monkey chat HTTP 400，Ovis/PP 验证通过；未推广。观察到 Monkey max_model_len=8192，而请求 max_tokens=8192；减至 2048 后完整新 run 成功。不引用或打印错误正文。
- 当前采用 `t0015-mac-20260909T061855Z` 唯一完整成功运行，未拼接旧请求与新请求伪造一次成功。

## 新增与修改文件

- `.env.example`
- `CHANGELOG.md`
- `VALIDATION_REPORT.md`
- `config/default.yaml`
- `docs/23_MODEL_DEPLOYMENT_BASELINE_V1_1.md`
- `docs/25_LOCAL_DEVELOPMENT.md`
- `pyproject.toml`
- `scripts/README.md`
- `scripts/discover_model_contracts.py`
- `scripts/model_contract_discovery.py`
- `specs/discovered-model-contracts.json`
- `specs/error-codes.md`
- `specs/model-gateway-contract.md`
- `tasks/reports/T0015_REPORT.md`
- `tests/conftest.py`
- `tests/fixtures/model_contracts/monkey.chat.observed.json`
- `tests/fixtures/model_contracts/monkey.chat.schema.json`
- `tests/fixtures/model_contracts/monkey.models.normalized.json`
- `tests/fixtures/model_contracts/monkey.models.observed.json`
- `tests/fixtures/model_contracts/ovis.chat.observed.json`
- `tests/fixtures/model_contracts/ovis.chat.schema.json`
- `tests/fixtures/model_contracts/ovis.models.normalized.json`
- `tests/fixtures/model_contracts/ovis.models.observed.json`
- `tests/fixtures/model_contracts/pp.error.normalized.json`
- `tests/fixtures/model_contracts/pp.errors.observed.json`
- `tests/fixtures/model_contracts/pp.openapi.normalized.json`
- `tests/fixtures/model_contracts/pp.openapi.status.json`
- `tests/fixtures/model_contracts/pp.success.observed.pruned.json`
- `tests/fixtures/model_contracts/pp.success.pruned.json`
- `tests/fixtures/model_contracts/run.provenance.json`
- `tests/unit/test_contract_normalization.py`
- `tests/unit/test_contract_redaction.py`
- `tests/unit/test_discovery_run.py`
- `tests/unit/test_local_model_config.py`
- `tests/unit/test_model_contract_discovery.py`
- `tests/unit/test_openapi_endpoint_discovery.py`
- `uv.lock`
