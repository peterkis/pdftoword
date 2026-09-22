# 全仓 mypy 扫描边界与历史脚本整理

日期：2026-09-22。状态：本地全仓类型检查及回归检查已验证；未提交、未推送。

## 修改

根因是 mypy 递归扫描不采用 `.gitignore`。`tmp/` 中保留的历史 writer 副本、诊断脚本及下载参考源码混入正式源码发现过程，导致同名模块在类型检查前就中断。

修复包括：

- `pyproject.toml` 将根目录 `tmp/`、`outputs/`、`artifacts/`、`build/`、`dist/`、`data/jobs/` 明确排除出递归发现。正则锚定仓库根，不排除 `tests/tmp/` 等嵌套源码目录。既有 `smoke_models` 例外收窄为准确文件 `scripts/smoke_models.py`，相似名称的新源码仍检查。严格类型规则未放宽，没有新增 ignore-errors 或屏蔽测试目录。
- 排除历史产物后暴露两处真实错误：两个新表格回归测试将 `Path` 传入标注接收 `str | IO[bytes] | None` 的 python-docx `Document`。现改用 `Document(str(...))`，保留原测试断言和转换行为。
- 新增 `tests/unit/test_mypy_scope.py`，实际调用 mypy 与仓库配置。用重复/无效历史模块证明它们不会阻断检查，同时在普通源码、`tests/tmp/` 及 `smoke_models_extra.py` 放入类型错误，确认三处仍被报告。修改前测试失败，修改后成功。
- README记录源码/产物边界、历史证据保留方式与可重建缓存的清理规则。CI的共享质量入口原本就执行同一个 `mypy .`，无需另造检查命令。

## 归档与清理

私有维护目录：`tmp/maintenance/mypy-20260922/`。

- 将41份历史/诊断Python脚本保存为 `historical-python.tar.gz`，原脚本合计331369字节，归档88373字节。`archive-manifest.json`记录相对路径、逐文件SHA-256及归档SHA-256；重新读取归档成员并逐项验证与原件一致。
- 归档是可复查的压缩副本。原脚本继续保留在旧报告所引用的位置，未迁移或删去历史writer副本，也未改写历史失败收据。
- 仅删除根目录 `.mypy_cache/`、`.ruff_cache/`、`.pytest_cache/` 三个可重建缓存目录，实际旧缓存18356470字节（约18.4 MB）。操作前确认目标是预期目录且非符号链接；核验过程会生成新的必要缓存，因此不将该数字表述为永久净节省量。
- 不清理 `tmp/` 整体、模型/虚拟环境、本地PDF、标注、旧自动输出或历史诊断证据。归档恢复应先解压到新目录并按manifest验哈希，避免覆盖原证据。

## 验证

| 命令 | 实际结果 |
|---|---|
| 原配置下新增扫描边界测试 | 失败，历史同名模块导致mypy退出2，证明可重现 |
| 排除运行目录后的诊断 | 暴露2个真实类型错误，均已修复 |
| `uv run --locked mypy --no-incremental .` | 退出0；217 source files，无问题；清理旧缓存后运行 |
| **`uv run mypy .`** | **退出0；217 source files，无问题** |
| `uv run --locked ruff check .` | 退出0 |
| `uv run --locked pytest -q` | 退出0；1726 passed，1条既有Starlette弃用警告，102.14秒 |
| `uv sync --locked --offline` | 退出0；锁文件保持 |
| `git diff --check` | 无问题 |

全量测试为工程回归，不代表PDF产品质量获批。没有发起远端CI；本地与CI配置共用不等于声称远端已运行。

## 证据与保留核对

- `baseline.json`、`baseline.diff`：HEAD与本轮开始前全部受Git管理及未忽略的新文件哈希、已有diff。
- `red.log`、`mypy-cold.log`、`mypy.log`、`ruff.log`、`pytest.log`、`checks.json`：实际检查收据。
- `archive-manifest.json`、`historical-python.tar.gz`：41份原脚本的可核验归档。
- `cache-cleanup.json`：三个缓存目录的清理范围、文件数和字节数。
- `preservation-final.json`：41个历史脚本原件哈希不变；HEAD不变；既有文件仅README、pyproject及上述两个测试文件发生本轮授权修改，其余已有未提交工作保持。

先前F3报告中的mypy阻断是当时事实，保持原文；本报告记录该工程阻断已关闭。之后新增维护源码应放在正式源码目录，不应依赖被排除的运行产物目录；导入检查仍由mypy规则约束。
