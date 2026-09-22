# P2W-F1-04：选项图源行排布切片

基线/本轮先行提交：`e1eef44`（F1-01 样式修复及 F2-01 归因），按用户要求本地提交，未推送。
F1-04 本轮代码保留未提交 diff。范围仅 F2-01 选中的 A-L1；局部工程与实际 Word 改善已核验，整体原页还原及用户接受仍 PENDING。

## 修改

- `planning/figure_rows.py`：在最终容器宽度确定后，检查既有 option_grid 的 2–4 个图。只有来源图框明确、图框与资产 source_bbox 一致、横向顺序不重叠、共同纵向交集达到最小图高的一半、标签为短 A–D 标记、自然图宽可容纳时，规划单行。该阈值是保守排布规则，不是质量验收线。
- `planning/flow.py`：调用局部规划。只读取原 IR，保留来源 bbox、阅读顺序、关系、人工锁及样式。
- `specs/render-plan.schema.json`：Group 增加可选 figure_layout，记录 columns、basis、reason、figure_ids。basis 区分 source_based / estimated / existing_group；没有声称模型图框是精确真值。不迁移旧计划。
- `writer.py`：Flow 消费已规划列数，继续使用现有无边框表格、可编辑标签与 inline figure。Legacy 默认、源图裁切和正文样式不变。
- `tests/demo/test_option_row_layout.py`：12 项回归，包括源同排正例、真实两行构造例、重叠/倒序、未知几何、资产框不一致、宽度不足、显式两列、长标签、人工锁、行内标签占位和 Legacy 对照。

宽度检查与 writer 的 16pt/30pt 单元格留量一致，不通过缩小图像来塞入一行。
不改表格识别、公式、全页分页、边距、字体比例或模型；不把所有选项图强制改成四列。

## 验证

|命令|结果|
|---|---|
|`uv run pytest tests/demo/test_option_row_layout.py -q`，修复前|退出 1；10 failed / 1 passed；Legacy 对照保留|
|同命令，最终|退出 0；12 passed；`targeted-final.log`|
|`uv run pytest tests/demo tests/productization/test_flow_planner.py tests/productization/test_style_profile.py tests/productization/test_columns.py tests/productization/test_renderer_boundary.py tests/productization/test_reconstruction_regression.py -q`|退出 0；427 passed；之后补充行内标签留量边界，定向 12 项再验退出 0|
|`uv run ruff check .`|退出 0|
|`uv run mypy prototypes/docx_output/planning/figure_rows.py prototypes/docx_output/planning/flow.py prototypes/docx_output/writer.py tests/demo/test_option_row_layout.py`|退出 0；4 files|
|`uv sync --locked --offline`|退出 0；无网络安装|
|`PYTHONPATH=. uv run python tmp/docx-demo/f1-04-20260921/replay.py`|退出 0；真实同源前后与构造两行对照，socket connect/connect_ex 阻断|
|`PYTHONPATH=. uv run python tmp/docx-demo/f1-04-20260921/verify.py`|退出 0；来源及历史文件集保持；交付 RenderPlan 与最终代码重算一致|
|`git diff --check`|退出 0|

既有 Starlette 弃用警告保留。未重跑模型门禁、未扩充真实 case；本轮模型请求 0。

## 证据与实际 Word

私有目录：`tmp/docx-demo/f1-04-20260921/`。

- `source-page-1.png`、`case-A-before.docx`、`case-A-after.docx`：复用 F1-01/F2-01 同一数学试卷物理第 1 页。冻结识别内容与 14pt/Arial/Songti SC 显式 profile 相同；新旧 writer 只有本切片差异。
- `case-A-frozen-ir.json`、`case-A-render-plan.json`：四个图 `p0-ovis6/8/10/12` 规划 columns=4，basis=source_based。模型图框来源保持 Ovis，不伪造原生字符框。
- `before-word-page-1.png`、`after-word-page-1.png`：两份 DOCX 均在 Microsoft Word 实际打开。前者选项图 2×2，后者 1×4；图片完整，没有观察到重叠或裁切。第 2 题起点上移，恢复局部源行关系。
- `case-A-word-inserted.docx`：第一选项标签插入 F104 后实际保存的副本。`case-A-word-edit.docx`：撤销、保存、关闭、按路径重开后的副本；`after-word-page-2-reopened.png`：重开后末页实图。
- `verification.json`：前后正文顺序、拼接公式文本、书签、原图字节、图片 extents、纸型完全相同；source-map 的实际 payload 范围和关系保持。Word 保存副本的正文/数学文本/书签/图片及尺寸一致，不声称其 OMML 内部 XML 字节未重写。
- `control-two-rows-{before,after}.docx`：明确标记的构造两行对照，document.xml 字节一致；它不是第二份真实质量验收页。真实页原有三图 shared_row 不受本规则影响。
- `evidence.json`：原作业、F1-01/F2-01 文件集校验，均保持不变。脚本、日志及 source-map 同目录保存，不写入公开正文证据。

Word 前一轮“打开”按钮不可用通过 Finder 按路径打开绕过；本轮实际保存重开成功。
这只更新本轮验证事实，不倒改 F2-01 当时的 NOT_RUN/NOT_VERIFIED，也未趁机执行 case B 新任务。

## 页差、风险与下一步

|项目|源页|before Word|after Word|结论|
|---|---|---|---|---|
|选项图第 1 题|1 行 4 图|2 行 2 列|1 行 4 列|局部原行关系改善|
|页数|1|2|2|未恢复整页分页；其他选项仍纵排，正文/标题和间距均沿用当前 profile|
|字号/图像尺寸|扫描原始字号未知|既有推断 profile / 自然图宽|相同|未靠缩小正文或图像换取横排|

只核验一个有证据的排布因素；标题、文字选项、原分页、答题留白等并未据此获得完整验收。
B 的单元格拓扑与复合图归属缺口仍保留，不能通过本次图组排布解决。
下一步建议围绕 B 的原生结构缺口做有界本地补证，再决定是否需要 F2-02；不默认新增模型。
本轮不执行其他 F 任务，不切生产 profile，不修改 U1 INCONCLUSIVE/PENDING 或历史接受状态。
