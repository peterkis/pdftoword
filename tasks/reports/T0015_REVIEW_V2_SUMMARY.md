# T0015 Review v2 Summary

## 修复完成状态

| Issue | Description | Status |
|-------|-------------|--------|
| 1 | 环境变量契约与 .env.example 对齐 | ✅ Fixed |
| 2 | 重构为可导入模块 + CLI 分离 | ✅ Fixed |
| 3 | HttpClient timeout 完整配置 | ✅ Fixed |
| 4 | Monkey Wire Contract (string + python_literal) | ✅ Fixed |
| 5 | PP 有界运行时探测矩阵 | ✅ Fixed |
| 6 | PP 请求必须包含 fileType | ✅ Fixed |
| 7 | Run 元数据追踪 (run_id, duration_ms, input_sha256) | ✅ Fixed |
| 8 | Artifact Promotion 函数 | ✅ Fixed |
| 9 | RequestMetadata 序列化 | ✅ Fixed |
| 10 | URL 规范化逻辑 (处理已含路径的 URL) | ✅ Fixed |
| 11 | 测试调用真实代码 | ✅ Fixed |
| 12 | ADR-007 文档 | ✅ Created |

## 测试结果

```
tests/unit/test_model_contract_discovery.py: 36 passed ✅
tests/unit/test_contract_normalization.py: 17 passed ✅
tests/unit/test_contract_redaction.py: 13 passed ✅
tests/unit/test_openapi_endpoint_discovery.py: 19 passed ✅
tests/unit/test_package_boundary.py: 4 passed ✅
tests/unit/test_provider_config.py: 11 passed ✅
tests/unit/test_windows_compat.py: 4 passed ✅

Total: 104 tests passed ✅
```

## Lint 结果

```
ruff check scripts/model_contract_discovery.py: All checks passed ✅
ruff check scripts/discover_model_contracts.py: All checks passed ✅
```

## 新增/修改文件清单

### 新增文件

1. `scripts/model_contract_discovery.py` - 核心模块 (可导入、可测试)
2. `tests/unit/test_model_contract_discovery.py` - 核心模块单元测试
3. `adr/ADR-007-PP-CONTRACT-RUNTIME-PROBE-WITHOUT-OPENAPI.md` - PP 探测策略 ADR
4. `tasks/reports/T0015_REVIEW_V2_SUMMARY.md` - 本文件

### 修改文件

1. `scripts/discover_model_contracts.py` - 重构为 CLI 包装层
2. `tasks/reports/T0015_REPORT.md` - 更新为 Review v2 版本

## 关键修复详情

### Monkey Wire Contract

- **修复前**：错误记录为 JSON 数组
- **修复后**：正确记录为 `wire_type=string`, `serialization=python_literal_list`
- **解析方式**：使用 `ast.literal_eval` 安全解析 Python 字面量字符串
- **坐标空间**：检测为 `normalized_1000` (0-1000 归一化坐标)

### PP Contract

- **OpenAPI**：不可用 (404)
- **探测策略**：bounded runtime probe
- **成功路径**：`/layout-parsing` + `json_base64` transport
- **必需字段**：`file` (base64), `fileType` (0=PDF, 1=image)

### URL 规范化

- **修复前**：`/v1/chat/completions/v1/models` (重复路径)
- **修复后**：正确处理已有路径的 URL，统一归一化为 `/v1` 基础

## 待执行操作

- ❌ 未执行 Git commit (用户指令)
- ❌ 未执行 T0016/T0017 (用户指令)
- ❌ 未实现生产 Adapter (超出 T0015 范围)

## 下一步

1. 配置 `.env.local` 中的真实模型服务器 IP 地址
2. 运行完整 Gate Run: `uv run python scripts/discover_model_contracts.py --output-dir tmp/model-contract-discovery/current`
3. 使用 `--promote-artifacts` 参数推广结果到 specs/ 和 tests/fixtures/
4. 确认所有服务可达后，更新 `docs/23_MODEL_DEPLOYMENT_BASELINE_V1_1.md`