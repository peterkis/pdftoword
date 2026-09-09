# macOS 本机迁移验证 — 2026-09-09

## 范围与保留项

当前分支 `feat/p0-gate-001a-contract-discovery` 自带 T0015 暂存/未暂存/未跟踪工作。未提交或切换分支；结束时逐字节核对 `git diff --cached --binary` 与开始时一致。未删除样本、历史报告、原始模型证据和 `tmp/`。

清理 Windows `.venv`（包含 `Scripts`、`Lib` 与旧 Windows Python 路径）、`.mypy_cache`、`.pytest_cache`、`.ruff_cache` 及 `__pycache__`；按锁文件重建为 macOS Python 3.12.13。跟踪文件权限恢复为 Git 记录的普通文件权限。本地 `.env.local` 权限为 0600。

迁移前 Git 暂存/工作区补丁与 `.env.local` 备份保存在仓库同级 `pdf2word-migration-backup-20260909/`（目录 0700，配置 0600）。这不是完整仓库备份；未跟踪工作仍保留在原位。

## 实施

- AGENTS.md 保留关键约束、授权范围、验证流程和按任务索引；原第 1–8 节完整迁入 docs/24_PRODUCT_AND_MODEL_RULES.md，未改变产品决策。
- README、START_HERE、组件说明与 scripts 文档更新本机入口；docs/25_LOCAL_DEVELOPMENT.md 记录配置优先级和调试命令。
- `.env.example` 使用安全回环地址；`.env.local` 保留既有凭据，服务根地址设为用户提供的三个 localhost 端口。兼容旧变量名，进程环境优先于文件，同一来源短名优先。
- mypy 搜索路径包含 scripts，解决 Gate 模块导入定位；不以忽略错误或放宽 strict 掩盖问题。
- 未配置或修改 FRP；使用用户已连接的隧道。

## 验证结果

| 验证 | 结果 |
| --- | --- |
| `uv sync --locked` | 通过，未修改依赖锁定 |
| 新配置测试先红后绿 | 先有 2 失败/2 通过，实现后 4 通过 |
| `uv run pytest` | 104 通过，均为 unit；integration/golden 尚无测试 |
| `uv run ruff check scripts/model_contract_discovery.py tests/unit/test_local_model_config.py` | 通过 |
| `uv run mypy scripts/model_contract_discovery.py tests/unit/test_local_model_config.py` | 通过 |
| `uv run python scripts/validate_model_baseline.py` | 通过 |
| `uv run python scripts/validate_task_catalog.py` | 通过，97 个 Ticket 一致 |
| `uv run python scripts/discover_model_contracts.py --help` | 通过 |
| `git diff --check` 与新增文档本地链接 | 通过 |
| Monkey/Ovis `GET /v1/models` | 均 HTTP 200，JSON 含 data 列表 |
| PP `GET /openapi.json` | HTTP 200，JSON 含 openapi 字段 |

只读检查使用本地配置和既有凭据，无输出凭据/响应正文；常规 httpx 环境下也通过。PP 当前返回 OpenAPI，与旧报告可能不同；未据此覆盖历史冻结契约。未发送样本进行推理，未更新黄金结果或阶段验收状态。

## 现有静态检查遗留

全仓 `ruff check .` 仍有 6 项错误，全部位于本次未改动的 `tests/unit/test_model_contract_discovery.py`（未用导入、导入位置/排序、未用变量、文件末尾换行）。

全仓 `mypy .` 仍有 17 项错误，位于本次未改动的 `test_openapi_endpoint_discovery.py`、`test_contract_redaction.py`、`test_contract_normalization.py`，主要是混合字典推断为 Collection/object 后索引/方法类型不匹配。模块导入路径问题已修复，本次行为代码和新增测试无静态错误。

本机环境和 Gate 配置可用于继续调试；全仓静态门禁尚未通过。API、桌面 UI、完整 PDF → DOCX 流水线与真实模型质量不在本次完成范围。
