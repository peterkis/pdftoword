# P2W-F1-01：行内公式前后文字样式贯通

基线 HEAD：`a18092a87071cf2415dcabd5c3ca5f095f758159`。
执行范围：v3.1 `prompts/00_START.md` / F1-01；仅本地未提交 diff。
工程回归已验证；Word 已执行有限检查，保存重开未核验；用户/产品接受 PENDING。

## 修改

- `prototypes/docx_output/writer.py`：原 inline_parts 分支只 `add_run(text)`，跳过普通正文使用的样式函数。现在先验证 parts（含公式 source_text）与 plain_text 的完整字符序列，再验证源 runs 的完整序列，按精确字符区间与来源 run 边界拆分，复用 `set_run_style`。Flow 使用既有规划样式；Legacy 使用已有来源样式与显式默认回退。覆盖中西文字体、字号、粗斜体、下划线、上下标。
- source-map 增加 `inline_text_spans`，记录字符区间、来源 run 索引、source_ref 与样式依据，不复制正文。无证据或源 runs 不匹配时使用输出样式继承，无法对齐的范围为 null，不通过搜索重复字符串猜测位置。
- `tests/demo/test_inline_styles.py`：9 个回归覆盖混合中英、多来源边界、连续公式、空格标点、锁定/非锁定、缺失/过期样式、OMML、图片回退和真实 payload 书签范围。导出测试阻断 socket connect/connect_ex。
- `docs/development-plan/README.md`：仅顶部追加当前 v3.1 路径/入口，历史正文保持。

没有修改公式转换、几何、表格、模型、服务、FRP 或生产 profile 默认；没有 Git 写操作。

## 验证

|命令|退出码/结果|
|---|---|
|`uv run pytest tests/demo/test_inline_styles.py -q`（修复前）|1；4 个用例复现两段文本未按样式边界拆分|
|同命令（修复后）|0；9 passed|
|`uv sync --locked --offline`|0；沿用现有锁定依赖，无网络安装|
|`uv run pytest tests/demo -q`|0；326 passed，1 个既有 Starlette 弃用警告|
|`uv run pytest tests/productization/test_{native_reflow,flow_planner,acceptance_harness,reconstruction_regression,renderer_boundary,style_profile,columns}.py -q`|0；138 passed，1 个既有弃用警告|
|`uv run ruff check .`|0|
|`uv run mypy prototypes/docx_output/writer.py tests/demo/test_inline_styles.py`|0；2 files|
|`PYTHONPATH=. uv run python tmp/docx-demo/f1-01-20260921/generate-both-sides.py`|0；禁 socket 导出，同源文件 inventory 不变|
|`git diff --check`|0|

未机械重跑模型门禁或全仓历史 tmp 的类型检查；本轮模型请求 0。

## 证据

私有根目录：`tmp/docx-demo/f1-01-20260921/`。可直接检查：

- `both-sides/constructed-before.docx` / `constructed-after.docx`：构造例，不计真实质量。旧输出丢失来源 run 的直接样式；新输出保留 14/12/10pt、多字体与强调属性。
- `both-sides/real-region-before.docx` / `real-region-after.docx`：既有数学试卷冻结作业的 `p0-ovis28`、`p0-ovis39` 两段，公式两侧都有正文，未人工修正文。使用原有 `plan_flow` 与新旧 writer，输入 IR/RenderPlan 相同；原作业及 auto 不改写。来源入口记录在私有 `generate-both-sides.py` 和 `both-sides/evidence.json`，调用现有 `verify_source` 验证图像来源。
- G2 优先检查结果：该作业只有两处纯公式 inline_parts，无邻接正文，不用其证明本项收益。转用既有数学试卷来源，不建新数据集。
- 真实片段没有实测源 runs，采用明确指定的 14pt / Arial / Songti SC 输出 profile；只能核验继承链，**不证明恢复了真实源字体，也未证明可见布局改善**。实测源样式修复收益由构造例支持。
- `constructed-word.png`、`constructed-before-word.png`、`both-sides/real-word.png`：实际 Microsoft Word 窗口截图。构造例可见上下标、斜体和下划线；真实两段公式与正文正常显示，未观察到重叠/截断。两段是局部诊断，未包含关联题图，不计题图关系质量验收。
- `both-sides/real-region-word-inserted.docx`：Word 插入 EDIT 后实际保存的独立副本；`real-region-word-edit.docx`：撤销再保存副本。正文恢复、书签名称和媒体保持，公式文本拼接一致；Word 重写了数学文本节点拆分，因此不声称 OMML 字节/结构完全不变。
- 保存关闭后 CUA 连续返回 ScreenCaptureKit `-3811`，**重开 NOT_VERIFIED**。不是 Word 未安装，也不是完整 Word 验收。未导出 Word PDF；未用其他渲染器冒充 Word。
- `verification.json`：新旧输出正文顺序、数学 token、书签与媒体一致；Word 副本区别另列。`both-sides/evidence.json`：原文件集哈希、零网络导出结果；所有 before/after 与冻结 IR 独立保存。
- `red.log`、`tests.log`、`planning-tests.log`、`ruff.log`、`mypy.log`：自动检查记录。第一次类型/格式检查发现问题后已修正，再次检查退出 0。

根目录早先 `real-region-*` 是仅公式前有选项标签的初步对照，保留作历史；本次交付以 `both-sides/` 为准。未覆盖先前产物。

## 风险与下一步

- 只解决 writer 样式传递，不能据此解释全部分页异常；真实源样式恢复、整页布局与关联题图仍不在本轮证据范围。
- 输入没有可核验的完整文字/run 对应关系时保守继承，不猜源字体；现有不支持公式的诊断与回退保持。
- Word 保存重开、Windows、完整产品接受保留未核验状态。源 DOCX 不受 Word 编辑影响，编辑均在副本。
- U1 INCONCLUSIVE/PENDING、SDK NOT_RUN、probe_c=false 及历史收尾不变。
- 本轮到此停止。下一建议 F2-01，仅查看最多两个目标 case，不自动执行。
