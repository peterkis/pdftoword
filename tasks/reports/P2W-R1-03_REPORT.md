# P2W-R1-03 auto 整页 Monkey 布局路由

- 开始 HEAD：`140945d`（R1-02 本地提交）；分支：`codex/r1-03-monkey-layout-routing`。
- 用户授权：提交 R1-02，开始 R1-03。本项代码保持未提交；未推送、未发起新全面审查。
- 工程状态：IMPLEMENTED；后续用户已授权并执行 6 次真实请求，作业 PARTIAL，见文末追加记录。人工/Word 接受 NOT_RUN。

## 修改

- `config/profiles/reconstruction-v2.json`：独立声明 Ovis 内容、PP 区域布局、Monkey 整页布局，每页最多一次、零隐式重试。旧 `legacy_ovis_pp` 仍为默认。配置使用 JSON 文件，不引入 YAML 依赖；`config/default.yaml` 的后续 8100 目标未改。
- `layout_route.py`：依据现有页面分类和区域证据生成整页发送任务，列出源图 hash、完整可见页范围、页码、原因、实际配置目标、模型、未知 revision、预算。可靠简单 native/blank 页零请求；没有另造复杂度模型。
- `route_plan.py`：将新范围、配置和目标绑定到同一 plan hash，检查原文件/准备 IR/区域图/整页图、过期、reviewed、预算、重复执行。内容与布局审批共用一个明确列出两类范围的新计划，旧 PP/Ovis 计划不含 Monkey 权限。
- `region_bridge.py`：复用既有串行 HTTP/缓存/失败账本，新增 Monkey 权限检查、正确 prompt/max_tokens、输入 MIME、未知 revision、请求指纹。HTTP 200 与有效 GeometryCandidate 分开记录。无 `/models` 探测，无隐式重试。
- `pipeline.py`、CLI、API、现有 UI：同一准备/执行服务。UI 展示整页范围包含电子正文和插图、目标、原因及一次预算；执行后展示候选状态，保持未选择。
- `execute-route --reuse-from ... --replay-only`：严格离线复用；缺失响应记录 SEALED_RESPONSE_UNAVAILABLE，不转在线。新任务下失败/取消/预算耗尽均留痕。
- `tests/productization/test_monkey_layout_route.py`：只替换 HTTP transport，真实调用计划、执行、解析、DOCX 输出和缓存回放；保留 PR #6 普通插图及含糊 full-crop single-text 保护。

## 验证

日志均在 `tmp/docx-demo/r1-03/checks/`。

- `uv run pytest -q tests/productization/test_monkey_layout_route.py tests/productization/test_auto_regions.py`：exit 0，43 passed；1 个既有 Starlette 警告。
- `uv run pytest -q`：最终 exit 0，1482 passed / 1 warning，见 `pytest-final.txt`。首轮 1481 passed / 1 failed，原因是新 API 测试未建立本机会话；补齐测试会话后复验，未放宽产品权限。
- `uv run ruff check .`：exit 0。
- `uv run mypy prototypes/docx_output scripts/docx_demo.py tests/productization/test_monkey_layout_route.py`：exit 0，49 files。
- `uv run mypy .`：exit 1，仅 R1-05 私有 `trace-public-calls.py` 的既有 2 项类型错误；未加 ignore。
- `node --check prototypes/docx_output/static/app.js`、`git diff --check`：exit 0。
- 已运行 `convert --help` / `execute-route --help`；CLI 实际运行 `convert --mode auto --auto-profile reconstruction-v2 --dry-run-route`，写出真实计划/DOCX，零网络。

反例覆盖：未授权、预算不符、reviewed、目标变更、整页图变化、重复执行、发送中取消后续布局、HTTP 503、超时、length 截断、坏 literal、PP 失败、普通图/含糊整块文字不触发 Ovis、预算耗尽、缺失回放响应、简单 native 零请求。Monkey 前后整页 blocks/reading_order 哈希一致。

## 实物与收益边界

1. 真实问题页离线准备：`tmp/docx-demo/r1-03/real-dry-run/demo-372a40eb024b461ab7bb5a2cf7856fc3/`。
   输入为既有问题 PDF 的 46–47 页，源文件 hash 未变；整页 Monkey 计划两次，区域 PP/Ovis 计划最大四次，总上限六次。**实际请求为零，未批准/未执行该真实计划。** `receipt.json` 位于父目录，记录 route-plan、IR、DOCX、RenderPlan、source-map hash。
2. 合成真实编排/HTTP stub：`tmp/docx-demo/r1-03/synthetic-execution/jobs/demo-1a63a99c99184a1fb0c6b3ec967d7310/`。
   PP/Monkey 各一次传输 stub，不是模型推理；原生内容与图域保持，Monkey 候选实际进入导出 IR。
3. 同一合成输入严格缓存回放：`tmp/docx-demo/r1-03/synthetic-execution/jobs/demo-e80eaa2fe08544ab81a77c701fac6de6/`。
   使用同一 execute_routes，复用两份响应，HTTP 0。父目录 `receipt.json` 保存两作业实际输出 hash，并明确标记 SYNTHETIC_HTTP_TRANSPORT_ONLY。
4. CLI 离线作业：`tmp/docx-demo/r1-03/cli-dry-run/demo-ab749d966cdd47fabdc3c3c522c8631d/route-plan.json`。

本项没有把真实 T0016 响应伪装成新的整页线上执行。真实封存模型响应的候选适配证据继承 R1-02；本项新增自动执行/缓存编排证据来自合成 transport。实际整页服务推理、浏览器人工操作、Microsoft Word 与排版收益仍 NOT_RUN/NOT_VERIFIED。

## 风险与后续

- provider revision 不可用时保持 null；使用已有经配置的回环服务合同，不修改 FRP/端口/部署，不读取秘密或擅自发送数据。
- 目前只追加几何候选，不自动选择，不改正文来源，不运行 MinerU 新模型。R1-04 仍负责仲裁、绑定与顺序消费。
- 真实模型验证需要对应输入、整页范围、目标、参数、版本未知状态和预算的明确授权；“开始 R1-03”未被当成真实发送授权。
- 不将自动测试、合成 replay 或离线 DOCX 当作产品/Word 接受。完整 R1-03 服务接受暂未签署。
- 回滚到 legacy_ovis_pp 时生成新计划，旧 profile 审批不能跨配置复用；保留失败响应及旧作业。


## 已授权真实模型验证（2026-09-18，覆盖前文 live NOT_RUN 状态）

用户明确授权“进行模型验证”后，执行此前已生成、hash 校验有效的 46–47 页计划：每页 PP/Ovis 各一次，Monkey 整页布局一次，最大 6 次；本次两个区域均覆盖完整可见页，执行前已明确告知。使用既有回环 8080/8000/9000；Ovis 8192 tokens、Monkey 2048 tokens，服务 revision 未知，PP 参数继承冻结合同。无额外 /models 探测、无重试、无补跑。

实际命令：`uv run scripts/docx_demo.py execute-route --job-id demo-372a40eb024b461ab7bb5a2cf7856fc3 --plan-hash 632b432db5b0124087ac636bd7d0993d223d8999929f89ebd48e92cf99a278ee --budget 6 --confirm-no-auth --output-root tmp/docx-demo/r1-03/real-dry-run`。exit 0；日志 `checks/live-execute.txt`。

| 检查 | 实际结果 |
| --- | --- |
| 模型请求 | 6/6，各页各 provider 恰好一次，HTTP 200，PP/Ovis/Monkey 合同均 COMPLETE |
| Monkey 几何 | 页 46 为 14 个，页 47 为 16 个候选；拒绝各 0，选择均 null |
| 内容保护 | 两页 Monkey 前后 blocks/reading_order hash 分别完全一致 |
| 原准备作业 | 原有 24 个文件 hash 未变，新增 route-execution 仅记录执行归属 |
| 页面重建 | 页 46：REGION_NO_EDITABLE_CONTENT，保留整页源图；页 47：RECONSTRUCTED |
| 页 46 原始 Ovis | finish_reason=stop，非空 412 字符；既有 Markdown 重建路径形成整页 fallback，不能写成“模型没输出内容” |
| 页 47 布局 | PP 映射 AMBIGUOUS_LAYOUT_MAPPING，保留 Ovis 流式输出，不强制套用布局 |
| 作业 QA | PARTIAL，489 可编辑字符、2 个图域、7 项未解决问题；不能据请求成功判产品成功 |
| 渲染 | 既有 render CLI exit 0，RENDERED，2 张 LibreOffice 页面；不是 Microsoft Word 检查 |
| 代理查看 | 查看两页 Monkey overlay 与两张渲染页。候选没有明显整页偏移，插图整体仍被包围；可编辑中文在预览中出现缺字/空白。IR 和 DOCX XML 均仍有 29 个可编辑 CJK 字符，不能以 QA fonts.missing=false 消除此发现 |

实际作业：`tmp/docx-demo/r1-03/real-dry-run/demo-d1bffe644d8e44a68a9a881015295cff/`，含 auto.docx、layout.auto.json、RenderPlan、source-map、原始/规范化响应、请求与候选账本、rendered/auto/page-{1,2}.png。

新增只读响应回放叠框：`tmp/docx-demo/r1-03/real-dry-run/live-overlay-{45,46}/`，使用本次 PP/Monkey 响应，逐个验证 response/input hash，额外请求 0。完整私有证据 `live-validation-receipt.json` 保存 47 个作业文件 hash、请求状态、内容保护、QA 与渲染发现；`live-authorization.json` 保存发送前范围/配置/旧文件 hash；`live-overlay-receipt.json` 保存叠框 hash。

本次冻结的发现：

- R1-03-LIVE-01：页 46 非空 Ovis 返回未转成可编辑正文；保留失败响应和整页回退，后续用 sealed replay 定位内容适配边界，不追加请求选优。
- R1-03-LIVE-02：LibreOffice 预览中文缺字/空白，XML 字符仍存在；后续检查字体/渲染路径，Word 未验证。
- R1-03-LIVE-03：页 47 PP 映射含糊，几何候选尚未经过 R1-04 仲裁；不宣称排版改善。

本轮预算已用尽。路由和实际 GeometryCandidate 进入 IR 已得到真实证据，产品质量仍 PARTIAL；不代签人工/Word 接受。本轮仅增加验证产物和报告，没有修改生产实现或重发模型请求。
