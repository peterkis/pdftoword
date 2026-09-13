# DEMO-001 — 本机 DOCX 输出验证原型

> 用户审阅后已完成 0.2.0 公式重建修正，见文末更新。下文首轮 0.1.0 数字保留为历史结果。

```ini
DEMO_EXECUTION = READY
AUTO_OUTPUT_QUALITY = REVIEW_REQUIRED
WORD_VISUAL_REVIEW = PENDING
PRODUCTION_READINESS = NOT_CLAIMED
```

已交付能启动的本机工具、真实试卷的 auto.docx、简单电子 PDF 的 auto.docx，以及真实浏览器操作产生的 reviewed.docx。READY 指本机原型可执行；不表示自动内容完全正确、live 已重新实测或用户已接受 Word 效果。

## 起点、分支与只读边界

开始执行并记录了：

```text
git status --short --branch
## main...origin/main

git log -4 --decorate --oneline
b147cda (HEAD -> main, origin/main, origin/HEAD) Merge pull request #2 from peterkis/feat/t0016-raster-regression
eb53255 fix(t0016): guard references and separate failed latency
155ac61 test(t0016): close raster regression with quality findings
db3439a Document partial T0016 raster regression evidence

git rev-parse HEAD
b147cda6c155544d5e0f265c620c67a03c5614bd
```

工作区开始时干净。GitHub `gh pr view 2` 核验 PR #2 为 MERGED，mergeCommit 为上述 b147cda，合并时间 2026-09-11T06:24:03Z。已从这个 main 创建 `proto/docx-output-demo`。整改提交 eb53255 和上一版本 155ac61 均在本机历史中；空白 confirmed 拒绝、成功/失败耗时分离、Gate B 后延续 ADR-006 保持不变。

本轮没有 commit、push、创建 PR、merge、amend、reset 或 clean。demo 不加入 PR #2。没有修改发现/评测代码、历史工具哈希、真值、协议、评分或公共 T0016 指标。历史两次 run 加已跟踪 model_contracts 夹具的本轮起止 **129 个文件哈希一致、文件集合一致**；私有证明在 `tmp/docx-demo/history-audit.json`。T0015 的已跟踪规范/来源夹具和两个评测脚本没有工作区 Diff；不宣称额外重跑了 T0015 私有 70 文件验收。

## 实际交付与输入来源

作业均位于忽略目录 `tmp/docx-demo/jobs/`，以下只列相对路径，不公开个人绝对路径或原文。

| 作业 | 文件 | 输入/来源 | 修正 |
| --- | --- | --- | --- |
| `demo-920fe16a52e3400e95c4c865352b3d72` | `auto.docx` | 真实数学试卷；`t0016-mac-20260911T030753Z-r2`；三家 JPG / repeat 1 | 无 |
| 同上 | `reviewed.docx` | 同一 auto IR 和源资产 | 1 次代理演示操作：在原图选项边界拆开 C/D；有原因和 offset，非用户验收 |
| `demo-b1fcc167c1894b1bbf6be7e13253f04e` | `auto.docx` | 自有 synthetic 中英文电子 PDF，1 页、两道短题、普通矢量图形 | 无 |

调试时较早的 `demo-e69928eb15114db4b1a250291a2f2946`（Replay）和 `demo-19445d1fc64e4e45843e3357af94606f`（synthetic native）也留在本机，没有覆盖它们的 auto.docx。首个 Replay 先于 Native、UI 和 live bridge 完成。当前检查与建议打开的交付物为上表作业。

Replay 校验指定 JPG SHA-256 `fe608629ae8af60890684c77437b3d62facd3a0c27b9fa019692890f96cbcf52`，根据 requests 的 provider/variant/repeat 唯一选择完整响应，核对 seal 及 request 记录的输入、裁剪媒体后响应、prediction 哈希。记录 source_run_id、request_id、历史采集工具 v1.1 哈希和当前 demo 版本；没有要求历史工具等于当前评测 v1.2，没有重评/推广或回填新 uv.lock 哈希。导入器不依赖文件遍历顺序，也没有读取 ground-truth、参考转录或 overlay 正文。

## 可观察结果

| 指标 | Replay auto | Replay reviewed | Synthetic native auto |
| --- | ---: | ---: | ---: |
| 本轮真实模型调用 | 0 | 0 | 0 |
| 可编辑文字字符 | 428 | 428 | 73 |
| OOXML 文字字符（含空白） | 442 | 442 | 73 |
| 唯一图域资产 / 放置图域 | 7 / 7 | 7 / 7 | 1 / 1 |
| 原生 OMML 公式 | 0 | 0 | 0 |
| 公式区域图片 | 14 | 14 | 0 |
| 完整局部文字块图片降级 | 0 | 0 | 0 |
| 公式/降级 bbox 并集占选中页面面积 | 3.0139% | 3.0139% | 0 |
| 有原因的人工操作 | 0 | 1 | 0 |
| 未解决 issue | 28 | 29 | 0 |
| DOCX 包检查 | PASS | PASS | PASS |
| 实际 LibreOffice 输出页数 | 2 | 2 | 1 |

字符计数排除每个段落/内嵌片段首尾空白；面积按每页 point bbox 矩形并集去重，分母为全部所选页面面积。普通配图不算文字降级。以上是组成/完整性指标，不是全文准确率。reviewed 增加了一条人工变更复核项，没有自动把历史问题标记已解决。

- Replay 标题、题干、普通文字与选项标签是 Word 原生段落/run；14 个公式保留原区域图，候选 LaTeX 只供诊断。图中文字不再重复输出正文。
- 原第 2/3 题合并块通过真实 OCR 行首和精确文本后缀切开；没有硬编码题号或坐标。其余若干多选项段落仍合并，已进入队列。浏览器中的一次演示修正拆开第 6 题 C/D，公式图片没有重复或减少。
- 第 1 题四个标签和对应图形形成 2×2 布局表格；共享三图保持原图行。只有有明确图题且题干在输入内的图建立 references；另两图保留 `target_not_in_input`，没有误挂到第 5 题。
- `<`/`≤` 模型候选冲突显式存在。DOCX 中公式源图本身显示原图符号，不以模型文本替换。没有重新提出已撤回的 y→v 误述。
- Native 的源文字经正常空白规则核对无丢失/重复，中文、英文、小于号和普通图形实际可见。此结果只支持有限 native 入口；不是完整 P1 验收。

## 渲染和视觉检查

实际使用本机运行环境已有的 **LibreOfficeDev 26.8.0.0.alpha0，build 2c87e51eeaa2b413ff4ae097b2705eea1995d8e5**，独立临时 profile、参数数组、超时；PDFium 串行生成逐页 PNG。没有安装 Office/LibreOffice，也没有云转换。

首次渲染发现中文空白/方框。为该作业的渲染进程写入私有 fontconfig 配置，引用本机已有字体目录后重渲染，中文恢复；没有复制或分发字体。DOCX 指定宋体 Songti SC 与 Arial，Raster 字号/样式明确是推断。Native 保留可提取字号/字体信息，实际字体替代仍以渲染器为准。

已查看 Replay auto 两页、reviewed 第二页及 synthetic native 一页；reviewed 第一页与已查看 auto 第一页 PNG 字节哈希相同。七图逐一对照源图可见，未见新增裁断、丢图、内容重叠、表格越界或额外空白页。图题与图片同单元格。自然分为两页，第二页留白较多；未以压小字号强行凑一页。仍需用户评估公式图片大小、图选项排布和文字阅读效果。

这是 **代理对 LibreOffice 实际页面的检查**，不是本机 Microsoft Word 或用户人工验收。`visual_review_status`/`WORD_VISUAL_REVIEW` 保持 PENDING，QA 另存 agent_render_review。HTML 结构预览不充当 Word 渲染。

## 启动、审阅与复现

```sh
uv sync --locked
uv run --locked python scripts/docx_demo.py serve --host 127.0.0.1 --port 8765
```

打开 `http://127.0.0.1:8765`，在已有任务下拉中选择上表 ID；点击块定位源区域，输入原因后编辑/候选接受/拆分/合并/移动；可拖出裁剪框、选择语义关系与渲染策略。保存后下载 reviewed，auto 原样保留。浏览器实操已验证选块、原因输入、公式段拆分、保存另存和零模型计数。

复现本轮留痕修正导出：

```sh
uv run --locked python scripts/docx_demo.py export \
  --job-id demo-920fe16a52e3400e95c4c865352b3d72 --revision reviewed
uv run --locked python scripts/docx_demo.py render \
  --job-id demo-920fe16a52e3400e95c4c865352b3d72 --revision reviewed
```

完整三个入口、合成样本生成、文件清单和无 renderer 时的 Word 打开步骤见 [原型 README](../../prototypes/docx_output/README.md)。

## live 与验证证据的界线

Raster live 入口已实现并通过冻结请求/响应 Schema、授权、串行预算、无 Authorization、回环地址限制、成功缓存、错误响应与断连缓存的离线测试。**本轮真实 live 调用为 0，未验证当前 FRP 服务连通性或真实新推理质量**。用户要使用时必须显式选择输入、模型发送授权和无鉴权确认；扫描 PDF 另需确认。默认每页 PP 一次，可选 Ovis/Monkey 各一次。没有运行任何新 T0016 矩阵。

本机完整门禁：

| 检查 | 结果 |
| --- | --- |
| `uv sync --locked` | PASS |
| `uv run --locked pytest` | 227 passed；新增 36 项 demo 测试 |
| `uv run --locked ruff check .` | PASS |
| `uv run --locked mypy .` | PASS，41 source files |
| `validate_task_catalog.py` | PASS，97 Ticket 未批量更改 |
| `validate_model_baseline.py` | PASS |
| `git diff --check` | PASS |
| 历史文件字节与集合 | 129/129 不变 |
| `tmp/docx-demo` 文件权限 | 目录 0700 / 文件 0600 |
| 既有锁定依赖版本 | 无升级；仅新增 demo 开发依赖及其传递依赖 |

测试调用真实 pipeline/writer/IR/修正逻辑，覆盖回放与 Native 零 HTTP、旧目录未写、wire 类型、坐标往返与旋转、等比图片/越界、图内文字去重、合并题目可靠与不可靠拆分、无目标题干、公式降级无重复、OOXML 关系、auto 不覆盖、恶意 HTML/路径、会话/同源、导出不重推理、live 成功和失败缓存。保留一条 Starlette TestClient 对 httpx 的弃用提示；没有为清警告升级已有 HTTP 客户端、关闭 strict 或跳过目录。

## 剩余问题与下一步

自动试卷仍需内容审阅：多个选项同段、候选差异和图外题干未提供。人工拆分若没有子行坐标保留父 bbox 并标记近似，不能声称精确定位。Ovis 段落对齐只是候选，不能等同真值。普通图片可保留，复杂表格不可编辑；公式暂未实现 OMML。Native 不保证复杂多栏、混合文字层、编码修复、Form XObject 组合与多页题图语义。

下一项最小改进应由用户打开 auto/reviewed 后选择一个实际妨碍阅读的点，优先收敛选项段拆分与公式行高，而不是更换模型或扩大实验矩阵。一次演示修正并不能证明整卷已经可用。

本轮没有执行 T0017、模型调参/部署、正式 Adapter、统一网关、完整 P1/P2/P3 或正式桌面应用；不将该原型冒充完整产品。


## 0.2.0 — 用户反馈后的公式重建修正

用户指出公式仍是裁剪图片，第六题有裁切问题。检查确认模型响应已有 LaTeX，缺失的是原型的 OMML 写入能力，而不是模型没有识别。首轮采用全部公式图片降级，未充分达到公式可编辑的实际需求。

第六题旧公式裁剪资产在左边缘带入相邻汉字的残缺笔画；原生 OMML 重建后该题干公式不再使用这张裁剪图。没有修改模型原框、历史响应或真值。其他图域裁剪策略没有因此被宣称普遍修复。

新增有限解析器保留分式分子/分母、平方根、上下标和常用符号；未知命令、缺失括号、重复脚本和不支持的根指数明确拒绝并保留图片降级。不进行数学纠错。含关键 ≤/≥ 运算符的自动候选仍保守待复核，避免将已知 < / ≤ 冲突固化为可编辑正文。

新私有作业：`tmp/docx-demo/jobs/demo-8bcb3554f0e042cead7899fa21821327/`。

| 项目 | 新 auto | 新 reviewed |
| --- | ---: | ---: |
| 可编辑 OMML 公式 | 13 | 13 |
| 公式图片 | 1 | 1 |
| 普通图域 | 7 | 7 |
| 模型调用 | 0 | 0 |
| 人工操作 | 0 | 1（显式回放旧 C/D 拆分记录） |
| LibreOffice 页数 | 2 | 2 |

已查看两版全部四张实际渲染页，第六题题干的分式和括号完整，图片残笔不再出现。部分选项之间的间距仍较紧，尚未做整卷选项排版优化；用户 Word 复核仍待完成。旧 auto/reviewed 均未覆盖。新版本只用同一真实响应重建，没有增加模型调用或运行新矩阵。

新增回归先复现原生 OMML 缺失，再验证实际 DOCX 内的分子/分母、根式、上下标、未知语法拒绝及关键符号降级。更新后的全仓门禁结果见本次交付说明。

0.2.0 全仓验证：238 passed（demo 47 项），ruff PASS，mypy PASS（42 source files），uv sync --locked、两个目录/模型校验和 git diff --check 均 PASS。历史 129 文件字节再次核对无变化。保留既有 Starlette/httpx 弃用提示；未 commit/push。


## 0.2.1 — 第六题 D 选项完成原生公式重建

用户继续指出 D 仍是裁剪图片。根因是自动候选的符号冲突保图策略之外，review.replan_text 在明确修正后仍继承旧图片，或把新表达式仅变成普通文本，没有重新进入 OMML 转换。

已修复通用审校路径：有原因的公式编辑/候选接受重新调用有限 OMML 转换；不支持的语法继续保图。自动冲突策略保留，不盲目删除符号审校。代理核对同一源图确认 D 为 x<0，与已有 Ovis 候选一致；将这一来源更正记录为独立 override，保留原 PP 的 x≤0 候选。没有解题、修改 GT 或新增模型请求。

新作业 `tmp/docx-demo/jobs/demo-96dbd7608af543ea8bdf50af18e9da96/reviewed.docx`：14 个原生 OMML、0 个公式图片、7 个普通图域、2 个留痕操作（C/D 拆分及源符号核对重建）。旧文件未覆盖。新 auto 仍保持未审校候选，不能把 reviewed 的更正计作自动识别效果。

实际 OOXML 检查确认 D 段落包含 OMML x<0，且无 drawing；LibreOffice 第二页已查看，D 完整显示，第一页与已检查版本的渲染 PNG 哈希一致。用户 Word 视觉验收仍待完成。新增两个先失败再通过的回归覆盖更正符号和确认原符号两条审校路径。

全仓门禁：240 tests passed，ruff/mypy、locked 同步、两个目录/模型校验和 diff 检查通过；历史 129 文件再次核对未变，未 commit/push。


## 0.3.0 — Ovis 主识别独立输出验证

按用户认可的设计，用同一 COMPLETE run 的 **Ovis / JPG / repeat 1** 生成独立自动结果；仅校验和读取该 Ovis 的历史响应/预测字节及输入 manifest，不读取 PP/Monkey 响应。不加载 GT、旧 overrides 或人工修改文本，不新增模型调用。

推荐打开：`tmp/docx-demo/jobs/demo-319142699c094fafa90f0d1ad631cca1/auto.docx`。较早布局检查版本 `demo-4f24b899e3114e7885c49e35afe59993` 留存，未覆盖。新 Replay 默认 Ovis；CLI `--content-provider pp` 或 UI 选择器可切回旧基线。live 入口本轮没有迁移或调用。

| 指标 | Ovis 独立 auto |
| --- | ---: |
| 实际新模型请求 | 0 |
| 人工 overrides | 0 |
| 普通图片资产 / 放置 | 7 / 7 |
| 可编辑 OMML 对象 | 20 |
| 公式图片 / 局部图片降级 | 0 / 0 |
| 普通可编辑文字字符 | 429 |
| 实际 LibreOffice 页数 | 2 |
| 未解决 issue | 3 |
| 未提供精确 bbox 的文字块 | 38 |

20 是 Ovis 的数学片段个数，包含单独变量和坐标表达式，粒度不同于之前的 14 个 PP 公式框；**不是多识别了六个公式或准确率提高的证明**。3 个 issue 分别为文字几何缺失和两处图题的题干不在输入内；单一 provider 不再生成跨模型差异 issue，数量减少也不代表准确率。

输出观察：第 2/3 题边界清楚，第 6 题 A/B/C/D 自动分段；D 使用 Ovis 原始 x<0，并作为原生 OMML 输出，段落没有 drawing，无需之前的人工修正。七图逐一对照原图检查可见且完整；第 1 题标签按 2×2 表格成组，后方三图保持源图行，仅对输入中存在的题干建立 references。文字对照以同一 Ovis 响应为输入核验，忽略空白与标题标记后全部保留；未用 GT 生成或校正文稿。

首次实际渲染发现第四题题干独留页末、页脚两段。已用通用规则让题干与第一个选项保持相邻，以及合并显式页码短语后重新生成新作业并渲染。两页均已查看，未见公式裁切、图丢失或表格越界；这仍不是用户 Word 视觉验收。

主要代价：Ovis 响应只提供图域 bbox，未提供文字行或公式精确框。IR 中这些文字块使用整页来源范围，并显式标记 unknown；UI 说明橙框是来源页，不是检测出的文字框。未借 PP 精确坐标掩盖这个差异。支持语法直接 OMML 不需要公式裁剪；不支持的表达式因缺少可靠源框明确失败，不输出假精确降级。

工程验证：246 tests passed（demo 55 项），ruff PASS、mypy PASS（44 source files），locked 同步、任务目录、模型基线及 diff 检查 PASS。新增测试覆盖 Ovis-only 导入不读取其他 provider、图标签/公式未知输入拒绝、显式题图关系、页脚合并和题干分页保持。历史 129 文件哈希再次一致，目录权限仍为 0700/文件0600；没有 commit/push、生产角色迁移或新的模型实验。

当前结论：本样本已经支持 **Ovis 独立承担正文、公式及图域输出**，无需 PP 才能生成可编辑 Word；精确文字定位与复杂文档能力尚未替代验证。DEMO_EXECUTION=READY，AUTO_OUTPUT_QUALITY=REVIEW_REQUIRED，WORD_VISUAL_REVIEW=PENDING，PRODUCTION_READINESS=NOT_CLAIMED。

## 0.4.0 — Ovis 内容＋PP 图片/布局区域验证

按用户要求生成混合结果：tmp/docx-demo/jobs/demo-f62b5728e48c4930801e07a18e252c54/auto.docx。同一 COMPLETE run 的 JPG 第 1 轮，读取 Ovis 与 PP 两个响应；新增模型调用 0、人工 overrides 0。较早布局检查版本 demo-a80e294c666840d89c80f5f4144f6bf8 留存，未覆盖。

PP 只贡献区域标签/框、文字行框和公式框几何，不使用其 block_content、rec_texts、rec_formula 进行输出或文本匹配。测试使用 POISON 识别文本验证隔离。实际比较确认所有文字 content 和 inline_parts（含全部 OMML）与 Ovis 独立作业 demo-319142699c094fafa90f0d1ad631cca1 一致；DOCX 内七张图片的字节哈希全部对应 PP 区域裁剪资产。

布局结果：第一题四图改为一行；第 2–5 题均为一行四选项；第六题两行两列；共享三图与图题保留同组；标题/总分/页脚居中。普通正文仍为 11pt，使用正常段落、OMML 和无边框布局表格，无绝对定位文本框或整页底图。首次检查第二题 C 末字换行，已通过纯文字列宽分配修复，未缩小字号。

最终 LibreOffice 实际渲染为 1 页，已查看全部页面，未见裁切、图丢失、公式缺失、表格越界或残留单字换行。与原图结构更接近，不宣称像素级一致或 Word 用户验收。

| 指标 | 混合 auto |
| --- | ---: |
| Ovis 原生 OMML 数学片段 | 20 |
| 公式图片 | 0 |
| PP 图域资产 / 放置 | 7 / 7 |
| 普通可编辑字符 | 429 |
| 未匹配来源区域的文字块 | 0 |
| 仅共享行几何的选项块 | 4 |
| 人工操作 / 新模型调用 | 0 / 0 |
| 未解决 issue | 3 |
| 实际渲染页数 | 1 |

三个 issue 是两幅图的目标题干不在输入，以及第二题四个选项共享一行 PP 几何。后者分列是排版推断，没有按字符数制造来源 bbox。其余文字定位对应 PP 区域，不等同逐字符/逐公式精确定位。

新增几何隔离、共享行/两行布局及人工移动解除布局组的回归；全仓 248 tests passed，ruff、mypy（46 source files）、locked 同步、任务目录、模型基线与 diff 校验通过。历史129文件再次核对未变。仍为可审查工作区变更，未 commit/push，未改写生产角色、历史评测或 live 策略。

## 0.5.0 — 通用规则固化与上传一致性

用户已认可 0.4.0 样本效果，并要求说明视觉调整与泛化边界。此前确有逐页视觉检查，第二题选项末字换行据此修正了通用列宽分配；没有手工改写这份 DOCX 的正文、公式或指定题目坐标。样本反馈参与了规则设计，因此不能将这次结果当作独立泛化验收。

新增 layout_rules.py（layout-rules/1.0）：统一 PDF point 几何、基于中位文字行高的有界容差、区域越界/重复/旋转/多栏预检查、完整映射、题目顺序、唯一放置、文字候选/公式/图域顺序不变等应用后检查。布局在 IR 副本中执行，全部通过后原子应用；异常保留 Ovis 内容与流式输出，记录 LAYOUT_RULES_FALLBACK 和具体原因。每页独立记录 APPLIED/FALLBACK，多页混合为 PARTIAL。这些规则不测量 OCR 准确率。

Replay 与 demo Raster live 现共用 reconstruct，默认 Ovis 内容→PP 几何，串行每页各一次；UI/CLI 已明确方案与发送授权。PP 失败保留 Ovis；Ovis 失败不偷偷改用 PP 内容，标记 PRIMARY_CONTENT_MISSING/DEMO_OUTPUT_INSUFFICIENT。失败缓存不重试，预览与导出不重新识别。没有新增真实模型请求、修改冻结 PP 参数、部署检测专用服务或改变生产模型角色。

验证结果：
- 全仓 279 tests passed（demo 88 项）；新增 31 项包含合成响应的三种尺寸、不同题数、2/4 选项、单/双行，异常几何、内容污染隔离、禁用方向检测的 -1 哨兵、上传成功/主内容失败/几何失败与缓存、多页结果保留。
- uv sync --locked、ruff、mypy（48 source files）、模型基线、任务目录和 diff 检查通过。既有 FastAPI TestClient/httpx 弃用警告仍在。
- 最终回放作业 tmp/docx-demo/jobs/demo-f8c359d844cd49e3a0621498caaa2553：APPLIED，1 页、20 OMML、7 图片、429 普通可编辑字符、0 公式图片、0 人工覆盖、0 新模型调用。实际渲染 PNG 与用户认可的 demo-f62b5728e48c4930801e07a18e252c54 字节一致。
- 开发中 demo-409f3b263a4441e090f5aedaa79ade03 曾因误判 PP 禁用方向检测的 -1 哨兵而降级；已修复并回归。保留该诊断作业，不将其解释成模型质量失败。
- 历史 129 个文件哈希全部一致；私有目录0700/文件0600；没有 commit/push。

当前证明的是同一样本保持输出、离线变体和故障能受控处理。新的真实图片、复杂表格、多栏、未知公式语法和低清晰度内容仍未完成模型泛化验证。规则保障来源与失败可见性，不能保证文字识别永不下降。该样本用户已认可；其他文档仍需审阅，生产验收未声明。

## PR #3 首轮审核修复（2026-09-13）

Codex 对 7e8abff 提出三项意见，均已通过先失败后通过的回归用例修复：Windows 输入路径使用 relative_to(anchor) 保留盘符/UNC 语义；段落合并保留两侧内容候选、来源引用及第二块完整快照，人工候选 supersedes 指向两侧原选择；可选 Monkey 解析/几何失败转为 MONKEY_CANDIDATE_REJECTED 审校项，保留 PP 主输出且不重试。

新增 7 项回归，全仓 286 tests passed，ruff、mypy（49 source files）和 diff 检查通过。Windows 验证为本机模拟 PureWindowsPath 的盘符及 UNC 锚点语义，不声明真实 Windows 应用验收。没有新增模型调用或改写历史证据，等待最新提交的 Codex 复审。

## PR #3 第二轮审核修复（2026-09-13）

复审补充了默认 Ovis 模式可选 Monkey 候选遗漏、人工合并几何来源及自动页码合并候选谱系问题。现各内容路径共用 recover_monkey，合法候选可供 UI 展示、非法候选只记录审校项；人工合并后的 bbox 标为 manual_correction，双方原几何保存在审计快照；Ovis 页码合并保留双方候选并显式 supersedes 双方选择。

新增 6 项用例先失败后通过，全仓 292 tests passed，ruff、mypy（49 files）及 diff 检查通过。无新增模型调用，继续等待最新提交的外部复审。

## PR #3 第三轮审核修复（2026-09-13）

电子 PDF 中与原生文字相交的矢量路径包围框不再压制原生文字，歧义框记录在私有 provenance 并转为 vector_text_overlap_review；保留源页待人工判定装饰边框或真实图域。人工拆分右侧候选显式 supersedes 原选择；包检查把有效 OMML 数学文本计入可编辑输出状态，纯公式页不再误报不足。

新增页框/正文容器、拆分谱系与纯公式 4 项回归，先失败后通过；全仓 296 tests passed，ruff、mypy（49 files）与 diff 检查通过。无新模型调用。歧义矢量分类仍需审阅，未声明复杂矢量图通用识别能力。

## PR #3 第四轮审核修复（2026-09-13）

歧义矢量路径除保留原生正文外也输出参考裁剪，记录 ambiguous_vector_reference 与 VECTOR_TEXT_OVERLAP_REVIEW，明确图内文字可能重复，需人工确定最终边界；避免删除真实带标签矢量图。PP OCR 行框与公式框统一校验页内边界，越界回退。共享图题行增加阅读序列连续性约束，禁止跨越中间正文。

新增4项回归先失败后通过，全仓300 tests passed，ruff、mypy（49 files）与diff检查通过，无新模型请求。歧义矢量参考裁剪是显式待复核保留策略，不声明装饰/图形分类已自动解决。

## PR #3 第五轮审核修复（2026-09-13）

网页上传暂存目录由所属请求/后台任务在结束时清理，覆盖成功、校验失败及后台失败；作业内复制的源文件继续保留。图选项网格按连续阅读序列分组，不能跨过正文。旧PP路径对解析区域、OCR行框及公式框使用前检查页内范围；人工裁剪在创建资产前拒绝页外框，避免源坐标与像素裁剪不一致。

新增6项回归先失败后通过，全仓306 tests passed，ruff、mypy（49 files）与diff检查通过。未进行新模型调用，也未批量清除旧上传目录或其他用户文件。

## PR #3 第六轮审核修复（2026-09-13）

布局验收为文字和图片分组统一增加连续阅读序列检查，跨块组拒绝应用并保留Ovis；旧PP图组选项按阅读顺序连续性分组，不再全页横坐标排序。人工合并同步迁移第二块审校项引用，保持可定位/可解决。图片表格块使用table类型，正确计入降级面积与区域数，不冒充普通配图。

新增4项回归先失败后通过，全仓310 tests passed，ruff、mypy（49 files）与diff检查通过，无新模型调用。

## PR #3 第七轮审核修复（2026-09-13）

PP投影只处理当前页两端均存在的图文关系。旧PP图题组要求阅读连续且图框纵向重叠；人工合并重定向第二块关系端点，折叠为自关系的情况保留证据并创建审校项。同一Ovis图片可保留标签/图题语义关系，但仅归入一个展示组。

新增4项回归先失败后通过，全仓314 tests passed，ruff、mypy（49 files）及diff检查通过，无新模型调用。

## PR #3 第八轮审核修复（2026-09-13）

PP自动按OCR行边界拆块时保留父块完整快照（含原内容候选），两侧派生候选显式supersedes父选择。新增1项回归先失败后通过，全仓315 tests passed，ruff、mypy（49 files）及diff检查通过，无新模型调用。

## PR #3 第九轮审核修复（2026-09-13）

公式匹配识别完整成对的单/双美元定界符，保留source_text供人工拆分长度与重新排版使用，避免展示公式残留美元符号。正文左边界写入逐页layout_by_page结果，writer按当前页读取，不受最后一页覆盖。

新增4项回归，全仓319 tests passed，ruff、mypy（49 files）与diff通过，无新模型请求。开发中公式正则写入转义错误被完整回归发现，修复后重新全部通过，未发布错误版本。

## PR #3 第十轮审核修复（2026-09-13）

Ovis与旧PP关联都保留同题号的多个题干，只有唯一候选才创建references；重复题号创建AMBIGUOUS_QUESTION_NUMBER，避免绑定最后一题。离线审阅HTML按reading_order输出，与已审阅DOCX保持顺序一致。

新增3项回归先失败后通过，全仓322 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第十一轮审核修复（2026-09-13）

Ovis块恢复新增公式之外的单换行明确题号边界，保留完整原始Markdown段落证据；公式内看似题号的行不拆分。新增回归先失败后通过，全仓323 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

第十一轮完整线程核对补充：REST默认分页未显示的另两项意见也已修复。pp_layout_only按页保存几何证据；人工关系按类型约束端点，拒绝自关联和跨页标签/图题，references要求图片指向题目。新增4项回归先失败后通过，全仓327 tests passed，ruff/mypy/diff通过。后续审核状态检查读取完整线程，避免默认分页遗漏。

## PR #3 第十二轮审核修复（2026-09-13）

覆盖半页以上的歧义矢量包围框保留来源证据与路由复核，不作为普通figure输出，避免页框导致整页内容重复；较小歧义参考裁剪仍显式待复核。人工合并重定向后复用关系端点类型校验，不适用关系保留前后证据并创建MERGED_RELATION_REVIEW。原关系迁移测试调整为有效的figure→question夹具，另补非法caption→question合并测试。

新增2项回归先失败后通过，全仓329 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第十三轮审核修复（2026-09-13）

大面积图片图域不再直接压制有效原生字符；背景/扫描底图仍保留图像与待复核路由，正文可编辑。新增关系ID跳过现存编号，删除后新增不碰撞。新增真实合成PDF背景图及ID回归先失败后通过，全仓331 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第十四轮审核修复（2026-09-13）

Native不再凭图域包含关系抑制任何原生字符，图片与文字相交即image_text_overlap_review；保留文字和图域供人工判定。普通文本及公式间文字片段遇到未处理LaTeX命令均拒绝导出，避免裸语法冒充完成。

新增4项回归先失败后通过，全仓335 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第十五轮审核修复（2026-09-13）

裸LaTeX检查收窄为已知数学命令或带花括号参数的命令证据，普通Windows路径/正则转义保留。歧义矢量不再按面积删除，只过滤贴近页面四边的页框候选，内嵌大图保留裁剪。裁剪/preserve_image解除包含目标的图片/文字展示组，避免行内标签类型改变后崩溃。

新增5项回归先失败后通过，全仓340 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。页框判断仍为有限几何启发式，来源范围及路由审校保留。

## PR #3 第十六轮审核修复（2026-09-13）

旧PP恢复复用收窄后的数学检测，普通路径/正则不再图片降级。文本编辑/候选接受完成重规划后解除受影响图组，使公式或图片标签走统一块写出路径。

新增2项回归先失败后通过，全仓342 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第十七轮审核修复（2026-09-13）

单美元货币对（如Price $5 and $4）不匹配数学片段，保留原文并要求审校而不静默移除美元。输入清单在提取后写入真实页数。旧PP不再用图片包含关系抑制OCR正文，保留可编辑文本并创建IMAGE_TEXT_OVERLAP_REVIEW；相应旧测试改为验证显式保留/审校。

新增3项回归先失败后通过，全仓345 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第十八轮审核修复（2026-09-13）

PP自动拆块把父级审校引用迁入实际子块。人工重规划复用统一数学检测，普通路径仍可编辑。人工拆分后父全文候选保留作证据并标记不可选择，API拒绝、UI过滤，避免全文恢复造成右侧重复。

新增3项回归先失败后通过，全仓348 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第十九轮审核修复（2026-09-13）

chat_content逐层验证choices/message结构，统一抛出域错误，调用层可记录失败缓存而保留已完成候选。resolve_issue在块匹配前按问题ID及页面/块范围执行，只记录审计、不新增MANUAL_CHANGE_REVIEW；无块页面级问题也可解决。网页增加相应标记已核对入口。

新增6项回归（5项复现失败、1项既有正确拒绝），全仓354 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第二十轮审核修复（2026-09-13）

有限Ovis入口对未支持的Markdown强调/列表/表格等结构创建OVIS_MARKDOWN_REVIEW_REQUIRED并保留响应，不将标记作为正文输出；现有标题和公式处理保留。各人工内容操作结束后统一校验受影响语义关系，失效关系保留证据并审校。离线待复核列表仅包含open项。

新增5项回归先失败后通过，全仓359 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。尚未新增通用Markdown表格/富文本转换能力。

## PR #3 第二十一轮审核修复（2026-09-13）

不支持Markdown改为源页图片降级并继续finish，生成可打开DOCX、issues和审阅页；保留原始响应且QA明确不可编辑/整页降级。增加单星号/下划线强调检测。人工拆分右侧按明确题号、选项和图题重新分类。

更新3项原拒绝测试为实际降级导出验证，新增4项（强调2、拆分2），7项均先失败后通过；全仓363 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第二十二轮审核修复（2026-09-13）

单标记Markdown强调允许跨软换行检测并生成源页降级。网页拆分发送码点偏移，避免UTF-16代理对导致扩展汉字/emoji后的切分错位。

新增3项回归先失败后通过，其中Node实际执行网页拆分处理器；全仓366 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第二十三轮审核修复（2026-09-13）

人工text/candidate操作按确认后的文本重新分类题目/选项/图题/普通段落，并由既有关系复核处理过期端点。新增双向分类回归先失败后通过，全仓368 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第二十四轮审核修复（2026-09-13）

人工编辑在无新词法分类证据时保留heading/footer/caption；question/option等词法类型仍随明确内容更新。类型变化解除包含该块或以其为question_id的文字布局组，避免新题目仍留在旧选项表格中。

新增5项回归先失败后通过，全仓373 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第二十五轮审核修复（2026-09-13）

人工拆分同步重分类左块、解除旧图组，并把拆分前语义关联隔离为SPLIT_RELATION_REVIEW。未保存预览使用独立状态，切换auto再返回reviewed仍请求preview资产。

新增2项回归先失败后通过（含Node实际执行版本切换处理器），全仓375 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第二十六轮审核修复（2026-09-13）

数学拒绝检测排除普通金额token，单个/成对金额原样可编辑导出；成对金额测试由拒绝改为明确原样输出。Native含XML非法字符的行保留原候选并降级源图，创建INVALID_XML_TEXT_FALLBACK。

新增3项回归先失败后通过，全仓378 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。非法字符用PDFium边界注入验证，不代表新增真实损坏PDF样本验收。

## PR #3 第二十七轮审核修复（2026-09-13）

统一数学检测覆盖反斜杠圆括号/方括号定界符，进入既定未渲染数学处理，不再裸语法输出；未新增该定界形式的OMML解析。币种前缀US/HK/CA/AU/NZ/SG/NT/A/C/S金额原样保留。

新增5项回归先失败后通过，全仓383 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第二十八轮审核修复（2026-09-13）

标准反斜杠公式在Ovis生成源页降级、Native生成对应行降级并继续导出审校。MathSpans在匹配前屏蔽金额起始美元，保留原偏移，避免金额抢占后续公式定界符。裁图文件名增加唯一后缀，预览不会覆盖已保存修订资产。

新增4项回归先失败后通过，全仓387 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第二十九轮审核修复（2026-09-13）

金额屏蔽/未渲染检测共用CURRENCY规则，接受中英文句末标点，金额不再抢占后续公式。Native行级降级复用统一数学检测，美元公式及其他未处理数学语法保留原行图片供审校。

新增7项回归先失败后通过，全仓394 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第三十轮审核修复（2026-09-13）

模型/人工文字非法XML字符保留候选并降级源图。预览成功替换后清理旧预览及本轮新建且所有layout均未引用的资产，失败时只清理新建未登记资产，保护auto/reviewed。撤销按ID重新绑定恢复块与编辑控件。

新增4项缺陷回归先失败后通过，完整398 tests passed；随后新增Node实际执行undo处理器1项通过（共399项），ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第三十一轮审核修复（2026-09-13）

保存修订复用一次apply_overrides生成的IR直接finish，不再以export重放同一账本；导出成功后更新当前overrides。新增API保存裁图资产登记回归先失败后通过，全仓400 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第三十二轮审核修复（2026-09-13）

Ovis预检美元公式是否可转换，不支持时生成源页图片与审校项并继续finish；原拒绝用例调整为实际降级导出验证。成功保存新reviewed后清理旧reviewed资产中所有layout都未引用的文件。

新增3项回归先失败后通过，全仓403 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第三十三轮审核修复（2026-09-13）

CLI export在成功替换reviewed后，同样清理旧资产中所有持久化layout均未引用的裁图。新增重复CLI导出回归先失败后通过，全仓404 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第三十四轮审核修复（2026-09-13）

HTTP保存及CLI导出成功后结束preview布局并清理其全部持久化layout未引用的资产。PP布局候选回退时回收trial新增且未登记的裁图，不触碰原IR资产。

新增2项回归先失败后通过，全仓406 tests passed，ruff、mypy（49 files）及diff通过。开发中遗漏导入被检查发现，补齐后重新全测通过。无新模型调用。

## PR #3 第三十五轮审核修复（2026-09-13）

Ovis非图片HTML结构进入源页降级并继续审校导出；非法图片标签仍拒绝。apply_overrides统一在失败时回收本次新增且所有layout均未引用的裁图，覆盖保存/CLI/预览入口。

新增3项回归先失败后通过，全仓409 tests passed，ruff、mypy（49 files）及diff通过。条件分支遗漏在检查中发现并修复后重跑通过，无新模型调用。

## PR #3 第三十六轮审核修复（2026-09-13）

成功渲染完成正式文件复制后删除本次attempt目录，失败诊断仍保留。新增合成PDF渲染清理回归先失败后通过（LibreOffice进程为模拟，PDFium页面处理实际执行），全仓410 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第三十七轮审核修复（2026-09-13）

成功发布渲染后删除正式目录中不属于本次页集合的旧page-N.png。版本切换先验证可用性，不存在reviewed时恢复控件并保留当前revision/preview状态。

扩展渲染回归并新增Node版本选择回归，两项先失败后通过；全仓411 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第三十八轮审核修复（2026-09-13）

Ovis在消费有效公式/金额后检测剩余未处理数学语法，未闭合美元和裸命令生成源页降级审阅，原裸命令拒绝测试相应更新。切换可用版本后清空旧selected与文本框，防止跨版本旧光标/文本继续操作。

新增2项回归先失败后通过，全仓413 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第三十九轮审核修复（2026-09-13）

PP hybrid及人工公式重排检查MATH消费后的剩余文本，混合未闭合语法按原区域降级而不中止保存。CURRENCY接受金额范围分隔符及单位斜杠后缀，保持原文可编辑。

新增5项回归先失败后通过，全仓418 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第四十轮审核修复（2026-09-13）

金额屏蔽前保留明确闭合、结束后非金额数字/字母且含运算符的数字公式，覆盖$5/x$和$5-10$。PP已知残留语法导致区域降级时不再执行公式裁图循环。

新增3项回归先失败后通过，全仓421 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。

## PR #3 第四十一轮审核修复（2026-09-13）

金额免屏蔽分支要求无币种前缀且区间不含多字母说明词，避免US$5/kg借用后续命令公式的起始美元。PP图域投影记录previous_asset_id和明确的pre_projection_geometry_comparison_evidence用途，使保留的Ovis裁图可追溯至替换前几何对照。

新增金额回归及投影证据单元检查，全仓423 tests passed，ruff、mypy（49 files）及diff通过，无新模型调用。上一轮两个已修复线程状态更新受GitHub GraphQL服务错误影响，已在PR评论记录修复提交。
