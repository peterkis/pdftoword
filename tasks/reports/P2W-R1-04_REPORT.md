# P2W-R1-04：来源绑定、列顺序与共享结构守恒

- 开始 HEAD：`9a73713`，为用户授权的 R1-03 本地提交；分支 `codex/r1-04-geometry-arbitration`。
- 状态：**按已知限制工程收口（2026-09-19 用户明确接受）**。真实采用/收益与完整产品验收缺口保留，见 [冻结记录](P2W-R1-04_FREEZE.md)。代码未提交。
- 下方“首轮”内容保留原始切片证据；文末续作记录覆盖其“尚未接入”状态。
- 网络策略：offline_or_sealed_replay；本轮新增模型请求 0，未推送或全面复审。

## 首轮修改与边界

- `geometry/binding.py`：封存输入 order 与内容原子 hash，验证 source-span 精确覆盖；允许输出 ID 改变，逐字符检查 split/merge，拒绝遗漏、重复、跨页、未证明合并作用域、人工锁内容/位置/相对顺序变化。显式 order edges 必须无环且足以支持所给新顺序。它验证证明，不自行推断模型顺序或物理子框。
- `geometry/support.py`：独立几何支撑；PP 文字仅用于唯一的精确（忽略空白的匹配）定位证据，不写回正文。同文异位无法唯一定位时弃权，整页回退图不被当成可拆分普通插图。
- `geometry/arbitrator.py`：仅在每个未锁内容块都有支撑、宏框合法且唯一对应时，选择一套提供者宏结构。检查坐标帧、重复/重叠、错误大框、遗漏、caption 类型；line/glyph 不作为 macro 竞争者。多个可行提供者保留弃权。Native 测量框不被模型宏框覆盖；其他选中框用保守 union，geometry_source=fused，selected_geometry_id 追溯提供者。
- `geometry_arbitration.py`：实际离线入口，要求已有全文件 seal，复用 R1-01 verify_source/inventory 与既有 finish/Legacy renderer，在新作业中写出候选、决策、IR、RenderPlan、DOCX、source-map。选中图片框变化时重新 crop；旧文件不覆盖。没有把模型原始 JSON 直接交给 writer。
- `test_geometry_binding.py`、`test_geometry_arbitration.py`：来源守恒、人工锁、双栏目标顺序的显式证明、Monkey/PP 选中、弃权以及实际 PDF/backend/Writer 的新作业集成测试。

没有更改默认转换、R1-03 auto 或旧 PP `accept_candidate`。旧 READING_ORDER_CHANGED 门禁暂保留，直到顺序证据的生成与完整接入可证明安全；不能只删除保护开关。完整一对多/多对一几何应用、column/header 规划、RelationDelta 和共享结构候选消费仍待实现。

## 验证

- 两个新模块测试：33 passed，exit 0（包括实际新作业 DOCX/source-map 中 Monkey 选中）。
- 首批新测试＋geometry candidates＋真实共享结构回归：90 passed，exit 0；随后补充了一个端到端选择测试。
- `uv run ruff check .`：exit 0。
- `uv run mypy prototypes/docx_output tests/productization/test_geometry_binding.py tests/productization/test_geometry_arbitration.py`：exit 0，53 files。
- `uv run pytest -q`：exit 0，1515 passed，1 个既有 Starlette 警告；日志 `tmp/docx-demo/r1-04/checks/pytest-full.txt`。
- 首次测试文件存在一处括号语法错误，收集失败；修正后运行以上真实检查，不将首次失败抹去。
- `--help` 已实际运行，核对入口参数。`git diff --check`：exit 0。

日志目录：`tmp/docx-demo/r1-04/checks/`。

## 实物

实际命令：

```sh
uv run python -m prototypes.docx_output.geometry_arbitration \
  --source-job tmp/docx-demo/r1-03/real-dry-run/demo-d1bffe644d8e44a68a9a881015295cff \
  --source-seal tmp/docx-demo/r1-03/real-dry-run/live-validation-receipt.json \
  --output-root tmp/docx-demo/r1-04/real
```

exit 0，新作业：`tmp/docx-demo/r1-04/real/demo-28e03cdd744c4198b3fc4501d05dcd7e/`。

| 源页 | 独立定位支撑 | 仲裁 | 原因 |
| --- | --- | --- | --- |
| 46 | 0/1 块 | ABSTAIN | 当前只有整页源图回退，不能从宏框猜出可编辑内容 |
| 47 | 7/16 块 | ABSTAIN | 其余内容缺少唯一定位支撑，Monkey/PP 均未证明全页绑定 |

实际输出：`auto.docx`、`layout.auto.json`、`render-plan.auto.json`、`source-map.auto.json`、`geometry-decisions.json`；hash 在 `arbitration-receipt.json`。原 47 个源作业文件完全未变。`content-comparison.json` 独立核对两页全部 blocks 和 reading_order 均未改变。

本切片没有重新生成对照 overlay：真实页未采用新几何，新增选中 overlay 记 NOT_CREATED；继承 R1-03 原始 PP/Monkey overlay 作为输入证据。没有人为降低阈值以制造 Monkey 胜出。合成端到端用例只证明选择确实进入导出链，不代表真实页排版收益。

## 尚未达到的 R1-04 条款

- AC01：已覆盖 Monkey 选中、PP 选中、弃权和显式 order projection；尚未把自动列/跨栏标题顺序证据与选择、最终 DOCX 一起联通。真实页改善仍 NOT_VERIFIED。
- AC02：精确 source-span proof 已测试；实际 split/merge 几何投影与受影响裁图/关系重建尚未接入。
- AC03：当前宏候选硬校验有反例；策略是保守工程规则，不是校准概率，缺失 engine_confidence 保持 null。
- AC04：尚未实现 SharedStructure 后的完整 AtomicCoverage/RelationDelta 消费与跨题/串栏/非连续页 merge 审计。不能凭当前独立 proof 声称此项达标。

下一步继续补齐带来源行/片段证据的绑定账本、可证明的列顺序、SharedStructure 前后关系守恒，再接替旧 layout gate。保持 R1-03 的内容回退与字体问题为独立已知发现，不增加真实请求、不静默修正文。

## 复用与接受

复用既有 PageGeometry/TransformChain、手工锁判定、seal 验证、Legacy Writer/RenderPlan。R1-05 的 public SharedStructure 调用本轮未加入新仲裁执行，记 NOT_RUN，未复制上游 caption/continuation 引擎。人工/Word 接受 NOT_RUN，真实排版收益 NOT_VERIFIED。本阶段尚未收口。


## 续作：来源行账本、可证明列顺序和共享守恒（覆盖前文未接入状态）

### 实际接入

- `geometry/line_ledger.py`：PP 行原始序号、canonical JSON 响应指纹、行 hash、原文字符区间、对应行区间、原文片段 hash 和整行 bbox。支持多行绑定一个块、一行中多个有边界的片段；共享行明确标为 whole_line_envelope，不按字符比例插值几何。不同块争用重叠来源行区间时弃权。
- `geometry/support.py`：新增 source_binding_ledger，逐块保留 BOUND/UNPROVEN、完整源跨度和缺失理由。同文异位、未知变换、定位缺失不会被补假框；PP 文字只参与匹配，不覆盖输出。
- `geometry/order.py`：基于独立支撑证明列区间、栏间空隙、栏内不重叠的先后关系、顶部/底部跨栏块；生成 column-major DAG。门禁重新计算完整证明并比对，不能仅给一个任意排序的边链。人工锁跨越、共享行细分顺序、栏中跨栏块和无法证明的边界仍明确拒绝。
- `structure_processors/conservation.py`：SharedStructure 前封存原子与 input order；之后核查每个块除受管理关系引用外的全部字段、内容候选、来源、几何和关系变化。非本阶段拥有的关系不可删除/改写；新增或刷新续段须通过相邻性、题目归属、人工锁、同栏/行支撑和连续源页检查。显式 contains 归属优先于原始流式顺序，含糊/循环归属不猜测。
- `DocVortexStructureProcessor`：实际公共后处理之后执行上述独立核验；不安全续段建议在采用前留下拒绝理由。保留 R1-05 的公共接口/失败边界，没有重写 caption/continuation 引擎或引入新模型。
- `layout_rules.py` / `pp_layout.py`：不再一概拒绝多栏与 reading_order 变化。有独立支撑、唯一宏布局和完整列证明的 PP 路径可进入原有原子发布流程并写出新 DOCX。旧单栏行为仍按原门禁检查；既有题图关系跨列或相邻关系被拆散则拒绝。
- 旧 gate 现在可接受不同输出 ID：必须有完整 source_bindings、来源候选守恒、实测行边界、同题/同栏依据与原子序列守恒。按字符比例切子框、改变原样式/角色、拆改可靠 native/样式 run、未明确归属的关系重绑仍拒绝。拆并与列重排需分步证明，不把一个任意新顺序当成证据。源块含 inline_parts、样式 run 或被 children/关系引用而尚无重绑证明时也拒绝改 ID，避免字符还在但公式/关系丢失。
- sealed 入口默认调用本地 public SharedStructure，保存 `shared-execution.json`、`source-binding-ledger.json` 和守恒报告；`--skip-shared-structure` 是明确的离线比较选项。

### 验证与实际输出

| 检查 | exit | 结果 |
| --- | --- | --- |
| `uv run pytest -q` | 0 | 最终 1531 passed，1 个既有 Starlette 警告 |
| `uv run ruff check .` | 0 | 无诊断 |
| `uv run mypy prototypes/docx_output tests/productization/test_geometry_evidence_gate.py tests/productization/test_geometry_arbitration.py tests/productization/test_geometry_binding.py` | 0 | 57 files |
| `uv run mypy .` | 1 | 仅 R1-05 私有 trace-public-calls.py 的既有 2 项错误，无新增 ignore |
| `git diff --check` | 0 | 无空白问题 |

日志：`tmp/docx-demo/r1-04/continued-checks/`；最终 pytest 为 `pytest-delivery.txt`，Ruff 为 `ruff-delivery.txt`，mypy 为 `mypy-delivery-final.txt`。曾有一次新拆分回归失败：旧 block-ID 比较仍在精确 source-span 验证后拒绝结果；修正 gate 的条件后最终全套成功。不是模型失败，不增加请求。

设计用例实际调用旧 PP 入口和 Writer，将 `A D B E C F` 改为 `A B C D E F`；另有顶部跨栏标题、篡改 proof、跨栏图注、人工锁、多个片段共享整行 bbox、不许子行插值、可变 ID 行边界拆分、显式题目归属冲突、内容候选丢失等回归。

保留的合成端到端产物：`tmp/docx-demo/r1-04/column-fixture/jobs/demo-24e0a5873591433285b8f55422d4f608/`，包含 input-fixture-ir、PP 夹具、实际 public SharedStructure 输出、DOCX/IR/RenderPlan/source-map。父目录 `receipt.json` 保存顺序前后、行账本、关系守恒与 hash。标记 SYNTHETIC_NO_MODEL，不冒充真实模型或真实页面收益。

最终真实封存回放新作业：`tmp/docx-demo/r1-04/gate-integrated-real/demo-d6257b7ceb334a0598c10ca6526bf647/`。

- 原作业 47 个文件 hash 未变；正文 blocks、reading_order、relations 完全未变。
- 原页 46：0/1 块有独立支撑；原页 47：7/16 块有独立支撑；两页继续 ABSTAIN。
- 实际本地 DocVortex 0.4.9 公共结构调用，worker network_requests=0，未加载 PDFium；1 个 heading_level 建议。6 项 TEMP_FIELDS_REMOVED_RETAINED_IN_LEDGER 表示共享格式丢弃的行字段已留在自有账本，不是丢了正文。
- SharedStructure 的关系 added/removed/updated 均为空，原子覆盖逐页 EXACT；新模型请求 0。
- `conservation-receipt.json`、`arbitration-receipt.json`、`source-binding-ledger.json`、`shared-execution.json` 保存可核对的来源/hash/范围；作业仍 PARTIAL。

### 接受边界

本轮指定的账本、列顺序、共享前后核验及旧 gate 接入已形成可执行代码和实际检查。完整 R1-04 的真实页改善仍 NOT_VERIFIED，不宣称永久几何赢家。自动提出所有复杂拆并、任意栏中跨栏区段、歧义题图重绑与复杂样式拆分不在已验证范围；这些场景仍弃权或拒绝，不凭 score 掩盖。

R1-03 的 REGION_NO_EDITABLE_CONTENT、AMBIGUOUS_LAYOUT_MAPPING 和 LibreOffice 中文缺字继续独立保留。本轮没有改正文适配/字体，也没有新的真实请求；不借这些改动静默修正文、不代签 Word/人工接受。

## 现有真实样本补证结论

按用户最新指令，先固定 R1-03 第 47 页正文检查已有封存证据，再检查其他已登记真实样本。
第 47 页仍为 7/16 绑定；9 块有标点、填空下划线或跨行连字符差异。同页旧 PP 的页面解析结果一致，不能作为新独立证据。

扩展检查覆盖 5 份真实来源、9 个物理页，保留所有受检历史版本及 6 组数学几何对照；没有可采用结果。缺历史响应 hash 或缺宏响应的记录标 NOT_VERIFIED，不记为质量失败。真实采用与布局收益继续 **NOT_VERIFIED**。

详见 [真实样本补证与收口建议](P2W-R1-04_REAL_SAMPLE_AUDIT.md)。建议按已知限制冻结工程结果、独立保留真实验收缺口；不自动签完整验收。本轮新增模型请求 0，生产代码、门槛、正文和历史评测不变。
