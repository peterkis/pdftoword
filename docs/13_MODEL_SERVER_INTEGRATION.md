# 13. GPU 模型机集成

## 1. 网络

主应用配置：

```text
MODEL_GATEWAY_BASE_URL=http://MODEL_SERVER_IP:8100
MODEL_GATEWAY_API_KEY=...
```

生产内网优先 HTTPS。模型机防火墙只允许指定客户端 IP。

## 2. 端口

**当前直接服务**：

| 端口 | 服务 | Gate 阶段直连 |
|---:|---|---|
| 9000 | MonkeyOCRv2 | 允许 |
| 8000 | OvisOCR2 | 允许 |
| 8080 | PP-StructureV3 | 允许 |

**目标架构**：

| 端口 | 服务 | 状态 |
|---:|---|---|
| 8100 | 统一模型网关 | 尚未部署 |

**历史端口**（V1.0 设计，已废弃）：
- 历史 8102 / 8104 / 8106：早期目标架构设计，**不是当前部署事实**

## 3. 逻辑接口

- `POST /v1/layout/fast`
- `POST /v1/layout/complex`
- `POST /v1/ocr/text`
- `POST /v1/parse/table`
- `POST /v1/parse/formula`
- `POST /v1/review/content`
- `GET /v1/health`
- `GET /v1/models`

完整契约见 `specs/model-gateway-contract.md`。

## 4. 任务语义

- 上传页面或区域图像，不上传任意文件路径；
- 元数据包含 PDF bbox、像素尺寸和输入哈希；
- 网关返回模型版本、耗时、队列时间和标准化结果；
- 支持幂等键；
- 允许客户端取消，但服务端仅在安全点取消；
- 超时后客户端可查询幂等结果，避免重复推理。

## 5. 16GB GPU 注意

- Paddle 专项服务可按需加载；
- Monkey 和 Ovis 不默认高显存并发；
- 模型网关实施队列和 profile；
- 客户端限制复杂模型并发为 1；
- DFlash 作为可选优化；
- 显存不足时不得无限自动重试。

## 6. 降级

- 8100 不可达：原生链路继续；
- Monkey 失败：PP 快速布局 + Issue；
- Ovis 失败：跳过复核；
- Paddle 专项失败：图片降级或作业待重试；
- 所有失败必须保留请求哈希和错误码，不记录图像正文。
