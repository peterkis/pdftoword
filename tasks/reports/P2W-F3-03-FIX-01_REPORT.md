# P2W-F3-03-FIX-01：N1 原生网格区域唯一输出

日期：2026-09-21。承接用户“继续推进”及 F3-03 唯一下一修复建议。
状态：N1 表2重复输出的局部修复已有工程及 macOS Word 显示证据；用户接受仍为 **PENDING**。未进入 F4-01、Beta 或发布。

## 修改

基线 HEAD：`e1eef44f8cd45b08e081ade3603cc31cbf9db25e`，分支 `codex/r2-03-columns-order`；已有 F1-04/F2-03 未提交修改原样保留。本轮未提交、未推送。

- `prototypes/docx_output/input_analysis.py`：从 PDFium 读取实际路径端点及对象/祖先变换。仅为不透明、非白色、实线描边的两点直线路径提供 `solid_line` 证据；包围框本身不证明线网格。
- `prototypes/docx_output/native_grid.py`：最少三条横线、三条竖线；每条横线与每条竖线的笔画范围相接，端点限定在外边界，网格内每个文字 run 完整归属唯一格，所有格有 run。曲线、未知路径、图像交叠、断线、跨格文字、空单元格或不完整外框均保守不处理。
- `prototypes/docx_output/native_pdf.py`：经上述证据确认的局部网格只输出一张源裁剪，类型为 `table`、策略为 `preserve_image`，发出 `NATIVE_RULED_GRID_IMAGE_FALLBACK`。原生文字、字体、bbox、run ID、逐格归属和路径 ID 保留在候选证据及 provenance；完整 observation 仍在。其他文字和区域沿用原路径。
- `tests/demo/test_native_grid_fallback.py`：10 个回归案例，覆盖完整网格、上述拒绝情形、紧邻表下正文，以及 legacy / fidelity 两种输出入口的 DOCX 与 fallback 来源记录。

这是共同 native 提取层的局部修复，两个输出 profile 均使用它；默认 profile、配置、依赖锁文件没有改变，未把候选切为默认。没有按页号、文件哈希、表题或标注内容设置特例。

## 验证

源为 WS/T 305—2023 物理第6页，沿用 F3-03 的原 PDF。转换不读取 batch4 标注。N1 已参与本轮调试，不能再算独立验证页。

| 检查 | 实际结果 |
|---|---|
| 原路径证据 | 12 条线，8×2 网格，16 格含17个原生 run |
| 内容候选守恒 | 全页62个原生 run 在输出IR来源中各归属一次；网格内17个run的正文及bbox逐项与observation一致 |
| 局部输出 | 原先40个块 → 31个块；8个重复文字行及2张表/底边裁剪合并为1个表格降级对象 |
| 图片保真 | 新表图与旧完整表图资产 SHA-256 相同，未重画 |
| DOCX | 全页1张图片，0个 `w:tbl`；source-map 的每个 bookmark 均包围实际正文或图片；表图 `fallback=true` |
| 实际 Word | macOS 26.6.2，Word 16.113.1（16.113.26091740）；打开全部输出页并通过本地打印 PDF 导出；原2页→现1页 |
| 视觉检查 | 表头、全部8行、左右边界及底边可见；表格只出现一次；表题及表下正文保留；未发现该局部遮挡裁切 |
| 邻接正文编辑 | OOXML保留可编辑文字；补充的实际Word编辑/保存/重开 **NOT_RUN**，桌面工具连续发生捕获连接失败；保留未改动的诊断副本，不借用F3-03的N2编辑记录冒充本次结果 |
| N2/N3/N4回归控制 | 三页均未触发新规则；各自 `word/document.xml` 与媒体哈希和旧F3-03完全一致；本轮未重做三页Word视觉验收 |

曾在中间输出发现该表图被记为普通 figure（`fallback=false`）。新增断言先产生 1 failed / 8 passed，再改为 table 图片降级。最终输出的全部 `word/` 包内容（XML、关系、样式和媒体）与已由 Word 显示/打印的中间副本逐字节一致，因此复用其 Word PDF；修正影响来源/质量分类，不改变 Word 展现。中间作业保留，最终交付位于 `final/`。

没有将页数恢复为1页当作布局合格线：页眉/页码位置、字体、字号视觉与段距仍与源页不同，布局仍为 **LIMITED**。整表保图后，表内文字不能在 Word 单元格中修改；可编辑表格仍为 **UNSUPPORTED**。本轮关闭的是 N1 局部重复内容问题，不是普通表格能力缺口。

命令与收据：

| 命令 | 退出码与结果 |
|---|---|
| `uv sync --locked --offline` | 0，环境审计，未联网安装 |
| `uv run --locked pytest -q` | 0；最终1708 passed，1条既有Starlette弃用警告，71.52s |
| `uv run --locked ruff check .` | 0 |
| `uv run --locked mypy prototypes/docx_output/native_grid.py prototypes/docx_output/input_analysis.py prototypes/docx_output/native_pdf.py` | 0，3个源文件 |
| `uv run --locked mypy .` | 2；历史临时目录两个 `writer-before.py` 同名模块导致检查中断，不宣称全仓类型检查通过 |
| 现有 CLI `convert --mode native --pages 6/7/24/26 --output-profile fidelity-v3.1` | 中间与最终各4次，共8次，全部0；最终单作业墙钟约0.48–1.54s，非性能分位数 |

生成子进程使用 socket connect/connect_ex/create_connection 拒绝钩子，连接尝试日志为空；8个作业模型调用计数均0。该监测不覆盖Word/macOS后台网络，不能据此声称整个桌面零网络。未调用OCR或外部模型，未安装权重/服务或修改FRP。

## 证据

私有根目录：`tmp/docx-demo/f3-03-grid-fix-20260921/`（源内容及产物不进入Git）。

- `baseline.json` / `baseline.diff`：实际HEAD、原有工作区哈希及diff；准备后快照时间17:05:32，报告整理约17:19，约14分钟，不含先前F3-03验收时间。
- `final/N1/auto.docx`：最终自动输出；`final/N1/word-render.pdf` / `word-page-1.png` / `word-screen.png`：真实Word导出与显示证据。
- `final/cases.json`：实际CLI、源哈希、job路径、退出码、耗时及RSS；`final/jobs/`：IR、RenderPlan、候选、assets、source-map。
- `final/verification.json`：run守恒、媒体、来源范围、回退分类及N2–N4控制结果；独立DOCX reader仍报 `UNSUPPORTED_TEXT_POSITION`，没有把其空列表当作无内容或成功，另用原始OOXML与Word核验。
- `red-fallback.log`、`final/pytest.log`、`final/ruff.log`、`final/mypy.log`、`final/mypy-all.log`、`final/checks.json`：实际检查收据。
- `preservation.json` / `final/preservation-final.json`：原PDF、标注、F1-01/F1-04/F2-01/F2-03及F3-03证据文件集合保持；所有证据载荷哈希不变。唯一例外是Finder浏览后更新旧F3-03目录的 `.DS_Store`，已显式列出，未伪称所有文件字节不变。既有dirty文件逐项哈希不变。

旧F3-03报告及结论不改写；本报告是后续修复附录。

## 风险与下一步

保守规则不支持合并格、真实空单元格、复合路径、曲线/斜线、虚线、未知交叠以及无法唯一归属的文字；此时维持旧路径及既有问题提示。N3/N4重复内容、B分类图连接关系等原发布阻断仍在。合同、真实操作手册、mixed和Windows没有增加覆盖。

**一个下一修复建议：N3（物理第24页）多表区域的输出归属。** 先核验其实际路径及表间边界，处理重复表图/文字/线段；不要直接放宽本轮守卫、误并相邻表或把真实空单元格当作可删内容。继续优先关闭内容/关系阻断，暂不建议进入F4-01。
