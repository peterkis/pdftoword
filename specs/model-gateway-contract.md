# 模型网关契约 V1.1

**重要说明**：本契约为目标架构规范。当前部署状态见 `docs/23_MODEL_DEPLOYMENT_BASELINE_V1_1.md`。

- 当前直接服务：Monkey :9000 / Ovis :8000 / PP :8080
- 目标统一网关：8100（尚未部署）
- PP HTTP 契约：**✅ 已冻结**（T0015 / P0-GATE-001A）

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

**注意**：PP HTTP 契约尚未冻结，端点路径和 Transport 待 T0015 验证。

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

## PP-StructureV3 直连契约（已冻结）

**端点**：`POST /layout-parsing`

**Transport**：`application/json`

**请求格式**：
```json
{
  "file": "<base64_encoded_file>",
  "fileType": 0
}
```

**fileType 值**：
- `0`：PDF 文件
- `1`：图片文件（JPG/PNG）

**成功响应**（HTTP 200）：
```json
{
  "logId": "<uuid>",
  "result": {
    "layoutParsingResults": [
      {
        "prunedResult": {
          "width": 800,
          "height": 1159,
          "model_settings": {
            "use_doc_preprocessor": true,
            "use_seal_recognition": false,
            "use_table_recognition": true,
            "use_formula_recognition": true,
            "use_chart_recognition": false,
            "use_region_detection": true
          },
          "parsing_res_list": [
            {
              "block_label": "text",
              "block_content": "...",
              "block_bbox": [x0, y0, x1, y1],
              "block_id": 0,
              "block_order": 1
            }
          ],
          "overall_ocr_res": {},
          "formula_res_list": []
        },
        "markdown": "...",
        "outputImages": {},
        "inputImage": "<base64>"
      }
    ],
    "dataInfo": {
      "width": 800,
      "height": 1159,
      "type": "image"
    }
  },
  "errorCode": 0,
  "errorMsg": "Success"
}
```

**错误响应**（HTTP 422）：
```json
{
  "logId": "<uuid>",
  "errorCode": 422,
  "errorMsg": "[{\"type\": \"missing\", \"loc\": [\"body\", \"file\"], \"msg\": \"Field required\"}]"
}
```

**验证信息**：
- 验证任务：T0015 / P0-GATE-001A
- 验证日期：2026-08-29
- 验证方法：手动 HTTP 探测
- OpenAPI：服务未暴露

## 通用响应

```json
{
  "request_id": "req-...",
  "task": "layout.complex",
  "status": "ok",
  "model": {
    "id": "zenosai/MonkeyOCRv2-B-Parsing",
    "revision": "pinned-revision",
    "service_version": "..."
  },
  "timing_ms": {"queue": 12, "inference": 1430, "total": 1468},
  "result": {},
  "warnings": []
}
```

## 错误

使用统一代码：认证、限流、队列满、模型未加载、OOM、超时、输入过大、格式错误、内部模型失败。客户端不得根据 HTTP 文本猜测错误类型。
