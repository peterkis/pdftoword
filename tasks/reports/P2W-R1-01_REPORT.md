# P2W-R1-01 实施报告

- 实际仓库/分支/开始 HEAD/结束 HEAD：`peterkis/pdftoword` / `main` / `6b94819a71ad033e480f3808f2f56f4d364a6453` / 同开始。
- 用户授权：仅 R1-01；未 commit/push/merge，未执行 R1-05。
- 工程状态：**VERIFIED（任务范围）**；全仓 quality 仍 FAIL，原因见下。
- 人工/视觉接受：PENDING；本次视觉检查、Microsoft Word 检查均 NOT_RUN。

## 已实现行为与文件

- `prototypes/docx_output/structure_processors/{base,legacy}.py`：独立协议和真实 identity 转发；对已选 Layout IR 做校验、深拷贝，生成结构候选及无损失报告，不实现新的段落/表格算法。
- `prototypes/docx_output/planning/render_plan.py`：`render-plan/1` 保存完整 IR、source IDs、内容、源样式引用、输出样式绑定和既有 A4 自然流布局。候选、锁、关系和 inline parts 不做有损中间格式转换；不支持的布局明确拒绝。
- `prototypes/docx_output/renderers/{base,legacy}.py`：输出协议与调用原 `writer.build` 的可执行 LegacyRenderer。原 writer 逐字节未修改。
- `prototypes/docx_output/pipeline.py`：finish 统一经过 StructureProcessor → RenderPlan → DocxRenderer；写入版本、实现文件 hash、结构候选、计划、mapping-loss-report。auto 已存在时在写任何文件前拒绝。
- `prototypes/docx_output/render_replay.py`：校验旧作业资产、input.pdf、wire/stored 响应 hash，封存完整只读输入快照；A/B 分配不同子作业，支持嵌套 region 图片。旧人工 overrides、auto/reviewed、请求清单不写入。原始页数超过 3 页拒绝，重复调用创建新作业。
- `scripts/docx_demo.py`、`prototypes/docx_output/server.py`：实际 `compare-renderers` CLI 和受现有会话/Origin/锁保护的 `POST /api/compare-renderers/{job_id}` 共享同一函数。当前可选 renderer 为 legacy；Python 协议支持独立注入。原命令继续保留。
- `tests/productization/test_renderer_boundary.py`：10 项真实回归，封锁 socket connect/connect_ex/DNS；实际运行 renderer/结构处理/CLI/API，覆盖重复输出、缺失/篡改资产、嵌套资产、响应篡改、symlink、源目录隔离、auto 不可变、独立替换。
- `docs/development-plan/README.md`、`r1-reuse-record.json`：最新外部计划指针和六类能力必做任务映射。新增目录内的 `__init__.py` 仅声明包。

相对参考提交 `6c41bd6`，开始 HEAD 仅 AGENTS.md 有变化，因此 PR #6 代码保护保留；本次未修改它的插图识别/替换逻辑。S1 废弃，S2-01～06 继承完成；旧 97 项和旧计划目录没有改写。

## 实物

实际使用问题作业的 2 页 IR，未重建大基线。源与新作业都保存在忽略的私有目录，公开报告不含原文/图片。

- 原作业：`tmp/docx-demo/s2-page-correction-20260917-114211/demo-9032ecb6a45b494eb8cee630d1ef0d3b`。
- 输入 IR SHA256：`80a51a83ffa77d41f12a8f8db95f9d894b4827bd7287445e38c4d65bf47b09c6`。
- 源 input.pdf SHA256：`df7a1da37ee7fbe028296d5be2a9b0ba134b69893f0aec24ea05c73a2df99d44`。
- 原 auto.docx SHA256：`c4d64308101407da6d4400da238e74bfd78e07f553a02e3c9d806546a6ca2f82`。
- 完整输入、资产、响应、DOCX 文件集合逐项 hash：`tmp/docx-demo/r1-01-evidence/real-replay-checks.json` 的 source_files。34 个文件前后集合与字节一致。
- 比较清单：`tmp/docx-demo/r1-01-evidence/final-jobs/demo-462b392c546c42dda9d50e8e7e70c3cf/comparison.json`；同目录 evidence 为完整快照。
- 两份 DOCX 均经 ZIP 完整性校验和 python-docx 重开；这不是 Microsoft Word 验收。
- preview 是现有 IR 预览；独立 overlay NOT_CREATED，Word 回渲染 NOT_RUN。

| 分组 | 实际产物 | SHA256 |
| --- | --- | --- |
| A | `tmp/docx-demo/r1-01-evidence/final-jobs/demo-50f0e0e50d1c4cacb2d4c18c51e4c7f8/auto.docx` | `01a01ff5d912b75d6c25519d73e7d208cc910a164fe31d202937935ef5564007` |
| A | `tmp/docx-demo/r1-01-evidence/final-jobs/demo-50f0e0e50d1c4cacb2d4c18c51e4c7f8/layout.auto.json` | `8032b1278e444d82133a3096fe9a47921855dd288027370f428812c5066af19d` |
| A | `tmp/docx-demo/r1-01-evidence/final-jobs/demo-50f0e0e50d1c4cacb2d4c18c51e4c7f8/render-plan.auto.json` | `64830f1038e5fff8871206fe45baa2cb3086e88d79d00fbd978b8aae7458fecb` |
| A | `tmp/docx-demo/r1-01-evidence/final-jobs/demo-50f0e0e50d1c4cacb2d4c18c51e4c7f8/source-map.auto.json` | `601ea4ff3cb12870c76dcf88864827089d94a60e19ce6dac13b76e2bb150cf6f` |
| A | `tmp/docx-demo/r1-01-evidence/final-jobs/demo-50f0e0e50d1c4cacb2d4c18c51e4c7f8/render-manifest.auto.json` | `a9746bd25b9e51aa0bfee4aa41b8cbaabdbc67872b1d34cdf0099eb54b5d6856` |
| A | `tmp/docx-demo/r1-01-evidence/final-jobs/demo-50f0e0e50d1c4cacb2d4c18c51e4c7f8/mapping-loss-report.auto.json` | `151783a5995109ccbd90f721ae4298c702187b2829bce4c7d8f16e24c82f9b66` |
| B | `tmp/docx-demo/r1-01-evidence/final-jobs/demo-ef17fbd481cd46648d6d994b96d13b33/auto.docx` | `01a01ff5d912b75d6c25519d73e7d208cc910a164fe31d202937935ef5564007` |
| B | `tmp/docx-demo/r1-01-evidence/final-jobs/demo-ef17fbd481cd46648d6d994b96d13b33/layout.auto.json` | `8032b1278e444d82133a3096fe9a47921855dd288027370f428812c5066af19d` |
| B | `tmp/docx-demo/r1-01-evidence/final-jobs/demo-ef17fbd481cd46648d6d994b96d13b33/render-plan.auto.json` | `64830f1038e5fff8871206fe45baa2cb3086e88d79d00fbd978b8aae7458fecb` |
| B | `tmp/docx-demo/r1-01-evidence/final-jobs/demo-ef17fbd481cd46648d6d994b96d13b33/source-map.auto.json` | `601ea4ff3cb12870c76dcf88864827089d94a60e19ce6dac13b76e2bb150cf6f` |
| B | `tmp/docx-demo/r1-01-evidence/final-jobs/demo-ef17fbd481cd46648d6d994b96d13b33/render-manifest.auto.json` | `a9746bd25b9e51aa0bfee4aa41b8cbaabdbc67872b1d34cdf0099eb54b5d6856` |
| B | `tmp/docx-demo/r1-01-evidence/final-jobs/demo-ef17fbd481cd46648d6d994b96d13b33/mapping-loss-report.auto.json` | `151783a5995109ccbd90f721ae4298c702187b2829bce4c7d8f16e24c82f9b66` |

## 验证

| 实际命令 | exit code | 结果 / 日志 |
| --- | --- | --- |
| `uv sync --locked` | 0 | 47 包解析，46 包检查；`tmp/docx-demo/r1-01-evidence/final-checks/uv-sync.txt` |
| `uv run scripts/quality.py --output-dir tmp/docx-demo/r1-01-evidence/quality-final` | 1 | 1292 PASS / 0 FAIL / 0 SKIP；Ruff、task_catalog、model_baseline、schema_samples exit 0；mypy exit 1，既有 19 错误。各步骤日志在 `quality-final/private/`，摘要在 `quality-final/public/summary.json` |
| `uv run pytest tests/productization/test_renderer_boundary.py -q` | 0 | 最终 10 PASS；`verification-final/boundary.txt` |
| `uv run mypy` 加本次 13 个模块/包/测试文件 | 0 | 精确 argv 对应 `pipeline.py`、`server.py`、`render_replay.py`、三个新增包、`scripts/docx_demo.py` 和新测试；`verification-final/focused-mypy.txt` |
| `uv run ruff check .` | 0 | `verification-final/ruff.txt` |
| `uv run scripts/validate_schema_samples.py` | 0 | `verification-final/schema-samples.txt` |
| `git diff --check` | 0 | `verification-final/diff-check.txt` |
| `uv run python -c "exec(open('tmp/docx-demo/r1-01-evidence/verify-real-replay.txt').read())"` | 0 | 封锁出站 socket 调用真实 CLI 并校验实际 DOCX；`logs/real-replay-final.txt` |

计划工具的最终实测（均 exit 0）：`python3 ~/Plans/PDF2Word_Development_Plan_v2.1_20260917/scripts/validate_package.py` 返回 PASS；`next_task.py` 初次只列 R1-01，更新本项后按顺序列 R1-05、R1-02。日志分别为 `logs/plan-validate-final.txt`、`logs/next-task-initial.json`、`logs/next-task-final.json`。本次只修改新包 R1-01 状态，接受记录仍 PENDING。

上述 verification-final 日志均位于 `tmp/docx-demo/r1-01-evidence/` 下。quality 完整运行后仅调整来源映射测试：分别校验当前 DOCX hash，再比较映射语义；最终定向回归与 Ruff/mypy/schema 重新执行。

全仓 mypy 的 19 项均在历史私有 `tmp/productization/source-review-20260915/build_review.py` 和 `tmp/productization/review-v5/build_private_review.py`；与 S2-01～06 报告记录一致。未修改私有脚本，也未添加 ignore/exclude。

调试记录保留：首轮测试 fixture 使用无效关系枚举导致 10 失败，修正为现有 anchored_to 后通过；首次回放漏复制嵌套 region 资产已修复；初次 mypy 重复模块导入已修复；来源映射初次严格比较包含新 DOCX hash，现改为校验各自 hash 后比较映射内容。最终工程结论以上述实际最终检查为准。

## 模型与网络

实际新增模型请求 **0**、metadata GET **0**、新增请求失败 **0**、blocked socket 尝试 **0**。旧请求共 4 份，wire 与 stored JSON 均按旧清单逐项校验；当前直接复用 IR 两次，重新解析/调用响应 **0**。旧历史 model_call_count 保存在 evidence，子作业本次计数为 0。

`uv sync --locked` 是独立依赖检查；本次无新模型/上游库安装。未知 provider revision 明确 unknown，render manifest 保留已有 registry；源码审查快照不冒充安装或调用证据。

## 内容、几何、布局的收益与退化

两份新 DOCX 的所有 `word/` 包部件（包括正文、样式、关系和图片）与旧 DOCX 字节相同；source-map 的 pages/blocks/relations 完全相同，各自 docx_sha256 对应各自实际 DOCX。原 source IDs、内容、阅读顺序、图题关系、资产、issues/provenance 逐项一致。DOCX ZIP 时间/核心元数据可能改变整个包 hash，这不构成正文变化。

本项证明接缝保持当前语义，**不声称排版改善**。Legacy mapping-loss-report 是实际 identity：losses 为空。真实样本未额外构造人工修订；人工证据保护、reviewed 回放及重复导出由合成回归验证。

## 保留/未解决/回滚

- 目标 Microsoft Word/视觉未运行，未签用户接受或发布。
- A/B 当前均为 legacy，未实现/测量 DocVortex 输出或共享后处理；未来通用算法等待 R1-05。
- 未历史封存的文件只有当前 before/after hash，不冒称历史真实性校验。
- 失败尝试输出保留在私有目录，不删除证据；最终比较清单明确选择 final-jobs 下的最终实现产物，非模型最佳结果筛选。
- 结构/renderer 默认均为 legacy，可继续选择 legacy；需要撤回接缝时只回退本次模块及 finish/入口改动，不修改原 writer、S2、源作业和历史记录。
- 下一任务 **P2W-R1-05**，本次停止于 R1-01。

## 接受记录（仅实际接受者填写）

未填写；无接受人/时间，不冒签。

## v2.1 共享复用记录

实际读取新计划包 `baseline/upstream_sources.json` 与 `architecture/reuse_matrix.json`，文件 hash 与完整接口映射见 `docs/development-plan/r1-reuse-record.json`。

- MinerU 参考发布标记 `mineru-4.0.1-released`，参考 commit `23caf85a1b788e56f3f81b587022a740ce2cd6ae`。
- DocVortex 参考 commit `e5b4b206a1cf62ac2b08247d7f42c1d0672487bf`。本任务安装版本、wheel/hash、公共调用输入输出均 NOT_RUN。
- 公共入口按提供的审查清单登记：`docvortex.postprocess.document.model_json_to_middle_json`、`docvortex.content.table.*` 的白名单函数、`docvortex.render.docx.render_docx`。没有导入内部实现。
- 六项 MU-HEADING / MU-PARAGRAPH / MU-TABLE / MU-FORMULA / MU-CAPTION / MU-ORDER 都绑定 R1-05 及后续 R1/R2/R3 必做任务。阅读顺序不把 index 排序等同模型预测。
- 采用/适配/拒绝尚无运行结论；公共共享层的字段损失、依赖许可和项目差异在 R1-05 用实际固定版本验证。本项仅 Legacy identity loss-report 可执行。


## PR #7 首轮审查修复（2026-09-18）

Codex 对 `9cfb53a` 提出的 3 个 P2 均有复现与修复：

- staged input 统一验证 PDF/PNG/JPG/JPEG，篡改拒绝。
- stored response 独立于 raw 路径校验，复用缓存按已有 region/provider 命名契约定位 JSON；缺失、篡改均拒绝。
- RenderPlan elements 通过块 ID 查表，遵循显式 reading_order，与 Legacy 输出一致。

`uv run pytest tests/productization/test_renderer_boundary.py -q`：修复前 6 failed / 11 passed，修复后 17 passed。日志 `tmp/docx-demo/r1-01-evidence/review-{red,green}.txt`。定向 Ruff/mypy exit 0，`git diff --check` exit 0。

`uv run scripts/quality.py --output-dir tmp/docx-demo/r1-01-evidence/review-quality`：1299 passed、无失败/跳过；Ruff/schema/catalog/baseline 正常，全仓 mypy 仍为已知私有 19 错误，整体 exit 1。

真实问题页再次在禁网条件下生成 A/B，34 个旧文件不变，DOCX 内容部件及来源语义与原版一致。新证据在 `tmp/docx-demo/r1-01-review-fixes/`，原证据不覆盖；产物 ID/hash 见 `P2W-R1-01_REVIEW_FIXES.json`。视觉与 Word 接受仍 NOT_RUN。此记录是修复验证，不预先宣称后续远端审查通过。


## PR #7 第二轮审查修复（2026-09-18）

Codex 对 `240fde6` 提出的 3 个 P2 已修复：

- 新 raster、native、region 作业记录来源图 image_sha256，回放逐页验证；旧单张 raster 可使用原文件 SHA256。缺少认证的旧 PDF 来源图必须显式传入已有比较清单 `--source-seal <comparison.json>`，完整源文件集合/hash 必须匹配。HTTP 参数 `source_seal_job_id` 仅定位现有输出根内作业。不能临时生成当前 hash 冒充历史封存。
- A/B 只处理一次 selected evidence，向两组提供独立深拷贝的同一 StructureCandidate，记录 structure_process_count=1。
- 新 `implementation.py` 记录实际 renderer/processor 类、MRO 来源模块 hash、执行方法代码 hash；不可获得源码时明确 UNAVAILABLE。原 shared/legacy 文件 hash 另行保留。

新增反例修复前 3 failed / 17 passed；最终接缝 21 passed。全仓 quality 1303 passed、无失败/跳过；Ruff/schema/catalog/baseline 正常，mypy 仍为历史私有 19 错误，整体 exit 1。`uv run mypy prototypes/docx_output tests/productization/test_renderer_boundary.py scripts/docx_demo.py`：34 source files，exit 0；diff check exit 0。

日志在 `tmp/docx-demo/r1-01-evidence/review2-*`。真实 2 页回放显式采用第一轮已有比较清单，34 个原文件完整匹配，新增输出保存在 `tmp/docx-demo/r1-01-review2-fixes/`，内容和来源语义不变；hash 见 `P2W-R1-01_REVIEW2_FIXES.json`。所有原作业及前两轮产物保留。远端复审待执行，视觉/Word 仍 NOT_RUN。
