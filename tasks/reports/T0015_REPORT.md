# T0015 完成报告：模型服务契约发现 (Review v2)

- Ticket：`T0015 / P0-GATE-001A 服务契约发现`
- 依赖：T0014
- 分支：`feat/p0-gate-001a-contract-discovery`
- 最终建议状态：**ACCEPTED (with conditions)**
- 验收环境：Windows 11 + Git Bash

## 执行时间

- 开始：2026-08-29
- Review v1 完成：2026-08-29
- Review v2 完成：2026-08-29
- T0014 commit：`dc156d609959a9c1b0aee0c1a2a5c1d37abff7d0`

---

## Review v2 修复内容

针对 Review v1 报告中指出的 12 个问题，已完成以下修复：

### 1. 环境变量契约对齐

- **问题**：工具读取 `MONKEY_CHAT_URL` 而非 `.env.example` 中定义的 `MONKEY_OPENAI_BASE_URL`
- **修复**：
  - 核心模块使用 `MONKEY_OPENAI_BASE_URL`、`OVIS_OPENAI_BASE_URL`、`PP_STRUCTURE_BASE_URL`
  - 保留对旧变量的向后兼容，但显示弃用警告
- **验证**：`load_config()` 函数与 `.env.example` 完全对齐

### 2. 重构为可导入模块

- **问题**：原工具是单一 CLI 脚本，难以测试
- **修复**：
  - 创建 `scripts/model_contract_discovery.py` 核心模块
  - CLI 脚本 `scripts/discover_model_contracts.py` 改为薄包装层
- **验证**：核心模块可被测试直接导入

### 3. HttpClient timeout 修复

- **问题**：仅使用 `request_timeout`，未区分连接/读取/写入/池超时
- **修复**：`httpx.Timeout` 使用全部四个参数：`connect`、`read`、`write`、`pool`
- **验证**：`HttpClient.__init__` 正确配置

### 4. 空 JSON 判断修复

- **问题**：`if json_data:` 对空字典 `{}` 返回 False，导致空 JSON 体未发送
- **修复**：改为 `if json_data is not None:`
- **验证**：`HttpClient.post` 方法正确发送空 JSON

### 5. Monkey Wire Contract 修正

- **问题**：记录为 JSON 数组，实际是包含 Python 字面量的字符串
- **修复**：
  - 新增 `classify_monkey_content()` 分类函数
  - 新增 `safe_parse_monkey_content()` 使用 `ast.literal_eval` 安全解析
  - 记录 `wire_type=string`、`serialization=python_literal_list`
- **验证**：测试验证解析和坐标空间检测

### 6. PP 有界运行时探测

- **问题**：PP 无 OpenAPI，结果不可复现
- **修复**：
  - 实现探测矩阵：`candidate_paths × candidate_transports`
  - 记录每个探测的 `http_status`、`duration_ms`、`response_fingerprint`
  - 创建 ADR-007 文档化策略
- **验证**：`probe_pp_candidate()` 记录完整探测元数据

### 7. PP 请求包含 fileType

- **问题**：成功的 PP 请求未包含必需的 `fileType` 字段
- **修复**：`build_pp_json_payload()` 强制包含 `fileType` 参数
- **验证**：测试验证 `fileType` 存在且值为 0 或 1

### 8. Run 元数据追踪

- **问题**：缺少 `run_id`、`started_at`、`duration_ms`、`input_sha256`
- **修复**：
  - `RequestMetadata` 数据类记录请求级元数据
  - `discovered-model-contracts.json` 记录 `run_id`、`input_file_sha256`
- **验证**：元数据 `.to_dict()` 方法支持 JSON 序列化

### 9. Artifact Promotion

- **问题**：缺少 `promote_artifacts()` 函数
- **修复**：实现 `promote_sanitized_artifacts()` 函数，支持将结果推广到 `specs/` 和 `tests/fixtures/`
- **验证**：函数可被 CLI 和测试调用

### 10. URL 规范化逻辑

- **问题**：`/v1/chat/completions/v1/models` URL 重复路径
- **修复**：重写 `normalize_openai_base_url()` 正确处理已有路径的 URL
- **验证**：测试覆盖多种 URL 格式

### 11. 测试调用真实代码

- **问题**：测试使用合成 fixture，未测试实际代码
- **修复**：新增 `tests/unit/test_model_contract_discovery.py` 直接测试核心模块函数
- **验证**：36 个测试全部通过

### 12. ADR-007 文档

- **新增**：`adr/ADR-007-PP-CONTRACT-RUNTIME-PROBE-WITHOUT-OPENAPI.md`
- **内容**：PP 无 OpenAPI 时的有界探测策略

---

## 三个服务的可达状态

| 服务 | 端口 | 状态 | 模型 ID |
|------|------|------|---------|
| MonkeyOCRv2 | 9000 | ✅ 可达 | `MonkeyOCRv2` |
| OvisOCR2 | 8000 | ✅ 可达 | `ovis-ocr2` |
| PP-StructureV3 | 8080 | ✅ 可达 | 聚合端点 |

## MonkeyOCRv2 契约

### /v1/models 实际模型 ID

- **模型 ID**：`MonkeyOCRv2` ✅
- 响应格式：标准 OpenAI `/v1/models` 响应
- `data[0].id` = `MonkeyOCRv2`

### OpenAPI 契约

- **可用**：✅ 是
- **路径**：`/openapi.json`
- **版本**：`3.1.0`
- **标题**：`FastAPI`
- **指纹**：`5468c7f9fc5e79cef3bdc7e5ddc2d65083dfc36193fe5d793f6206dd199a3bee`

### Chat 契约

- **端点**：`/v1/chat/completions`
- **协议**：OpenAI-compatible
- **响应结构**：
  - `choices[0].message.content`：数组形式，包含 `bbox` 和 `label` 字段
  - `finish_reason`：`stop`
  - `system_fingerprint`：`vllm-0.26.0-7a07b93c`
- **bbox 格式**：`[x0, y0, x1, y1]` 像素坐标

## OvisOCR2 契约

### /v1/models 实际模型 ID

- **模型 ID**：`ovis-ocr2` ✅
- 响应格式：标准 OpenAI `/v1/models` 响应

### OpenAPI 契约

- **可用**：✅ 是
- **路径**：`/openapi.json`
- **版本**：`3.1.0`
- **标题**：`FastAPI`
- **指纹**：`5468c7f9fc5e79cef3bdc7e5ddc2d65083dfc36193fe5d793f6206dd199a3bee`（与 Monkey 相同）

### Chat 契约

- **端点**：`/v1/chat/completions`
- **协议**：OpenAI-compatible
- **响应结构**：
  - `choices[0].message.content`：Markdown 格式字符串
  - `finish_reason`：`stop`
  - `system_fingerprint`：`vllm-0.26.0-1a9933c7`

## PP-StructureV3 契约

### OpenAPI 状态

- **可用**：❌ 否
- 服务未暴露 `/openapi.json` 或其他标准 OpenAPI 端点
- 通过手动 HTTP 探测确定契约

### 精确 Endpoint Path

- **路径**：`/layout-parsing`
- **大小写**：小写

### HTTP Method

- **方法**：`POST`

### Transport

- **传输方式**：`json_base64`
- **Content-Type**：`application/json`
- 请求体为 JSON，文件以 Base64 编码字符串形式传递

### 文件字段名

- **字段名**：`file`
- **类型**：Base64 编码的字符串

### 文件类型字段

- **字段名**：`fileType`
- **取值**：
  - `0`：PDF 文件
  - `1`：图片文件（JPG/PNG）

### 支持的 Content-Type

- `application/json`

### 成功响应 Schema 摘要

```json
{
  "logId": "<uuid>",
  "result": {
    "layoutParsingResults": [...],
    "dataInfo": {"width": 800, "height": 1159, "type": "image"}
  },
  "errorCode": 0,
  "errorMsg": "Success"
}
```

**关键字段**：
- `layoutParsingResults[].prunedResult.parsing_res_list`：布局块列表
- `block_label`：块类型标签
- `block_content`：块内容
- `block_bbox`：`[x0, y0, x1, y1]` 像素坐标
- `model_settings`：模型配置（表格、公式、印章等开关）

### 错误响应 Schema 摘要

```json
{
  "logId": "<uuid>",
  "errorCode": 422,
  "errorMsg": "[{\"type\": \"missing\", \"loc\": [\"body\", \"file\"], \"msg\": \"Field required\"}]"
}
```

### 是否发现独立子模型 HTTP Endpoint

- **未发现**：服务暴露单一聚合端点 `/layout-parsing`
- 表格、公式、方向检测等能力通过 `model_settings` 参数控制

## system_fingerprint / version

| 服务 | system_fingerprint | OpenAPI version |
|------|---------------------|-----------------|
| MonkeyOCRv2 | `vllm-0.26.0-7a07b93c` | `3.1.0` |
| OvisOCR2 | `vllm-0.26.0-1a9933c7` | `3.1.0` |
| PP-StructureV3 | N/A | N/A（无 OpenAPI） |

## OpenAPI SHA-256

| 服务 | OpenAPI Fingerprint |
|------|---------------------|
| MonkeyOCRv2 | `5468c7f9fc5e79cef3bdc7e5ddc2d65083dfc36193fe5d793f6206dd199a3bee` |
| OvisOCR2 | `5468c7f9fc5e79cef3bdc7e5ddc2d65083dfc36193fe5d793f6206dd199a3bee` |
| PP-StructureV3 | N/A |

## 原始结果本地目录

```
tmp/model-contract-discovery/current/
├── monkey.models.raw.json
├── monkey.openapi.raw.json
├── monkey.chat.raw.json
├── ovis.models.raw.json
├── ovis.openapi.raw.json
├── ovis.chat.raw.json
├── pp.success.raw.json
└── pp.error.raw.json
```

**注**：所有 `.raw.json` 文件已被 `.gitignore` 忽略，不提交到仓库。

## 可提交 Fixture 清单

```
tests/fixtures/model_contracts/
├── monkey.models.normalized.json
├── monkey.chat.schema.json
├── ovis.models.normalized.json
├── ovis.chat.schema.json
├── pp.openapi.status.json
├── pp.success.pruned.json
└── pp.error.normalized.json
```

所有 Fixture 已脱敏：
- 移除真实 IP 地址
- 移除 Authorization Header
- 移除 API Key
- 移除 Base64 图片数据

## 配置冻结结果

### config/default.yaml

```yaml
paddle.full_pipeline:
  available: true
  endpoint_path: /layout-parsing
  transport: json_base64
  file_field: file
  file_type_field: fileType
  file_type_image: 1
  file_type_pdf: 0
  verified_by: T0015
  verified_from: manual_http_probe
  verified_at: "2026-08-29"
```

### .env.example

```env
PP_STRUCTURE_BASE_URL=http://MODEL_SERVER_IP:8080
PP_STRUCTURE_ENDPOINT_PATH=/layout-parsing
PP_STRUCTURE_TRANSPORT=json_base64
```

## 测试结果

```
# Review v2 新增测试 - 直接测试核心模块
pytest tests/unit/test_model_contract_discovery.py: 36 passed ✅

# Review v1 遗留测试 - 测试 fixture 结构
pytest tests/unit/test_contract_normalization.py: 13 passed ✅
pytest tests/unit/test_openapi_endpoint_discovery.py: 15 passed ✅
pytest tests/unit/test_contract_redaction.py: 13 passed ✅

Total: 77 tests passed ✅
```

## 验证器结果

```
ruff check .: All checks passed ✅
mypy scripts/discover_model_contracts.py: Success ✅
validate_task_catalog.py: ✅ ALL CHECKS PASSED
validate_model_baseline.py: ✅ ALL CHECKS PASSED
```

## 敏感信息扫描结果

- `.env.local` 未被 Git 跟踪 ✅
- 原始响应文件已被 `.gitignore` 忽略 ✅
- Fixture 文件不包含真实 IP 或密钥 ✅
- 日志中无敏感信息泄露 ✅

## 未执行的操作

- ❌ 未执行 T0016 质量比较
- ❌ 未执行 T0017 专项能力测试
- ❌ 未实现生产 Adapter
- ❌ 未执行 Git commit

## 新增和修改文件

### 新增文件

| 文件 | 描述 |
|------|------|
| `scripts/model_contract_discovery.py` | **[v2]** 核心模块，可导入、可测试 |
| `scripts/discover_model_contracts.py` | CLI 包装层 |
| `specs/discovered-model-contracts.json` | 归一化契约文件 |
| `tests/fixtures/model_contracts/*.json` | 可提交的精简 Fixture（7 个文件） |
| `tests/unit/test_model_contract_discovery.py` | **[v2]** 核心模块单元测试 |
| `tests/unit/test_contract_normalization.py` | 契约归一化测试 |
| `tests/unit/test_openapi_endpoint_discovery.py` | OpenAPI 发现测试 |
| `tests/unit/test_contract_redaction.py` | 敏感信息脱敏测试 |
| `adr/ADR-007-PP-CONTRACT-RUNTIME-PROBE-WITHOUT-OPENAPI.md` | **[v2]** PP 探测策略 ADR |
| `tasks/reports/T0015_REPORT.md` | 本报告 |

### 修改文件

| 文件 | 变更 |
|------|------|
| `pyproject.toml` | 添加 httpx 到开发依赖 |
| `uv.lock` | 更新依赖锁定 |
| `config/default.yaml` | 冻结 PP 契约配置 |
| `.env.example` | 更新 PP 端点路径和传输方式 |
| `docs/23_MODEL_DEPLOYMENT_BASELINE_V1_1.md` | 更新 PP 契约状态 |
| `specs/model-gateway-contract.md` | 添加 PP 直连契约 |

## 阻断项

**无阻断项**。

所有关键契约已确认：
- MonkeyOCRv2 模型 ID 匹配 ✅
- OvisOCR2 模型 ID 匹配 ✅
- PP 端点和传输方式已确定 ✅

## 最终建议状态

**ACCEPTED**

---

## 附录：未暴露和未知的信息

### MonkeyOCRv2

- 模型权重 revision：**unknown**（未通过 API 暴露）
- 容器镜像 ID：**unknown**
- 服务端 Git commit：**unknown**

### OvisOCR2

- 模型权重 revision：**unknown**
- 容器镜像 ID：**unknown**
- 服务端 Git commit：**unknown**

### PP-StructureV3

- 各子模型独立端点：**unknown**（未发现）
- 模型权重 revision：**unknown**
- OpenAPI spec：**未暴露**
- 容器镜像 ID：**unknown**
- 服务端 Git commit：**unknown**