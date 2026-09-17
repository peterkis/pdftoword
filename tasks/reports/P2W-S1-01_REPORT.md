# P2W-S1-01 实施与验收报告

状态：**READY_FOR_REVIEW**。日期：2026-09-15。仅完成本项文档接入与离线核对，尚未接受。

## 1. 起点与范围

- 仓库 remote：`https://github.com/peterkis/pdftoword.git`，本机目录名为 pdf2word。
- 开始分支 `main`，`git status --short --branch` 为 `## main...origin/main`，无暂存/未提交/未跟踪项。
- base/current commit：`3241f10804a899f8ec2b0bdb6512e1f6cd5e456a`。
- base tree：`924dc06f22bfa7e2401e2cb89ca71461769ad09c`。
- 交付分支：`codex/p2w-s1-01`；只新建分支，未提交。
- 计划包已存在于仓库外 `~/Plans/pdftoword-development-plan/`，复用现有安装。
  完整读取 `prompts/00_START.md`、START_HERE、基线、playbook、S1-01 及其执行模板。
- `inspect_repo.py` 为 EXACT_BASELINE，祖先关系为 true，11/11 Git blob 锚点匹配，无基线后增量。
  未 fetch；远端当前 HEAD 未独立联网确认，本地 origin/main 仅作本地引用。

### 实际文件变更

| 文件 | 变更 |
|---|---|
| [README](../../README.md) | 修正忽略已存在 DEMO 的活动说明，增加计划/报告/profile 入口 |
| [profile 决策](../../docs/decisions/productization-profile-v1.md) | 新建，限定 Ovis＋PP 适用范围及 Alpha/Beta/Release 边界 |
| [映射入口](../../docs/development-plan/README.md) | 新建，说明外部计划、状态及旧任务关系 |
| [映射 JSON](../../docs/development-plan/legacy_ticket_map.json)、[CSV](../../docs/development-plan/legacy_ticket_map.csv) | 从包内 mappings 逐字节导入，97 个 ID/标题全部与当前旧目录匹配 |
| [检查证据](P2W-S1-01_CHECKS.json)、本报告 | 新建，仅脱敏结构、hash、检查结果和限制 |

仓库外仅更新计划 `state/progress.json` 中本项状态/证据与说明；其余 40 项 TODO，accepted_by/accepted_at 为空。
包内任务 catalog 和任务 Markdown 继续保持初始 TODO，不把计划定义当执行账本；原分发 MANIFEST 不改写。

### 核对范围与实现现状

查阅实际入口与有限相关实现；12 个模块的存在、顶层定义及当前 SHA-256 记录在检查证据。
这不是全仓代码审查，也不是重新运行功能验收。

| 入口 | 当前事实 | 限制/后续落点 |
|---|---|---|
| pipeline.replay/convert/reconstruct/finish/export | CLI/UI 共用；默认 ovis-pp；auto 禁止通过 export 覆写 | native/raster 二选一；自动区域执行待 S2 |
| native_pdf.extract/parse_pages | PDFium 原生路径已存在 | 有限单栏、水平、正常编码 1–3 页；一般段落与隐藏层待 S2 |
| raster_bridge.recognize、replay.load | 显式授权串行 HTTP 与只读封存加载路径分别存在 | 本轮仅阅读；不调用、重建或写回历史 |
| ovis_replay、formula | 内容恢复及有界 OMML | 未知节点可能整页降级；复杂公式待 S3 |
| pp_layout、layout_rules、structure、writer | 几何关联、题图/选项布局、真实 Word Writer 已有模块 | 布局表不代表普通数据表恢复，复杂结构待 S3 |
| review、server、render | 人工账本、本机网页与渲染模块已存在 | 没有运行网页/Word/LO；桌面、可靠运行和跨平台分发待 S4 |
| __init__.py、pyproject.toml | demo-001/0.5.0；根项目 0.1.0，runtime dependencies=[]，wheel 仅 core-domain | demo 依赖在 dev，尚非完整安装产品 |

不新建重复模块，不把计划建议路径当当前 API。探索时曾误查 cli.py/native.py/raster_live.py，
这些名称不存在（rg 退出 2）；随后按模块清单定位 scripts/docx_demo.py、native_pdf.py、raster_bridge.py。
没有据此修改代码或建立占位模块。

### 本项旧 Ticket 映射

| 原 Ticket | 当前关系 | 状态处理 |
|---|---|---|
| T0001 初始化 Monorepo 与工具链 | 复用现有工程、dev 工具和历史收窄范围报告 | 不以 demo 抵充完整桌面构建 |
| T0006 定义引擎 Adapter 协议 | 本项仅确认边界，后续 S2-01/S4-01 补齐 | 未重新验收 Protocol/DTO/Mock，不关闭 |
| T0014 模型部署基线与架构文档对齐 | 复用现有基线、保留待部署与当前事实区分 | 不改部署文档或历史状态 |
| T0015 服务契约发现 | 复用已冻结 PP JSON Base64 合同 | 不重探服务，未知 revision 不补造 |
| T0016 JPG/PNG 与数学试卷回归 | 保留旧 PARTIAL 与新 COMPLETE 独立证据；ADR-006 延续多候选 | 不重评、不改真值、不自动形成唯一权威 |

完整 97 项映射只是覆盖关系。原 TICKETS.md/tickets.json 与 HEAD 逐字节一致；tickets.csv 仅有现存 CRLF/LF 换行表示差异，规范化后与 HEAD 一致，未改写。

## 2. AC 逐项证据

| AC ID | 状态 | 证据 | 限制 |
|---|---|---|---|
| P2W-S1-01-AC01 | PASS | 外部计划隔离；初始 41 TODO；97 ID/标题比对及三格式 validator；映射独立目录 | 完成进度只记录 S1-01 待审阅，不批量 DONE |
| P2W-S1-01-AC02 | PASS | commit/tree、11 锚点、模块源 hash、保护文件前后比对 | 服务与全仓功能未重新验收 |
| P2W-S1-01-AC03 | PASS | profile 网络条款，本项预算 0、实际请求 0 | 未来预算仍须匹配已授权输入/目标/任务 |
| P2W-S1-01-AC04 | PASS | pipeline/CLI 中 pp、ovis、ovis-pp 三选项；CLI help 实跑；profile 限定范围 | 仅入口和文档验证，不冒充 PP 新转换验收 |

以上 PASS 指可核验文档/检查条件。三层交付边界的用户人工核对为 REVIEW_PENDING，最终接受仍待审阅。

## 3. 自动化验证

环境：macOS，zsh；系统 Python 3.9.6；uv 0.11.28；仓库锁定环境 Python 3.12.13。
`UV_OFFLINE=true` 用于仓库命令；本项不需要安装或修改依赖。

| 实际命令/检查 | 退出码 | 结果 |
|---|---:|---|
| git status --short --branch；git rev-parse HEAD；git rev-parse 'HEAD^{tree}'；git remote -v | 0 | 起点、源码与仓库身份如上 |
| python3 "$HOME/Plans/pdftoword-development-plan/scripts/validate_package.py" | 0 | PASS：41 tasks、4 phases、140 AC、97 legacy、11 JSON；初始及进度更新后校验 |
| python3 "$HOME/Plans/pdftoword-development-plan/scripts/inspect_repo.py" --repo . | 0 | EXACT_BASELINE，11/11 anchors，ancestor=true |
| python3 "$HOME/Plans/pdftoword-development-plan/scripts/next_task.py" | 0 | 初始仅建议 S1-01；更新待审阅后 ready=[] |
| UV_OFFLINE=true uv run --locked python scripts/validate_task_catalog.py | 0 | 原三格式各 97，全字段/依赖/语义一致 |
| UV_OFFLINE=true uv run --locked python scripts/validate_model_baseline.py | 0 | ALL CHECKS PASSED（离线文档基线检查） |
| UV_OFFLINE=true uv run --locked python scripts/docx_demo.py replay --help | 0 | 实际可选 content-provider={ovis,ovis-pp,pp}；未执行 Replay |
| 本轮 Python 标准库只读比对 | 0 | 映射字节/ID/标题、模块库存、受保护文件集合/hash、文档相对链接及敏感模式检查，见 CHECKS |
| git diff --check | 0 | 无空白错误 |

纯文档接入无行为变更，未造故障测试，未运行 pytest/ruff/mypy 全矩阵，也未 uv sync。
本轮 pytest 数为 NOT_RUN；499 passed 为旧报告记录。未运行包 --integrity：外部目录含分发 ZIP，
且进度更新本就会改变原分发 hash；不宣称分发包整体完整性通过，仅运行默认结构/一致性校验。

## 4. 真实文档与人工验收

新 run_id、数据集、输入标注、auto/reviewed、Word/LibreOffice 版本与渲染：NOT_RUN。
模型推理请求 0，模型元数据请求 0；未启动 FRP、模型、网页服务或任何云端动作。
历史 T0015/T0016 和 DEMO 证据复用为存在性与保留证据，不转换为本轮真实推理结论。

## 5. 指标及分母

本轮新文档数 0、评测页数 0。内容准确率、可编辑覆盖、表格/公式、题图、顺序、降级比例、
错误率和人工 active 时间均 N/A（没有本轮输入或标注分母），不得报告为 0% 错误或质量 PASS。

## 6. 安全、兼容与历史

对 tmp/model-contract-discovery、tmp/t0015-offline-baseline、tmp/raster-regression、tmp/docx-demo
建立只读 SHA-256 快照并前后比对，包含封存 run、GT、旧汇总与现有自动/人工产物。
只散列字节，不将正文、候选或图片打印到日志；私有逐文件清单保留在系统临时目录，
公开 CHECKS 仅记录数量、集合/字节相等及聚合 hash。该检查证明本轮未改动，不等于重验 seal 内部语义。
原生产源码、AGENTS、ADR、契约、任务目录、锁文件及历史报告保持 Git 内容不变。
逐字节对比 HEAD 时发现 scripts/smoke_models.py 和 tasks/tickets.csv 的工作树为 CRLF、Git blob 为 LF，
首次检查在 smoke_models.py 处退出 1；核对后两文件均仅换行差异，换行规范化比对通过。
文件未改写，Git 对 smoke_models.py 的属性为 text=auto。
其余 180 个受检跟踪文件（README 除外）与 HEAD 逐字节一致。
四个私有目录共 706 个文件的集合与 SHA-256 前后完全一致。
本轮文档未包含原文/图片/Base64/密钥或绝对用户路径；Windows/真实 Word 验收仍保留未运行。

## 7. 未确认事项与下一任务

- 审阅接受：本项仍 READY_FOR_REVIEW，三层交付及 profile 等待用户核对。
- 范围排除：新 holdout、全内容质量、一般数据表、自动区域 OCR、生产网关、三平台 CI、安装/签名、Word 实审均未在本项验收。
- 当前服务可用性、权重 revision、远端 CI 和远端最新 HEAD 本轮未查，不把历史状态写作实时验证。
- 下一建议：本项接受后执行 **P2W-S1-02：建立可复现的本地与三平台自动质量门禁**。
  P2W-S1-03 样本准备亦依赖本项，可另行授权；本轮不继续执行。
- 回滚：仅撤回本次七个文档/映射文件的改动及外部本项进度字段，保留原已安装计划包、Git 内容和私有历史。
  不删除用户此前已存在的计划目录，不 reset/clean。

## 8. Git 与交付

本报告形成时：分支 codex/p2w-s1-01，HEAD 未变；README 为未暂存修改，六个新文件未跟踪，暂存区为空。
外部进度不在本仓 Git 中。未 commit/push/merge，交付停在 READY_FOR_REVIEW。
