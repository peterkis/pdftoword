# R1-05：DocVortex 0.4.9 的共享结构与输出 POC

工程结论：采用 **有边界的公共 API 适配**，继续保留 Legacy 默认路径。本项不决定永久几何权威，也不声称真实问题页的排版已经改善。

实际执行的发布 wheel 为 `docvortex-0.4.9-py3-none-any.whl`，SHA256
`03e1616466a2f309115bb4c003d3f3aed4fd5b5d9b97129835aa312b2c57d2fb`。
386 个包内文件与参考 commit `e5b4b206a1cf62ac2b08247d7f42c1d0672487bf` 的 Git blob 匹配，无差异。
完整版本、许可证文件 hash、公共接口表、依赖切片见 [runtime record](../development-plan/r1-05-runtime-record.json)。

公共源码参考：[Model/Middle 协议](https://github.com/myhloli/DocVortex/blob/e5b4b206a1cf62ac2b08247d7f42c1d0672487bf/docs/JSON_PROTOCOL.md)、[PUBLIC_API](https://github.com/myhloli/DocVortex/blob/e5b4b206a1cf62ac2b08247d7f42c1d0672487bf/src/docvortex/public_api.py)、[DOCX 公共门面](https://github.com/myhloli/DocVortex/blob/e5b4b206a1cf62ac2b08247d7f42c1d0672487bf/src/docvortex/render/docx.py)。这些来源由实际 wheel/固定提交比对确认；不以源码阅读代替下面的执行证据。

## 实际采用的范围

| reuse_id | 决定与实测 | 项目保真边界 | 后续必做任务 |
| --- | --- | --- | --- |
| MU-HEADING | ADAPT_PUBLIC_API：实际 postprocess 生成 paragraph_title 默认 level=2 | 默认 level 不是模型检测；源文字变化、人工锁不采用 | R2-02、R2-07 |
| MU-PARAGRAPH | ADAPT_PUBLIC_API：提供行证据的连续源页产生 continues_prev | 缺行、非连续页、题/选项/人工锁边界不采用；只加结构关系，不另写通用合段器 | R1-06、R2-01、R3-04 |
| MU-TABLE | ADAPT_PUBLIC_API：公共 HTML state 识别两列；公共 renderer 输出真实表格、rowspan/vMerge | 当前是显式 selected_html 的小型 POC；完整 Layout IR cells/span bridge、续表接受仍未实现 | R3-02、R3-04、R3-07 |
| MU-FORMULA | ADAPT_PUBLIC_API：公共 renderer 实际输出块公式和行内 OMML | 坏公式图片回退单列；裸 LaTeX 不算转换成功，适配器拒绝冒充 OMML | R3-03、R3-05、R3-07 |
| MU-CAPTION | ADAPT_PUBLIC_API：共享层实际形成 image/body/caption 分组 | 只能确认已有明确 caption_of；无归属证据保留原关系并报审校，不按最近框配题图 | R2-04、R2-05、R2-07 |
| MU-ORDER | REFERENCE_ONLY：实测保留输入数组顺序并重建 index | 不是学习得到的阅读顺序；来源用原 page_index+输入索引 ledger 绑定，未知/重复映射拒绝 | R1-02、R1-04、R2-03、R2-07 |

运行产物中的 `reuse-decisions.json` 为逐能力输入/输出 hash；此表补充精确任务映射。六类 POC 不代表 R2/R3 专项接受。

## 两条独立轴

- **结构轴**：同一源 IR、相同 LegacyRenderer，比较 LegacyStructure 与实际 DocVortexStructureProcessor 的候选。所有原子内容、来源、几何、人工修改和关系保留；共享字段清理/结构建议另存 ledger 与 loss-report。
- **渲染轴**：同一 IR/RenderPlan，比较 LegacyRenderer 与 DocVortexRenderer。直接构造严格 MiddleJson 调用 `render_docx`，不再运行 Model 后处理。范围标记包围实际 OOXML 内容；数量/文本/图片 hash 不能一一确认时，保留 raw 候选并显式退回 Legacy。

当前真实问题作业共 2 个源页、15 个块；两轴实际运行，DocVortex 写出轴未回退。共享层在该作业上没有提出可采用的新结构建议；本次不能据此宣称结构或视觉改善。六能力正/反例来自独立标记的自有合成探针，不冒称真实模型或人工作业验收。

## 隔离与许可

先执行 `uv run scripts/setup_docvortex_runtime.py`。安装位置为专属私有 `.venv`，按 `requirements/docvortex-poc.txt` 全量 hash 锁定切片；主项目 `uv.lock` 不改。
这是已验证公共后处理/写出的实验依赖切片，**不是完整 DocVortex SDK 安装**。没有安装其 parse/classifier/Office 全套依赖，不支持在这个环境直接使用完整解析 CLI。具体省略项列在 runtime record。

运行 worker 时先封锁 socket connect/DNS、子进程与 os.system，再加载公共模块；PDFium、DocVortex PDF、模型模块禁止导入。实际调用记录 PDFium 未加载。AssetResolver 仅读取注册的本地 hash 资产；URL、data URI、HTML 内未注册图片不能绕过它。

DocVortex 项目代码声明 MIT；依赖并非全为 MIT：例如 ftfy 为 Apache-2.0，lxml 为 BSD-3-Clause，NumPy wheel 声明组合许可，Pillow 为 MIT-CMU。mathml2omml 0.0.2 的实际许可证文件及 metadata classifier 为 MIT。详细文件 hash 见 runtime record。没有附带第三方源码、权重或字体；未来发布必须按实际分发包重新核对依赖义务，进程隔离不自动豁免许可。

## 明确未支持与回滚

公共 `render_docx(MiddleJson, *, asset_resolver=None)` 没有样式或模板参数。本项目只在其产物上按既有 A4 流式布局应用默认样式和可核验来源标记；显式 run 样式、已有分组/几何布局等不支持项退回 Legacy，不任意改字体换外观。

Model 的全半角/连字样例在本版本保持原样；标题换行会清理，进入 loss-report 并保留原 IR。公共默认导出会跳过 footer；适配器明确保留其可见文本。坏公式有图片/裸 LaTeX 两类真实探针，后一类被排除在成功转换之外。

默认生产编排仍为 Legacy。停止使用 `reuse-poc`/DocVortex 注入即可回滚；不回退 S2、PR #6、R1-01，不删除历史作业。新 worker/桥接层没有调用 `docvortex.parse`、MinerU 推理或任何模型网关。
