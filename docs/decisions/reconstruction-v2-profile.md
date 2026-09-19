# reconstruction-v2 共用导出链

2026-09-19。R1-07 工程接入；不签署完整产品接受。

CLI/API/UI 的 auto profile 继续显式选择 `reconstruction-v2`。prepare-routes 和 execute-routes 均进入同一个 `finish`：逐页 GeometryArbitrator → 独立来源绑定 ledger → DocVortex 公共确定性结构候选/保真门禁 → 自有 IR 1.2 → RenderPlan v2 → FlowRenderer → 实际内容范围 source-map。候选不保证被选中；不能用全局 provider 覆盖整份文档。

## 能力决定

| 输出能力 | Legacy | DocVortex 公共输出适配 | Flow |
| --- | --- | --- | --- |
| legacy_flow 固定布局契约 | 支持 | 已验证有限子集，其他由既有内容门禁拒绝/回退 | 不接收 |
| flow_v1 Section/样式/尺寸/分组节点 | 不接收 | 无公开 section/style 参数，不接收 | 支持既有内容写出边界 |
| 共享标题/段落/图注候选 | 消费自有 IR | 公共结构处理后回映自有 ledger | 同一共享候选，不再次后处理 |

机器矩阵位于 `renderers/capabilities.py`。reconstruction-v2 请求不支持 Flow 契约的 renderer 时显式记录 requested/effective/reason 并使用 Flow；独立 renderer 的原有契约仍直接拒绝不支持的计划。固定 IR 的 Legacy/Flow 消融是显式的不同输出计划，不把 Flow 计划有损转换为 Middle 再重建。

选择 Flow 是保留本项目可控 section/style、图片及来源能力的有限扩展，不改写上游或依赖 `_internal`。DocVortex 0.4.9 公共 postprocess 仍实际调用，版本、输入输出与执行记录留在新作业；未采用的复杂内容继续既有适配边界。

## 状态、失败与人工修订

每页 QA 公开 `selected_geometry_provider`、`retained_geometry_sources`、`layout_status`、`renderer`、问题及人工接受状态。候选可用不等于 SELECTED；ABSTAIN 明确保留原几何。页面证据缺失/hash 不符时仅该页弃权。共享 worker 不可用时保留最后可用自有结构并记录问题。

结构 stage 绑定来源 pages/relations/assets hash；已 finalized 的自动 IR 如发生漂移则拒绝。reviewed 输出保留人工变化及来源锁，跳过自动仲裁/共享后处理，只重做输出规划。不能把清理后的 Middle 再送回 Model。RenderPlan 与 source-binding ledger 独立持久化。

新增 `docx_demo.py status` 只读显示状态，优先 reviewed；API 和现有 UI 同样展示每页实际结果。新增来源书签包住实际文字/数学/图片范围，保留源 block_id 与 bbox。

## 回滚及接受限制

新建作业切回 `legacy_ovis_pp` 即可使用原链；已有 Flow reviewed 保持其显式 profile。旧输出不覆盖，不回退 S2 或插图保护。完整 R1-07-AC01 的真实 Monkey 采用仍 NOT_VERIFIED，用户要求不降低门槛。真实 Word 编辑/视觉与题图归属仍需独立接受。见 R1-07 报告。
