# 当前计划：PDF2Word Reconstruction V2.1

2026-09-18 按用户指令切换到仓库外独立目录
`~/Plans/PDF2Word_Development_Plan_v2.1_20260917/`，执行入口为 `prompts/R1_FULL.md`。
S1 **已废弃**；S2-01～06 **继承完成并保留质量发现**。以下旧计划记录仅供历史追溯，
不再用于调度。原 97 项目录、映射、源码、CI 和历史证据不改写。

R1-01 历史授权记录：当时仅授权 **P2W-R1-01**。初次 `next_task.py` 实测仅推荐 R1-01；本项工程
验证后建议 R1-05，不自动签署视觉/Word/发布接受，也不执行下一项。

- [R1-01 实施报告](../../tasks/reports/P2W-R1-01_REPORT.md)
- [六类公共接口与后续任务](r1-reuse-record.json)：计划包提供的源码审查快照，公共调用均 NOT_RUN。
- 工程实现与工具状态分离：报告在仓库，执行状态只更新新包 `state/progress.json` 的 R1-01。

本机只读计划检查：

```sh
python3 "$HOME/Plans/PDF2Word_Development_Plan_v2.1_20260917/scripts/validate_package.py"
python3 "$HOME/Plans/PDF2Word_Development_Plan_v2.1_20260917/scripts/next_task.py"
```

回放入口（输入作业不变；输出根必须位于当前私有存储目录）：

```sh
uv run scripts/docx_demo.py compare-renderers --source-job <已有作业目录> --revision auto
```

旧 PDF 作业缺少 provenance image_sha256 时，显式传入先前可信比较记录
`--source-seal <已有 comparison.json>`；校验整份旧文件集合/hash 后才回放。
没有既有封存记录的旧来源图拒绝，不用当前 hash 补写历史。新作业已在来源图生成时记录 hash。

同源 A/B 当前均用 legacy，独立子作业可使用原下载与预览接口；后续 renderer 通过
`DocxRenderer` 注入，结构候选通过独立 `StructureProcessor` 注入。HTTP 对应
`POST /api/compare-renderers/{job_id}`，继续使用现有本机会话与 Origin 防护。


## R1-05 共享结构/输出 POC（2026-09-18）

当前按用户新指令收口为[带已知限制的 POC](../../tasks/reports/P2W-R1-05_FREEZE.md)：停止扩展能力及主动全面复审，最终针对性验证和既有 CI 正常后可工程合并；随后按依赖进入 R1-02 及主线集成，以真实问题页验证收益。继承适配边界和失败案例，不继承“完善的 DocVortex 渲染器”结论。以下“仅执行 R1-05”是初次授权的历史记录。

仅执行 R1-05；工程、视觉、Word 接受分开。实际版本 0.4.9、依赖隔离、六能力决定见
[评估记录](../decisions/docvortex-renderer-evaluation.md)与[实施报告](../../tasks/reports/P2W-R1-05_REPORT.md)。
R1-01/PR #7 的保护保持；原计划、S2 和历史状态不倒改。R1-05 工程验证后的下一建议为 R1-02，本次不自动执行。

```sh
uv run scripts/setup_docvortex_runtime.py
uv run scripts/docx_demo.py reuse-poc --source-job <已有作业目录> --source-seal <先前可信 comparison.json>
```

来源图已有 image_sha256 的新作业可以省略 `--source-seal`。两个轴的输出是全新独立作业，
默认转换、保存和导出继续使用 Legacy。依赖安装是单独的网络步骤，worker 后处理/导出禁网。

---

## 历史接入记录（不再作为当前执行指令）

# 增量产品化计划接入

本入口由 P2W-S1-01 接入，状态为 READY_FOR_REVIEW。完整计划已独立安装于仓库外
`~/Plans/pdftoword-development-plan/`，入口为 `prompts/00_START.md`。
包内脚本、测试和 41 项任务目录继续留在该目录，不进入项目源码扫描。

- 当前交付：[基线报告](../../tasks/reports/P2W-S1-01_REPORT.md)、[检查证据](../../tasks/reports/P2W-S1-01_CHECKS.json)。
- 范围决策：[productization-profile-v1](../decisions/productization-profile-v1.md)。
- 全部旧任务覆盖映射：[JSON](legacy_ticket_map.json)、[CSV](legacy_ticket_map.csv)。
  两份文件逐字节导入自外部计划包的 `mappings/`，保留全部 97 个旧 ID 和标题。
- 原任务规范：[TICKETS.md](../../tasks/TICKETS.md)、[tickets.json](../../tasks/tickets.json)、[tickets.csv](../../tasks/tickets.csv)继续独立保留。

`new_task_ids` 是补齐或验证范围的关联，`planning_assessment` 是计划评估，均不是旧 Ticket 状态。
本轮关联 T0001、T0006、T0014、T0015、T0016；逐项说明见基线报告。
S1–S4 是增量交付路线，原 P0–P7 的验收仍需对应证据，不能批量关闭旧任务。
T0103 不代表已有 pdf-inspector SDK；T0301 不要求重部署现有 Medium；
T0406 的延后仍待确认；T0607 的 React 目标不能由 HTML 原型抵充。

包内 `tasks/catalog.json` 的 41 项保持初始 TODO；执行状态单独记录于外部
`state/progress.json`。本轮只将 P2W-S1-01 置为 READY_FOR_REVIEW，接受者与接受日期为空，
其余 40 项仍 TODO。包的原始 MANIFEST 不随进度更新重写；默认 validate_package 校验工作包，
`--integrity` 用于未修改的分发包，不能用来验证已更新的执行状态。

本机可在仓库根运行：

```sh
python3 "$HOME/Plans/pdftoword-development-plan/scripts/validate_package.py"
python3 "$HOME/Plans/pdftoword-development-plan/scripts/inspect_repo.py" --repo .
python3 "$HOME/Plans/pdftoword-development-plan/scripts/next_task.py"
```

这些工具不会执行任务。其他机器需另行安装完整计划包；本目录仅版本化当前接入说明与映射。
P2W-S1-01 接受后，下一建议为 P2W-S1-02（质量门禁）；P2W-S1-03（样本集）也依赖本项。
当前仅 READY_FOR_REVIEW，建议器不会把依赖当作已接受。本轮不执行后续任务。

## 2026-09-17 开发顺序修订

用户已要求能力交付优先：直接实现 S2-01～06，S1-04～06测量工作后置；S2-07进入下一条结构主线，S2-08不再等待S1统计阈值。外部 `REPLAN_20260917.md`、任务JSON/CSV、阶段与执行提示已同步。开发就绪与正式接受分开，原状态和历史报告不倒改。pdf-inspector 1.20.0已实际接入，T0103不再以缺少可调用实现为替代依据；详见[接入决策](../decisions/auto-mixed-native-backend-v1.md)。

## R1-02 主线接入切片（2026-09-18）

R1-05 已作为带已知限制的 POC 合并至 `f300bf0`。按最新推进主线指令，
R1-02 已在独立分支形成未提交的候选适配、变换、schema 和离线叠框入口，
见[实施报告](../../tasks/reports/P2W-R1-02_REPORT.md)。候选解析不等于仲裁/Word 收益；
同输入三类真实非空证据及后续共享结构消费仍缺失，完整任务接受未签署。
此前“本次不自动执行”仅指 R1-05 初次授权时的历史边界。

## R1-03 已开始（2026-09-18）

R1-02 已本地提交为 `140945d`。新分支 `codex/r1-03-monkey-layout-routing`
接入显式 `reconstruction-v2` auto 布局计划：整页 Monkey 与区域 PP/Ovis
范围共同显示并重新绑定审批，默认仍为兼容模式。见[R1-03 报告](../../tasks/reports/P2W-R1-03_REPORT.md)。
真实问题页仅做离线准备；HTTP stub 与缓存回放不代表真实模型接受，尚未发送新真实请求。


R1-03 后续真实验证：用户授权后对已列出的 46–47 页执行 6/6 请求，
Monkey 返回 14/16 个候选且正文 hash 不变；作业仍 PARTIAL（页 46 内容回退，
页 47 布局含糊，LibreOffice 中文显示有缺字），详见报告末尾真实验证记录。
本轮不重试、不扩展预算，不将请求成功当作产品接受。

## R1-04 已进入（2026-09-18）

R1-03 按用户授权本地提交为 `9a73713`。R1-04 首个切片已实现来源片段守恒、
保守宏候选选择和 sealed 新作业入口；真实问题页因支撑不完整而弃权，旧输出未改。
见[R1-04 进行中报告](../../tasks/reports/P2W-R1-04_REPORT.md)。完整几何拆并、列顺序、
SharedStructure 关系守恒与真实改善证据仍待补齐，不标阶段完成。


R1-04 续作已接入来源行/片段账本、可重新计算的列顺序证明、SharedStructure
前后 AtomicCoverage/RelationDelta，以及允许有证明重排/行边界拆并的布局门禁。
最终 1531 项自动测试成功；真实两页仍因支撑不足弃权，新增模型请求 0。
R1-03 内容回退/字体问题独立保留，真实布局改善不作已验证结论。

R1-04 已追加[现有真实样本补证](../../tasks/reports/P2W-R1-04_REAL_SAMPLE_AUDIT.md)：
检查第 47 页及其他已登记真实样本后，当前可核验比较仍全部弃权；真实采用/收益保留
NOT_VERIFIED。建议按已知限制冻结工程结果，不调整门槛或重做历史评测。

## R1-04 工程收口与 R1-06（2026-09-19）

用户明确接受 R1-04 按已知限制工程收口，真实采用/收益仍 NOT_VERIFIED，
不签署完整产品接受，见[收口记录](../../tasks/reports/P2W-R1-04_FREEZE.md)。
R1-06 已实现 Flow Planner v1、IR 1.2 与独立 RenderPlan，生成同源 Legacy/Flow
真实 DOCX 和 LibreOffice 预览，见[实施报告](../../tasks/reports/P2W-R1-06_REPORT.md)。
新增模型请求为 0；第 46 页内容回退、R1-04 真实采用缺口及 Word 人工接受继续独立保留。

## R1-07 共用导出链（2026-09-19）

R1-04/R1-06 已提交 `4e2c952`。R1-07 已接通逐页仲裁→共享结构→Flow→实际来源范围，
并生成零请求四组消融；见[实施报告](../../tasks/reports/P2W-R1-07_REPORT.md)与
[profile 决定](../decisions/reconstruction-v2-profile.md)。真实 Monkey 采用仍 NOT_VERIFIED，
Word/题图归属接受缺口及一次未查明的 LibreOffice 中文渲染不稳定仍保留；不签完整产品接受。
