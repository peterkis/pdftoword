# P2W-S1-03 实施与样本准备报告

工程与候选准备：**READY_FOR_REVIEW**。真实数据集：**BLOCKED_INPUT**，同时存在来源/调试历史及人工标注待确认项。
日期：2026-09-15。未声明本项真实数据集验收完成，未冻结或执行 S1-04。

## 1. 起点与实际变更

仓库 peterkis/pdftoword；起点/当前 HEAD 为 `3241f10804a899f8ec2b0bdb6512e1f6cd5e456a`。
从 codex/p2w-s1-02 建立 codex/p2w-s1-03，保留 S1-01/S1-02 的全部已有改动与状态。
用户明确指令执行本项；没有代替用户接受前置任务，也没有改动原 97 项 Ticket。

本轮新增：

- scripts/product_dataset.py：离线清单/授权/hash/分组/标注校验，私有初始化、只新增冻结版本和 seal 验证。
- specs/product-quality/dataset-manifest.schema.json、annotation.schema.json、development-only-sources.json。
- tests/productization/test_dataset.py、test_synthetic.py、synthetic/generate.py、synthetic/encrypted-pdf.json、synthetic/README.md。
- [样本与标注规范](../../docs/27_DATASET_PREPARATION.md)、本报告及 [检查证据](P2W-S1-03_CHECKS.json)。
- 私有 tmp/productization：16 份源文件副本、版本化清单与初始标注、来源/图层观察、访问记录、人工队列和合成故障资产。

代码没有导入转换 pipeline、模型客户端或历史 evaluator。当前候选清单入口为
`tmp/productization/manifest.v4.json`；人工队列为 `tmp/productization/human-review-queue.private.md`。
原始 Downloads 文件未修改，所有正文、PDF、图片、转录与私有路径未进入 Git。

## 2. 真实输入及授权

用户授权本地读取 Downloads 顶层 PDF，声明无敏感内容，并补充文件。
首次找到 5 份，增量增加 11 份，共 16 个不同 SHA-256 的 PDF，均可打开并逐字节复制核对。
单份源文档 6–343 页；每份只选择连续 1–2 页，满足当前原型每份最多 3 页的限制。

所有记录均为仅本地读取，model_send_authorized=false、allowed_providers=[]。
许可栏表示本机评测授权声明，不是对作者/版权身份的独立认证。可见出版物/行业标准署名保持原状，
未将其冒充自有合成文档；原声明和接收记录保留在私有 intake 版本中。

### 当前候选配置

| 维度 | 实际数量 | 限制 |
|---|---:|---|
| 已登记源文件 | 16 | 不等于 16 个已确认独立 family |
| 首批文件 / 选定页 | 13 / 24 | 另 3 份备用；每份 1–2 个连续页 |
| 保守独立 family | 11 | 同系列分册、标准新旧版本保守归组；尚待人工核对，未为凑数拆组 |
| N / R / M / T / C | 6 / 6 / 4 / 4 / 4 页 | 初步分类，不等于产品支持或识别通过 |
| development / validation / holdout | 12 / 6 / 6 页 | 同 family/原稿不跨集合；当前初始 holdout 已有准备访问记录 |
| 人工复核覆盖类别 | 0 / 5 | 至少每类别一份仍待实际 human 复核 |
| 完整正文参考字符 | 0 | 仅初始路由观察，全文、表格、公式与关系仍待标注 |

M 的依据是实际源对象：一份所选页为整页扫描图加 mode=3 不可见文字；另一份整页扫描图
在文字对象之后绘制、覆盖文字层。普通配图电子页没有因为“有图”被自动划为 M。
该图层检查纠正了早期 M 不足的草稿判断，保存为 v4，未覆盖 v1–v3 或旧标注版本。
调整依据来源结构，未用转换结果或模型反馈改变分组。

原 13 条首批 route 确认属于 agent_visual/结构观察；另有 35 个未确认单元。
scored_count=0、reference_characters=0、value=null、NOT_SCORED。不能据此计算正文 CER 或宣称内容 100% 正确。
每份标注都是 PARTIAL，没有写 REVIEWED_HUMAN。

## 3. AC 与验证证据

| AC | 已完成部分 | 未完成/限制 |
|---|---|---|
| AC01 | 16 份许可声明、读取授权、源/副本 hash 可追溯；配额短缺阻止冻结 | 目前只保守确认分为 11 个 family，独立性及调试历史尚待用户确认 |
| AC02 | 同 family/原稿/相同源 hash 跨 split、缺授权、错 hash、空确认均拒绝；无评分分母保持 N/A | 字节 hash 不能发现所有未申报截图/重采样；来源字段仍需人工核对 |
| AC03 | 旧数学试卷 JPG/PNG 已知 hash 限定 development/regression，未纳入本次新 holdout | 不重跑或改写 T0016 |
| AC04 | holdout 准备访问、草稿重分配均留 events；人工状态不伪造 | 人工复核尚未进行；初始 holdout 不是最终完全未读的 Release 盲集 |

### 实跑命令与结果

| 命令/操作 | 退出码/结果 |
|---|---|
| 14 个新增 productization 回归 | 通过；使用实际校验器、文件、子进程和 PDFium |
| uv run --locked python scripts/quality.py --output-dir tmp/quality-s1-03/final-gate | 0；546 passed，0 skip/XFAIL/XPASS；六项检查全部 0 |
| 原 task/model validators | 通过，原三格式仍各 97 项 |
| product_dataset.py validate --manifest tmp/productization/manifest.v4.json | 3，BLOCKED_INPUT，errors=[]；这表示清单结构有效但准备条件未满足 |
| product_dataset.py freeze … --output tmp/productization/blocked-freeze-v1 | 3，未创建冻结目录 |
| 合成 fixture 的 READY→freeze→验证→篡改检查 | 成功路径及篡改拒绝通过；只是测试夹具，不是现实 human 验收 |
| 合成生成器 | 20 个故障资产，精确 hash；可打开的 10 个 PDF 已渲染并进行 agent 视觉检查 |
| git diff --check；外部计划包校验 | 通过 |

沿用锁定环境 Python 3.12.13、Node 24.18.0、uv 0.11.28，未改 pyproject/uv.lock。
加密空白合成 fixture 由已安装的 bundled pypdf 一次生成；项目回归只解码固定自有字节，
不依赖 bundled runtime，不新增项目依赖。损坏/遮挡/不可见文字是故障设计，不进行“美化修正”。

本轮曾遇 PDFium 页面不支持 context manager、文字提取去重等差异；改为 closing 及验证原始文字对象/render mode，
未将渲染/提取差异伪装成真实文档缺陷。新增 Ruff/mypy 问题均在最终门禁前修复，red 日志保留。
原有 StarletteDeprecationWarning 仍保留；未因此更换 HTTP 栈。

## 4. 隐私、来源与历史保护

开始保护集为 908 个文件：当时 Git 可见文件和四个指定历史私有目录的文件。
本轮结束这些文件 SHA-256 均相同；指定历史目录的 706 个文件集合也相同。
Downloads 的 16 个已登记原文件和 corpus 副本再次核对一致。
这只是列明范围的保留检查，不宣称已审查全盘其他文件。

普通输出仅统计/错误码，不含私有路径、原图或识别正文；Git 新增内容只有代码、Schema、自有合成字节与脱敏报告。
T0015/T0016 raw、GT、manifest、报告以及 DEMO 代码/作业未写回。历史和本轮样本均未调用模型。

模型请求 0；新转换作业、DOCX/Word/LibreOffice 人工验收、内容准确率/可编辑率、人工 active 时间：NOT_RUN/N/A。
本轮源 PDF 预览与合成资产渲染不等于 DOCX 渲染，更不等于 Word 产品验收。

## 5. 还需完成的真实事项

1. 核对同系列分册是否确属独立原稿，或补充独立 family，确保至少 12 个独立单元。不会自动拆分保守分组。
2. 确认每份样本是否曾参与规则调优；目前为 null/family_review=PENDING。
3. 按私有人工作业队列至少复核每类一份，补正文、表格拓扑、公式、阅读锚点和题图边；当前 GT 不完整。
4. 修正用新版本并记录原因；条件满足后再冻结，不覆盖当前草稿和标注。

工程可审阅，真实数据集尚不能被标 READY/ACCEPTED。S1-04 的离线工具开发可在另行授权后安排，
其真实评测仍须依赖合格数据，不在本轮自动执行。

## 6. Git 与回滚

分支 codex/p2w-s1-03，HEAD 未变，暂存区为空；本轮仅新增文件，前两项改动保持原字节。
未 commit/push/merge，未改远端 CI/分支保护或 FRP。
外部计划仅将本项工程进度置 READY_FOR_REVIEW 并登记数据阻塞，原任务与 accepted_by/accepted_at 不变。
回滚只撤回本轮新增源码/文档及进度；保留已接收私有原稿和版本记录，不 reset/clean 或删除 Downloads 文件。
