# P2W-R1-05 实施报告

- 实际仓库/分支/开始与结束 HEAD：`peterkis/pdftoword` / `main` / `5c176a70294ca6ca4104630110a9b3740e16101e`。
- 用户授权：仅执行 R1-05；本次未 commit/push/PR/merge，也未执行 R1-02。
- 工程状态：**VERIFIED（R1-05 POC 范围）**。全仓 quality 仍因既有私有 mypy 缺陷 FAIL，不称整仓全绿。
- 人工/视觉接受：PENDING；Microsoft Word 未安装，Word/视觉检查 **NOT_RUN**；远端 CI **NOT_RUN**。

## 已实现行为与文件

- `structure_processors/bridge.py`：Layout IR → 真实公共 ModelJson 协议；PDF 点坐标显式归一化，非连续页保留 page_index_map，全文标记由实际页选择确定。producer 为 pdf2word，原文档信息保存在 source ledger，不冒称运行 MinerU。完整 block、候选、lines/angle/score/label、原顺序、人工修改、元数据和 provenance 均保留在 ledger。
- `structure_processors/docvortex.py`：独立进程调用公共 `model_json_to_middle_json`，按源页/输入索引及内容/bbox/图片严格核对映射；未知、重复、清理、归属歧义进入 loss-report。只有可核验建议可采用；缺 lines、非连续页、题/选项或人工修改不自动续接。stage marker 绑定 IR hash，重复导出不重复后处理，输入改动会重新核验。
- `renderers/docvortex.py`、`renderers/capabilities.py`：最终 IR 直接投影严格 MiddleJson，调用公共 `render_docx`，不重复结构处理。对实际 OOXML 范围进行数量、文字、图片 hash 核验并绑定 source-map；明确的未支持样式/布局或输出差异退回 Legacy。坏公式有图时保留原图，裸 LaTeX 不作为 OMML 成功；资产完整性失败不能通过 Legacy 降级绕过。
- `docvortex_worker.py`、`docvortex_runtime.py`：主项目与 SDK 运行时分离，IPC 内容捕获后仅写私有证据。worker 在导入前阻止网络和外部进程，禁止 PDFium/模型相关运行时导入；实际每次回报 PDFium 未加载。图片必须为注册的本地 hash 文件；远程、data URI、HTML 内未注册图片均拒绝。
- `reuse_poc.py`、`scripts/docx_demo.py`：新增真实 CLI `reuse-poc`。结构轴固定 LegacyRenderer，渲染轴固定 IR/RenderPlan；生成独立作业、10 个正/反例探针、公共表格 state、六能力决定和版本证据。
- `scripts/setup_docvortex_runtime.py`、`requirements/docvortex-poc.{in,txt}`、`.github/workflows/quality.yml`：显式安装 hash 锁定的 SDK 后处理/输出依赖切片，CI 在离线 gate 前安装。主 `pyproject.toml`、`uv.lock` 不变，无新模型/推理依赖。CI 配置已做本地静态/测试检查，未冒称远端执行。
- `pipeline.py`：渲染清单记录 effective_renderer，公式实际图片回退参与 fallback 区域统计；默认 Legacy 不变。
- `tests/productization/test_shared_structure_actual.py`、`test_docvortex_renderer.py`：新增 **28 项**回归；连同 R1-01 的 21 项接缝测试，定向 **49 项**。实际调用 SDK，不用 Mock 替代公共函数。
- 版本/许可与复用决定：[评估记录](../../docs/decisions/docvortex-renderer-evaluation.md)、[运行时记录](../../docs/development-plan/r1-05-runtime-record.json)。

上述相对源码路径位于 `prototypes/docx_output/`，除已明确标注的 scripts/tests/requirements/docs 文件。保留 S2、PR #6 和 PR #7 的代码及历史证据；不导入 DocVortex `_internal`、paragraphs/visual 等内部模块作为项目依赖。

## 实物

最终私有目录：`tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3`。

输入为既有问题作业的 **2 个源页、15 个块**，不是 2 页 Word 的声称。原作业 34 个文件集合和 hash 完全不变；以 R1-01 先前可信 comparison seal 校验，4 份原始/存储响应继续保留，不重新识别、不重建大基线。

- 输入 IR SHA256：`80a51a83ffa77d41f12a8f8db95f9d894b4827bd7287445e38c4d65bf47b09c6`。
- 原 input.pdf SHA256：`df7a1da37ee7fbe028296d5be2a9b0ba134b69893f0aec24ea05c73a2df99d44`。
- 结构轴：LegacyStructure + LegacyRenderer 对照 SharedStructure + 同一 LegacyRenderer。
- 渲染轴：同一 IR/RenderPlan 的 Legacy 与 DocVortex；实际 DocVortexRenderer 未回退。
- 根 `model.json`、`middle.json`、`source-ledger.json`、`loss-report.json` 是真实共享调用结果。
- 原始文件逐项 hash 位于 `poc-manifest.json` 的 source_files；不把私有正文、图片或响应正文提交到公开仓库。
- 现有 IR HTML 预览在各子作业 `review/index.html`；它不是 Word 回渲染。独立 overlay **NOT_CREATED**。
- DOCX 已经实际 ZIP/XML 校验并由 python-docx 打开、检查内容范围/图片；Microsoft Word/视觉接受仍 NOT_RUN。

| 产物 | 实际路径 | SHA256 |
| --- | --- | --- |
| Legacy | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/jobs/demo-dd3549d24d284f7582d4b1fe4d1ab7d2/auto.docx` | `038ddbf5ee5abdf1d4113e1337e28f86a89202a148b6e8469cabaa0c235f8848` |
| Legacy | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/jobs/demo-dd3549d24d284f7582d4b1fe4d1ab7d2/layout.auto.json` | `8032b1278e444d82133a3096fe9a47921855dd288027370f428812c5066af19d` |
| Legacy | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/jobs/demo-dd3549d24d284f7582d4b1fe4d1ab7d2/render-plan.auto.json` | `64830f1038e5fff8871206fe45baa2cb3086e88d79d00fbd978b8aae7458fecb` |
| Legacy | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/jobs/demo-dd3549d24d284f7582d4b1fe4d1ab7d2/source-map.auto.json` | `d24a8568918d2af60eeddfea5b6f8e04e24161f2caef65209d0cf3c3d81a016f` |
| Legacy | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/jobs/demo-dd3549d24d284f7582d4b1fe4d1ab7d2/render-manifest.auto.json` | `4f8225e438903cbbc2502e72867333b546b8bc6d6c0acda2105ca05837c7f086` |
| Legacy | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/jobs/demo-dd3549d24d284f7582d4b1fe4d1ab7d2/mapping-loss-report.auto.json` | `151783a5995109ccbd90f721ae4298c702187b2829bce4c7d8f16e24c82f9b66` |
| DocVortex | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/jobs/demo-8646b0401b68422e9d45b7630eb9d43d/auto.docx` | `45d672b4b6f11b8024d0d3375accfffeaefa20d75011ad4161247b0b2756d497` |
| DocVortex | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/jobs/demo-8646b0401b68422e9d45b7630eb9d43d/layout.auto.json` | `8032b1278e444d82133a3096fe9a47921855dd288027370f428812c5066af19d` |
| DocVortex | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/jobs/demo-8646b0401b68422e9d45b7630eb9d43d/render-plan.auto.json` | `64830f1038e5fff8871206fe45baa2cb3086e88d79d00fbd978b8aae7458fecb` |
| DocVortex | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/jobs/demo-8646b0401b68422e9d45b7630eb9d43d/source-map.auto.json` | `677e235a797be8c0b8c354e2eb471a079d1a0d8715fce704f6a1d706ca5bfd23` |
| DocVortex | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/jobs/demo-8646b0401b68422e9d45b7630eb9d43d/render-manifest.auto.json` | `ed79ec969d3f88fa59888d3effac51125f7faf30b2686d24820a4330db94fe73` |
| DocVortex | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/jobs/demo-8646b0401b68422e9d45b7630eb9d43d/mapping-loss-report.auto.json` | `151783a5995109ccbd90f721ae4298c702187b2829bce4c7d8f16e24c82f9b66` |
| Shared+Legacy | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/jobs/demo-29b2f771dc5d4d24861fcf1b461b049d/auto.docx` | `f06eb1dbcd83e5da9a08b4f4d4bbe73f62d80b142c591b7fb800e7562915b10c` |
| Shared+Legacy | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/jobs/demo-29b2f771dc5d4d24861fcf1b461b049d/layout.auto.json` | `d25ae2798fa02a5fd294c4b670ddef2f44cb65dc73579fa9a38e125d9735bf59` |
| Shared+Legacy | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/jobs/demo-29b2f771dc5d4d24861fcf1b461b049d/render-plan.auto.json` | `d05c2205cd6daa63a1ba567e3b9cc86a13e95f0b3bd08ced693a88e9eab40dbf` |
| Shared+Legacy | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/jobs/demo-29b2f771dc5d4d24861fcf1b461b049d/source-map.auto.json` | `cb3207f06a836b2b1f52a6f298969381d3af91bef3b03539d20799a3cc5c0410` |
| Shared+Legacy | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/jobs/demo-29b2f771dc5d4d24861fcf1b461b049d/render-manifest.auto.json` | `26dcb0698c1d13a45465959eb4a18629b0eddffec1915c6667a258e254d14c88` |
| Shared+Legacy | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/jobs/demo-29b2f771dc5d4d24861fcf1b461b049d/mapping-loss-report.auto.json` | `59e3ba4e00c9e415cfb74a28e6250bcdf127dca33adc9a7c6ec9b34ade3b69b5` |
| model.json | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/model.json` | `0f3ec52688ab72d6de20844335fbded99e1f9d436909f10f2f567d06ec21118e` |
| middle.json | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/middle.json` | `40da86bb812d5f6e4e5a122dd0cf75f0a3556d210e2425d6a4b3088643f43c9e` |
| source-ledger.json | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/source-ledger.json` | `484f3fe6acd23f5be5a973c01e351dd5ca22c57e6f8528d7c06f903c9cc7ed19` |
| loss-report.json | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/loss-report.json` | `59e3ba4e00c9e415cfb74a28e6250bcdf127dca33adc9a7c6ec9b34ade3b69b5` |
| reuse-decisions.json | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/reuse-decisions.json` | `c0ef00b8371f257fd465bf958d0d789a3c30f6c9ea25f9b55a13a7ed5e609d19` |
| runtime-identity.json | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/runtime-identity.json` | `d34dc371604030a5e99ba18f4382252c318d9f0862f553f5ee4425a5edc31a24` |
| poc-manifest.json | `tmp/docx-demo/r1-05/final-poc/demo-75fb696470bf4c488833808602be9dc3/poc-manifest.json` | `b7179ebb700b0f413ace0c44cb70199517fbb2f0b1af0b6c7f338b1a0faae6eb` |

探针的全部 Model/Middle/DOCX 与 probe-results 文件逐项字节 hash 已列入 `P2W-R1-05_CHECKS.json`。`loss-report`/`probe-results` 的 `json_hash` 是排序键、紧凑 JSON 的语义 hash；本报告表及 CHECKS.artifacts 则是实际文件原始字节 SHA256，两者不混称。

## 验证

| 实际命令 | exit code | 实际结果与日志 |
| --- | --- | --- |
| `uv sync --locked` | 0 | `tmp/docx-demo/r1-05/release-checks/uv-sync.txt` |
| `uv run scripts/setup_docvortex_runtime.py` | 0 | hash 锁定运行时安装；安装/下载日志保留在任务自有 upstream 缓存，位置见私有 `upstream-location.json` |
| `uv run pytest tests/productization/test_shared_structure_actual.py tests/productization/test_docvortex_renderer.py tests/productization/test_renderer_boundary.py -q` | 0 | **49 passed**；`release-checks/focused-tests.txt` |
| `uv run mypy prototypes/docx_output scripts/setup_docvortex_runtime.py scripts/docx_demo.py tests/productization/test_docvortex_renderer.py tests/productization/test_shared_structure_actual.py` | 0 | **43 source files**，无新增错误；`release-checks/focused-mypy.txt` |
| `uv run ruff check .` | 0 | `release-checks/ruff.txt` |
| `uv run scripts/validate_schema_samples.py` | 0 | `release-checks/schema-samples.txt` |
| `git diff --check` | 0 | `release-checks/diff-check.txt` |
| `uv run scripts/quality.py --output-dir tmp/docx-demo/r1-05/quality-release` | 1 | pytest **1331 PASS / 0 FAIL / 0 SKIP**；Ruff/schema/catalog/baseline exit 0；mypy 既有 **19 errors / 2 private files**，exit 1 |
| `uv run scripts/docx_demo.py reuse-poc --source-job tmp/docx-demo/s2-page-correction-20260917-114211/demo-9032ecb6a45b494eb8cee630d1ef0d3b --source-seal tmp/docx-demo/r1-01-evidence/final-jobs/demo-462b392c546c42dda9d50e8e7e70c3cf/comparison.json --output-root tmp/docx-demo/r1-05/final-poc` | 0 | `final-poc.log`，实际两轴与全部探针产物 |

未写全路径的日志均在 `tmp/docx-demo/r1-05/`。逐命令 argv、状态、退出码在 `release-checks/summary.json`；全仓步骤和测试数量在 `quality-release/public/summary.json`，私有原始日志在 `quality-release/private/`。

全仓 mypy 仅剩 `tmp/productization/source-review-20260915/build_review.py`、`tmp/productization/review-v5/build_private_review.py` 的历史 19 项。本次代码的类型/格式缺陷已修复；未新增 ignore/exclude。初次下载检查文件和探索虚拟环境是本任务生成物，保留在仓库外缓存以避免把第三方源码/activate 脚本混入项目扫描，未删改历史私有脚本。

新增表格回归的单行格式问题已修复；最后完整 gate 与定向检查已重新运行。

初次探针曾错误预期全半角/连字会清理；实际 0.4.9 保留它们，因此修正的是测试假设，原输入/输出探针仍保留。标题换行实际发生改变，已验证拒绝静默回写。其他初次工程失败日志保留于 `structure-tests-initial.txt`、`renderer-tests-initial.txt`、`quality-initial/`；最终结论使用上述最终检查。

计划工具 `validate_package.py`、`next_task.py` 最终均 exit 0；日志 `plan-validate.txt`、`next-task.json`。工具列出 R1-02、R1-06 可开发，按用户指定执行顺序下一建议 R1-02。仅 R1-05 状态更新为 VERIFIED，接受者/日期仍为空。

## 模型与网络

- 新增模型请求 **0**，模型 metadata GET **0**，模型请求失败 **0**。
- 响应重新执行 **0**；直接复用已有 IR，生成 4 个渲染分组产物，源 4 份封存响应按 hash 验证。
- 最终 POC 实际公共后处理调用 **11** 次（真实共享轴 1 + 合成探针 10），公共 render_docx **11** 次（真实渲染轴 1 + 合成探针 10），公共表格 state **1** 次。它们均为本地确定性库调用，不是模型请求。
- 依赖与来源下载确有公网访问，单独记录；依赖 HTTP 请求总数未计量，不报告为 0。没有默认部署模型、修改网关/FRP、防火墙或 Windows GPU。

## 内容、几何、布局的收益与退化

真实作业的 15 个块全部映射，source ledger 保留原候选/几何/来源；共享后处理在此作业上 **0 个新结构建议、0 个内容或几何丢失项**。当前不能据此声称结构恢复或视觉排版改善。

六能力的正/反例是显式标记的自有合成数据。实际观察：标题默认层级、连续源页的 continues_prev、缺行/非连续页弃权、图注分组、表格/rowspan、行内与块公式 OMML 均有执行证据。公共默认 footer 被跳过；适配器把其可见内容显式保留。坏公式的图片和裸 LaTeX 回退分开，后者不计成功。工程覆盖不代表六类 R2/R3 任务已接受。

来源映射通过固定最终 Middle 树对应的实际 OOXML 范围验证，不用最近 bbox 或文本长度归属。明确 source IDs、人工修订和题图关系继续由项目 ledger/IR 持有；上游清理后的字段不当作原始证据。

## 保留/未解决/回滚

- Word 未安装、视觉未验收；远端 CI 未运行。此项不签发布接受。
- SDK 安装为独立的最小确定性切片，不是其全部声明功能；版本升级必须重新生成 hash 锁、核对许可证和重跑探针。
- 完整原生 table cells bridge、跨页续表、复杂行内样式、复杂布局/分组、完整六类产品规则保留给后续必做任务；本项不自研同类通用引擎。
- 可停止使用 DocVortex 注入/`reuse-poc` 回到默认 Legacy；新旧原始作业和所有候选、raw DOCX、审计记录都保留。
- 建议下一项 **P2W-R1-02**。本次不执行它，也不恢复 S1 或重做已继承 S2。

## 接受记录（仅实际接受者填写）

未填写；没有接受人/时间，不冒签。

## v2.1 共享复用记录

实际使用 DocVortex 0.4.9 官方 wheel，与固定参考 commit 的 386 个包内文件匹配。调用 public ModelJson/MiddleJson、model_json_to_middle_json、content.table.build_table_state_from_html、render_docx；完整调用白名单、wheel/依赖/许可证 hash 见运行时记录。

MU-HEADING、MU-PARAGRAPH、MU-TABLE、MU-FORMULA、MU-CAPTION 决定为受限 ADAPT_PUBLIC_API；MU-ORDER 为 REFERENCE_ONLY，不能把输入 index 保序称作学得阅读顺序。逐项证据在最终 `reuse-decisions.json`，精确后续任务映射见 [评估记录](../../docs/decisions/docvortex-renderer-evaluation.md)。MinerU 推理/权重安装未执行，SOURCE_REVIEW 不等于模型调用。


## PR #8 第一轮审查修复

对 `6fb443b` 的 3 个 P2 已复现并修复：

- 去重图片依据 ledger 中原始 asset ID 查来源记录，不能按复用路径挑第一项；公式图片同样保留原始 ID。
- selected_html 用禁网 HTML parser 处理，支持 `<br>`、`&nbsp;` 等普通 HTML；HTML 和 OOXML 文本核验保留显式换行/制表符。
- 共享结构审校问题依据源 ledger 定位 page_index，部分页选择不再误记到第 0 页。

修复前 3 failed / 28 passed，修复后相关 31 passed；全仓 1334 passed。Ruff、定向 mypy 与 diff check 正常，全仓 mypy 仍为既有私有 19 错误。日志 `tmp/docx-demo/r1-05/pr8-{red,green}.txt` 和 `pr8-quality-r1/`。真实两轴重新生成到全新目录，原 34 个文件不变，产物 hash 见 `P2W-R1-05_PR8_FIXES.json`；前期证据不覆盖。远端复审待执行，Word/视觉接受仍 NOT_RUN。


## PR #8 review round 2

Commit 8561b87 reconciles stage-owned continuation relations after edits: reuse stable IDs, retire invalid links and block references, and preserve manual relations. Regressions cover repeated edits, retirement and manual ownership. The POC rejects finalized cached structure inputs rather than claiming another public postprocessing call.

Validation: uv sync --locked exit 0. uv run scripts/quality.py --output-dir tmp/docx-demo/r1-05/pr8-quality-continued: 1337 passed, no failures/skips; Ruff/catalog/baseline/schema exit 0. Overall exit 1 due only to the existing 19 mypy errors in two private scripts. Targeted mypy over prototypes/docx_output and tests/productization/test_shared_structure_actual.py: 40 files, exit 0. git diff --check exit 0. Earlier focused log pr8-r2-final.txt records 18 passed.

Existing replay artifacts remain in tmp/docx-demo/r1-05/pr8-poc-r2-final/. Remote re-review pending; Word and visual acceptance NOT_RUN.


## PR #8 review round 3

Stage-generated issues now retain ownership snapshots in the structure audit. Reprocessing replaces only untouched owned warnings, reuses matching IDs, retires losses that no longer occur, and preserves manually changed or unrelated issues. Records without ownership evidence remain untouched. Two new regressions failed before the change and passed afterward (20 focused tests).

Full quality run tmp/docx-demo/r1-05/pr8-quality-r3: 1339 passed, no failed/skipped tests. Ruff, schema/catalog/baseline and targeted mypy (40 files) pass; overall quality exit 1 remains the existing 19 private-script mypy errors. git diff --check exit 0. No model requests; Word/visual acceptance NOT_RUN.


## PR #8 review round 4

The renderer verifies table cell coordinates, row/column spans and per-cell text against selected HTML. Changed boundaries or merges fail closed. Block and inline OMML are compared as bounded mathematical trees against the existing source LaTeX parser; unknown constructs/properties or differing expressions trigger explicit Legacy fallback rather than acceptance of the candidate. The accepted math subset is intentionally conservative and excludes unverified constructs.

Four regressions reject changed cell boundaries/merges and changed block/inline equations before source binding. Renderer tests: 20 passed. Full quality tmp/docx-demo/r1-05/pr8-quality-r4: 1343 passed, 0 failed/skipped; Ruff/catalog/baseline/schema pass. Targeted mypy: 41 files, exit 0. Overall quality exit 1 remains the 19 existing private-script mypy errors. git diff --check exit 0. Word/visual acceptance NOT_RUN.


## PR #8 review round 5

Text-backed table blocks without nonempty selected HTML now trigger TABLE_STRUCTURE_EVIDENCE_MISSING on the renderer bridge and explicitly use the Legacy fallback. Three regressions cover absent, empty and whitespace-only evidence. Full quality tmp/docx-demo/r1-05/pr8-quality-r5: 1346 passed; Ruff/catalog/baseline/schema pass; targeted mypy 41 files passes. Overall quality remains exit 1 from the 19 existing private-script mypy errors.

The preceding ad7f69b macOS CI failed one existing CLI/API acceptance test (test_cli_and_upload_api_run_real_shared_pipeline_once); all other tests and checks passed. Its sanitized artifact has no exception detail, so the cause is undetermined. The failure is retained in tmp/docx-demo/r1-05/pr8-r4-macos/ and pr8-r4-ci-failed.txt; this record is not replaced by subsequent CI outcomes.
