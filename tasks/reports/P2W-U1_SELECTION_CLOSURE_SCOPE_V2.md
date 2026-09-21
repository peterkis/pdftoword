# U1 选型收尾：用户确认核心范围后的最终记录

状态：收尾材料已交付；路线INCONCLUSIVE；质量/用户接受PENDING；不进入U2。
实际HEAD：`32b9e13d9ef752fc6c945ec62e58abb031da837f`，未commit/push。

## 本轮实际变更

1. 最终需求固化到`docs/PRODUCT_REQUIREMENTS.md`，并同步AGENTS、README、启动入口、PRD、范围与验收文档。试卷、合同、手册、一般文档为主要对象，力求原布局与排版还原；杂志/网络期刊排除。活跃计划入口和work状态也记录该用户确认。
2. 对已有证据作scope-v2离线筛选，不重新识别：supermix3–6页全部排除，G1–G4保留；25源页、12自动DOCX、140实际Word页。旧29页/18份产物、分母、标注、响应和结论保留，不把范围外缺陷改为成功。
3. 六类能力映射中保留5个诊断case、6源页；原多栏case为杂志而排除，目标类别多栏NOT_COVERED。合同及技术/操作手册专门case不足，采购说明/教学材料不冒充该验收。
4. 已做两个人工Word修复诊断；范围变化后仅G1计入当前决定，G5试验转历史OUT_OF_SCOPE。每次只开一个Word，保存/导出/重开后关闭。
5. 形成路线JSON、短ADR、42任务与97旧Ticket责任处置表；probe_c=false，未生成C-compose，未新建生产主路径。

## 范围内结果

|组|源页|A Word页|官网pipeline页|官网VLM页|
|---|---:|---:|---:|---:|
|G1|2|2|3|2|
|G2|12|34|34|33|
|G3|9|10|7|7|
|G4|2|2|3|3|

主要问题仍存在于目标文档：G1上游跨源页合表；G2原生行/公式片段散开和题图重排；G3/G4教学表公式字符串化、列宽与跨页失真。它们足以阻止直接替换，无需引用杂志六栏或封面缺陷。

G1修复副本在Word中拆表，操作至保存88.316秒，表数2→3、页数3→2。正文及媒体内容未改，但原页边界、公式错误仍未解决；Word保存造成数学序列变化。判PARTIAL_EARLY_STOP，完整修复时间unknown；没有声称耗尽每页10分钟或完整修复已完成。G5的56.434秒六栏尝试不进入当前路线结论。

probe_c=false的核心依据：尚未有同内容、内容/结构已可用且主要只剩布局的决定性case；A现有保图外观不证明Flow对同一MinerU可编辑内容有收益。跳过组合试验不等于证明COMPOSE永远不可行。

## 正式停止与下一条件

DIRECT实测不达核心目标；COMPOSE未证明；PATCH_RENDERER不能覆盖已观察的上游结构问题；RETAIN_SPECIALIST尚不能指定整条主链路。路线INCONCLUSIVE，当前生产默认与回退入口保留。

五gap仍必要，候选首批为tables/formulas/layout，其余relations/continuation延期而非删除；当前无gap开发激活。新版业务范围是后续映射任务的强制过滤条件。

下一步必须先明确拟生产部署/版本，并在相应授权下最多两个目标case补关键证据，优先合同/手册与现有试卷/表格；预算另定，禁重新跑整套矩阵。原本地SDK4.0.4及保存结果后的离线公共DOCX重导出仍NOT_RUN。线上API后端3.4.4不等于该证据。没有路线批准前不进入U2。

## 产物与证据

当前公开决定：`docs/decisions/mineru-replacement-v3.json`、同名md；旧scope-v1文件保留。
私有入口：`tmp/docx-demo/u1-selection-closure-20260921/scope-v2/index.html`。
同目录：`scope.json`、`cases.json`、`comparison.json`、`repair-log.json`、`probe-feasibility.json`、`route-decision.json`。
范围内修复DOCX：`tmp/docx-demo/u1-selection-closure-20260921/repair/G1-pipeline-repair.docx`，附实际WordPDF/PNG。
全部自动原件仍在`tmp/docx-demo/compare-batch3-20260921-03/runs/`，当前入口只列12份核心产物。

本轮模型调用0；未安装或改服务/FRP，无生产算法变化。仅需求文档、范围派生证据、人工修复副本和状态记录有变更。原件18套封存结果哈希复核；模型旧门禁不重跑。既有pytest1672、Ruff/定向mypy退出0可复用；63个历史tmp类型错误仍保留。

状态契约检查退出0；调度器仍可能先返回U1-01的TASK_NEEDS_RESOLUTION，准确反映SDK未执行，不能伪造成功来移动指针。U1-02为PARTIAL/STOPPED_FOR_DECISION；U1-03跳过；U1-04为裁决材料VERIFIED，接受仍PENDING。最终检查、工时和保持清单见closure-receipt。

最终收尾墙钟约0.32小时（包含本轮需求修订；无下载等待排除）。scope检查退出0，18套封存结果与案例哈希核验，31个当前入口链接有效；git diff --check退出0。
