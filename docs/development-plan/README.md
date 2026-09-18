# 当前计划：PDF2Word Reconstruction V2.1

2026-09-18 按用户指令切换到仓库外独立目录
`~/Plans/PDF2Word_Development_Plan_v2.1_20260917/`，执行入口为 `prompts/R1_FULL.md`。
S1 **已废弃**；S2-01～06 **继承完成并保留质量发现**。以下旧计划记录仅供历史追溯，
不再用于调度。原 97 项目录、映射、源码、CI 和历史证据不改写。

本次仅授权 **P2W-R1-01**。初次 `next_task.py` 实测仅推荐 R1-01；本项工程
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

同源 A/B 当前均用 legacy，独立子作业可使用原下载与预览接口；后续 renderer 通过
`DocxRenderer` 注入，结构候选通过独立 `StructureProcessor` 注入。HTTP 对应
`POST /api/compare-renderers/{job_id}`，继续使用现有本机会话与 Origin 防护。

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
