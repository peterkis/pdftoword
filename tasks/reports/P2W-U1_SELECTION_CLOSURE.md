# U1 选型收尾实际报告

状态：选型收尾材料已执行并交付；路线INCONCLUSIVE；产品接受PENDING；不进入U2。

## 实际范围与交付

HEAD仍为`32b9e13d9ef752fc6c945ec62e58abb031da837f`。用户授权按上一轮建议完成选型收尾；本轮无生产代码变更、无新模型请求、无安装/服务/FRP变更、无commit/push。

复用18份自动DOCX与完整固定矩阵，将旧6类能力槽映射到8个已测试物理页。该子集是看过结果后的诊断映射，不是新预注册/holdout；不截取或改写原自动DOCX来冒充独立新输出。

|能力槽|现有来源物理页|已有输入组|
|---|---|---|
|原生单栏|native 7|G2|
|扫描试卷/公式|scan 7|G3|
|页内混合|native 1|G2|
|普通表格|mix 2|G1|
|真实多栏|supermix 3、4|G5、G6|
|续表关系|scan 8、9|G3|

cases.json逐页绑定原文件、选页输入、DOCX哈希、收据和Word映射；comparison.json保留全矩阵与失败/未评分证据。

## 两个实际修复诊断

仅修改独立Word副本，保存、实际本地PDF导出、重开并关闭；原18份自动DOCX未变。

|案例|实际操作|实测至保存|结果|
|---|---|---:|---|
|G1 pipeline|在误合表分界行拆分表格|88.316秒|表数2→3，Word页数3→2；原页边界与公式仍未恢复，PARTIAL|
|G5 pipeline|全选、横向、六栏|56.434秒|仍5页，图片被窄栏裁切，PARTIAL|

没有将简单操作耗时作为完整修复成本；完整修复时间unknown。试验在出现明确剩余问题后提前停止，未耗尽每页10分钟，不伪记censored-at-budget。操作由代理执行，不冒充用户人工修复或接受。

G1普通正文与媒体内容保持；Word保存改变数学run/字符序列，显式记录。G5正文、数学及媒体哈希内容比较未变化，但视觉裁切仍发生，证明素材哈希守恒不能代替视觉完整性。

## 路线裁决与前三缺口

前三缺口：内容/结构完整性、Word布局与关系、公式/表格真实可编辑性。上游合表已经存在于layout结果；纯Renderer补丁不能解释全部损失。

`probe_c=false`，U1-03本轮SKIPPED_NOT_NEEDED：未建立内容可用的纯布局决定性case，且不得把已后处理官网结果重新送旧Model→Middle处理。没有生成C-compose.docx，也不把人工修复稿称为组合收益。该判断局限于本轮有界选型，不否定未来可用组合方案。

U1-04形成`INCONCLUSIVE`路线文件与简短ADR。DIRECT实测不满足；COMPOSE未证明；PATCH_RENDERER范围不足以覆盖上游缺陷；RETAIN_SPECIALIST缺少足以指定整条主链路的证据。现有入口保留，不表示质量胜出。

五个gap均为必要缺口；首批候选tables/formulas/layout，relations/continuation延期保留。未获路线批准，不激活任何U2/U3开发。42项v2.1任务、97旧Ticket责任映射均逐项保留，未修改历史状态、未删除源码。

## 产物路径

公开：
- `docs/decisions/mineru-replacement-v3.json`
- `docs/decisions/mineru-replacement-v3.md`
- `docs/decisions/mineru-replacement-v3-task-disposition.json`

私有、相对仓库：
- `tmp/docx-demo/u1-selection-closure-20260921/index.html`
- 同目录`cases.json`、`comparison.json`、`repair-log.json`、`probe-feasibility.json`
- 同目录`repair/G1-pipeline-repair.docx`、`repair/G5-pipeline-repair.docx`及Word PDF/PNG
- 自动原件仍在`tmp/docx-demo/compare-batch3-20260921-03/runs/`

## 验证与停止

本轮只需文档、产物哈希、状态契约和映射完整性检查；没有生产行为修改，不重跑整套模型或无关门禁。已有pytest1672、Ruff和定向mypy收据继续保留；全仓63个历史tmp类型错误不宣称解决。

预期状态：U1-01保留PARTIAL（原本地SDK NOT_RUN）；U1-02保留PARTIAL/STOPPED_FOR_DECISION；U1-03明确跳过；U1-04的裁决文件可记VERIFIED但接受PENDING。调度器仍可能先提示U1-01需解决，不能为让指针前进伪造SDK成功。

下一条件：明确目标生产部署/版本，针对最多两个决定性case补足对应真实输出与离线重导出证据，预算另行确定；随后才可申请明确路线批准。本轮到此停止，不自动重开选型或进入生产接入。
