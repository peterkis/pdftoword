# 08. MonkeyOCRv2 集成规范

## 重要说明

本文档已根据 V1.1 部署基线更新。几何权威关系已变更为临时策略（不预设永久权威），详见 `adr/ADR-006-MULTI-CANDIDATE-GEOMETRY-UNTIL-GATE.md`。

## 1. 选型

默认模型：`zenosai/MonkeyOCRv2-B-Parsing`。

可选加速：`MonkeyOCRv2-B-Parsing-DFlash`。DFlash 只作为部署优化，不作为业务契约依赖；首个版本应先支持普通服务。

不使用：

- 仅视觉编码器 `MonkeyOCRv2-B` 直接承担解析；
- `MonkeyOCRv2-B-Und` 文档问答模型用于 PDF 转 Word主流程。

## 2. 服务位置

**当前部署**：
```text
主应用 → Gateway :8100（目标架构，尚未部署）
或
主应用 → Monkey Service :9000（当前直接服务，Gate 阶段允许）
```

**端口对照**：
- 当前直接服务：`http://MODEL_SERVER_IP:9000`
- 目标统一网关：`http://MODEL_SERVER_IP:8100`（尚未部署）
- 旧设计端口：8106（**不是当前部署事实**）

主应用不得依赖 Monkey 官方 FastAPI、vLLM 或提示词细节。

## 3. 业务任务

### layout

只需要类别、坐标和阅读顺序。用于复杂页面几何候选。

### end_to_end

需要类别、坐标、阅读顺序和内容候选。用于扫描复杂页初始解析，但内容仍需专项模型复核。

## 4. 标准请求

必须包含：

- `request_id`；
- `job_id`；
- `page_index`；
- `region_id` 可为空；
- `task`；
- 图像；
- 原始图像像素尺寸；
- 对应 PDF bbox；
- 文档类型提示；
- 语言提示；
- 输入 SHA-256；
- 模型 revision 请求或默认策略。

## 5. 标准响应

每个块：

- `raw_label`；
- `normalized_type`；
- `bbox_normalized`；
- `bbox_pixel`；
- `bbox_pdf_pt`；
- `reading_order`；
- `raw_content`；
- `content_format`；
- `engine_confidence`：可为空；
- `model_id`、`model_revision`、`service_version`；
- `raw_response_ref`。

## 6. 归一化

- `[0,1000]` 坐标按原始输入尺寸映射为像素；
- 再按裁剪区域映射到 PDF point；
- 处理旋转和页面裁剪框；
- bbox 越界、零面积和严重重叠必须产生 Issue；
- 未知标签保留为 `unknown`，不得丢弃。

## 7. 置信度

如果模型原始协议没有概率：

```text
engine_confidence = null
```

系统置信度可由以下构成：

- bbox 合法性；
- 块覆盖率；
- 重叠/空洞；
- 与 PP-DocLayout_plus-L / PP-DocBlockLayout 一致性；
- 与原生对象几何一致性；
- 阅读顺序规则；
- 与专项模型内容一致性；
- 回渲染结果。

不得将经验分数冒充模型概率。

## 8. 使用边界（临时策略，见 ADR-006）

**重要变更**：MonkeyOCRv2 现为**几何候选**，不预设永久唯一权威。

调用条件：
- 多栏、拍照、倾斜、题图密集
- 快速布局低可信
- 复杂扫描页
- 准确模式下的复杂布局

不调用：
- 普通电子单栏
- 简单原生报告
- 仅需单个文字框 OCR 的区域

**Gate B 验证**：T0016 将对比 PP 新版布局与 MonkeyOCRv2 的几何质量，决定是否形成新的终局 ADR。

## 9. 安全注意

- 如模型需要 `trust_remote_code=True`，锁定 revision；
- 在隔离容器运行；
- 禁止模型容器访问互联网；
- 只读挂载模型目录；
- 禁止上传任意路径；
- 保存模型和代码哈希。
