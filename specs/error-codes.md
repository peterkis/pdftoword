# 错误码

## PDF

- `PDF_INVALID`
- `PDF_ENCRYPTED`
- `PDF_DAMAGED`
- `PDF_UNSUPPORTED_PAGE`

## 模型网关

- `MODEL_GATEWAY_UNREACHABLE`
- `MODEL_AUTH_FAILED`
- `MODEL_QUEUE_FULL`
- `MODEL_TIMEOUT`
- `MODEL_OOM`
- `MODEL_NOT_LOADED`
- `MODEL_RESPONSE_INVALID`

## IR/融合

- `IR_SCHEMA_INVALID`
- `COORDINATE_INVALID`
- `CONTENT_CONFLICT`
- `GEOMETRY_CONFLICT`
- `READING_ORDER_CONFLICT`

## DOCX

- `DOCX_BUILD_FAILED`
- `DOCX_PACKAGE_INVALID`
- `FORMULA_CONVERSION_FAILED`
- `TABLE_REBUILD_FAILED`

每个错误包含 retryable、stage、job/page/region、建议动作和 cause chain；不得包含正文。

## T0015 Gate 契约发现（工具层）

以下是离线/实测发现状态，不是生产 Adapter 错误码。

| 状态/类别 | 含义 |
| --- | --- |
| REVALIDATION_REQUIRED | 历史证据不足，等待当前运行 |
| BLOCKED_PREFLIGHT | 本地安全确认、配置、文件权限或输入检查失败 |
| SECURITY_CONFIRMATION_REQUIRED_KEY_ROTATION_OR_NO_AUTH | 缺少操作人的鉴权安全确认 |
| BLOCKED_NON_LOOPBACK_ENDPOINT | 运行地址不在允许的回环端口内 |
| BLOCKED_MODELS_ENDPOINT_UNAVAILABLE | 模型列表端点连接/HTTP/结构失败，无身份不匹配证据，禁止推理 |
| BLOCKED_MODEL_IDENTITY_MISMATCH | 模型列表或请求模型不匹配，禁止推理 |
| CONTRACT_RUNTIME_DIVERGENCE | 文档化请求/响应与实际行为不一致 |
| BLOCKED_PP_CONTRACT_UNRESOLVED | 有界候选中没有验证成功的 PP 契约 |
| BLOCKED_ERROR_CONTRACT | 无害错误探测未得到可验证的错误响应 |
| BLOCKED_CONTRACT_UNRESOLVED | 至少一个服务契约尚未验证 |
| BLOCKED_DISCOVERY_ERROR | 发现过程中结构或解析异常，保留失败状态和请求证据 |
| BLOCKED_INCOMPLETE_EVIDENCE | 请求缺少响应摘要，不能推广 |
| RUN_DIRECTORY_ALREADY_CONTAINS_EVIDENCE | 运行目录非空，避免覆盖已有证据 |
| PROMOTION_REQUIRES_ACCEPTED_COMPLETE_RUN | 仅完整成功的同一次运行可推广 |
| RUN_RESULTS_DIGEST_MISMATCH | 运行结果文件与生成时摘要不一致 |
| EVIDENCE_DIGEST_MISMATCH / EVIDENCE_REQUEST_MISMATCH | 本地脱敏证据与请求/摘要不对应 |

HTTP 失败只记录异常类型、状态码与摘要，不记录异常消息中的路径、正文或密钥。HTTP status 与 body.errorCode 始终分开记录。
