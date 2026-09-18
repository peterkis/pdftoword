# P2W-R1-02 统一几何候选：首个主线接入切片

- 分支：`codex/r1-02-geometry-candidates`；开始/当前 HEAD：`f300bf048c6c145514e523ea7d25d162d4567570`，本报告所在提交包含本项实现；提交前 HEAD 为上述基线。
- 授权：R1-05 按带已知限制的 POC 收口、工程合并后推进主线；不再发起全面审查，不扩展 DocVortex 能力。
- 工程状态：IMPLEMENTED，离线自动检查有证据；完整 R1-02 接受仍有下列缺口，不自动签署 VERIFIED/人工接受。
- 人工/Word 接受：NOT_RUN；代理叠框查看：LIMITED，不能代替人工接受或排版收益验证。

## 修改

- `prototypes/docx_output/geometry/`：纯 Monkey/PP/Native adapters 和连续 TransformChain。Monkey 兼容 JSON/合法 literal，限制长度、嵌套、token、数量，拒绝未完整结束、无效框、非数值、越界及重复区域。无网络、重试或正文恢复。
- PP 输出区域、OCR 行、公式四角，排除识别正文；预处理不明确则拒绝。只保留实际 block_id/block_order，未证明的顺序标 unknown/partial，不用 Y/X 排序伪造模型顺序。
- Native 复用 PageGeometry 的 CropBox/旋转映射，保留已验证 run 的 advance/em 测量，独立标注精度，不声称紧致字形框。主文字、块框及内容候选不受此新增路径修改。
- `structure.py` 保留 recover_monkey 兼容入口及历史 provenance 投影，额外附加独立 Monkey/PP 候选；`pipeline.py` 传递请求证据；`native_pdf.py` 附加 Native 候选。
- `specs/geometry-candidate.schema.json` 定义 `geometry-candidate/1`；Layout IR 1.1 添加可选候选及独立 selected_geometry_id，兼容旧 IR。standalone 与内嵌 schema 有同步回归。当前选择保持 null，尚未实施 R1-04 仲裁。
- `geometry_replay.py` 提供显式 manifest/hash 输入、私有新目录输出、候选 JSON、逐提供者 overlay 和 receipt。旧输入不覆盖，同提供者不同重复须分开回放。
- `tests/productization/test_geometry_candidates.py` 验证实际适配器、真实 PDF backend、变换、内容保持及 sealed replay。

## 验证

| 实际命令 | exit | 结果 |
| --- | --- | --- |
| `uv sync --locked` | 0 | 47 resolved / 46 checked；无新增依赖 |
| `uv run pytest -q` | 0 | 1462 passed，1 个既有 Starlette 警告；随后新增超大整数反例并做下项最终验证 |
| `uv run pytest -q tests/productization/test_geometry_candidates.py tests/demo/test_pr_review.py tests/productization/test_input_analysis.py` | 0 | 最终 274 passed，1 警告 |
| `uv run ruff check .` | 0 | 无诊断 |
| `uv run mypy prototypes/docx_output tests/productization/test_geometry_candidates.py` | 0 | 47 files 无诊断 |
| `uv run mypy .` | 1 | 3 份已有私有脚本 21 项错误：旧产品化脚本 19 项，R1-05 trace-public-calls 2 项；本项无新增 ignore |
| `git diff --check` | 0 | 无空白问题 |
| `uv run python -m prototypes.docx_output.geometry_replay --help` | 0 | 核实实际离线入口 |

日志：`tmp/docx-demo/r1-02/checks/{pytest,targeted-final,ruff,mypy-targeted,mypy-full}.txt`。
首次针对性验证 248 passed / 1 failed：新测试用了系统临时目录，被现有 PRIVATE_STORAGE_REQUIRED 拒绝；已改为项目私有目录，未放宽存储约束。首次类型检查暴露 tuple 长度及一次注解误改，已修复。以上失败不算模型质量问题。

## 证据与收益边界

- T0016 全部 6 组 JPG/PNG 对照、12 份 Monkey/PP 响应均按原封存清单校验，没有挑选最佳重复。每组候选数依次为 164、162、164、146、150、161，解析拒绝均 0；这只是合同解析结果，不是识别正确率。
- 新目录 `tmp/docx-demo/r1-02/{jpg,png}-{1,2,3}/` 保存 `candidates.json`、`monkey-overlay.png`、`pp-overlay.png`、`receipt.json`。栅格采用明确的 72 dpi 参考点坐标，不冒充来源 PDF 的真实物理尺寸。
- 原问题页索引 45/46 的响应 hash 与历史 request-manifest 一致，输入 hash 与源页图一致；各生成 34/37 个 PP 候选。Native observations 没有可用文字 run，候选为 0；没有同输入 Monkey 响应，不借用其他页、不新增推理。
- 问题页产物：`tmp/docx-demo/r1-02/problem-{45,46}/`，具体 hash 见各 receipt；输入源作业 34 个文件未变，原 T0016 全封存文件未变。汇总在 `problem-summary.json`、`t0016-summary.json`。
- 代理查看了问题页 45/46 的 PP overlay 及 T0016 jpg-1 Monkey overlay：宏框/行框没有明显整页偏移；PP 同时产生插图整体框与内部细框。后续必须保留图域整体，不能以内部框包含关系删字或拆图。本次查看没有逐框测量正确性。
- 原子内容、reading_order 和渲染行为在兼容回归中保持；本项不产生新的 RenderPlan/DOCX/source-map，记 NOT_CREATED。POC 最终 DOCX 对照仍以 R1-05 freeze receipt 为准，不能把新增叠框当作 Word 收益。
- 模型新请求 0，metadata GET 0，复用 14 份模型响应和 2 份 Native observation；无新增外部服务、模型、字体或 DocVortex 下载。

## 风险、未解决与回滚

- AC01 的三类 adapter 已有实际代码和测试，但尚缺同一真实输入的三类非空证据；真实问题页的 Native 为空、Monkey 不可用，如实保留。
- AC02 校准覆盖 0/90/180/270、非零 CropBox、crop/resize/padding，float roundtrip ≤0.5px，整数边界 ≤1px。Native 测量保留既有 observer 允许的 1pt 边界余量，不进行静默裁框。
- AC03 已有拒绝/正文不变测试；AC04 保留行支撑及来源，但共享结构消费、几何仲裁与内容绑定尚未接入。缺失指纹为 null，不从 model 名称制造已验证 revision。
- schema 中可选 geometry 选择字段只声明合同；现有 writer 仍使用原块几何。跨粒度 IoU 排名、新 winner、全能力 renderer 均未实现。
- 下一项按依赖推进 R1-03 的受控 Monkey routing，再做 R1-04 仲裁与内容绑定；复用同一问题页检查图域保护及实际收益。未经明确发送范围/目标/参数/版本/预算授权，不补真实模型调用。
- 回滚：撤销本分支未提交的特定接入及新增文件即可回到已合并 POC；不删除旧作业/封存响应，不运行 reset/clean。用户于本次交付后明确授权本地提交 R1-02 并开始 R1-03；未授权本次推送或合并。

## 接受记录

未签署人工、视觉、Word 或发布接受。DocVortex POC 冻结结论不变；本项没有新增共享 renderer 调用，结构/renderer 收益仍 NOT_VERIFIED。

## 提交前补充

用户已要求分别归档两份旧产品化 Python 草稿，ZIP 内容/hash 校验后移除原脚本，其他 34 个历史文件不变。重新 `uv run mypy .` 仅剩 R1-05 `trace-public-calls.py` 的 2 项私有脚本类型错误；此前 21 项记录保留为历史检查结果。归档证据在私有目录，不加入 Git。
