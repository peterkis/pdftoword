# 模型网关契约 V1.1

**重要说明**：本契约为目标架构规范。当前部署状态见 `docs/23_MODEL_DEPLOYMENT_BASELINE_V1_1.md`。

- 当前直接服务：Monkey :9000 / Ovis :8000 / PP :8080
- 目标统一网关：8100（尚未部署）
- PP HTTP 契约：**verified_from_openapi**（T0015 / P0-GATE-001A）

## 通用

- Base URL：`/v1`
- 鉴权：`Authorization: Bearer <API_KEY>`
- 幂等：`Idempotency-Key`
- 追踪：`X-Request-ID`
- 图像使用 multipart；元数据 JSON 单独字段。

## 接口

### POST /layout/fast

**模型**：PP-DocLayout_plus-L（当前部署）或 PP-DocLayout-M（旧名称）。

返回区域 bbox、标签、置信度和模型元数据。

**注意**：此处为目标网关业务接口；当前 PP 直连契约见下方 Gate 小节。

### POST /layout/complex

MonkeyOCRv2。`task=layout|end_to_end`。返回原始标签、归一化标签、阅读顺序、坐标和内容候选。没有原始概率时 `engine_confidence=null`。

### POST /ocr/text

PP-OCRv6。返回文字框、行、文本、置信度。

### POST /parse/table

PP-StructureV3。返回表格区域、网格、单元格、跨度、内容、置信度。

### POST /parse/formula

PP-FormulaNet。返回 LaTeX/MathML 候选和置信度。

### POST /review/content

OvisOCR2。返回 Markdown、HTML 表格、LaTeX 和图片区域候选；不返回最终 IR。

### GET /health

网关、队列、GPU 和内部服务健康。

### GET /models

模型 ID、revision、hash、loaded、device、服务版本。

## PP-StructureV3 Gate 直连契约

状态：**verified_from_openapi**。来源 run_id：`t0015-mac-20260909T061855Z`；接入 `frp_stcp_loopback`。

- primary：`POST /layout-parsing`；operationId=`infer`；Transport=`json_base64`，Content-Type=`application/json`。
- OpenAPI 可用，3.1.0，FastAPI / 0.1.0；paths=`/health`、`/layout-parsing`。
- Schema required 为 `file`。`fileType` 允许 0/1/null；本工具图片请求始终明确传 `fileType=1`。
- query 参数为空；成功 200 与错误 422/500 Schema 由 OpenAPI 自动解析。实际成功响应通过 Schema 验证。
- alternatives=`[]`：没有文档化 multipart 或 `/PP-StructureV3`，本轮未额外探测，不声明不存在兼容端点。
- OpenAPI 响应 SHA-256：`d8fa7c68be55a2ff12e5d01b47e60c15535170318d51814985cf542df3f1a885`。
- 三类 PP 错误实测均 HTTP 422、body.errorCode=422、errorMsg string；二者独立记录。

Monkey Wire 为 string / python_literal_list，strict_json=false，经 ast.literal_eval 解析为 array<object>，坐标 normalized_1000；Ovis 为 string / markdown。

完整规范和请求来源见 [生成契约](discovered-model-contracts.json) 与 [报告](../tasks/reports/T0015_REPORT.md)。原始详细证据仅留在忽略的 tmp 目录。服务指纹不等同于权重 revision 锁定；未暴露字段为 unknown/null。

原 2026-08-29 Windows 静态冻结声明属于 Historical，不能覆盖当前自动生成契约。
