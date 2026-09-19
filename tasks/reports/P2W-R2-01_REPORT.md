# R2-01 原生段落重建与 Word 校对

2026-09-19。HEAD `a81c4e6`，分支 `codex/r2-01-native-paragraphs`。R1-07 `9006988` 与 R1-08 `a81c4e6` 已分别提交；本阶段代码未提交、未推送。

工程状态：**VERIFIED（限定于下述保守重建范围）**。用户接受仍为 PENDING；完整产品视觉与发布接受仍 WITHHELD。没有把 R1 的已知限制写成已解决。

## 修改

- `prototypes/docx_output/planning/paragraphs.py`：不可变原生观察账本、稳定 source_span_ids、先按测量空隙划分区域再组基线、同行标签组合、保守多行段落候选、首行/悬挂缩进依据及独立原子守恒校验。
- 拆合产生新 block ID；没有拆合且类型不变的块保留原 ID 和完整候选。新组合候选明确记为原生 run 精确拼装；原始 block、原候选、来源引用、run 字体/上下标属性与原顺序全部保留在账本。每个原块恰好覆盖一次，原始 run 序列无字符改写。
- 字号、行距、行末覆盖、缩进与标点共同约束组合。题号（包括无空格题号）、选项、标题、人工锁、现有关系端点、组与图形边界保守处理；方向/行证据不足或图形纵向重叠时弃权。不同字体资源 tag 本身不阻止同字号组行。
- `reconstruction.py`：几何选择之后、公共结构处理之前运行 builder 和独立守恒校验，保存 `native-paragraph-ledger.auto.json`；reviewed/finalized 路径不重复自动拼装。
- `structure_processors/bridge.py`：透传真实 lines 和 `_paragraph_boundary`。继续实际调用 DocVortex 公共接口；业务代码不导入上游私有段落模块。
- `planning/flow.py`、`writer.py`、`specs/render-plan.schema.json`：传递并实际写入首行/悬挂缩进，不添加占位空段。
- `tests/productization/test_native_reflow.py`：16 项原生观察、原子变更拒绝、同 Y 双栏、不同字体 tag、中英/数字/连字符/上标字符、正负缩进、题/选项/锁/结构障碍及公共续接边界检查。

## 复用决定与边界

本地工作是从真实单行观察构造原生段落候选。公共 `model_json_to_middle_json` 负责后续共享续接，`continues_prev` 仍须通过现有来源/关系守恒 gate 才能成为自有关系。没有复制上游段落引擎，也没有重复行、假框或虚构源页号。

两个真实单页样本公共跨块续接均为 0，不能把本地候选组合归功于上游。另行封存实际公共 API 的合成多行探针：相邻物理页正例 1 次续接，题目、人工锁、非连续页 3 类拒绝；测试中另有跨栏及缺行证据负例。这是公共实现验证，不是真实跨页产品验收。

不删连字符、不做全半角或连字归一化。消除原块边界属于结构重组，不修改 run 字符；原观察中的任何实际空格都保留。图注关系不根据框包含自动创造。

## 验证

实际命令与日志在 `tmp/docx-demo/r2-01/checks/`：

| 命令 | 结果 | 日志 |
| --- | --- | --- |
| `uv sync --locked` | exit 0 | `final-sync.txt` |
| `uv run pytest -q` | exit 0，1583 passed，1 个既有 Starlette 警告 | `final-full-tests-v3.txt` |
| `uv run pytest tests/productization/test_native_reflow.py -q` | exit 0，16 passed | `final-native-tests.txt` |
| `uv run ruff check .` | exit 0 | `final-ruff.txt` |
| 变更模块与测试的 `uv run mypy` | exit 0，5 个文件 | `final-focused-mypy.txt` |
| `uv run mypy .` | exit 1，只有既有私有 R1-05 临时脚本的 2 个错误 | `final-mypy.txt` |
| `git diff --check` | exit 0 | 当前工作树 |

全仓 mypy 的既有错误为 `tmp/docx-demo/r1-05/trace-public-calls.py:15–16` 的 counts 类型与函数注解；没有增加 ignore 或删除证据来遮蔽。

首次全套检查出现 7 项 ID 回退契约失败，已通过保留未拆合单块修复；失败日志 `reflow-full-tests.txt` 保留，相关 33 项回归成功记录在 `regressions.txt`。

## 实物校对与证据

只使用两个封存电子 PDF 作业，新增真实模型请求 **0**。旧作业文件集及全部 hash 在新旧比较后不变。

| 样本 | 原块 → 新块 | Word 页数 | 实际观察 |
| --- | --- | --- | --- |
| native4，源物理页 4 | 63 → 33 | 2 | a)–f) 恢复为各自正文的同行标签；多行列表采用悬挂缩进，未串到下一选项 |
| native25，源物理页 25 | 23 → 10（含 2 个图块） | 2 | 正文连续重流；完整主体图与三行图注在同页；正文越过图形时不拼成一个段落 |

已用电脑工具在 Microsoft Word 16.113.1 中打开本地副本，自动保存关闭，导出实际 Word PDF，并逐页对照两张原页图检查全部 4 个输出页。未发现新增裁切、图像变形或图文重叠；不据此声称字体或分页已复原为源 PDF。

native25 实际执行插入一行长度文字、删除/撤销、整段重排、恢复独立段落边界、撤销、保存关闭与重新打开。文字和图片自然下移。最终恢复后 10 个段落逐字相同，来源书签中的正文与图片 payload 再次独立核验。早期 v1 的手动删除曾遗留一个空格，已检测、留证且不作为交付副本；最终 v2 精确还原。

最终代码补充无空格题号边界后重新生成独立作业，全部 DOCX ZIP 部件（除 core 时间元数据）与已在 Word 校对的 v2 完全相同；没有将未核验的布局改动套用旧截图结论。

私有证据入口：

- `tmp/docx-demo/r2-01/final-verification.json`：最终源码 hash、输入文件清单、输出各文件 hash、原子覆盖与包核验、Word 对照与接受边界。
- `real-reflow-final/manifest.json`：两个最终作业的精确路径；各作业包含 `auto.docx`、`layout.auto.json`、`render-plan.auto.json`、`source-map.auto.json`、段落账本及结构执行报告。
- `final-public-probes/`：真实公共 API 的输入、执行结果及候选，全部明确为合成几何探针。
- `word-review/native4-v2-word.pdf`、`native25-v2-word.pdf` 及对应逐页 PNG：实际 Word 渲染。
- `word-review/native25-v2-inserted.docx`、`native25-v2-reordered.docx`、`final-roundtrip/audit.json`：编辑过程与恢复后来源范围核验。
- R1-08 的 before DOCX/PDF 继续封存，不覆盖；本轮早期候选及失败诊断也保留。

## 风险与后续

- 只采用证据充分的水平单行原生观察；已混在单个不可靠框中的双栏、复杂环绕、多方向文字、组与既有关系保护区不强行重建。双栏正确性目前有几何反例测试，未声称覆盖所有真实复杂双栏文档。
- 自然分页仍是每个源页输出 2 个 Word 页；native4 末尾列表延续到第二页。页眉页脚角色、精确字体复原和三行图注的进一步结构恢复仍有改进空间。
- 技能的捆绑 `render_docx.py` 已运行，但捆绑 LibreOffice 输出漏显中文，目视判定失败，不能替代 Word 验证。没有为了使该渲染器好看而改正文或分发字体。
- native4 Word PDF 提取正文去除布局空白后完全相同；native25 在一个行末连字符将 ASCII `-` 提取为 U+FFFE。原图、Word 页图中该连字符可见，DOCX 字符与来源 payload 完整；PDF 文本提取仍记为有发现，不静默归一化成 PASS。
- R1-03 的内容回退/字体问题以及真实几何正向采用验收缺口继续独立保留；本阶段不赋予完整产品接受或发布接受。
- 回滚只需停用 reconstruction 的原生 paragraph builder，或使用封存的旧策略作业；不回滚原文件、模型响应或人工修订。

下一任务建议按计划进入 R2-02；本轮没有提前实现该阶段，也没有提交或推送代码。
