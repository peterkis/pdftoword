# services/core-api — 本地 API 服务（占位）

T0001 仅建立目录边界，本目录当前没有任何代码。

## 未来职责（T0011 及后续 Ticket）

- FastAPI 本地服务，向 Desktop UI / CLI 暴露作业创建、状态查询、取消、导出接口；
- 所有请求携带 `request_id`；
- 错误使用统一错误码（T0009），不吞异常。

## 硬性边界

- 调用链必须是 `Tauri / React → 本地 Core（macOS / Windows） → Provider/HTTP Adapter → Ubuntu GPU 模型服务`；
- UI 不得绕过本服务直连 GPU 模型机（见 `AGENTS.md` 第 3 节）；
- 本服务属于核心层，不得 import 具体模型 SDK。
