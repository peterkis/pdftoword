# P2W-R2-03 实施报告

- 分支：`codex/r2-03-columns-order`；开始/当前 HEAD：`ab20f2a`。
- R2-02 已按本轮授权提交为 `ab20f2a`（`feat: add auditable document style profiles and offline restyling`），未推送。
- R2-03 工程状态：**VERIFIED，限受控合成样例及已执行的离线/Word 检查范围**。本阶段代码未提交。
- Word 执行/用户接受：**VERIFIED / PENDING**。用户解锁后，2026-09-20 已由代理操作 Microsoft Word 16.113.1 完成三份样例的打开、插字、撤销、保存重开和实际 PDF 校对。真实多栏采用与完整产品接受仍未验证。

## 已实现行为与文件

- `planning/columns.py`：先识别跨栏标题/区域和横向 band，再在 band 内建立 2–4 个有限列容器。采用可验证的间隙、纵向同时覆盖与列内不重叠条件，支持不等宽栏；没有把一条全页最大缝隙永久应用到所有区段。
- 各 band/column 有稳定的页内 ID、成员列表与包围框。通栏图/图注写成局部单栏节；相邻单栏 band 可共享连续节，显式确认的图注与其图保持同节。正文不包装成整篇布局表格。
- `planning/reading_order.py`：显式 DAG，包括列内顺序、列先后、band 先后、`precedes/follows`、图注关系和竖向证据；检测环/缺端点，保留完整 source order 为证据与降级顺序。无部分拓扑结果冒充完整输出。
- PP/Monkey 序列只有匹配 source page/content hash 的绑定约束才进入图。缺失、失效、冲突分别记录；原始 provider array 索引不会自行成为排序置信度，`engine_confidence` 保持 null。真实模型顺序质量并未因此得到验收。
- `reconstruction.py`：原生段落构建后、共享层之前选择顺序；实际调用公共结构接口后验证自有顺序和全部 block payload 没有变化。原生与扫描消费同一 planner。
- `structure_processors/conservation.py`：跨已选 column/band 的段落续接被拒绝，非连续源页不连成分栏节。
- `planning/flow.py`、`writer.py`、RenderPlan schema：实际输出 `w:cols/w:col`、列宽/间距、换栏与连续分节；正文仍为可编辑段落和内联图。输出宽度守恒、列索引有检查。换栏标记在来源书签之外，不污染 source payload。
- 人工锁、已有局部网格、失效证明、复杂多栏表格与无法解释的几何有明确局部或页级降级。旧选项网格继续走既有无边框表格；失效分栏证明不会继续套在人工改动之上。
- `columns_replay.py`：新增可执行 CLI；完整文件封印、资产与响应 hash 验证后，只在新作业生成候选/RenderPlan/DOCX。复用现有 `render_replay.verify_source`，不重新识别、不写源作业。CLI 对失败只输出诊断码，新增反例确认 schema 错误不泄露正文或 traceback。

## 实物与证据

私有根：`tmp/docx-demo/r2-03/`。

- `manifest-v2.json`：三个最终候选的源作业、seal 与输出作业路径；均为**合成受控几何样例**，不冒充真实论文或试卷接受。
- 每个输出作业有 `auto.docx`、`layout.auto.json`、`render-plan.auto.json`、`source-map.auto.json`、`column-layout.json`、`public-execution.json`、`column-replay.json`。
- `verification.json`：Word 校验前的历史回执，保留源码/输出 SHA-256、确认顺序对、来源范围与当时 Word NOT_RUN 状态，不覆盖历史阻断记录。
- `word-verification.json`：2026-09-20 实际 Word 核验回执，记录三个 DOCX/PDF 的 hash、来源审计、节与换栏数量、插字撤销及保存重开。
- `word-review/plain-v2.docx`、`heading-v2.docx`、`span-v2.docx`：实际 Word 校对、撤销并保存后的副本；`*-inserted.docx` 保留插字状态，三个同名 PDF 均由 Word 打印到 PDF，每份 1 页，未执行实体打印。
- `word-roundtrip/{plain,heading,span}/audit.json`：Word 保存后重新执行来源包审计，18 个来源范围、完整段落字符串及嵌入图片字节与不可变候选一致，源作业封印仍相符。
- `word-png/{plain,heading,span}/page-1.png`：实际 Word PDF 的三页图像，全部由代理目视校对。不等宽双栏、通栏标题及跨栏图片/图注没有观察到串栏、裁切或重叠；插字时左栏局部重排，右栏起点保持，跨栏图与图注一起下移。
- `bundled-render/{plain,heading,span}/`：早先捆绑渲染器 PDF/PNG，保留为独立证据，不替代实际 Word 核验。
- `historical-candidate-audit-v2.json`：18 个历史作业、34 页；18/18 历史文件封印相符，读取期间无修改。14 页弃权，20 页未采用分栏（`SINGLE_COLUMN`）。这个标签表示保留当前单栏输出策略，不代表已经看穿图片或确认源 PDF 本身只有一栏。
- `current-real-sample-audit.json`：R2-02 两个已处理真实样本也未形成可确认多栏采用。真实多栏正向采用仍为未验证，不用合成样例提高真实分数。

| 合成样例 | 输出节的栏数 | 宽度与间距 | 确认顺序对 |
| --- | --- | --- | --- |
| 纯不等宽双栏 | 2 | 200/270 pt，间距 40 pt | 6/6 不反转 |
| 通栏标题后双栏 | 1 → 2 | 同上 | 10/10 不反转 |
| 标题、双栏、跨栏图及图注、再双栏 | 1 → 2 → 1 → 2 | 图区全宽 510 pt | 36/36 不反转 |

共 52 个合成确认对无反转，18 个 source range payload 核验成功，无遗漏；0 张全文布局表格。跨栏图是保留源裁剪 PNG，嵌入字节 hash 一致，没有生成模型重画。图/标题等语义边界及旧关系原样保留，不静默改正文。

## 验证

- `uv sync --locked`：exit 0，`checks/sync.txt`。
- `uv run python scripts/quality.py --help`：先核对当前入口，记录 `checks/quality-help.txt`。
- `uv run python scripts/quality.py --output-dir tmp/docx-demo/r2-03/checks/quality-final-guarded`：1623 项测试成功，Ruff 正常；overall exit 1 仅因既有临时 mypy 错误，不能写成整仓全绿。
- `uv run pytest tests/productization/test_columns.py -q`：19 项成功，`checks/columns-tests-v6.txt`。覆盖原生/扫描同规划器、同 Y、不等宽、通栏/脚注、跨栏真实图片与图注、局部表格弃权、DAG 环、模型顺序缺失/一致/冲突/失效、人工锁、非连续页、宽度校验和完整封印重放。
- 相关 planning/writer/reconstruction/columns_replay/test 的 mypy：12 个文件无问题，`checks/focused-mypy-final.txt`。
- 实际 `python -m prototypes.docx_output.columns_replay` CLI 已用于生成三个样例，exit 0；不是只执行 `--help`。
- `git diff --check`：exit 0。
- 实际 Word GUI：三个受控样例均执行插字→保存→撤销→保存→关闭重开；实际导出 PDF 的三页已目视校对。保存后 `package_inventory` 核验来源范围和图片，18/18 一致。此次只补 Word 证据及文档，未修改实现，沿用上列已执行代码检查。

原有 `tmp/docx-demo/r1-05/trace-public-calls.py:15–16` 两个注解问题保留，没有增加 ignore 或清理证据来遮蔽。

## 共享复用与模型

MU-ORDER：实际调用 DocVortex 0.4.9 公共 `model_json_to_middle_json`。读取本地 `pages.py` 仅理解其按提供 index 组页的行为，没有业务 import 私有实现。借鉴计划记录的 PP-DocLayout 排序信号边界，不新增排序训练模型。

自己的 selected order 在进入 bridge 之前确定；公共输入/输出与映射报告均封存。出共享层后校验选定顺序和完整 block 内容，渲染器只消费 Layout IR/RenderPlan。原 source order 不被删除，也不会无条件阻止有证据的新顺序。

新增真实模型请求、metadata GET、重试均为 **0**。公共结构处理为本地确定性调用。原候选、engine confidence、题图关系及原生测量未被分栏评分覆盖。

## 待补、限制与回滚

1. **Mac 锁屏阻断已解除**：三份合成样例已补实际 Word 打开、插字撤销、保存重开、PDF 校对和来源复核。该结果只覆盖受控样例，不能作为真实多栏文档或完整产品验收。
2. 真实多栏采用缺口保留。历史 34 页的弃权/未采用单列，未将其排除后计算高分，也不要求 Monkey 胜出。
3. 几何不可靠、重叠复杂、人工锁和已有局部组可能退回当前页的可编辑单栏。复杂多栏表格仅保守处理；本阶段不替代后续表格重建任务。
4. 分栏是有限左到右列容器；复杂环绕、竖排、跨页栏身份连续性等不猜测。源页边界按新页节处理，同页 band 采用连续节；当前 Word 编辑证据限三个合成单页样例，Windows 和跨页编辑未验证。
5. R1 内容回退/字体/真实几何采用缺口、R2-02 混合纸型 PDF 和字体跨平台限制继续独立保留。
6. 回滚为同内容单栏可编辑输出，带 `COLUMN_*` 降级记录；原文件、旧 auto/reviewed、封存响应和本轮失败/早期候选都保留。

接受记录仍 PENDING；未代填接受者，未进入 R2-04，未提交或推送 R2-03。
