# 本地与三平台工程质量门禁

P2W-S1-02；工程门禁与真实文档/模型/Word 验收分别记录。
当前检查入口不会安装工具、调用模型、修改锁文件或设置 GitHub 分支保护。

## 环境与执行

使用 Python **3.12.13**、Node **24.18.0**、uv **0.11.28**，从现有锁文件准备开发环境：

```sh
uv sync --locked
uv run --locked python scripts/quality.py
# 可指定新的独立目录；已有非空目录拒绝覆盖
uv run --locked python scripts/quality.py --output-dir tmp/quality/my-run
```

脚本从自身位置确定仓库根，Python 子检查使用当前解释器，路径支持中文和空格。
从仓库外调用时使用该环境的 Python 和脚本绝对路径；不要使用其他 Python 环境。
CI 的 Python/Node/uv 固定；本地 quality 强制 Python/Node 版本，其他 Python 工具版本从锁定环境记录。
依赖安装允许访问依赖源，执行测试不允许真实网络。

预检检查 Python/Node/Git 和 pytest/ruff/mypy/jsonschema。之后串行执行完整 pytest、
Ruff、mypy、原任务目录校验、模型基线文档校验、Schema/样例校验。
后一个独立步骤不因前一个失败被跳过；无自动修复、无重试或任选子集参数。
子进程不继承 PYTEST_ADDOPTS/PYTEST_PLUGINS，避免环境中的筛选参数静默减少完整门禁。
现有 pyproject 检查范围保持不变；未新增 mypy 排除，也未把代码格式化扩为门禁。

| 整体退出码 | 意义 |
|---|---|
| 0 | 所有必要检查成功且没有未批准跳过 |
| 1 | 检查失败、超时、测试报告不完整或跳过策略失败 |
| 2 | 环境、必要工具、版本或入口配置错误 |
| 130 | 用户中断 |

各步骤保留真实子进程退出码；超时/无法启动/中断等未正常返回的情况用 null。
原始输出留在运行目录的 private 子目录，公开摘要不拼接 stdout/stderr。
默认输出在已忽略的 tmp/quality 下；每次新目录，不覆盖失败证据。

## 默认 pytest 网络与 Node 策略

测试插件在 collection 前安装同步/异步 httpx 与 Python socket 防护；真实互联网连接、
DNS、UDP 发送均禁止，包含 localhost/IPv4/IPv6 和所有 FRP 端口。
MockTransport、ASGI/WSGI/TestClient 仍使用进程内调用；socketpair 的标准库内部通信可用。
Windows 的标准库 socketpair 可能使用回环实现，仅该同步调用具有线程内窄例外。
Python 防护不构成 Node/其他进程的系统级沙箱；现有 Node 测试只执行内存处理器，禁止新增网络子进程。

五个前端处理器测试使用统一 node fixture；缺 Node/版本不符为错误，不再跳过。
原型的业务模式、模型预算与封存 Replay 均未因门禁改变。

## 平台差异与跳过白名单

[白名单](../tests/quality-skip-allowlist.json)精确登记测试 ID、平台和固定原因：

- Windows 不适用 POSIX 0600/0700 模式位测试；公开摘要隐私检查继续在全部平台执行。
- Windows 创建符号链接只在 winerror=1314 时允许该单项跳过，其他失败仍抛出。
- 所有平台执行路径穿越、已登记资产与 session/Host/Origin 访问隔离、中文空格真实文件测试。
- 完整 quality 拒绝未登记 skip、XFAIL、XPASS，不放行缺 Node 或整个目录。

Windows 应用访问隔离不等于 Windows ACL/多用户安全验收；本项不实现或宣称后者。
直接 pytest 可供开发定位问题；最终完整状态以 quality 的跳过策略检查为准。

## Schema 样例

```sh
uv run --locked python scripts/validate_schema_samples.py
```

只登记两个已存在契约：Layout IR → sample-layout-ir-v1.1；Job Config → sample-job-config。
检查 Schema 自身和实例，错误只列文件、Schema 字段路径、规则与错误码。
当前契约仅需文档内 fragment 引用；其他引用明确拒绝，不使用远端解析器。
其余 sample-fusion-decision、sample-question-figure-relation、sample-monkey-normalized-response
尚无本入口配对的独立 Schema，记为 NOT_COVERED_BY_SCHEMA_PAIR，不伪造契约。

## CI 与安全产物

[工作流](../.github/workflows/quality.yml)在 ubuntu-24.04、macos-15、windows-2025 执行同一入口。
每项 30 分钟，matrix fail-fast=false；PR、main push、手动事件均可触发。
只读 contents 权限；checkout 不保存凭据；Actions 固定完整 SHA；无项目缓存；不使用 pull_request_target。
固定 OS 标签仍会更新镜像，报告记录可用的 ImageOS/ImageVersion，不能宣称 OS 字节级冻结。

Artifact 仅列明 public/summary.json、environment.json、tests.json、junit.xml，保留 7 天。
JUnit 是结构化结果新生成的副本，移除失败消息、captured output；参数化值以 hash 区分。
不上传原始 JUnit、测试作业、PDF/DOCX、原图、响应、GT、overrides，即使它们由合成测试生成。
GitHub 未运行与真实三平台成功分开记录；仅添加 workflow 不代表启用分支保护。

## 场景延续与后续边界

原 499 个测试 ID 保留。原隐私测试中的 POSIX mode 断言拆入独立权限测试；
原 HTML/路径测试中的 symlink 断言拆入独立 symlink 测试，其余断言保留。
五个 Node 用例保留原 ID 与断言。新增质量入口、Schema、网络和安全报告测试。

本项仅覆盖旧 T0002 的门禁及 T0012/T0013 的部分测试/安全摘要，不自动完成旧 Ticket。
真实 holdout、Word/LibreOffice 验收、桌面分发与生产网关保持后续范围。
实施与未确认事项见 [P2W-S1-02 报告](../tasks/reports/P2W-S1-02_REPORT.md)。
