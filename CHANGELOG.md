# Changelog

## 2026-09-09 — T0015 Mac + FRP 可复现契约证据

- 收敛 core/CLI 为一套发现实现，新增 loopback、安全确认、无重定向、严格模型身份与 Wire 检查。
- PP 优先读取当前 OpenAPI；失败/不完整时仅执行有限回退，运行差异阻断验收。
- 响应摘要、逐请求元数据、运行来源与全部 Artifact 使用同一生成链；合成数据明确标识。
- 测试调用真实函数，通过 MockTransport 离线验证，修复全仓 T0015 lint/type 问题。
- 完整真实运行 `t0015-mac-20260909T061855Z` 已通过，13 个请求与 8 个 observed/provenance Fixture 同源；147 项测试及全仓门禁通过。


## 2026-09-09 — macOS 开发迁移

- 清理复制自 Windows 的虚拟环境和 Python 工具缓存，按 `uv.lock` 重建 Python 3.12 环境，补充 macOS 元数据忽略规则。
- 根 AGENTS.md 精简为操作规则与阅读索引，完整产品/模型约束迁至 docs/24；本机调试与既有 FRP 接入说明放在 docs/25。
- Gate 配置增加 MONKEY_BASE_URL、OVIS_BASE_URL、PP_BASE_URL 服务根地址；环境变量优先，兼容旧名称和简单引号值。
- 修正 mypy 的 scripts 模块搜索路径与过期开发说明；保留原有工作、暂存区、样本和历史验收记录。
- 验证与剩余静态检查问题见 tasks/reports/LOCAL_MAC_MIGRATION_REPORT.md。


## 0.1.0 — 2026-08-27 — T0001 工程初始化

- 初始化 Monorepo 工程骨架：`packages/core-domain`、`services/core-api`、`apps/desktop`、`tests`、`scripts` 目录边界。
- 建立 Python 3.12 + uv 工具链（pytest / ruff / mypy），新增 `pyproject.toml`、`.python-version` 与 `uv.lock`。
- 新增 Provider 配置数据结构骨架（`ModelProviderConfig` / `EndpointProfile` / `ProviderCapability` / `ProviderStatus` / `TransportProfile`），仅声明式 Schema，不含任何运行时行为。
- 预留 `raster_io` / `image_normalization` 空模块边界。
- 新增 `.env.example`（仅占位符）、`.editorconfig`、`.gitattributes`；完善 `.gitignore`（含 `tests/fixtures` 例外规则与 raw 响应强制忽略）。
- 建立最小单元测试：包导入与模型 SDK 隔离、配置结构校验、Windows 路径与 tempfile 兼容性。
- `config/example.env` 中的内网 IP 替换为占位符 `MODEL_SERVER_IP`。
- 收尾修复：`scripts/smoke_models.py` 服务地址全部改为强制环境变量读取（`require_env`），不再包含任何默认服务器地址；新增真实 Windows 中文/空格路径文件读写测试（pytest 19 passed）；验收在 Windows 原生 PowerShell 5.1 中通过（pytest/ruff/mypy）。
- 复验修正：SDK 隔离测试改为导入前后差集判定并加 30 秒超时（环境预加载模块不再造成假失败）；`EndpointProfile.base_url` 契约统一——允许 `/v1` 稳定 API 前缀、拒绝 query/fragment，校验改用 `urllib.parse.urlsplit`，docstring/测试/`.env.example` 三处一致（pytest 23 passed）。
- 复核修正（四）：`agents.md` 经两步 `git mv` 重命名为规范名 `AGENTS.md`（消除 Windows 大小写双入口），README 目录移除独立 `agents.md` 条目；移除失效的 `MANIFEST.sha256` 与 `PACKAGE_MANIFEST.md`（原 PRD 包清单，哈希与文件计数均已失效），正式交付包将由发布脚本按 Git commit 重新生成。
- 完整验证证据见 `tasks/reports/T0001_REPORT.md`。

## 1.1.0 — 2026-08-20

- 将 `MonkeyOCRv2-B-Parsing` 纳入复杂页面版面主链路。
- `PP-DocLayout-M` 固定为快速初筛；`PP-DocLayout-L` 从默认升级链路移除。
- 明确 MonkeyOCRv2 为复杂页几何与阅读顺序权威，不是文字、表格和公式最终权威。
- 将 OvisOCR2 调整为高风险内容与完整性复核器。
- 新增本地应用与 GPU 模型网关分层，统一外部端口 `8100`。
- Layout IR 升级至 `layout-ir/1.1`，增加内容候选、几何来源、模型置信度与系统置信度分离。
- 新增多模型融合、MonkeyOCRv2 Adapter、模型网关、题图关系和迁移规范。
- 将开发计划重构为 P0–P7，每阶段包含目标、具体 Ticket、依赖和退出门槛。
- 增加机器可读 `tickets.json`、`tickets.csv`、模型路由配置和三档运行配置。

## 1.0.0 — 2026-08-20

- 首次确认 native / mixed / scanned 三类 PDF 处理链路。
- 确认流式 DOCX、局部 OCR、Layout IR 和 OvisOCR2 兜底策略。
