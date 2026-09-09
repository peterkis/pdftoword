# T0014 完成报告：模型部署基线与架构文档对齐

- Ticket：`T0014 模型部署基线与架构文档对齐`（P0，依赖 T0001）
- 分支：`docs/p0-model-baseline`（基于 `feat/p0-foundation`）
- 最终建议状态：**ACCEPTED**
- 验收环境：Windows 原生 PowerShell

## 核心纠正

| 服务 | 当前端口 |
|------|---------|
| MonkeyOCRv2 | 9000 |
| OvisOCR2 | 8000 |
| PP-StructureV3 | 8080 |

目标网关 8100 **尚未部署**。

历史端口映射：
- Paddle：历史 8102
- Ovis：历史 8104
- Monkey：历史 8106

## 变更摘要（Git Index 统计）

**Git 统计**：
- 新增文件：7
- 修改文件：35
- 删除文件：0
- 总变更：42 文件

**注**：精确行数以最终 `git diff --cached --shortstat` 和归档 Patch 为准，不在本报告中固化，以避免报告自身修改造成统计失效。

### 新增文件（7 个）

| 文件 | 类型 |
|------|------|
| `adr/ADR-006-MULTI-CANDIDATE-GEOMETRY-UNTIL-GATE.md` | 临时几何权威决策 |
| `docs/23_MODEL_DEPLOYMENT_BASELINE_V1_1.md` | 部署基线文档 |
| `scripts/validate_model_baseline.py` | 部署基线校验脚本 |
| `scripts/validate_task_catalog.py` | 任务目录校验脚本 |
| `tasks/reports/T0001_BASELINE_COMMIT.md` | T0001 基线提交记录 |
| `tasks/reports/T0014_LEGACY_REFERENCE_AUDIT.md` | 遗留引用审计 |
| `tasks/reports/T0014_REPORT.md` | 本报告 |

### 修改文件（35 个）

**根文档（4 个）**：
- `AGENTS.md` — 几何策略改为 Arbitration，第10条端口规则修订
- `README.md` — 当前模型基线
- `START_HERE.md` — 当前模型基线
- `VALIDATION_REPORT.md` — NEEDS_FIX 统计

**ADR（2 个）**：
- `adr/ADR-003-MONKEY-GEOMETRY-AUTHORITY.md` — 状态改为 Superseded
- `adr/ADR-005-MODEL-GATEWAY.md` — Amended 状态，当前端口

**配置（6 个）**：
- `config/default.yaml`
- `config/model-routing.yaml`
- `config/profiles/accurate.yaml`
- `config/profiles/balanced.yaml`
- `config/profiles/fast.yaml`
- `samples/sample-job-config.json`

**架构文档（10 个）**：
- `docs/01_PRD.md`
- `docs/03_TECHNICAL_ARCHITECTURE_V1_1.md`
- `docs/04_TECH_STACK.md`
- `docs/05_PDF_ROUTING.md`
- `docs/07_MODEL_ROLE_MATRIX.md`
- `docs/08_MONKEYOCRv2_INTEGRATION.md`
- `docs/09_MULTI_MODEL_FUSION.md`
- `docs/13_MODEL_SERVER_INTEGRATION.md`
- `docs/19_DECISION_LOG.md`
- `docs/21_MIGRATION_V1_0_TO_V1_1.md`

**阶段文档（5 个）**：
- `phases/P0_工程基础与契约.md`
- `phases/P2_混合 PDF 与局部 OCR.md`
- `phases/P4_MonkeyOCRv2 与多模型融合.md`
- `phases/P7_性能、安全、部署与发布.md`
- `phases/PHASES_OVERVIEW.md`

**规格与任务（6 个）**：
- `specs/model-gateway-contract.md`
- `tasks/DEPENDENCY_GRAPH.md`
- `tasks/EPICS.md`
- `tasks/TICKETS.md`
- `tasks/tickets.json`
- `tasks/tickets.csv`

**其他（2 个）**：
- `pyproject.toml` — 添加 jsonschema 依赖
- `uv.lock`

## 关键修正

### 几何权威

AGENTS.md 现使用 Geometry Arbitration 表达：
```
有效 PDF 原生对象几何（最高优先）
  > Geometry Arbitration {
      PP-DocLayout_plus-L / PP-DocBlockLayout 候选,
      MonkeyOCRv2 布局候选
    }
  > 规则推断
```

### T0405 验收标准

```text
- PP 与 Monkey 作为并列候选
- 选择理由可解释
- 不得无实测证据固化固定主导关系
- 原生有效几何不被无证据覆盖
```

### ADR-005 修订

Status: Accepted — Amended
- 主应用生产目标仅连接 8100
- Provider endpoint 由配置注入
- 当前直接服务为 9000/8000/8080
- 历史端口 8102/8104/8106 为早期设计

## 验收结果

### 工作区验证：PASS

```
pytest: 23 passed ✅
ruff: All checks passed ✅
mypy: Success (10 files) ✅
validate_task_catalog.py: ✅ ALL CHECKS PASSED
validate_model_baseline.py: ✅ ALL CHECKS PASSED
Job Config schema/sample: PASS ✅
```

### Index Archive 解压验证：PASS

```
Archived pytest: 23 passed ✅
Archived ruff: All checks passed ✅
Archived mypy: Success (10 files) ✅
Archived validate_task_catalog.py: ✅ ALL CHECKS PASSED
Archived validate_model_baseline.py: ✅ ALL CHECKS PASSED
Archived Job Config schema/sample: PASS ✅
```

## Dependency Graph 与 EPICS 检查

**DEPENDENCY_GRAPH.md**：
```
├─ T0014（基线文档对齐）
├─ T0015（Gate A：服务契约发现）
│   ├─ T0016（Gate B：几何回归）
│   └─ T0017（Gate C：能力矩阵）
```

**EPICS.md**：
```
- T0014 / P0-BASELINE-001：模型部署基线与架构文档对齐
- T0015 / P0-GATE-001A：服务契约发现
- T0016 / P0-GATE-001B：JPG/PNG 与数学试卷回归
- T0017 / P0-GATE-001C：旋转、UVDoc、多栏、表格和公式专项能力矩阵
```

## Legacy Audit

| 类别 | 数量 |
|------|------|
| CURRENT_CORRECT | 5 |
| HISTORICAL_MARKED | 5 |
| UNRESOLVED_CONTRACT | 3 |
| CONTRADICTION | 0 |
| NEEDS_FIX | 0 |

## Gate 依赖

```
T0001 (已完成)
  ↓
T0014 (本次)
  ↓
T0015 (P0-GATE-001A)
  ├→ T0016 (P0-GATE-001B)
  └→ T0017 (P0-GATE-001C)
```

---

## 最终声明

- 本轮完成**模型部署基线与架构文档对齐**，纠正历史端口，更新几何权威策略，修正 T0405 验收标准。
- **网络访问**：未访问任何模型服务器。
- **未执行任何模型调用**。
- **未执行 Git commit**；工作区存在未提交变更。