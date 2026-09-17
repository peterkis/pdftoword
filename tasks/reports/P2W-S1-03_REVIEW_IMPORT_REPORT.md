# P2W-S1-03 人工核对包接入补充报告

日期：2026-09-16。工程接入 READY_FOR_REVIEW；全量数据集 **BLOCKED_ANNOTATION**。
本报告补充此前 S1-03 报告，不改写昨日状态与证据。

## 本轮授权与事实

用户明确确认样本独立、此前未参与任何调试，并授权读取指定外置卷目录内的 PDF 和核对材料。
随后针对包内仍标 agent_visual 的差异，用户明确确认已逐页核对五份/九页。
这两条会话确认分别作为来源/调试确认与后续人工核对依据；原包仍保持原来的 agent_visual 状态。

包内 50 个 SHA256SUMS 条目全部匹配；五份实物 PDF 的 SHA-256 均与本机原样本一致，
所选原物理页也全部匹配。没有用抽页序号替换原物理页，也没有把补充清单覆盖全量清单。
原始包完整复制到私有 imports 目录；包中的脚本没有执行。

## 新版本与保留

- 当前清单：`tmp/productization/manifest.v9.json`。
- 五份适配标注先写到各样本新的 `.v6.json`，随后 N/M 的明确读法继续写入各自下一版本，完整原稿与来源映射保存在私有导入归档。
- 昨日以外本机还存在 v5 清单及新增访问事件；首次以 v4 为基线形成的 v6 仅保留为中间记录，
  v7 重新基于 v5 合并；v8 处理用户明确读法，v9 补入原包 2026-09-15 的 holdout 访问事件，全部旧事件/其他样本/split 均保留。v6 不作为当前入口。
- 全部 16 份样本采用用户确认的独立原稿分组；若 original_sha256 相同仍强制同组，不能解除派生约束。
  初始 13 份独立文档/24 页，备用 3 份；family_review=CONFIRMED、participated_in_tuning=false。
- 5 份/9 页依据用户逐页确认登记 REVIEWED_HUMAN；不会把该确认扩到未提供的其余 15 页。
- 剩余队列：`tmp/productization/human-review-queue.v4.private.md`。

## 内容与语义适配

保留 208 个文字块、338 个源锚点、3 个网格/表结构、107 个单元格（含 2 个空 cell）和 8 个表达式。
三个表结构分别保留 data_table、borderless_linguistic_comparison、exercise_response_grid 和 is_data_table 标记；
无边框对照/练习网格不冒充普通数据表，空 cell 保持空字符串。

源锚点 ID 不变，项目 kind 仅作有据的适配；完整原 kind、bbox 证据级别、层级、页外引用、边注顺序
等在原包归档中保留。项目正文阅读顺序单独映射，边注/图内文字保留 content_scope，不混为正文次序。

两条可用现行角色约束表达的关系映射为确认关系；其余 117 条关系保留原 relation、两端 ID，
因项目现行关系枚举/角色限制记为不可直接评分的 uncertain。它们不是 117 处原文错误，也不是源包的四处内容疑问。
未放宽生产 Schema 来制造通过，未静默删除关系或改造成错误类型。

用户进一步明确了四处读法：M4 为阴，M5 为 1640，N25 两处各为两个下划线字符。
只替换相应四个占位，三个受影响文字块按人工确认升级，旧 uncertain 版本和确认事件保留。
没有将其他不可评分关系或剩余部分标注升级。确认文本字符数为 6609，仍不表示识别评分。
当前参考字符聚合值只用于记录已有确认文本量；正文/图内字/边注/表格用途保留分层，尚未执行任何 CER 或质量评分。

M 候选是“隐藏 OCR 层”专项样本，项目 DATASET_PLAN 的 M 类包含该场景；页面可见主文字载体应为 scan，
适配后采用源包的 scan 路由，没有把隐藏文字当作可见原生混排来满足配额。
分类与页面路由是不同字段；本轮不更改生产转换策略。

## 验证

新增 `scripts/import_review_annotations.py` 及 9 个合成回归，覆盖 source hash/源页错配拒绝、
未获得人工确认时保持 agent_visual、uncertain 不升级确认、空 cell 与不支持关系保留、包 hash 篡改拒绝。

实跑：

- 新增目标测试通过；完整 pytest 555 passed，0 skip/XFAIL/XPASS。Ruff、原校验器与 Schema 检查通过。
- 完整 quality 仍返回 1：mypy 发现本轮开始前已存在的两份私有构建脚本共 19 个类型错误；
  路径为 tmp/productization/source-review-20260915/build_review.py 和 review-v5/build_private_review.py。
  二者与开工快照 hash 一致，本轮未改写；新增适配器及测试的定向 mypy 通过。没有扩大排除规则或隐藏失败。
- `product_dataset.py validate --manifest tmp/productization/manifest.v9.json` 返回 3 / BLOCKED_ANNOTATION，errors=[]。
- 13 个独立初始文档；N6/R6/M4/T4/C4；split 12/6/6；provenance_pending=false；human_reviewed_categories 覆盖五类。
- 仍有 8 份/15 页为部分标注；严格全量准备条件未通过，不冻结、不标 ACCEPTED。
- 数据转换、模型调用与 Word 验收均 NOT_RUN；scored_count=0、指标 null。

本轮只做适配与元数据核对，不把包内“2992 项结构检查/9 页渲染一致”的历史报告写作本项目本轮实跑。
导入时少量新增 lint/type 问题已修复；所有中间导入版本保留。
完整门禁先发现两份导入包 Python 脚本重名。已把每份包完整原字节保存为 source-package.zip，
只不展开 Python 辅助源码；成员 hash 全部匹配，原始外置卷不变，未修改项目检查范围。
随后暴露的两个既有私有脚本类型问题单独保留为已有失败。

## Git、文件与后续

仍在 codex/p2w-s1-03，HEAD 未变，原有工作区文件与私有版本未修改；本轮新增适配器、测试和补充报告。
未 commit/push/merge，未调用模型，未改 FRP/分支保护。
机器证据见 [REVIEW_IMPORT_CHECKS](P2W-S1-03_REVIEW_IMPORT_CHECKS.json)。

下一步是补齐剩余 8 份/15 页的标注覆盖，再按已有准备门禁校验和冻结。现有五类人工核对已满足，
无需重复要求本次独立性、未调试或这五份九页的人工确认。
