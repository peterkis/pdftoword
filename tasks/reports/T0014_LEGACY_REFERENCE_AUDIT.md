# T0014 Legacy Reference Audit

文档版本：`3.0.0`
日期：`2026-08-28`
状态：**COMPLETED**

## 审计结果摘要

| 类别 | 数量 | 状态 |
|------|------|------|
| CURRENT_CORRECT | 5 | ✅ |
| HISTORICAL_MARKED | 5 | ✅ |
| UNRESOLVED_CONTRACT | 3 | ✅ |
| CONTRADICTION | 0 | ✅ |
| NEEDS_FIX | 0 | ✅ |

## CURRENT_CORRECT（当前正确）

| 文件 | 内容 | 说明 |
|------|------|------|
| `START_HERE.md` | 模型基线描述 | ✅ 已更新为 PP-DocLayout_plus-L / PP-DocBlockLayout 与 MonkeyOCRv2 均为候选 |
| `VALIDATION_REPORT.md` | Ticket 数量 | ✅ 已更新为 97 |
| `AGENTS.md` | 几何权威策略 | ✅ 已使用 Geometry Arbitration 表达 |
| `docs/08_MONKEYOCRv2_INTEGRATION.md` | 使用边界 | ✅ 已改为"几何候选" |
| `docs/09_MULTI_MODEL_FUSION.md` | OCR 策略 | ✅ 已移除 Small/Medium 升级路径 |

## HISTORICAL_MARKED（历史标注）

| 文件 | 内容 | 说明 |
|------|------|------|
| `CHANGELOG.md` | 原始 V1.1 模型决策历史 | Changelog 天然属于历史记录 |
| `adr/ADR-003-MONKEY-GEOMETRY-AUTHORITY.md` | 原 Monkey 几何权威 | ✅ 状态标记 Superseded |
| `docs/21_MIGRATION_V1_0_TO_V1_1.md` | V1.0→V1.1 迁移对照 | ✅ 迁移文档 |
| `tasks/reports/T0001_BASELINE_COMMIT.md` | T0001 基线记录 | ✅ 历史记录 |
| `docs/23_MODEL_DEPLOYMENT_BASELINE_V1_1.md` | 模型名称对照表 | ✅ 明确标注迁移完成状态 |

## UNRESOLVED_CONTRACT（未冻结契约）

| 文件 | 内容 | 说明 |
|------|------|------|
| `docs/23_MODEL_DEPLOYMENT_BASELINE_V1_1.md` | PP HTTP 端点路径 | ✅ 待 T0015 Gate 验证 |
| `config/default.yaml` | `endpoint_path: ""` | ✅ 显式标记为未冻结 |
| `specs/model-gateway-contract.md` | PP 契约状态 | ✅ 记录两种候选端点 |

## CONTRADICTION（矛盾）

**无**

## NEEDS_FIX（需要修正）

**无**

## 校验脚本结果

```
validate_task_catalog.py: ✅ ALL CHECKS PASSED
validate_model_baseline.py: ✅ ALL CHECKS PASSED
```

## 已完成的修正

1. ✅ AGENTS.md：几何策略改为 Geometry Arbitration
2. ✅ docs/08：将"几何权威"改为"几何候选"
3. ✅ docs/09：移除 Small/Medium 升级路径
4. ✅ T0405：验收标准不预设 Monkey 主导
5. ✅ sample-job-config.json：移除 layout_block 符合 Schema
6. ✅ validate_task_catalog.py：添加 T0405 语义断言
7. ✅ validate_model_baseline.py：添加精确断言检查

## 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-08-28 | 初始审计报告 |
| 2.0.0 | 2026-08-28 | 最终审计：CONTRADICTION = 0 |
| 3.0.0 | 2026-08-28 | 收口审计：NEEDS_FIX = 0，所有校验通过 |