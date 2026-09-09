# ADR-003：MonkeyOCRv2 作为复杂页几何权威

状态：**Superseded / Pending empirical validation**

变更记录：
- 2026-08-20：初始状态 Accepted
- 2026-08-28：状态变更为 Superseded，由 ADR-006 替代

原决策（历史记录）：

PP-DocLayout-M 快速初筛；复杂页由 MonkeyOCRv2-B-Parsing 提供块级几何和阅读顺序。

限制：文字、表格和公式内容仍由专项模型或融合决定；无原始概率时不伪造置信度。

---

## 变更说明

此 ADR 已被 ADR-006 替代。原因：

1. **部署基线已升级**：PP-StructureV3 已升级为新版子模型（PP-DocLayout_plus-L、PP-DocBlockLayout 等），其布局能力需要实测验证。
2. **单页回归不足**：单页测试结果不足以形成永久唯一权威结论。
3. **需要 Gate B 验证**：几何权威关系必须通过 T0016 / P0-GATE-001B 实测对比 PP 新版布局与 MonkeyOCRv2 的几何质量。

**替代方案**：见 ADR-006-MULTI-CANDIDATE-GEOMETRY-UNTIL-GATE.md
