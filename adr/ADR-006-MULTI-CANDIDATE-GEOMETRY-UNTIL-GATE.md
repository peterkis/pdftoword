# ADR-006：Gate B 前的多候选几何权威

状态：**Accepted — Temporary**

日期：2026-08-28

Review trigger：**T0016 / P0-GATE-001B completion**

替代：ADR-003（Superseded）

## 背景

### 部署基线升级

Paddle OCR 生态系统已升级，PP-StructureV3 现包含新版子模型：
- PP-DocLayout_plus-L：全局布局分析
- PP-DocBlockLayout：块级布局

这些模型的布局能力需要实测验证，不能预设其弱于或强于 MonkeyOCRv2。

### 单页回归不足

几何权威关系涉及：
- 多栏布局质量
- 阅读顺序准确性
- 题图密集页面
- 拍照/倾斜页面
- 跨页关系

单页测试无法覆盖这些复杂场景，不足以形成永久唯一权威结论。

### Gate B 验证需求

T0016 / P0-GATE-001B 的目标是：
- JPG/PNG 输入一致性
- 数学试卷几何回归
- PP 新版布局 vs MonkeyOCRv2 几何质量对比
- 决定是否形成新的几何权威 ADR

## 决策

在 T0016 / P0-GATE-001B 完成前，采用以下临时权威关系：

### 1. PP 与 Monkey 均为几何候选

- PP 新版布局（PP-DocLayout_plus-L、PP-DocBlockLayout）：全局和块级布局候选
- MonkeyOCRv2-B-Parsing：复杂页面几何与阅读顺序候选

两者均为独立候选，**不预设永久唯一权威**。

### 2. Gate B 前的临时几何策略

```
有效 PDF 原生对象几何（最高优先）
  > Geometry Arbitration {
      PP-DocLayout_plus-L / PP-DocBlockLayout 候选,
      MonkeyOCRv2 布局候选
    }
  > 规则推断
```

**重要说明**：
- PP 和 Monkey **均为独立候选**，调用顺序不代表权威顺序
- 最终选择必须基于：来源可信度、几何合理性、覆盖率、与其他模型的一致性、系统置信度
- 所有选择必须保存完整审计记录

### 3. 电子 PDF 原生内容仍优先

有效原生 PDF 文字和几何对象仍然是最高优先级的内容和几何来源。OCR/VLM 结果只有在以下情况才能替换原生内容：
- 编码损坏
- 错位
- 重复
- 覆盖率异常
- 顺序严重错误
- 有明确证据支持

必须记录 `supersedes`、原因和原候选。

### 4. 最终几何选择必须有来源、理由和系统置信度

每个几何块必须保存：
- `geometry_source`：几何来源（native_pdf / pp_layout / monkey_layout / inferred）
- `content_candidates`：内容候选列表
- `selected_candidate_id`：被选择的候选 ID
- `engine_confidence`：模型原始置信度（可为空）
- `system_confidence`：系统计算的置信度（基于一致性、几何合理性、覆盖率等）
- `render_policy`：渲染策略

### 5. 单页回归结果不足以形成永久权威结论

Gate B 的数学试卷回归结果需要结合：
- 多页样本
- 不同文档类型
- 不同布局复杂度
- 长期维护成本

才能决定是否形成新的终局 ADR。

### 6. Gate B/C 完成后再决定是否形成新的终局 ADR

可能的终局方案：
- **维持多候选**：PP 和 Monkey 均保留，由 Fusion Engine 按场景选择
- **PP 主导**：PP 新版布局成为主要几何权威，Monkey 降级为复杂场景候选
- **Monkey 主导**：维持原 ADR-003，Monkey 为复杂页面几何权威
- **混合策略**：不同文档类型使用不同的几何权威

终局决策必须基于实测结果，不得凭文档描述或单一样本预设。

## 限制

- 此 ADR 仅适用于 T0016 完成前的临时状态
- 不得因多候选而增加不必要的模型调用
- 必须记录所有候选和选择理由，支持事后审计
- 禁止伪造 `engine_confidence`（模型无原始概率时保持 `null`）

## 影响

### 需要更新的文档

- `AGENTS.md` 第 4.2 节：几何与阅读顺序权威
- `docs/07_MODEL_ROLE_MATRIX.md`：PP-DocLayout 和 Monkey 的角色说明
- `docs/08_MONKEYOCRv2_INTEGRATION.md`：使用边界
- `docs/09_MULTI_MODEL_FUSION.md`：几何选择策略

### 需要实现的组件

- `GeometryArbitrator`（T0405）：在多个几何候选中选择
- `SystemConfidenceCalculator`（T0407）：计算系统置信度
- `FusionEngine v2`（T0409）：支持多候选融合

### 不影响的内容

- PP-OCRv6_medium_det/rec 仍是文字 OCR 主候选
- PP-StructureV3 仍是表格主候选
- PP-FormulaNet_plus-L 仍是公式主候选
- OvisOCR2 仍是内容复核候选
- 电子 PDF 原生文字的优先级

## 验证标准

Gate B 完成后，此 ADR 的有效性可通过以下标准验证：

1. ✅ 多候选机制已实现
2. ✅ 所有几何块均有 `geometry_source` 和 `system_confidence`
3. ✅ 无伪造的 `engine_confidence`
4. ✅ PP 和 Monkey 均有实测几何质量数据
5. ✅ 可基于实测数据形成终局 ADR

## 相关 ADR

- ADR-003：原 MonkeyOCRv2 几何权威（已 Superseded）
- 待形成：Gate B/C 后的终局几何权威 ADR

## 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0.0 | 2026-08-28 | 初始版本：Gate B 前的临时几何权威策略 |