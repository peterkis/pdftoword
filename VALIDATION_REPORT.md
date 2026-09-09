# 验证报告 — T0015 Mac + FRP

最终建议状态：**ACCEPTED（HTTP 契约）**。

- 分支：`fix/t0015-reproducible-contract-evidence-macos`。
- 起始公开提交 / 运行 HEAD：`a5f1fd713715e2304432ac3cc9d27544f849e904`。
- 真实 run_id：`t0015-mac-20260909T061855Z`；execution_mode=live；access_mode=frp_stcp_loopback。
- Monkey / Ovis：verified；PP：verified_from_openapi；overall_status=ACCEPTED。
- 用户确认无需 API Key；旧值未用于鉴权，当前不发送 Authorization。`.env.local` 未跟踪、0600。
- Spec、8 个 observed/provenance Fixture、13 个请求摘要与当前执行 core 哈希关联一致。

## 质量门禁

| 命令 | 结果 |
| --- | --- |
| uv sync --locked | PASS |
| uv run pytest | 147 PASS |
| uv run ruff check . | PASS |
| uv run mypy . | PASS |
| uv run python scripts/validate_task_catalog.py | PASS |
| uv run python scripts/validate_model_baseline.py | PASS |
| git diff --check / 敏感信息扫描 | PASS |

## NEEDS_FIX 统计

- 初始基线：104 单测通过，ruff 6 项、mypy 17 项错误。
- 当前静态错误：0；当前 T0015 HTTP 契约阻塞：0。
- 未声称锁定服务未暴露的权重 revision / 容器镜像；这些字段保持 unknown/null。

完整逐请求证据、错误契约、来源关联、历史失败尝试和变更清单见 [T0015 报告](tasks/reports/T0015_REPORT.md)。此前 Windows/启动包和未连通结果仅为 Historical。

本轮未执行 T0016/T0017、生产 Adapter、网关开发、FRP 修改、commit、push 或 PR 操作。
