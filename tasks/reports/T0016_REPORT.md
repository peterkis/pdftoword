# T0016 / P0-GATE-001B — JPG/PNG 与数学试卷回归

最终建议：**PARTIAL，暂不 ACCEPTED**。14 次请求尝试得到 13 个完整响应，最后 Ovis PNG 建连失败；没有重试或选择性补跑。模型质量问题本身不阻断验收，本次未满足验收的原因是输入矩阵缺少一个真实响应。

| 字段 | 当前结果 |
| --- | --- |
| execution_status | PARTIAL |
| annotation_status | REVIEWED，agent_visual（非人工） |
| quality_findings | 图域结果较好，但分块、顺序覆盖和关键字符存在缺陷 |
| input_policy_decision | 已有 JPG 保留原字节；新生成工作图可暂用 PNG 避免新增有损编码，单页未证明识别优势 |
| geometry_decision | 维持 ADR-006 多候选，不建立永久唯一权威 ADR |

## 起点与 T0015 只读证明

- 已先读 OS 交接文档；初始工作区干净，旧功能分支 HEAD 为 `69271280e6897eda7ef1a008efac4024dc130fb9`。
- 按授权 fetch 后将本机 main 快进到 `74f619b8ebea1ce75cf07629022bf60728d00a3d`，无后续 main 提交。新建工作分支 `feat/t0016-raster-regression`，本轮起始 HEAD 即该 SHA，祖先检查通过。
- T0015 已接受 run：`t0015-mac-20260909T061855Z`。其生成 Spec、整个 model_contracts 夹具目录、两份发现脚本、报告和现存历史运行文件共 70 个文件先保存哈希，收尾逐文件验证。
- 起始私有哈希清单 SHA-256：`962515bb3a50d3b3a4a893149314de06ea16c79c4bc00f5f824a62c30b0c04e2`；收尾结果 **70/70 未改写**。原清单位于 `tmp/raster-regression/t0015-readonly-start.private.json`。
- 未调用 T0015 artifact promotion，未修改已验收的发现代码或契约。只复用配置、URL、HttpClient、OpenAPI 归一化和安全 literal parser。

## 输入与视觉标注

case_id：`math_exam_001`。源图由文件内容识别为 JPEG，800×1159，RGB，EXIF orientation=1，无 ICC。无旋转、展平、缩放、锐化、二值化或边框操作。

| 对象 | 文件大小 | SHA-256 |
| --- | ---: | --- |
| JPG 文件 | 94410 bytes | `fe608629ae8af60890684c77437b3d62facd3a0c27b9fa019692890f96cbcf52` |
| PNG 文件 | 381127 bytes | `505d5b8cbbbe91f530dfd9af7d8e2ef48592e6673ddb117ffe1eeb1ea2269afd` |
| 两者相同的 decoded_pixel_sha256 | — | `82e2ef3ea21b23129162e9aab9433644672a71032f95bb8cdf6bd943527c2265` |
| ground-truth.private.json | — | `ec7aab31c0a4589a1651345a301a5ab6837ecf3ffa5b2e116ab3a0bb7320e64b` |
| 冻结 protocol.snapshot.json | — | `5b1ae72d4d0b3ef4fe6aeef5c3945ff9074126a30e9c204c81e7c7c114539d4c` |

- Pillow 12.1.1，JPEG decoder version 6.2；PNG compress_level=6、optimize=false。逐像素 RGB bytes 与宽高一致，源 JPEG 的文件 SHA 与授权预期值一致，源字节未重新编码。
- 像素哈希算法：ASCII `width,height,RGB` + NUL + RGB bytes 的 SHA-256。文件 SHA 不冒充像素 SHA。
- 标注 v1.0，reviewer_type=`agent_visual`，reviewer_id=`codex-visual-t0016`；直接查看原图及标注预览后冻结于 `2026-09-09T08:12:56.076501+00:00`，早于本轮任何推理。
- 45 个确认区域：7 个 visual、38 个段落/标题/图题/页脚；1 个不确定边缘标记排除精确评分。17 个确认参考检查，14 个阅读顺序锚点对。细粒度 OCR 框无确认真值，明确 not_scored。
- 第 1 题四个选项与图的位置关系、三个图题均重新对照当前原图；第 8/9 题为 explicit reference，target_not_on_this_page，没有验证完整跨页关系。
- GT 不含模型输出派生答案，未因本轮响应调整区域、转录或阈值；图内字母作为图的一部分，未重复作为正文计数。

**从已有 JPG 生成 PNG 不能恢复 JPEG 之前丢失的细节。本实验只是当前页面的格式接入回归，不是完整编码质量优劣实验，也不能替代纯电子 PDF 验证。**

## 协议、调用与来源

真实 run：`t0016-mac-20260909T081611Z`；开始 `2026-09-09T08:16:11.233770+00:00`，结束 `2026-09-09T08:16:40.521459+00:00`。macOS + Python 3.12 + uv；仅访问既有本机 loopback visitor，未改 FRP、未发送 Authorization。大小写 NO_PROXY 均设置为 127.0.0.1,localhost。

- 元数据 GET 共 3 次，均 HTTP 200。Monkey/Ovis model ID 与基线一致；PP OpenAPI 原始 SHA 与基线相同，归一化结构也相同。无身份/契约漂移。
- Monkey max_tokens=2048、Ovis max_tokens=8192，提示词与 T0015 成功配置一致；temperature 未发送，不声称确定性。只改变输入字节、MIME、input_id。
- PP `POST /layout-parsing` / JSON Base64 / fileType=1。显式关闭 useDocOrientationClassify、useDocUnwarping、useTextlineOrientation、useSealRecognition、useTableRecognition、useChartRecognition；useFormulaRecognition=true；returnMarkdownImages=false、visualize=false。其余参数均沿用服务默认值。
- PP model_settings 回显：use_doc_preprocessor=false、use_seal_recognition=false、use_table_recognition=false、use_formula_recognition=true、use_chart_recognition=false、use_region_detection=true、format_block_content=false。六次回显一致；只是聚合 Pipeline，不声称独立验证两个布局子模型。
- Monkey/Ovis 服务指纹分别为 `vllm-0.26.0-7a07b93c`、`vllm-0.26.0-1a9933c7`，与 T0015 一致；PP fingerprint 未暴露。权重 revision 仍 unknown。
- 所有请求串行，connect timeout=10s、request timeout=600s，重试/warm-up=0。最后 PNG 在建连时失败，不能证明已到达模型推理端。所有 14 次尝试都保留，未拼接其他运行。

| 顺序 | Provider | 格式 / 轮次 | HTTP | 结果 | 总耗时 ms |
| ---: | --- | --- | ---: | --- | ---: |
| 1 | monkey | jpg / 1 | 200 | COMPLETE | 1348.033 |
| 2 | monkey | png / 1 | 200 | COMPLETE | 1224.777 |
| 3 | monkey | png / 2 | 200 | COMPLETE | 1563.719 |
| 4 | monkey | jpg / 2 | 200 | COMPLETE | 1022.900 |
| 5 | monkey | jpg / 3 | 200 | COMPLETE | 1027.400 |
| 6 | monkey | png / 3 | 200 | COMPLETE | 864.945 |
| 7 | pp | jpg / 1 | 200 | COMPLETE | 2587.861 |
| 8 | pp | png / 1 | 200 | COMPLETE | 2617.457 |
| 9 | pp | png / 2 | 200 | COMPLETE | 2558.734 |
| 10 | pp | jpg / 2 | 200 | COMPLETE | 2451.646 |
| 11 | pp | jpg / 3 | 200 | COMPLETE | 2453.523 |
| 12 | pp | png / 3 | 200 | COMPLETE | 2891.987 |
| 13 | ovis | jpg / 1 | 200 | COMPLETE | 5805.602 |
| 14 | ovis | png / 1 | 无响应 | NETWORK_BLOCKED | 1.822 |

13 个完整响应无截断，Monkey/Ovis 成功响应 finish_reason=stop；PP application errorCode=0。最后一个状态 NETWORK_BLOCKED / ConnectError，无 HTTP 响应、无原响应 hash，不能记作 OCR 错误或身份不匹配。

| 格式 / Provider | 中位数 ms | 范围 ms |
| --- | ---: | --- |
| monkey_jpg | 1027.400 | 1022.900–1348.033 |
| monkey_png | 1224.777 | 864.945–1563.719 |
| pp_jpg | 2453.523 | 2451.646–2587.861 |
| pp_png | 2617.457 | 2558.734–2891.987 |
| ovis_jpg | 5805.602 | 5805.602–5805.602 |
| ovis_png | 1.822 | 1.822–1.822 |

Ovis PNG 的 1.822ms 是失败建连耗时，不是模型延迟。所有耗时包含 FRP、传输和服务处理，不代表 GPU 纯推理时间、P95/P99 或生产容量。

## 评分方法与可审计修正

按同类区域降序 IoU 确定性贪心一对一匹配；同分按 opaque id。0.50/0.75 为诊断匹配阈值，不是生产质量承诺。漏检分母包含全部已确认 GT；非法框单独记录，不修剪。合并/拆分按交叠覆盖关系输出，绝不重复增加 TP。

首次离线核对发现工具没有统一 Monkey 的首字母大写类别，导致其零匹配统计失效。保留 v1.0 评分及原脚本于该 run 的 evaluation-history.private/；评估 v1.1 修复类别大小写/语义别名，并从 paragraph 分母排除独立 visual。修正说明见 `specs/t0016-evaluation-correction.json`，新增真实函数回归测试。该修正不改真值、bbox、阈值、推理协议、响应或已采集预测，不新增请求；初版零匹配不能解释为质量结果。

- 协议和输入在推理前冻结；修正版本属于公开的评估实现修复，不能隐称整个最终评估实现都在推理前已验证无误。
- 原采集工具哈希、最终评估工具哈希及修正文件哈希分别保留；后者不同是明确记录的实现修复。
- macro 对 PP 使用 layout_det_res、对 Monkey 使用模型块；包含全部 45 个视觉标注区域。PP 检测层还独立输出公式，粒度和 GT 不完全一致。macro 的 FP/分割统计不能简单视为内容错误。
- paragraph 对 PP 使用 parsing_res_list、对 Monkey 使用相同模型块的非 visual 子集；GT=38。fine 只记录框数和未评分原因。visual 专项对 7 个图域同类比较，是本页更直接可比的几何指标。

## 几何准确性：分别对视觉 GT

### 全页块与段落层

以下 TP/FP/FN 同时列出两个阈值；precision/recall、IoU 均值/中位数、无效数量的逐次全量值在 `T0016_METRICS.json`。所有成功预测的非法框数量为 0。

| Provider / 格式 / 轮次 | macro 预测数 | macro TP/FP/FN @.50 | @.75 | paragraph 预测数 | paragraph TP/FP/FN @.50 | @.75 |
| --- | ---: | --- | --- | ---: | --- | --- |
| monkey / jpg / 1 | 32 | 22/10/23 | 10/22/35 | 25 | 15/10/23 | 9/16/29 |
| monkey / png / 1 | 36 | 33/3/12 | 27/9/18 | 29 | 26/3/12 | 24/5/14 |
| monkey / png / 2 | 36 | 28/8/17 | 22/14/23 | 29 | 21/8/17 | 16/13/22 |
| monkey / jpg / 2 | 38 | 35/3/10 | 25/13/20 | 31 | 28/3/10 | 18/13/20 |
| monkey / jpg / 3 | 35 | 31/4/14 | 20/15/25 | 28 | 24/4/14 | 14/14/24 |
| monkey / png / 3 | 24 | 18/6/27 | 6/18/39 | 17 | 11/6/27 | 3/14/35 |
| PP / 全部六次相同 | 61 | 34/27/11 | 21/40/24 | 23 | 15/8/23 | 8/15/30 |

PP fine 层 82 个 OCR 框；该粒度没有确认 GT，not_scored，不能报告细粒度 accuracy PASS。

### 关键图域

两模型每次都输出 7 个图域，IoU .50 时均 TP=7、FP=0、FN=0、precision=recall=1。高阈值及边界差异如下。

| Provider / 格式 / 轮次 | TP/FP/FN @.75 | precision / recall @.75 | 7 个匹配图域平均 IoU @.50 | 中位数 IoU @.50 |
| --- | --- | --- | ---: | ---: |
| monkey / jpg / 1 | 1/6/6 | 0.1429 / 0.1429 | 0.7204 | 0.6901 |
| monkey / png / 1 | 3/4/4 | 0.4286 / 0.4286 | 0.7750 | 0.6901 |
| monkey / png / 2 | 6/1/1 | 0.8571 / 0.8571 | 0.8582 | 0.9049 |
| monkey / jpg / 2 | 7/0/0 | 1.0000 / 1.0000 | 0.9331 | 0.9385 |
| monkey / jpg / 3 | 6/1/1 | 0.8571 / 0.8571 | 0.8890 | 0.9300 |
| monkey / png / 3 | 3/4/4 | 0.4286 / 0.4286 | 0.7896 | 0.6978 |
| PP / 全部六次相同 | 7/0/0 | 1.0000 / 1.0000 | 0.9467 | 0.9528 |

| GT opaque id | Monkey 六次 IoU 范围 | PP 六次 IoU |
| --- | --- | ---: |
| r006 | 0.6632–0.9673 | 0.9779 |
| r007 | 0.6720–0.9603 | 0.9756 |
| r008 | 0.6901–0.9338 | 0.9262 |
| r009 | 0.6495–0.9049 | 0.9045 |
| r034 | 0.8434–0.9385 | 0.9331 |
| r035 | 0.6409–0.9435 | 0.9528 |
| r036 | 0.7441–0.9554 | 0.9570 |

未发现该页完整图域漏检；Monkey 部分框包含选项标签，部分框裁掉图的上沿/图内文字，亦有向下偏移的文字框。不能用“7/7 找到图”替代图片完整性或题图绑定验收。

## 重复稳定性与跨格式差异

- PP 六次私有预测文件 hash 完全相同：同格式三个两两比较、跨格式九个比较，检测层均 61/61 匹配、IoU=1.0000；文字候选、段落、模型设置也一致。此页 PP JPG/PNG 的对 GT 质量差值为 0。
- Monkey JPG 块数为 32/38/35，PNG 为 36/36/24；存在同格式波动。其正文是 layout-only，N/A，不记零。
- Monkey 同格式块匹配 IoU 均值范围：JPG 0.8510–0.9498，PNG 0.8167–0.9397；跨格式九次两两比较为 0.8811–0.9285。它们只描述匹配部分；未匹配框数量见公共 JSON，不能只用高均值掩盖拆合差异。
- Monkey 对 GT 的 macro recall@.50：JPG 三次平均 0.6519，PNG 0.5852；图域平均 IoU 的 JPG/PNG 三次均值分别 0.8475 / 0.8076。重复波动明显，样本不足以归因于格式或挑选赢家。
- PP 与 Monkey 同格式同轮的块 agreement：匹配数 20–32，匹配 IoU 均值 0.8152–0.9196。该值不是 accuracy；其 GT 指标独立列在上一节。
- Ovis 只有一个成功 JPG，PNG 为 NETWORK_BLOCKED；不声称格式差异、重复稳定性或几何能力。

## 阅读顺序与内容

使用预先确认的 14 个锚点对，IoU .50 一对一匹配段落；没有几何排序补齐模型顺序。

| Provider / 格式 / 轮次 | correct / incorrect / missing | 覆盖率 |
| --- | --- | ---: |
| monkey / jpg / 1 | 0 / 0 / 14 | 0.0000 |
| monkey / png / 1 | 8 / 0 / 6 | 0.5714 |
| monkey / png / 2 | 2 / 0 / 12 | 0.1429 |
| monkey / jpg / 2 | 6 / 0 / 8 | 0.4286 |
| monkey / jpg / 3 | 2 / 0 / 12 | 0.1429 |
| monkey / png / 3 | 0 / 0 / 14 | 0.0000 |
| PP / 全部六次相同 | 5 / 0 / 9 | 0.3571 |

0 个 incorrect 不等于全页顺序正确；缺失锚点很多。PP 页脚 block_order=null 保持 missing，图域与图题仍需后续关联逻辑。

- PP 每次 17 个参考检查中，13 项在受限区域候选中原始/轻量规范化均命中，4 项缺少可定位候选。四项分别涉及题干与选项的合并，不能单据此判为 OCR 字符错误。
- 另行查看已保留的 PP 合并块上下文：第 2 题选项与第 3 题题干合并，第 6 题 C/D 合并；其中第 6 题 D 的 `<` 被写成 `\leq`，`y` 被写成 `v`。这是视觉复核后的质量发现，未增加或回填原先 17 项的计分。六次 PP 预测相同，因此该缺陷在全部六次保留。
- Ovis JPG：17 项 page-presence 检查原始命中 13 项，按已冻结空白/LaTeX 定界符处理后命中 17 项；对应高风险字符在该响应中保留。page presence 不证明图题绑定、完整公式等价或每个字符正确；Ovis 不作为 GT。
- 第 1 题的四个选项标签和三个图题在 PP 受限候选检查中命中；仍不能仅因识别出题号/标签就声称实现 QuestionBlock/Figure Resolver。图题指向本页外题干的两项只记录 explicit reference。
- 未建立公式等价器、未解题、未合并 `<`/`≤` 或 `y`/`v`；公式候选保留在私有证据，正文与公式没有重复计数。

## 决策与适用范围

1. 已有 JPG：保留原字节，避免再次有损重编码。此页生成 PNG 增大到 381127 bytes，不能恢复既有 JPEG 损失。
2. 新渲染/裁剪工作图：PNG 可作为避免新增有损压缩的保守暂定格式；本轮不新增生产格式策略实现，也不把该建议写成 PNG 识别精度更高的实验结论。
3. 单页已解码等像素对照只能说明当前服务对这两个文件的接入表现；不能覆盖原生 PNG、不同 JPEG 编码质量、其他页面、拍照旋转、密集公式、表格或电子 PDF。Ovis 格式结论尤为空缺。
4. 继续维持 ADR-006。PP 在本页图域几何/重复稳定性较好，但其段落合并与关键字符错误不能忽略；Monkey 的波动明显。无永久唯一几何权威，无新终局 ADR，无 T0405。

## 本地证据与离线复算

私有 case：`tmp/raster-regression/cases/math_exam_001/`；私有 run：`tmp/raster-regression/runs/t0016-mac-20260909T081611Z/`。原图、完整标注、响应、预测、叠加图、审阅 HTML、历史评分和质量复核仅在这些忽略目录。目录 0700、文件 0600。

运行目录额外保存 inputs.private/ 两份输入及 ground-truth.snapshot.private.json，确保不依赖后来变化的 case 文件。HTTP 原字节 SHA 与私有裁剪版 SHA 分开；图片 Base64 剥离、URL 不跟随，普通日志及公共摘要无正文。

```sh
RUN_DIR="tmp/raster-regression/runs/t0016-mac-20260909T081611Z"
uv run --locked python scripts/evaluate_raster_models.py evaluate \
  --run-dir "$RUN_DIR" \
  --ground-truth tmp/raster-regression/cases/math_exam_001/ground-truth.private.json
uv run --locked python scripts/evaluate_raster_models.py promote --run-dir "$RUN_DIR"
```

以上命令只读本地采集证据，不发模型请求。该 PARTIAL run 的 CLI 返回 2 是执行状态提示，不代表离线计算失败；正常生成 metrics.private.json 与脱敏 T0016_METRICS.json。任何输入/真值/协议/请求链哈希或版本不一致均拒绝评分/推广。最终工具变化后须重新 evaluate，不能推广旧评分。

| 来源 | SHA-256 |
| --- | --- |
| 采集 scripts/raster_regression.py | `6bf19bd0efd2562cc96db149636995c35c5324c9eb58763d2028e824efcd9d73` |
| 采集 scripts/evaluate_raster_models.py | `6210b31aacfc753e1c3859072cbe0605e94fc94908f55e8d841bc0f986cf5be6` |
| 采集 scripts/model_contract_discovery.py | `f1ccda2cc9cffd7565b232474d26948a91ee496d5ed609086ca171e2c20d05da` |
| 采集 uv.lock | `32767c6633890497305d5259c48727ba568bb9f43ac9793b690420435d2aff0d` |
| 最终评估 scripts/raster_regression.py | `89d0ed8a48c5cdca9aa9bc9ece6e081aecbb9284679d590c4cc104a305265c58` |
| 最终评估 scripts/evaluate_raster_models.py | `9da833296a95228d94f5876b05820899157a89a8cb322a5363c3ae7a1e498a31` |
| 最终评估 scripts/model_contract_discovery.py | `f1ccda2cc9cffd7565b232474d26948a91ee496d5ed609086ca171e2c20d05da` |
| 最终评估 uv.lock | `32767c6633890497305d5259c48727ba568bb9f43ac9793b690420435d2aff0d` |
| 评估修正说明 | `22c441a531fbe690166c19383eec79bfde4b204c2c50bed2c3844e2cba073fca` |

## 验证与边界

| 检查 | 结果 |
| --- | --- |
| uv sync --locked | PASS |
| uv run --locked pytest | **182 passed**（含 35 项新增 raster 测试）；无失败 |
| uv run --locked ruff check . | PASS |
| uv run --locked mypy . | PASS，25 source files |
| validate_task_catalog.py | PASS，97 个 Ticket 三处一致，依赖/语义检查通过 |
| validate_model_baseline.py | PASS |
| git diff --check | PASS |
| 同一 run 离线重复 evaluate | metrics SHA 完全相同，requests 文件不变，未发网络 |
| T0015 只读检查 | 70/70 不变 |
| 公共隐私 / 私有权限检查 | 15 个交付文件未含原文、输入 Base64 或本机绝对路径；私有文件 0600、目录 0700 |

全仓测试包含原有 147 项及新增 35 项；未忽略测试目录、关闭类型严格度或删除既有测试。初版新测试的预期失败和评分修复已解决，不以此掩盖 Ovis PNG 的真实网络失败。

- 新增合成 MockTransport 测试直接调用真实实现；默认 pytest 仍禁止真实 HTTP。合成通过不替代上述真实模型结果或阶段验收。
- 已查看原图、标注预览、六次 Monkey 与代表性 PP 叠加图、私有关键内容对照；PP 六次预测 hash 相同。没有人工 reviewer，不伪称 human reviewed。
- 未执行 T0017；未实现生产 Adapter、Layout IR、PDF 解析、QuestionBlock/Figure Resolver、DOCX Builder、桌面 UI 或统一网关 8100；没有模型下载、部署或调参。
- 未执行 commit、push、创建 PR 或功能分支 merge。唯一 Git 更新是用户要求的 fetch 和 main 快进同步；没有新建合并提交。没有暂存、没有 ZIP/Patch 交付，保持可审查 Diff。

## 文件清单

新增：

- `scripts/raster_regression.py`
- `scripts/evaluate_raster_models.py`
- `specs/t0016-evaluation-protocol.json`
- `specs/t0016-evaluation-correction.json`
- `tests/unit/test_raster_regression.py`
- `tests/unit/test_raster_metrics.py`
- `tests/unit/test_raster_evidence.py`
- `tests/fixtures/raster_regression/geometry.synthetic.json`
- `tasks/reports/T0016_METRICS.json`
- `tasks/reports/T0016_REPORT.md`

修改：

- `pyproject.toml`
- `uv.lock`
- `scripts/README.md`
- `specs/error-codes.md`
- `CHANGELOG.md`

## 剩余事项

完整验收仍缺 Ovis PNG 真实响应；本轮 14 次预算已用尽，没有自动重试。恢复连接并另行确认新的完整 run 后，必须保留本次 PARTIAL、使用新 run_id 和清晰原因，不能只补一个请求后拼接成此次成功。该限制属于证据完整性，不是要求模型效果变好。当前不建议 ACCEPTED 或 ACCEPTED_WITH_QUALITY_FINDINGS。
