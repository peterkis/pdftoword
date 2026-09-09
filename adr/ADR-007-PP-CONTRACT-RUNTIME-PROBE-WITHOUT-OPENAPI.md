# ADR-007：PP 服务无 OpenAPI 时的有界运行时探测

状态：**Accepted**

日期：2026-08-29

## 背景

PP-StructureV3 服务当前不暴露标准 OpenAPI 端点（如 `/openapi.json`、`/swagger.json`）。这意味着无法通过 OpenAPI 规范自动发现端点、传输格式和参数 Schema。

然而，服务本身是可用的，需要一种可靠的方式来发现和冻结其契约，同时：

1. 不无限扫描或猜测端点
2. 记录所有探测尝试及其结果
3. 明确标记契约来源为运行时探测而非 OpenAPI
4. 承认探测范围的局限性

## 决策

当 PP 服务确认不暴露 OpenAPI 时，采用**有界运行时探测**策略。

### 1. 探测候选来源

候选端点和传输方式由配置显式提供：

```yaml
PP_STRUCTURE_CANDIDATE_PATHS=/layout-parsing,/PP-StructureV3
PP_STRUCTURE_CANDIDATE_TRANSPORTS=json_base64,multipart
```

默认值来自历史文档和常见模式，但**不得硬编码为唯一答案**。

### 2. 探测矩阵

按顺序、串行验证每个候选组合：

| Path | Transport | 优先级 |
|------|-----------|--------|
| `/layout-parsing` | `json_base64` | 1 |
| `/layout-parsing` | `multipart` | 2 |
| `/PP-StructureV3` | `json_base64` | 3 |
| `/PP-StructureV3` | `multipart` | 4 |

每个候选探测必须记录：

```json
{
  "path": "/layout-parsing",
  "transport": "json_base64",
  "http_status": 200,
  "response_content_type": "application/json",
  "application_error_code": 0,
  "response_fingerprint": "sha256:...",
  "success_predicate": true,
  "duration_ms": 1234.56,
  "request_payload": {"file": "[REDACTED]", "fileType": 1}
}
```

### 3. 成功谓词

判定探测成功的条件：

1. HTTP 状态码为 2xx
2. 响应 `errorCode` 字段为 0（成功）
3. 响应包含 `result.layoutParsingResults` 数组

### 4. 多候选成功处理

若多个候选都成功：

- 记录所有成功候选
- 选择第一个成功的作为 `primary`
- 其他成功候选作为 `alternatives`
- 记录 `selection_reason`

若只有一个候选成功，则冻结该组合。

### 5. 无候选成功处理

若所有候选都失败：

- 状态标记为 `BLOCKED_PP_CONTRACT_UNRESOLVED`
- 记录所有探测结果
- 不猜测或创建假设端点

### 6. 契约来源标记

通过此方式获得的契约必须标记：

```json
{
  "contract_source": "bounded_runtime_probe",
  "openapi_available": false,
  "probe_scope": "configured_candidates",
  "contract_completeness": "runtime_verified_without_openapi"
}
```

### 7. 独立子模型端点枚举

关于表格、公式、方向检测等独立子模型端点：

```json
{
  "submodel_endpoint_enumeration": "unknown",
  "reason": "openapi_not_exposed_and_probe_scope_limited"
}
```

最多可以声明："在本次限定候选路径中未观察到独立子模型 HTTP Endpoint"

**不得声明**："服务只暴露一个聚合端点"

## 限制

1. 探测范围仅限于配置中明确列出的候选
2. 不保证枚举了所有可能的端点
3. 契约验证仅针对请求成功响应，不保证覆盖所有功能
4. 服务行为可能在版本更新后改变

## 影响

### 需要更新的内容

- `scripts/model_contract_discovery.py`：实现探测矩阵逻辑
- `specs/discovered-model-contracts.json`：添加探测元数据
- `tasks/reports/T0015_REPORT.md`：记录探测过程

### 验收标准

- [ ] 探测矩阵按顺序执行
- [ ] 每个候选记录完整元数据
- [ ] 成功候选选择有明确理由
- [ ] 契约来源正确标记为 `bounded_runtime_probe`
- [ ] 无 OpenAPI 时不进行无限扫描
- [ ] 子模型端点状态标记为 `unknown`

## 相关 ADR

- ADR-005：统一模型网关
- ADR-006：多候选几何权威

## 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0.0 | 2026-08-29 | 初始版本：PP 服务无 OpenAPI 时的有界探测策略 |