# P2W-F2-01：两例复核与下一小片选择

实际 HEAD：`a18092a87071cf2415dcabd5c3ca5f095f758159`。
本轮只执行 F2-01；保留 F1-01 未提交改动。新增模型调用 0，不改生产默认，不执行 Git 写操作。
结论：**选择 F1-04 的单一切片：case A 第 1 题选项图按已有源行几何排布**。
该切片仅选入、未执行；没有新增全链路胜出或产品接受结论。

## 修改与范围

本轮新增本报告及私有对照产物，未修改核心代码、F1-01 文件、历史 U1 报告或正式数据集。
私有总入口：`tmp/docx-demo/f2-01-20260921/summary.json`。

|case|来源与物理页|本轮执行|
|---|---|---|
|A|沿用 F1-01 的数学试卷，同一 PNG 源页，物理第 1 页|冻结完整页 IR，以同一显式 14pt/Arial/Songti SC profile 分别调用 F1-01 前后 writer；不增加第二份试卷 case|
|B|用户补充的 batch4：WS/T 306—2023，物理第 4–5 页（印刷第 2–3 页）|没有找到同源旧自动作业；使用原 PDF 进行现有 native-only 本地解析，冻结该结果后生成同内容 before/after；不调用 OCR|

B 准确类别为**技术标准（一般文档）**，按用户指定纳入第二个 case；不冒充合同或操作手册。
合同、真正技术/操作手册的独立业务覆盖仍 NOT_COVERED。本轮未检查其他标准页的转换质量。

batch4 三份原 PDF 的 SHA-256 均与包清单相符；完整包文件哈希在执行前后保持一致。
标注虽然经过两遍代理精校，文件仍标 `DRAFT_AGENT_VISUAL`，不是人工验收真值。
标注只在生成后用于源页/结构核对，没有进入 native 解析、IR、writer 或正文纠正；
正式 manifest、family、split、人工签署均未变。本次源页曝光单独记录于私有 summary 的 exposure_events。

## 三个优先缺口及归因

### A-L1 — layout：同一行四个选项图被固定排成两列

- 位置：源物理第 1 页，第 1 题；图块 `p0-ovis6/8/10/12`。
- 源图四图横排，既有图框横向不重叠、纵向相交；四个图与标签的关联已在 `figure_groups.option_grid` 中。
- 实际 Word 输出为 2×2。原 1 个源页变为 2 个 Word 页；此外第 2–6 题文本选项逐段纵排也占用高度，**不能把全部分页差异都归因于这一个图组**。
- 代码依据：`ovis_replay.associate_ovis` 记录 pairs 但未给 columns；`writer.py` 的 `g.get("columns", 2 if ... option_grid ... else 3)` 固定回退到两列。已有几何可供局部决策，无需重新识别。
- 下一小片：F1-04，只处理有明确同一行证据、实际宽度放得下的此类图组；真实两行/歧义情况保留保守回退。不得全局缩字、硬改所有图组为四列或承诺整页恢复。

### B-S1 — structure：源表 1 没有进入单元格结构

- 位置：源物理第 5 页上半部表 1。原图与辅助标注对照为 11×5 原子网格、39 个真实单元格，含纵向合并；这是复杂合并表的诊断，不能冒充普通表格支持率。
- 当前 native IR 中表区域为 `p4-figure0` 图片，同时有 22 个与该范围相交的独立文字块；没有 table block/cell grid。生成的两份 DOCX 都没有 Word 数据表。
- 这属于原生对象到结构的缺口，图片与独立文字并存带来重复呈现风险；不是源 PDF 没文字，也不是已证明 OCR 不足。
- 本例没有 `COLUMN_TABLE_SCOPE_UNSUPPORTED`，且原页为单栏。**不选 F1-03 来绕过表格保护**。先保留原生结构适配/区域降级缺口，之后仅在本地结构契约确实不足时再考虑 F2-02 的有界候选。

### B-S2 — structure：一个分类图被拆成多个无整体归属的对象

- 位置：同页图 1（表下方四个分类框与连接箭头）。
- native IR 中出现四个框裁图 `p4-figure11/13/12/14`、三个箭头裁图 `p4-figure2/1/3` 及独立原生文字，未形成一个复合图对象。
- `native_pdf.py` 对模糊矢量保留裁图且不抑制原生文字，这是已显式报告 `VECTOR_TEXT_OVERLAP_REVIEW` 的保护路径；不能只删掉文字来消除重叠。
- 后置最小方向：原生复合图归属或有理由的局部整体源图回退，继续保留源资产及可追溯范围。当前不启动新模型。

识别与转换：本轮没有发现足以选入 F1-02 的“正确公式在转换层失败”证据。
A 既有可编辑 OMML 保持；B 包内所谓形式表达式不能自动当作数学方程。
未执行全页逐字评分，不以 XML 数量或测试数量作为质量得分。

## 实际 Word 与局部收益

- A：实际 Word 打开并查看输出上下两页，保存 `word-page-1.png`、`word-page-2.png`。执行插字 F2EDIT → 保存独立 `word-inserted.docx` → 撤销 → 再保存。
- 磁盘复核：撤销后的正文、拼接数学文本、书签名称与媒体哈希与自动 after 一致。此检查不宣称 Word 没有重写 OMML 内部结构。
- A 重开：尝试时 Open 对话框持续不可用，曾出现 ScreenCaptureKit `-3811`；**重开 NOT_VERIFIED**。
- B：已尝试在 Word 选择编辑副本，Open 持续禁用；**Word 显示/编辑 NOT_RUN**，不推测 Word 页数或视觉效果。已提示用户可解除锁屏/弹窗；未用 LibreOffice/HTML 冒充实际 Word。
- F1-01 的来源样式修复工程证据保留，但 A 没有实测源 runs，B 没有 inline_parts；这两例**未证明新增可见样式/分页收益**。before/after 的正文、公式、媒体和来源顺序一致，只说明比较受控，不代表产品质量合格。

## 验证

|实际命令|退出码与结果|
|---|---|
|`PYTHONPATH=. uv run python tmp/docx-demo/f2-01-20260921/replay.py`|0；A 同源前后 DOCX；阻断 socket connect/connect_ex；原作业及 F1 文件集不变|
|`PYTHONPATH=. uv run python tmp/docx-demo/f2-01-20260921/case-b.py`|0；B 原生第 4–5 页解析与两份 DOCX；不读标注生成；模型调用 0|
|`PYTHONPATH=. uv run python tmp/docx-demo/f2-01-20260921/verify.py`|0；两例正文/数学/书签/图片前后一致，原作业、batch4 包、F1 产物及原未提交文件哈希不变；A 撤销保存内容一致|
|`git diff --check`|0|

本轮没有行为代码修改，未重复 F1-01 已执行的 464 项测试或旧模型门禁。
本轮检查是局部产物验证，不能替代人工接受。

## 证据路径

均位于 `tmp/docx-demo/f2-01-20260921/`，正文/图片只在私有产物中保留：

- A：`source-page-1.png`、`before.docx`、`after.docx`、`word-edit.docx`、`word-inserted.docx`、`word-page-{1,2}.png`。
- B：`case-B/source-page-{4,5}.png`、`case-B/before.docx`、`case-B/after.docx`、`case-B/word-edit.docx`；`case-B/native-jobs/` 保留未人工修订的原生自动输出。
- `frozen-ir.json` / `render-plan.json` 与 B 同名文件：每组前后共用输入；`before/` / `after/` 中保留实际来源图、DOCX 与 source-map。
- `summary.json`：唯一汇总、三项归因、selected_optional_tasks、业务覆盖与 Word 状态；`verification.json`：保存检查和输出哈希；两份 `preservation.json`：执行前文件集。
- `case-b.log`：原生解析/导出执行记录；三个局部脚本仅为本轮复现，未建立新评测服务或数据集。

## 风险与下一步

`selected_optional_tasks = [P2W-F1-04]`，状态 SELECTED_NOT_EXECUTED，只选 A-L1 图组一片。
B-S1/B-S2 后置，不删除，也不通过。F2-02/F2-03 本轮不执行。
历史 U1 INCONCLUSIVE/PENDING、SDK NOT_RUN、probe_c=false 不变；未比较或宣称 MinerU SDK 能力。
生产默认、服务、FRP、正式样本清单和源资产保持。本轮到 F2-01 停止，产品/用户接受仍 PENDING。
