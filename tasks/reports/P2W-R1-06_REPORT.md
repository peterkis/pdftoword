# R1-06 Flow Planner v1 实施报告

日期：2026-09-19。工程实现已落地，真实封存样本已生成独立 DOCX；完整产品接受与 Microsoft Word 人工接受未签署。R1-04 按用户明确指令以[已知限制工程收口](P2W-R1-04_FREEZE.md)，真实采用及收益仍为 NOT_VERIFIED。

## 修改

- `planning/flow.py`、`planning/styles.py`：只读兼容 IR 1.1，生成 IR 1.2 副本及独立 RenderPlan v2。Section/Paragraph/Figure/Table/Group 节点持有输出宽度、缩进、间距、keep 规则；来源 bbox 不变。
- `specs/layout-ir-1.2.schema.json`、`specs/render-plan.schema.json`：约束样式、规划、原始 IR 和完整节点覆盖，拒绝丢失、重复、无证明重排及非有限数值。
- `renderers/flow.py`、`pipeline.py`、`writer.py`、`common.py`：显式 Flow profile 消费规划，保留 Legacy 默认入口。纸张/方向优先使用来源；字号取原生主要正文证据或显式 profile，未知扫描样式标 inferred。字体写入 ascii/hAnsi/eastAsia，保留可用原生 run 字号、字重、斜体、下划线、上下标、颜色；缺字体单列问题，不分发字体。
- 图片按容器及纸张可用高度等比放置；Flow 不再使用固定 A4 内容宽/650pt 高度，不仅因水平偏移而居中。段落只消费经过守恒检查的 DocVortex 公共 continuation，不新增任意拼段规则。
- `flow_replay.py`：校验完整封存文件集，公共结构处理一次后固定同源 Legacy/Flow 比较；独立产物不覆盖源作业。CLI 异常只输出安全错误码/类型。
- `tests/productization/test_flow_planner.py`：21 项回归覆盖横竖纸张、11/15pt、字体缺失与原生 CJK、源/输出坐标、长段落重规划、超高图、公共 continuation、节点丢失、Legacy 兼容及错误输出保护。

## 验证

最终命令及原始结果保存在私有 `tmp/docx-demo/r1-06/checks/`：

- `uv sync --locked`：成功，无新增依赖。
- `uv run pytest -q`：1552 passed，1 个既有 Starlette 弃用警告；见 `pytest-release.txt`。
- `uv run pytest -q tests/productization/test_flow_planner.py`：21 passed。
- `uv run ruff check .`：成功。
- `uv run mypy prototypes/docx_output tests/productization/test_flow_planner.py`：59 个源文件无错误。
- `uv run mypy .`：仍有 2 个旧错误，均在未跟踪的 `tmp/docx-demo/r1-05/trace-public-calls.py:15–16`；未添加 ignore 或改动该历史脚本。
- 最终 schema 已实际验证保存的真实 Flow RenderPlan；长段落编辑后通过实际 finish/replan/render 生成 4 页 DOCX→PDF。

## 证据

私有目录不入 Git，公开报告不包含正文/截图/机器绝对路径：

- 比较及 hash 收据：`tmp/docx-demo/r1-06/real/demo-05a5808c3da24742889f6a11c4442dbd/visual-verification.json`。
- Flow：`tmp/docx-demo/r1-06/real/demo-8ba0eac79ced4a0dba8d670b7b1248af/`，包含 `auto.docx`、IR 1.2、RenderPlan v2、source-map、两页渲染 PNG/PDF。
- Legacy：`tmp/docx-demo/r1-06/real/demo-fb2f98f5e4be4df6a5175d994fa5c876/`。
- 编辑重流：`tmp/docx-demo/r1-06/edit-reflow/receipt.json`；明确为合成长段落实验，不替代真实样本质量接受。

同源比较的三个可见变化：输出纸张从 A4 约 595×842pt 改为来源约 376×572pt；Flow 第 2 页中文在本机预览中可见；第 47 页文字、图形与习题在同页容器内排列。两份输出均保留 489 个可编辑字符、2 张图片，嵌入图片字节完全相同，来源 pages/blocks/geometry 相同，源作业 47 个文件 hash 不变。新增模型请求 **0**。

这里的图像为 **IR preview（实际 LibreOffice DOCX→PDF→PNG，非 Word 实际输出）**。代理查看了两页 Flow 图像；此记录不将 QA 的人工视觉状态改成接受。旧 Legacy 文字层可提取到中文，不代表其中文字已经可见；R1-03 原字体发现及旧产物仍保留。

## 风险与接受边界

- AC01：在该封存样本有消除固定纸张/字体默认值偏差的输出证据；不推广为其他样本均改善。
- AC02：字体映射及受保护公共续段有自动回归；扫描字号/标题比例仍是 inferred，真实多类段落质量未全面接受。
- AC03：样本内容、图片、source-map 保持，合成长段落可自然重分页；真实作业仍 **PARTIAL**，第 46 页保留整页图像回退。
- AC04：复用已冻结的 R1-05 公共适配边界；不重做共享段落引擎。
- R1-04 真实几何采用、布局收益继续 NOT_VERIFIED；本次样式改善不能补签它们。
- Microsoft Word 人工打开/编辑/视觉接受：NOT_RUN。字体可用性仅检测本机 family，不证明任意字形或其他机器覆盖。
- 尚未受现有 renderer 支持的原生复杂内容显式拒绝，未扩展表格/公式引擎。
- R1-04 和 R1-06 代码仍未提交；未 push/merge，未进入 R1-07。下一步建议先审阅本阶段真实 DOCX 与保留限制，再决定提交及后续阶段。
