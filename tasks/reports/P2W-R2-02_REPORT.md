# P2W-R2-02 实施报告

- 分支：`codex/r2-02-style-profile`。
- R2-01 已按本轮授权提交：`0799af4`（`feat: reconstruct native paragraphs with auditable source spans`）。R2-02 开始与当前 HEAD 均为该提交；本阶段改动尚未提交、未推送。
- 范围：离线样式档案、字体替代、确定性标题层级候选、只改样式的重导出，以及由代理实际操作 Word 校对。
- 工程状态：**VERIFIED，限定于下述能力与反例**。用户接受为 PENDING；不授予完整产品视觉或发布接受。

## 已实现行为与文件

- `planning/style_profile.py`：以非空白有效字数加权，将相差不超过 0.25 pt 的原生字号聚类。页眉/标题不进入正文样本；扫描 run 不充当原生测量。只有标题而无正文测量时标记兼容默认，不能称已测得正文或精确扫描字号。
- StyleProfile 保存正文/标题/图注/列表/选项/表格角色、原生角色聚类、源页面尺寸依据、输出节/内容宽度、可用行证据的平均字符数与基线步长、字体替代、标题 ID 与原文本 hash。扫描保持显式推定角色比例，不把 line box 高度当字号；未知 DPI 的栅格画布不称物理纸型。
- `config/font-mapping.yaml`（JSON-compatible YAML）：本机可验证的候选字体和替代顺序。只剥离规范 PDF subset 前缀；`C2_3` 等资源标识不被冒认为字体名。缺失字体、替代以及可能回流风险记录在档案。没有复制、下载或分发字体文件。
- `planning/styles.py`：原生字号聚类、字体映射；源 run 的强调、上下标、下划线和颜色仍保留。可选 `editable_styles` 让普通正文继承 Word 基础样式；有独立字体/强调或人工锁的 run 保留必要覆盖。显式字号变更只改变输出，源 runs 不变。
- `planning/flow.py`、`writer.py`、两个 schema：档案接入真实 RenderPlan；确定性标题候选写入 Heading 1–9，unknown 不冒充 Heading 1；清理 Word 内置标题主题字体/颜色。OOXML 的 ascii/hAnsi/eastAsia/cs 均有明确来源。OMML 与已有表格路径保持可编辑。
- `structure_processors/bridge.py`：明确的文档标题证据可映射公共 `doc_title`，普通标题走 `paragraph_title`。上游默认 level 1/2 单独记为默认值，不当作层级推理结果。
- `style_replay.py` 与 `config/profiles/document-styles.json`：校验输入 Layout IR hash、资产 hash及已有源图 hash，再在新作业重建 RenderPlan/DOCX。缺历史 hash 的辅助源图仅保留当前文件清单校验，不冒充历史封印。源内容/关系不变，OCR 和结构重新调用均为 0；默认兼容 profile 保留，样式继承显式启用。
- `tests/productization/test_style_profile.py`：21 项测试涵盖字符加权/字号聚类、缺字体/无 family/不同 subset、CJK 属性、原生标题页/空白页、未知 DPI、混合纸型、层级跳变/重复/空标题/局部导入/新文档起点、题号保护、人工锁、输出样式重导出及实际公共标题调用。

## 实物

私有证据根：`tmp/docx-demo/r2-02/`，不进入 Git。

- `verified-manifest.json`：最终两个真实样本与一个合成样本作业路径。各作业含 `auto.docx`、`layout.auto.json`、`render-plan.auto.json`、`source-map.auto.json`、`style-profile.json`、`style-replay.json`。
- `verification.json`：逐产物 SHA-256、源码 SHA-256、源文件集不变证明、源/输出纸型与行统计、Word 修改核验及接受边界。当前规划器重新计算的档案与产物档案相同；最终 DOCX 部件（除 core 时间元数据）与已校对候选相同。
- `public-headings/input.json`、`execution.json`、`style-profile.json`：实际公共 DocTitle/ParagraphTitle 输入、返回及自有层级候选。
- `word-review/*-final.docx`、`*-final.pdf` 和对应目录的 PNG：实际 Word 输出，共 6 页已逐页检查。
- `word-review/semantic-style.docx`：在 Word 中将 Normal/正文从 12 pt 改为 16 pt 后保存的副本。它是编辑证据，不覆盖自动输出。
- `cli-proof.json`：真实执行 `python -m prototypes.docx_output.style_replay` 的 argv、exit 0、新作业路径与 hash 绑定；入口不止于 `--help`。

真实 native4 与 native25 的正文档案分别为 **10.56 pt** 与 **10.02 pt**，沿用各自源纸张尺寸和可追溯的内容宽度；没有统一缩小字体以减少页数。Word 的半磅字号表示分别为 10.5 与 10.0 pt，量化差异记录在验证清单，原生测量没有被改写。合成文档正文为 12 pt，含两级标题、真实 Word 表格、行内 OMML、独立 Caption 和 800×400 pt 横版节。合成证据不计作真实复杂文档验收。

## 验证

| 实际命令/操作 | 结果 | 日志/证据 |
| --- | --- | --- |
| `uv sync --locked` | exit 0 | `checks/sync.txt` |
| `uv run python scripts/quality.py --help` | exit 0，按当前入口执行 | 工具调用记录 |
| `uv run python scripts/quality.py --output-dir tmp/docx-demo/r2-02/checks/quality-final-audit` | overall exit 1，仅既有 mypy 项；pytest **1604 passed**，Ruff 正常 | `checks/quality-final-audit/` |
| 相关 planning/writer/style_replay/test 的 mypy | exit 0，9 个文件 | `checks/final-mypy.txt` |
| 变更模块及 Flow 回归 | exit 0 | `checks/final-regressions.txt` |
| `git diff --check` | exit 0 | 当前工作树 |
| hash 绑定的 style_replay CLI | exit 0，真实新 DOCX | `checks/cli-proof.txt`、`cli-proof.json` |

全仓 mypy 仍只有 `tmp/docx-demo/r1-05/trace-public-calls.py:15–16` 两个原有注解问题。曾发现并修复测试夹具未复制源图、测试的 nullable 类型问题；失败日志保留，不增加 ignore、不删除历史证据。

Microsoft Word 16.113.1 实际打开三个本地候选，自动保存关闭。完成全部 6 个 Word PDF 页面目视核验。两个真实样本的 source ranges、文字与图像 payload 通过独立包核验；合成 OMML 路径不受现有通用 source-range audit 支持，因此没有伪称同样的完整范围审计。

合成 Word 实物操作：在“格式→样式→正文→修改”将字号 12 改为 16，观察正文、表格单元格与公式整体随样式变化，标题层级/Caption 保持独立，横版节仍存在。保存后的正文、表格文字一致，OMML 表达式与上标位置一致；Word 将相邻 `+`、`1` math run 合并为 `+1`，不声称 XML 字节相同。

使用技能的捆绑 `render_docx.py` 另行渲染三个候选并查看全部 4 页 PNG：中文漏显，判定该渲染路径视觉失败。它没有被当作 Word 验证结果；没有借此修改正文或分发字体。

## 模型与共享复用

新增模型请求、模型 metadata GET、重试均 **0**。样式重导出函数不包含模型入口，不重新调用结构处理器。公共标题探针单独实际调用本地 DocVortex 0.4.9 的 `model_json_to_middle_json`，输入/输出/worker 记录封存。

MU-HEADING：采用公共文档标题/段落标题类型及默认值，项目仅在已有 heading 类型上依据可靠编号给出确定性候选。空标题、跳级/重复、缺源页或局部导入返回 unknown；题号和页眉不会被该层升级为标题。未编号标题也保留 unknown，没有声称实现完整语义层级预测或复制私有 `title_leveling` 即可识别。外部标题 LLM 默认关闭，未调用。

源 block ID、原文 hash、源字号及角色判断分开保存。真实样本内容、几何、阅读顺序、题图关系均保持；只改变输出样式。兼容 profile 可回退，旧作业与旧 DOCX 不覆盖。

## 保留/未解决/接受边界

1. **混合纸型 Word 打印 PDF 限制**：DOCX 两节为 595.3×892.9 pt 和 800×400 pt；Word 窗口实际显示横版节，但打印 PDF 产生 595.3×892.9 与 892.9×595.3 pt。横竖方向保留，第二节自定义纸型未保真；AC01 的 DOCX 工程证据不能代替 PDF 打印保真接受。没有实体打印验收。
2. 字体可用性仅针对当前提供的本机 family inventory。Windows 实机字体/Word 验证 NOT_RUN；无字体时明确回流风险，不能声称跨平台字体保真。捆绑 LibreOffice 的中文漏显仍有独立发现。
3. native4/native25 仍自然分页为 2 页；角色比例、未编号标题和扫描相对样式是保守估计，不是完整排版恢复。正文平均行字符统计仅作对照，不自动压缩文字或以缩字号换页数。
4. 现有 `style_ref` 对齐与 run 覆盖继续使用；本阶段没有加入跨文档智能匹配、模型标题识别、新 UI 或新模型。普通样式继承通过显式 profile 启用，不静默改变旧兼容导出。
5. R1-03 内容回退/字体问题和真实几何正向采用缺口继续独立保留。完整产品/视觉/发布接受仍 WITHHELD，用户接受字段不代签。

下一项可按计划进入 R2-03；本轮只完成 R2-02 的上述工程与实物验证范围，没有提前执行下一阶段，也未提交本阶段代码。
