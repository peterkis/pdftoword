# scripts — 辅助脚本

## 现有脚本

- `smoke_models.py`：历史遗留的手工模型 smoke 脚本（直连模型服务、依赖 `httpx`）。
  - T0001 不运行该脚本、不改动其识别逻辑；
  - 收尾修复：所有服务地址（`MONKEY_CHAT_URL`、`OVIS_CHAT_URL`、`PP_STRUCTURE_URL`）
    必须从环境变量读取，缺失时脚本立即以清晰错误退出，不再包含任何默认
    服务器地址（模型名保留非敏感默认值）；
  - 它依赖 `httpx`（已在 dev 依赖组安装），故被 `pyproject.toml` 的 mypy 配置排除；
  - 输出默认写入仓库根 `tmp/model-smoke/results/`（已被 `.gitignore` 忽略）。

## 计划脚本

- 质量门禁聚合脚本（lint / typecheck / test）将在 T0002 建立。

## 约定

- 自动化脚本优先使用跨平台 Python；macOS 可用 zsh，Windows 可用 PowerShell 7；
- 不依赖 Bash、make 或 WSL；
- 路径处理使用 `pathlib`，临时目录使用 `tempfile`；
- 必须兼容中文文件名与含空格的路径。

## 本机 Gate 调试

使用 `discover_model_contracts.py`，配置与命令见 [本机调试](../docs/25_LOCAL_DEVELOPMENT.md)。
`model_contract_discovery.py` 支持短名称服务根地址与旧 Gate 变量；环境变量优先于 `.env.local`。
