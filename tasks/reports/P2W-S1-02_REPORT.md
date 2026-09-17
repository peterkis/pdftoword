# P2W-S1-02 实施与验收报告

状态：**READY_FOR_REVIEW**；远端三平台证据 **PENDING**。日期：2026-09-15。

## 1. 起点与实际范围

仓库 peterkis/pdftoword，起点 commit `3241f10804a899f8ec2b0bdb6512e1f6cd5e456a`，
base tree `924dc06f22bfa7e2401e2cb89ca71461769ad09c`。从 codex/p2w-s1-01 新建 codex/p2w-s1-02，
HEAD 未变。开始时 S1-01 的七个文件改动已存在，本轮保留其原字节，未暂存或提交。

S1-01 在外部账本中仍为 READY_FOR_REVIEW。用户本轮明确要求实施 S1-02，作为本项继续开发授权；
没有替用户接受 S1-01，也没有据此解锁后续任务。只实现工程门禁，不更改转换业务或模型职责。

### 本轮新增

- scripts/quality.py：统一入口、真实子命令、预检、独立报告、原始退出码与源码指纹。
- scripts/quality_pytest.py：collection 前网络保护、Node fixture、私有场景与结果记录。
- scripts/quality_results.py：精确跳过策略、参数脱敏及重新生成的安全 JUnit。
- scripts/validate_schema_samples.py：两个已有 Schema/样例配对；拒绝外部引用及未解析引用。
- .github/workflows/quality.yml：三平台共用入口、只读权限、完整 SHA 固定、精确 artifact 清单。
- tests/unit/test_quality_entrypoint.py、test_quality_network.py、test_quality_results.py、test_schema_samples.py。
- tests/quality-skip-allowlist.json、docs/26_QUALITY_GATE.md、本报告与 P2W-S1-02_CHECKS.json。

### 本轮修改

- tests/conftest.py：在 collection 前载入网络保护插件。
- tests/demo/test_pr_review.py：五个 Node 场景保留原 ID/断言，移除缺 Node 自动跳过。
- tests/demo/test_output.py：符号链接检查独立，保留 HTML/路径/作业检查。
- tests/unit/test_raster_evidence.py：POSIX 权限断言独立，全部平台仍验证公开摘要隐私。
- scripts/README.md、tests/README.md：接入门禁说明。
- 仓库外计划 state/progress.json：仅本项置 READY_FOR_REVIEW 并登记证据；不自动 ACCEPTED。

详见[使用说明](../../docs/26_QUALITY_GATE.md)和[机器可读检查证据](P2W-S1-02_CHECKS.json)。

## 2. AC 逐项证据

| AC | 状态 | 证据与限制 |
|---|---|---|
| AC01 | PASS | 真实 exit-7、超时、缺工具、Node 缺失、用户中断、非法样例；临时副本故障整体 1，恢复整体 0 |
| AC02 | PENDING | workflow 已实现且 actionlint 通过；Ubuntu/macOS/Windows Actions 均未触发，无远端链接，不称 CI 全绿 |
| AC03 | PASS | 修改前本机 499 passed；全部 499 场景 ID 保留，最终 532 passed，新增 33、移除 0，跳过/XFAIL/XPASS 均 0 |
| AC04 | PASS | contents:read、persist-credentials:false、无 pull_request_target；四个 Actions 完整 SHA 经官方 Git 标签和 commit API 核验 |

PASS 是本地工程实现/验证，不是阶段产品质量或人工接受。

## 3. 实际验证

环境：macOS arm64；Python 3.12.13、Node v24.18.0、uv 0.11.28。详细依赖版本、源码 SHA-256、
步骤耗时和退出码见 CHECKS。未更新 pyproject.toml 或 uv.lock，未扩大 Ruff/mypy 排除。

| 命令/检查 | 结果 |
|---|---|
| 修改前 uv run --locked pytest -q | 499 passed，1 条已有 StarletteDeprecationWarning |
| 修改前 Ruff、mypy、原两个 validator | 均通过 |
| 第一个真实 exit-7 回归 | 先因缺少 quality 模块失败，最小实现后通过；保留原始 red 日志 |
| Schema 与忽略数据指纹回归 | 先失败后修复，真实临时样例/文件，无业务算法替身 |
| uv run --locked python scripts/quality.py --output-dir tmp/quality-s1-02/verified-gate | 整体 0；pytest 532 passed，Ruff、mypy、原两个 validator、Schema 检查全部 0 |
| actionlint 1.7.12 .github/workflows/quality.yml | 0；下载的官方归档 SHA-256 与官方 checksums 匹配 |
| 隔离源码副本 uv sync --locked | 新建独立 .venv 成功，使用相同锁文件；无私有样本/响应复制 |
| 同一副本故障注入质量入口 | 532 passed + 1 failed，pytest 返回 1，后续五项仍执行并通过，整体返回 1 |
| 移除临时测试后同一副本质量入口 | 532 passed，全部步骤 0；最终源码指纹与当前工作区检查一致 |
| git diff --check；计划包 validate_package.py | 0 |

副本是当前未提交源码的隔离复制加空 Git 元数据，不冒充已提交的干净 checkout 或远端 runner。
原生环境 `.venv` 未复制；从锁文件建立新的依赖环境。临时故障仅在副本中，未进入交付工作树。
失败、恢复和此前检查产物均保留在独立忽略目录，不覆盖失败历史。

私有日志目录：tmp/quality-s1-02；最终正常门禁为 verified-gate；
最终副本公开摘要为 fault-verified-public 与 recovery-verified-public。
系统临时源码副本的位置仅在私有 snapshot-location.json 中记录。

### 发现及处理

- 首轮完整入口 524 测试通过，但 3 个新增 Ruff 问题使整体返回 1；已修复，没有伪报成功。
- 未解析的 Schema fragment 曾抛引用异常；补回归后返回安全错误码 REFERENCE_UNRESOLVED。
- 最后源码指纹比对发现 scripts/tmp 下既有忽略文件被初版扫描计入；只曾散列字节，未发布正文。
  已补回归，改按 Git 可见文件集合散列，最终工作区与隔离副本指纹一致。先前检查记录不抹除。
- 既有 Starlette 弃用警告继续显示，不禁 warning、不自动升级到 httpx2。
- actionlint 匿名 release 查询曾遇 GitHub API 限额，改用现有 gh 的只读访问完成核验；无远端写入。

## 4. 场景、隐私与平台边界

原 499 个测试 ID 全部保留。POSIX mode 与 symlink 原断言分别移入新增测试，原覆盖没有删除；
五个 JS 处理器实际执行且未跳过。真实子 pytest 的未批准 skip/xfail 即使自身退出 0，质量结果仍失败。

公开产物只含结构化摘要、工具版本、hash 化参数 ID、状态和耗时。公开 JUnit 从结果新建，
不复制断言文本、stdout/stderr。最终产物扫描无绝对用户路径、私有哨兵或 raw 文本。
workflow 不上传整个 tmp、DOCX、图片、response、GT、overrides；依赖与 GitHub 访问不记作模型调用。

网络保护覆盖 pytest collection 与执行阶段的同步/异步 httpx 和 Python socket；TestClient、
MockTransport 和标准库 socketpair 可用。它不是 Node/任意子进程的 OS 网络沙箱。
Windows socketpair 的标准库回环实现具有同步、线程内例外；不放行普通 localhost 请求。

Windows POSIX 权限单项不适用；symlink 只有 winerror=1314 可以登记跳过。
应用路径/session/资产访问隔离仍在所有平台测试；本机未执行 Windows，不能以模式位或合成测试声明 ACL 验收。

## 5. 真实文档、指标与历史

新真实输入、模型推理、Word/LibreOffice、人工视觉验收：NOT_RUN。模型请求数 **0**。
识别正确率、可编辑覆盖、表格/公式/题图/降级比例和人工 active 时间均 N/A（本项真实页分母 0）。
临时合成 PDF/DOCX 仅来自既有离线测试，不能计为新 holdout 或产品 Gate。

706 个既有 T0015/T0016/DEMO 文件的集合与 SHA-256 前后相同；S1-01 七个已有改动文件保持原字节。
不读真值作为输出、不 evaluate/promote 历史运行，不修改原 97 项 Ticket、生产源码、历史报告或 ADR。
本项只覆盖 T0002 质量门禁及 T0012/T0013 的部分测试/摘要，不自动关闭旧任务。

## 6. Git、未确认项与下一任务

- 分支 codex/p2w-s1-02，HEAD 未变，暂存区为空，新增/修改均未提交；前一项改动继续存在。
- 未 commit/push/merge，未触发远端 CI，未设置分支保护；配置 workflow 不等于合并已被强制阻断。
- Ubuntu/macOS/Windows 远端正常运行及远端真实失败注入均 PENDING，需后续明确远端授权。
- S1-01 和本项最终人工接受仍待审阅；本轮实施授权不伪造 accepted_by/accepted_at。
- 下一建议：P2W-S1-03 样本集准备；S1-04 的依赖仍需逐项满足，不自动执行。
- 回滚仅撤回本项列出的代码/测试/工作流/文档与外部本项状态，不删除旧 pytest/validator、S1-01、私有历史或用户文件。
