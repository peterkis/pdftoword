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

## T0016 栅格格式与数学试卷评测

`scripts/raster_regression.py` 实现输入准备、标注校验、独立 collector、分层评分和私有证据；`evaluate_raster_models.py` 仅解析参数和输出安全摘要。它们是开发期 Gate 工具，不是生产 Adapter 或 Layout IR。新增唯一开发依赖 Pillow 12.1.1，用于固定 JPEG 解码、无损 PNG 对照和本地叠加图；版本由 `uv.lock` 锁定。

只有显式 `run` 发网络请求。沿用 `.env.local`、T0015 的 `HttpClient`、URL 构造和安全 literal parser；不调用 T0015 discovery / promotion。CLI 限制私有 case/run 在忽略的 `tmp/raster-regression/cases/`、`tmp/raster-regression/runs/` 内，目录 0700，文件 0600，拒绝非空目录和符号链接。

```sh
uv run --locked python scripts/evaluate_raster_models.py prepare \
  --source "$T0016_TEST_IMAGE" --case-id math_exam_001 \
  --case-dir tmp/raster-regression/cases/math_exam_001
```

原图按实际文件内容识别，原 JPEG 字节不重新保存。必须满足正常 EXIF 方向、RGB/灰度、无 ICC 配置；其他情况以 `SIMPLE_COMPARISON_CONDITIONS_NOT_MET` 停止简单对照。PNG 使用 RGB、compress_level=6、optimize=false；逐字节验证解码 RGB 相等。像素哈希定义为 ASCII `width,height,RGB` + NUL + RGB bytes 的 SHA-256，与文件哈希不同。

推理前直接查看原图，建立 `ground-truth.private.json`：case/文件/像素哈希、宽高、annotation_version、reviewer_type/id、reviewed_at、review_status，以及 regions、reading_order_constraints、critical_text_checks。区域必须有 opaque id、type、bbox、reference、status、uncertainty、notes、layer。真实标注不放公共 fixture；合成示例见 `tests/fixtures/raster_regression/geometry.synthetic.json`。`reviewer_type=agent_visual` 不代表人工验收。无法确认的内容标记 uncertain；关键标注缺失不能冒充 REVIEWED。

```sh
uv run --locked python scripts/evaluate_raster_models.py validate-ground-truth \
  --case-dir tmp/raster-regression/cases/math_exam_001

export NO_PROXY=127.0.0.1,localhost
export no_proxy="$NO_PROXY"
RUN_ID="t0016-mac-$(date -u +%Y%m%dT%H%M%SZ)"
uv run --locked python scripts/evaluate_raster_models.py run \
  --case-dir tmp/raster-regression/cases/math_exam_001 \
  --protocol specs/t0016-evaluation-protocol.json \
  --run-id "$RUN_ID" --output-dir "tmp/raster-regression/runs/$RUN_ID" \
  --confirm-no-auth --confirm-local-quality-evidence

uv run --locked python scripts/evaluate_raster_models.py evaluate \
  --run-dir "tmp/raster-regression/runs/$RUN_ID" \
  --ground-truth tmp/raster-regression/cases/math_exam_001/ground-truth.private.json
uv run --locked python scripts/evaluate_raster_models.py promote \
  --run-dir "tmp/raster-regression/runs/$RUN_ID"
```

`validate-ground-truth` 将真值哈希写入独立 manifest；已冻结标注变更被拒绝。需要修订时保留原 case 和版本，建立新版本目录及原因，不能覆盖旧真值。`run` 保存输入和真值快照、冻结协议、完整请求表、剥离图片后的私有响应、分层预测及证据 manifest。原 HTTP bytes 只在内存哈希，裁剪版另有哈希；不跟随任何响应图片 URL。

执行顺序固定为 Monkey、PP、Ovis；Monkey/PP 各三轮，格式为 JPG→PNG、PNG→JPG、JPG→PNG；Ovis 只有 JPG→PNG。三次预检 GET 验证模型身份与 PP 归一化结构；不会运行 T0015 的完整请求集。请求无重试、无预热，temperature 沿用已验收配置不发送；PP 所有显式参数见冻结 JSON，其余参数使用同一服务默认值并保留回显。

评分分开 whole-page block / paragraph / fine / visual；同类降序 IoU 贪心匹配（相同 IoU 按 opaque id），一对一，阈值 0.50/0.75。段落层排除独立 visual；细粒度无确认真值则 not_scored。合并/拆分仅为覆盖关系诊断，不增加 TP。阅读顺序必须有模型原始 order，PP null 保持 missing。内容是参考片段 presence 诊断，不是完整 OCR 准确率；只移除预先允许的空白与 LaTeX 外层定界符，不合并数学符号/变量。图内文字不重复计入正文，公式候选不重复累加。

`specs/t0016-evaluation-correction.json` 记录首轮离线评估发现的类别大小写/别名及段落分母修正。原协议、真值、响应和采集预测不改写；历史错误评分留在该 run 的 `evaluation-history.private/`，评估版本及工具哈希另存。不得将初版 Monkey 零匹配解释为模型质量问题。

`evaluate` 只用同一 run 的本地文件重算，检查输入/真值/协议/响应/预测/矩阵链，拒绝哈希漂移。`promote` 仅写 `tasks/reports/T0016_METRICS.json` 的 allowlist 脱敏指标，不调用模型、不触碰 T0015；PARTIAL 也可公开失败证据，**不等于验收通过**。CLI 对 PARTIAL/BLOCKED 返回 2，局部输入/证据错误返回 1，完整执行返回 0。不要用 `&&` 隐去 PARTIAL 的后续证据整理。

本地 `review.private.html` 包含原图叠加和转录评分细节，不能提交或上传。T0016 当前状态及全部限制见 `tasks/reports/T0016_REPORT.md`。


### PR #2 防错修订（评估 v1.2）

见 `specs/t0016-evaluation-correction-v1.2.json`：confirmed 参考在既定规范化后必须非空，标注校验和内容评分均拒绝无效参考，不自动改写为答案。耗时的 count/median_ms/min_ms/max_ms 只统计 COMPLETE；无成功结果时为 0/null/null/null。failed_count 与 failures（request_id、status、duration_ms）单独保存，公开摘要保持相同区分。

两个真实运行仍使用其封存的 v1.1 评分和当时工具哈希。本轮没有重新 evaluate/promote 它们；新代码版本与历史证据版本不同是有意保留的来源事实，不应手工改写历史哈希。修复不改变 T0016 的 ACCEPTED_WITH_QUALITY_FINDINGS 结论。

## P2W-S1-02 统一工程门禁

`uv run --locked python scripts/quality.py` 串行执行完整测试、Ruff、mypy、原两个校验器及 Schema 样例检查。
Python 3.12.13、Node 24.18.0 是必需环境；失败整体非零，原始输出与可公开报告分别保存。
独立 Schema 入口为 `uv run --locked python scripts/validate_schema_samples.py`。
详见[门禁说明](../docs/26_QUALITY_GATE.md)。不启动模型、服务或历史评测。
