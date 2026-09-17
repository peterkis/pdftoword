# P2W-S1-03 第二批人工标注接入与数据冻结

日期：2026-09-16。**数据准备 READY，已冻结 frozen-v1；工程变更 READY_FOR_REVIEW。**
未运行转换、模型推理或识别效果验收；全量工程门禁仍有两份既有私有脚本的类型问题。

## 1. 本轮来源和授权

用户提供剩余 8 份/15 页的标注，并明确裁决两处内容、M 路由和 T5 合并关系。
此前独立性、未调试及第一批 5 份/9 页的人工确认继续有效，没有重复要求确认或采纳包内过时的 null。
本次实际核对第二批 8 份原 PDF SHA-256、所选物理页与当前清单一致；包内 76 个 SHA256SUMS 条目通过。
原始外置卷及第一批标注不改写，原始包按完整 ZIP 字节归档，Python 辅助脚本不展开到源码扫描目录。

## 2. 明确裁决的落实

| 项目 | 处理 |
|---|---|
| U-C15-01 | 扫描噪点；从正文单元和阅读顺序排除，保留来源锚点/原单元的非内容裁决记录；原 PDF 像素不改 |
| U-C16-01 | 按字面连字符 `-` 替换占位，保留源换行，不拼成无连字符的单词 |
| Q-M8-ROUTE | 页面路由 scan；可复制层记录为 garbled_not_content_source，不用于确认正文 |
| Q-T5-WHITE-LINES | 与用户规则逐列核对，11×5 原子网格、39 个原点 cell、4 个合并 cell，覆盖完整且无重叠 |

T5 使用 0-based 原子网格：

- 第 1 列：表头 row0 单独；row1 起 rowspan=9；最后 row10 单独。
- 第 2 列：row1 起 span=6，row7 起 span=2；row0、row9、row10 单独。
- 第 3 列：row1 起 span=3；row0、row4–row10 均为单行。
- 第 4、5 列：row0–row10 均为单行。

这与包内已有四处合并一致，因此没有猜测新的边界、拼接 cell 文本或填充答案。

第二批保留 337 个原文字块（其中 1 个已确认噪点移出正文）、4 个物理表段、147 个 cell、
4 个空 cell 和 10 个表达式。M 的两个表段保留 logical_table_id、段序、18 个逻辑数据行映射、
重复表头标记，不能把重复表头算成新的数据行。

## 3. 版本与冻结结果

以原有效 manifest.v9 为底稿，v10 接入第二批，v11 落实用户具体裁决；所有既有样本/split/事件保留。
新标注只写到下一未使用版本，原包仍保留 agent 来源；派生标注的人工作用依据本轮用户明确陈述单独记录。

当前工作清单：`tmp/productization/manifest.v11.json`。
冻结入口：`tmp/productization/frozen-v1/manifest.json`，外置 seal 为同目录 `seal.json`。
共 33 个文件列入 seal（16 份原稿副本、16 份当前标注、1 份清单），另有 seal 自身；备用材料不计初始配额。

| 准备条件 | 实际结果 |
|---|---|
| 初始独立文档 / 选定页 | 13 / 24 |
| N/R/M/T/C | 6 / 6 / 4 / 4 / 4 |
| development/validation/holdout | 12 / 6 / 6 |
| 初始文档人工核对 | 13 份全部登记，覆盖 24 页及五类别 |
| 来源与调试状态 | 已确认，无来源阻塞 |
| validate / freeze / 冻结后 validate | 均退出 0，READY，errors=[] |

M 是本计划中的隐藏/失真文字层专项类别，页面实际可见正文载体仍为 scan。
没有为了配额把隐藏文字当作可见原生混排；也没有因导入包不知道现有 split 而改动 split。

现行 Schema 无法直接评分的关系仍按原语义保留并单列：334 个 uncertain 单元是这些关系映射限制，
不是 334 处未确定文字。它们未被自动升格成正确关系。确认文本量 17831 是分层参考聚合记录，
scored_count=0、value=null、NOT_SCORED；未计算 CER/准确率或声称转换通过。

## 4. 实际检查

- 新增/扩展适配回归共 12 项，涵盖批次清单版本、未知 split 继承、噪点排除、显式 span 验证和连字符读法。
- 完整 pytest **558 passed**，0 skip/XFAIL/XPASS；原有 Starlette 弃用警告保留。
- Ruff、两个原 validator、Schema 样例检查通过；新增/变更适配器与测试的定向 mypy 通过。
- 完整 quality 返回 1：全量 mypy 仍报两个既有私有构建脚本的 19 个类型错误。
  `source-review-20260915/build_review.py` 与 `review-v5/build_private_review.py` 位于私有 tmp/productization，
  本轮字节未改；未增加排除项，也没有把全量门禁写成通过。
- `product_dataset.py freeze --manifest tmp/productization/manifest.v11.json --output tmp/productization/frozen-v1`
  真实执行后，再读取冻结清单验证，均 READY。seal 的 33 个成员 hash 再次独立核对一致。
- 第二批包的源哈希、旧版本保留和文件级证据见 [DATASET_FREEZE_CHECKS](P2W-S1-03_DATASET_FREEZE_CHECKS.json)。

本轮开始的 1209 个保护文件中，仅适配器与其测试这 2 个本轮授权源码发生变化，其余 1207 个文件原字节保留。
Downloads/外置卷原文未写入 Git；正文、标注、图片、原包和冻结集继续留在忽略目录。

## 5. 交付边界与下一步

本轮修改 `scripts/import_review_annotations.py` 与其回归测试，新增本补充报告及检查证据；旧报告不改写。
Git 仍为 codex/p2w-s1-03，HEAD 未变、暂存区为空，未 commit/push/merge，未改 FRP 或模型部署。
任务工程状态保留 READY_FOR_REVIEW，不自动代替用户接受代码。数据准备的 BLOCKED_INPUT/PROVENANCE/ANNOTATION 已解除。

下一可执行任务为 P2W-S1-04 的上传到 Word 端到端验收工具；本轮不启动它，也不消费任何模型预算。
本次冻结不代表 S1 产品 Gate、完整 Word/Windows 验收或远端 CI 已通过。
