# T0016 / P0-GATE-001B — 有限完整重跑与阶段收尾

最终建议：**ACCEPTED_WITH_QUALITY_FINDINGS**。2026-09-11 新运行 14/14 完整，证据链、离线评分与工程门禁通过。此状态只表示约定评测完成，不表示生产识别质量、试卷全文、细粒度 OCR 或跨页题图验收通过。

| 字段 | 当前结果 |
| --- | --- |
| execution_status | COMPLETE（仅新 run） |
| annotation_status | REVIEWED / agent_visual，沿用冻结标注 v1.0，不是新增人工审阅 |
| quality_findings | PP 分块合并及不等号差异仍在；Monkey 分块和边界波动；阅读顺序覆盖不足 |
| input_policy_decision | 已有 JPG 保留原字节，新工作图 PNG 为避免新增有损编码的保守建议；不宣称 PNG 更准确 |
| geometry_decision | 维持 ADR-006 多候选，无永久唯一赢家 |

## 分支、检查点与运行边界

- 当前分支 `feat/t0016-raster-regression`；本轮起始/结束 HEAD 均为 `db3439a1512220c12164458f4ada1a29ae2ff0be`（Document partial T0016 raster regression evidence）。本地 HEAD 与现存 origin 分支引用一致；本轮不 fetch、不写远端。
- main 的已合并 T0015 基线为 `74f619b8ebea1ce75cf07629022bf60728d00a3d`。没有重复创建分支、重复提交、amend 或重写已存在检查点。
- 本轮起始工作区、暂存区均干净；本轮只修改公共报告和公共指标两文件。旧报告“未提交”描述 2026-09-09 报告形成时状态，不否认之后形成的 db3439a。
- 新运行原因：`network_failure_revalidation_of_complete_matrix`；predecessor run_id 为 `t0016-mac-20260909T081611Z`。获准的一次新增 14 请求预算已执行；无第三轮、重试、预热或参数调整。

## 旧 PARTIAL 与新 COMPLETE 独立保存

| 运行 | 推理尝试 / 完整响应 | 状态 | 网络结果 |
| --- | --- | --- | --- |
| `t0016-mac-20260909T081611Z` | 14 / 13 | 永久 PARTIAL | 最后 Ovis PNG ConnectError，没有 HTTP 响应 |
| `t0016-mac-20260911T030753Z-r2` | 14 / 14 | COMPLETE | 14 次均 HTTP 200；无网络、应用、解析或截断失败 |

- 旧目录 `tmp/raster-regression/runs/t0016-mac-20260909T081611Z/` 的请求、响应、预测、输入/真值/协议快照、封存清单、全部历史评分和复核文件原样保留。前后核对 **59/59 文件字节不变，文件集合不变**；没有对旧目录执行 evaluate/promote。
- 更新公共摘要前，旧 `T0016_REPORT.md` 与 `T0016_METRICS.json` 已按原字节保存到 `tmp/raster-regression/closeout-history/t0016-mac-20260911T030753Z-r2/`。该独立忽略目录同时保存旧目录哈希清单和本轮命令状态；不是向旧 run 追加文件。
- 公共 `T0016_METRICS.json` 仅指向新 run。旧公开指标仍可从 db3439a 获取；旧本地证据继续有效。未拼接新旧响应，旧 Ovis JPG 不参与新 Ovis 配对。

## 有界网络诊断与预检

- 单次 `lsof -nP -iTCP:8000 -sTCP:LISTEN` 确认本机 loopback 8000 有 frpc 监听，退出 0。未读取或修改 FRP 配置，没有杀进程或重启服务。
- 单次 curl GET `/v1/models`，connect-timeout=5s、max-time=15s、noproxy=*，只输出 HTTP 状态：200，退出 0。该 GET 只证明 HTTP 可达，不代替身份核验。
- run 自带的三次预检 GET 均 200：Monkey/Ovis 预期身份通过；PP OpenAPI 原始字节 SHA 与 T0015 相同，归一化结构相同，无 CONTRACT_DRIFT。**元数据 GET 共 4 次，与 14 次推理尝试分开计数。**
- 请求只走既有 127.0.0.1:9000/8000/8080，NO_PROXY/no_proxy 均含 127.0.0.1,localhost；沿用无需 API Key 的确认，无 Authorization，不访问响应中的图片 URL。
- 旧 ConnectError 只能说明连接未建立；不能由 1.822ms 推断远端 OOM、崩溃、PNG 不支持或特定 FRP 组件故障。新运行成功也不反向证明旧失败的根因。

## 冻结输入、协议与工具来源

复用 math_exam_001；800×1159，RGB，EXIF orientation=1、无 ICC。没有重新生成 JPEG/PNG、重新标注或修改坐标/阈值/类别映射。45 个确认区域、1 个不确定边缘标记，17 项确认参考检查、14 个阅读顺序锚点对；不确定项仍排除精确评分。

| 对象 | SHA-256 |
| --- | --- |
| 原 JPG（94410 bytes） | `fe608629ae8af60890684c77437b3d62facd3a0c27b9fa019692890f96cbcf52` |
| PNG（381127 bytes） | `505d5b8cbbbe91f530dfd9af7d8e2ef48592e6673ddb117ffe1eeb1ea2269afd` |
| 两者相同的解码像素 | `82e2ef3ea21b23129162e9aab9433644672a71032f95bb8cdf6bd943527c2265` |
| GT v1.0 | `ec7aab31c0a4589a1651345a301a5ab6837ecf3ffa5b2e116ab3a0bb7320e64b` |
| 公共协议文件 / 原快照 / 新快照 | `5b1ae72d4d0b3ef4fe6aeef5c3945ff9074126a30e9c204c81e7c7c114539d4c` |
| 评估修正 v1.1 | `22c441a531fbe690166c19383eec79bfde4b204c2c50bed2c3844e2cba073fca` |

协议不仅解析后相同，本次三份协议的文件字节哈希也相同。解码像素按现有工具再次只读验证；Pillow 12.1.1 与 uv.lock 未变。原 PNG 编码参数仍为 compress_level=6、optimize=false。

| 本轮采集与评估使用的文件 | SHA-256 |
| --- | --- |
| scripts/raster_regression.py | `89d0ed8a48c5cdca9aa9bc9ece6e081aecbb9284679d590c4cc104a305265c58` |
| scripts/evaluate_raster_models.py | `9da833296a95228d94f5876b05820899157a89a8cb322a5363c3ae7a1e498a31` |
| scripts/model_contract_discovery.py | `f1ccda2cc9cffd7565b232474d26948a91ee496d5ed609086ca171e2c20d05da` |
| uv.lock | `32767c6633890497305d5259c48727ba568bb9f43ac9793b690420435d2aff0d` |

新采集与新评估使用相同的上述当前哈希。旧采集 core 哈希 `6bf19bd0efd2562cc96db149636995c35c5324c9eb58763d2028e824efcd9d73` 只属于旧运行；没有冒充新版本。评估仍为已公开 v1.1：类别大小写/别名与 paragraph 分母修正的历史保持，不采用失效的 v1.0 Monkey 零匹配结果。该方法修复不是模型改进；本轮未修改任何评测代码或评分口径。

**从已有 JPG 生成 PNG 不能恢复 JPEG 之前丢失的细节。本实验是这一页的格式接入回归，不是编码质量优劣实验，也不能替代纯电子 PDF 验证。**

## 新运行实际参数、状态与耗时

- 固定順序 Monkey → PP → Ovis；Monkey/PP 每组三轮格式顺序为 JPG→PNG、PNG→JPG、JPG→PNG，Ovis JPG→PNG。串行，重试 0、预热 0。
- Monkey layout 请求 max_tokens=2048，Ovis max_tokens=8192；提示词与冻结协议一致；没有新增 temperature、seed 或任何调参。
- PP `/layout-parsing`、JSON Base64、fileType=1；方向/展平/文字行方向/印章/表格/图表识别关闭，行内公式开启，returnMarkdownImages=false、visualize=false；其余同一默认值。model_settings 六次回显一致，未独立验证两个布局子模型。
- Monkey/Ovis 成功响应均 finish_reason=stop；PP application errorCode=0。服务指纹与前次一致，权重 revision 仍 unknown，不声称完全锁定。
- 新运行开始 `2026-09-11T03:08:16.353256+00:00`，结束 `2026-09-11T03:08:51.345008+00:00`。validate-ground-truth / run / 两次 evaluate / promote 退出码分别为 **0 / 0 / 0,0 / 0**。

下表成功耗时仅统计 COMPLETE 请求；失败时间单列，不能计入成功推理统计。全部耗时包含 FRP、传输和服务处理，不是 GPU 纯推理或容量指标。

| 运行 / Provider / 格式 | COMPLETE 数 | success_latency_ms 中位数（范围） | 失败耗时 ms |
| --- | ---: | --- | --- |
| 旧 / monkey / jpg | 3 | 1027.400（1022.900–1348.033） | — |
| 旧 / monkey / png | 3 | 1224.777（864.945–1563.719） | — |
| 旧 / pp / jpg | 3 | 2453.523（2451.646–2587.861） | — |
| 旧 / pp / png | 3 | 2617.457（2558.734–2891.987） | — |
| 旧 / ovis / jpg | 1 | 5805.602（5805.602–5805.602） | — |
| 旧 / ovis / png | 0 | null / N/A | 1.822 |
| 新 / monkey / jpg | 3 | 1425.124（1030.528–2183.076） | — |
| 新 / monkey / png | 3 | 1230.828（1212.718–1544.498） | — |
| 新 / pp / jpg | 3 | 2516.584（2429.168–5601.155） | — |
| 新 / pp / png | 3 | 2633.878（2532.575–2744.508） | — |
| 新 / ovis / jpg | 1 | 3715.932（3715.932–3715.932） | — |
| 新 / ovis / png | 1 | 3533.268（3533.268–3533.268） | — |

旧公共摘要的 generic durations 曾包含失败请求；旧摘要原样归档。本报告明确将其从成功耗时剔除，未重算旧评分或改写旧指标文件。新摘要仅有 COMPLETE 请求，因此其耗时统计没有混入失败。

## 新旧几何与阅读顺序：分别报告，不择优

评分仍为同类降序 IoU、opaque id 打破同分、一对一匹配，阈值 .50/.75。macro GT=45，paragraph GT=38 且排除独立 visual。PP 的检测层额外拆出公式，不能把不同粒度的所有 FP 都当内容错误；fine 无确认真值，不评分。模型之间的 agreement 不是对 GT 的 accuracy。

### 旧运行（PARTIAL；PP/Monkey 12/12 完整）

| Provider / 格式 / 轮次 | macro 框数 | macro TP/FP/FN .50；.75 | paragraph TP/FP/FN .50；.75 | visual TP/7 .75 | visual IoU 均值 .50 | order 正确/错误/缺失 |
| --- | ---: | --- | --- | ---: | ---: | --- |
| monkey/jpg/1 | 32 | 22/10/23；10/22/35 | 15/10/23；9/16/29 | 1 | 0.7204 | 0/0/14 |
| monkey/png/1 | 36 | 33/3/12；27/9/18 | 26/3/12；24/5/14 | 3 | 0.7750 | 8/0/6 |
| monkey/png/2 | 36 | 28/8/17；22/14/23 | 21/8/17；16/13/22 | 6 | 0.8582 | 2/0/12 |
| monkey/jpg/2 | 38 | 35/3/10；25/13/20 | 28/3/10；18/13/20 | 7 | 0.9331 | 6/0/8 |
| monkey/jpg/3 | 35 | 31/4/14；20/15/25 | 24/4/14；14/14/24 | 6 | 0.8890 | 2/0/12 |
| monkey/png/3 | 24 | 18/6/27；6/18/39 | 11/6/27；3/14/35 | 3 | 0.7896 | 0/0/14 |
| PP 全部六次一致 | 61 | 34/27/11；21/40/24 | 15/8/23；8/15/30 | 7 | 0.9467 | 5/0/9 |

### 新运行（COMPLETE；PP/Monkey 12/12 完整）

| Provider / 格式 / 轮次 | macro 框数 | macro TP/FP/FN .50；.75 | paragraph TP/FP/FN .50；.75 | visual TP/7 .75 | visual IoU 均值 .50 | order 正确/错误/缺失 |
| --- | ---: | --- | --- | ---: | ---: | --- |
| monkey/jpg/1 | 38 | 32/6/13；24/14/21 | 25/6/13；18/13/20 | 6 | 0.9086 | 3/0/11 |
| monkey/png/1 | 20 | 14/6/31；9/11/36 | 7/6/31；6/7/32 | 3 | 0.7982 | 0/0/14 |
| monkey/png/2 | 24 | 17/7/28；10/14/35 | 10/7/28；9/8/29 | 1 | 0.7291 | 0/0/14 |
| monkey/jpg/2 | 36 | 28/8/17；22/14/23 | 21/8/17；16/13/22 | 6 | 0.8582 | 2/0/12 |
| monkey/jpg/3 | 38 | 35/3/10；25/13/20 | 28/3/10；18/13/20 | 7 | 0.9331 | 6/0/8 |
| monkey/png/3 | 35 | 31/4/14；20/15/25 | 24/4/14；14/14/24 | 6 | 0.8890 | 2/0/12 |
| PP 全部六次一致 | 61 | 34/27/11；21/40/24 | 15/8/23；8/15/30 | 7 | 0.9467 | 5/0/9 |

各次 precision/recall、IoU 均值/中位数和缺失原因分别保存在旧、新公共指标；当前公共 JSON 不包含旧结果拼接。两轮两模型的 visual 在 IoU .50 下均 7/7，图域数相同并不保证边界完整或题图关联正确。

- PP：新六次预测 hash 相同，且与旧六次预测 hash 相同。两格式及三次重复的框、内容候选和回显一致；本页格式质量差为 0。visual IoU 均值 0.9467，.75 下 7/7；paragraph recall@.50 仅 15/38，顺序覆盖 5/14。分块合并并未因连接恢复消失。
- Monkey：旧 JPG 框数 32/38/35、PNG 36/36/24；新 JPG 38/36/38、PNG 20/24/35。新旧都存在明显分块、图域边界及阅读顺序锚点覆盖波动，不能只展示较好的某次结果。

- 旧 Monkey JPG：macro recall@.50 三次均值 0.6519；visual IoU 三次均值 0.8475。
- 旧 Monkey PNG：macro recall@.50 三次均值 0.5852；visual IoU 三次均值 0.8076。
- 新 Monkey JPG：macro recall@.50 三次均值 0.7037；visual IoU 三次均值 0.9000。
- 新 Monkey PNG：macro recall@.50 三次均值 0.4593；visual IoU 三次均值 0.8054。

新运行各类 agreement（只统计匹配框的 IoU，不隐藏未匹配框；完整分母在 JSON）：

| 比较范围 | 配对数 | 匹配 IoU 均值范围 @.50 |
| --- | ---: | --- |
| monkey / within_format_repeat | 6 | 0.8959–0.9219 |
| monkey / cross_format | 9 | 0.8474–0.9498 |
| pp / within_format_repeat | 6 | 1.0000–1.0000 |
| pp / cross_format | 9 | 1.0000–1.0000 |
| PP/Monkey 同格式同轮 | 6 | 0.7953–0.9196 |

PP block_order=null 保持 missing，不用几何排序补齐；0 个 incorrect 不能掩盖大量 missing。保留第 1 题选项图与第 5/8/9 题图题的冻结检查，后两者 target_not_on_this_page；不宣称跨页题图验证完成。

## Ovis 新配对与关键内容限制

| 运行 / 格式 | 完整响应 | 原始参考命中 | 轻量规范化参考命中 | 可作格式配对 |
| --- | --- | ---: | ---: | --- |
| 旧 / jpg | 是 | 13/17 | 17/17 | 仅历史单次观察 |
| 旧 / png | 否，ConnectError | N/A | N/A | 否 |
| 新 / jpg | 是 | 13/17 | 17/17 | 新 run 内配对 |
| 新 / png | 是 | 10/17 | 17/17 | 新 run 内配对 |

- 新 Ovis JPG/PNG 都在预先确认的 17 项参考片段中规范化命中 17/17，原始字符串差异主要涉及空白及 Markdown/LaTeX 定界符。该结果不是全文准确率、一般公式等价判定、重复稳定性或几何证据；每种格式只有一次成功结果。
- 新 PP 与旧 PP 每次都为 13/17 局部片段命中，另 4 项 missing_localized_candidate；不能把合并框造成的定位缺失直接记成字符错误。Monkey 仍 layout-only，正文 N/A。
- 原报告记录的第 2 题选项与第 3 题题干合并、第 6 题 C/D 合并，以及后者 `<` 写成 `\leq`，在相同 PP 预测中继续保留。没有调参消除它们。
- **报告观察更正（不改变指标）**：旧报告另称 `y` 被写成 `v`。本轮对同一旧/新 PP 预测的对应 D 段进行字符级核对，实际包含 `y`、不含 `v`；因此撤回这一项错误文字描述。旧公开报告和旧私有人工观察记录仍原样保存在原位置/归档，不伪称模型改善；真值、映射、计分及所有旧证据未改写。
- 已查看新 run 私有关键内容对照图；保留原始比较与现有轻量规范化结果，不合并 `<`/`≤`、`y`/`v`，不解题、不新增高风险字符仲裁或裁剪策略。

## 离线复算、只读证明与验证

新 run 两次 evaluate 的 metrics SHA-256 相同：`a2580fb1c6d1371bc20d48f99a7096db9f93495e9a6e0d0681646a6fd42a4b63`。requests SHA-256 前后相同：`90df9a51cf2f354e5419f91591dbb79a18babcdda3deec17168635b70d45bc9c`。只用新 run 的本地响应，verify_run 通过，不发模型请求。

```sh
RUN_DIR="tmp/raster-regression/runs/t0016-mac-20260911T030753Z-r2"
uv run --locked python scripts/evaluate_raster_models.py evaluate \
  --run-dir "$RUN_DIR" \
  --ground-truth tmp/raster-regression/cases/math_exam_001/ground-truth.private.json
uv run --locked python scripts/evaluate_raster_models.py promote --run-dir "$RUN_DIR"
```

以上命令只面向新目录；旧 PARTIAL 目录已封存，不再执行会写回评分/叠加图的命令。

| 检查 | 本轮实际结果 |
| --- | --- |
| uv sync --locked | PASS |
| uv run --locked pytest | 182 passed，0.65s；本轮无代码变更、无新增测试 |
| ruff check . | PASS |
| mypy . | PASS，25 source files |
| validate_task_catalog.py | PASS，97 个 Ticket、依赖/语义一致 |
| validate_model_baseline.py | PASS |
| git diff --check | PASS |
| T0015 原清单 | 70/70 文件哈希不变 |
| 原 PARTIAL 全目录 | 59/59 文件哈希不变，集合不变 |
| 复算确定性 | 两次一致，requests 不变 |
| 隐私与权限 | 公共两文件无原文、Base64、密钥、用户绝对路径；私有文件0600/目录0700 |

T0015 原 70 文件清单 SHA 为 `962515bb3a50d3b3a4a893149314de06ea16c79c4bc00f5f824a62c30b0c04e2`。没有改写已验收发现代码、Spec、model_contracts 夹具或历史运行。182 是这次真实重新执行的结果，不仅引用上轮证书；测试仍禁止真实 HTTP，不用 Mock 代替本轮14个真实响应。

## 交付、决策与后续边界

本轮可提交 Diff 只有：

- `tasks/reports/T0016_REPORT.md`
- `tasks/reports/T0016_METRICS.json`

新私有证据：`tmp/raster-regression/runs/t0016-mac-20260911T030753Z-r2/`；收尾归档与证明：`tmp/raster-regression/closeout-history/t0016-mac-20260911T030753Z-r2/`；原 case 和原 run 原样保留。正文、原图、预测和审阅图不进入 Git。

格式策略维持：已有 JPG 保留原字节；新工作图 PNG 是避免新增有损编码的保守建议，不是 PNG 更准确的实验结论。单页结果不足以指定永久几何权威，继续 ADR-006。

阶段建议 ACCEPTED_WITH_QUALITY_FINDINGS 的依据是同协议新 run 14/14、证据链/离线复算有效、门禁通过；不是模型无缺陷。全文、细粒度 OCR、跨页关系和生产转换链路仍未验收。

本轮未 commit、push、merge、amend、创建 PR、修改 FRP、执行第三轮推理或 T0017；未重做 T0015，也未实现生产 Adapter、QuestionBlock/Figure Resolver、DOCX/PDF 主流程、网关或裁剪策略；无 ZIP/Patch。停在未暂存、可审查的新 Diff。

后续经授权可用当前功能分支的增量提交和 PR 收口。独立路线为 T0017（依赖 T0015）及 T0002/模型无关 P0/P1；不人为把 T0016 增加为全部独立工作的总闸门。本轮没有自动启动后续 Ticket。
