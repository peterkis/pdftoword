# 21. V1.0 → V1.1 迁移

> **状态**：历史迁移快照
>
> 本文档记录原始 V1.1 设计方案，但模型职责已被以下文档修订：
> - `docs/23_MODEL_DEPLOYMENT_BASELINE_V1_1.md` — 当前部署基线
> - `adr/ADR-006-MULTI-CANDIDATE-GEOMETRY-UNTIL-GATE.md` — 几何权威临时策略
>
> **不得作为当前实现依据**。请参考上述文档。

## 1. 模型职责（三阶段对照）

| V1.0 | 原始 V1.1 设计 | 当前部署对齐 V1.1 |
|---|---|---|
| PP-DocLayout-M | PP-DocLayout-M → Monkey complex | PP-DocLayout_plus-L / PP-DocBlockLayout（布局候选） |
| Ovis 复杂结构兜底 | Monkey 几何主模型 | MonkeyOCRv2（布局候选），不预设主导 |
| 单一 VLM 字段 | layout_complex 和 reviewer 分离 | 同左，但 geometry_source 待 T0016 回归 |

## 2. Layout IR

- `schema_version`：`layout-ir/1.0` → `layout-ir/1.1`；
- `confidence` 拆成 `engine_confidence` 和 `system_confidence`；
- 新增 `geometry_source`；
- 新增 `content_candidates`；
- 新增 `selected_candidate_id`；
- 新增 `render_policy`；
- 来源增加 `monkeyocrv2` 和 `inferred`。

## 3. 配置

V1.0：

```yaml
vlm:
  engine: ovisocr2
```

V1.1：

```yaml
model_gateway:
  base_url: http://MODEL_SERVER_IP:8100
model_policy:
  layout_complex: monkeyocrv2-b-parsing
  content_reviewer: ovisocr2
```

## 4. 代码迁移

- 将原 `vlm_fallback` 拆成 `layout_complex_adapter` 与 `content_reviewer_adapter`；
- 增加 Candidate/Fusion；
- DOCX Builder 只读被选择候选；
- 保存 V1.0 IR 时先执行迁移函数，禁止双写两套业务逻辑。
