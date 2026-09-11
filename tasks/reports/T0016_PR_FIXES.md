# T0016 PR #2 合并前防错修复

T0016 仍为 **ACCEPTED_WITH_QUALITY_FINDINGS**；本次是评测工具防错和 ADR 适用期限修订，不是新模型运行或模型质量改进。

- `validate_ground_truth` 和内容评分均拒绝规范化后为空的 confirmed 参考，使用 `EMPTY_CONFIRMED_TEXT_REFERENCE`；字符串类型仍校验。不静默改写参考。对真实 GT 的只读检查确认 17/17 项均非空，因此不推翻现有参考检查结果。
- 耗时汇总仅将 COMPLETE 纳入 count/median_ms/min_ms/max_ms；无成功请求时为 0/null/null/null。failed_count 和 failures 单独保留失败请求 ID、状态和耗时，公开摘要与私有结果保持一致。
- 评估代码版本为 v1.2，修正记录见 `specs/t0016-evaluation-correction-v1.2.json`。两次真实运行继续保留原 v1.1 指标和当时源码哈希；没有重新 evaluate/promote 真实目录，没有手工替换历史哈希。新 run 原本 14/14 COMPLETE，成功耗时数值不受本次样本筛选修复影响。
- ADR-006 记录 Gate B 已复审，继续多候选，在后续明确决策替代之前有效；下一复审结合 T0017 与代表性多页、多类型样本，触发复审不等于自动失效。原生 PDF 优先原则不变。

本机离线验证：**191 passed**（原182项加9项回归）；ruff、mypy（25 source files）、任务目录校验（97 tickets）、模型基线校验、git diff --check 全部通过。这不是 GitHub CI 全绿的声明。

回归覆盖空串、空白、LaTeX 定界符、正常参考和 uncertain 空参考；耗时覆盖全部成功、成功失败混合、全部失败，并通过实际 evaluate/public_summary 入口检查公开结果。

两次真实运行及现有公共报告/指标前后逐文件哈希不变；T0015 的70文件清单不变。保留旧 PARTIAL、R2 COMPLETE、`y→v` 误述撤回和生产质量未验收边界。无第三轮推理、FRP访问、重新标注、参数调整、T0017或生产实现。
