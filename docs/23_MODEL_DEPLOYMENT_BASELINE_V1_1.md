# 23. 模型部署基线 V1.1

> 2026-09-09 本机接入更新：Mac 通过 FRP visitor 的 `127.0.0.1:9000/8000/8080` 访问现有服务，端口及模型职责不变；操作见 [本机调试](25_LOCAL_DEVELOPMENT.md)。下文历史探测证据不等同于本机验收。


文档版本：`1.1.0`
日期：`2026-08-28`
状态：**当前部署事实与目标架构对照**

## 重要说明

本文档明确区分三类内容：
- **当前部署事实**：已完成且可验证的部署状态
- **目标产品架构**：计划实现但尚未完成的架构
- **待 Gate 验证的假设**：需要通过 T0015/T0016/T0017 实测冻结的事项

不得将目标架构或待验证假设表述为已部署事实。

---

## 1. 运行边界

### 1.1 当前部署事实

#### Windows 11 客户端

- **桌面应用**：Tauri 2 + React + TypeScript（目标架构，T0001 已完成工具链初始化）
- **本地 Core**：Python 3.12 包（T0001 已初始化骨架）
  - PDF 原生解析（pdf-inspector + pypdfium2 / PDFium）
  - 页面渲染
  - Layout IR 1.1（Schema 已定义，实现待 T0007）
  - DOCX 生成（python-docx + lxml）
  - QA 与审校
- **不部署**：CUDA、vLLM、Paddle GPU、模型权重

#### Ubuntu 26 GPU 服务器

- **硬件**：NVIDIA RTX 5060 Ti 16GB
- **基础设施**：Docker Engine + Compose、NVIDIA Container Toolkit、systemd
- **运行内容**：所有模型推理（Paddle、Monkey、Ovis）

### 1.2 调用边界

**当前部署状态**：
- 端口 **9000/8000/8080** 已有服务运行
- 统一网关 8100 **尚未部署**（目标架构）

**目标架构**：
```
Tauri / React
  → Windows 本地 Core
    → Provider / Gateway Adapter
      → Ubuntu 模型服务
```

**重要约束**：
- UI 不得直接访问模型服务器
- Windows Core 只感知抽象能力，不感知具体模型端口

---

## 2. 当前模型清单

### 2.1 MonkeyOCRv2

- **对外模型名**：`MonkeyOCRv2`
- **协议**：OpenAI-compatible（`/v1/chat/completions`）
- **当前端口**：**9000**
- **可选加速**：DFlash（服务端透明，不是客户端独立模型）
- **客户端约束**：不得建立 `MonkeyOCRv2-DFlashAdapter`

**当前状态**：
- 服务在 **9000** 端口运行
- 客户端 Adapter 待 T0401 实现

### 2.2 OvisOCR2

- **对外模型名**：`ovis-ocr2`
- **协议**：OpenAI-compatible
- **当前端口**：**8000**

**职责**：
- 高风险内容完整性复核
- 复杂公式、表格的第二候选
- 整页 Markdown 序列化对照
- PP-OCRv6 与 MonkeyOCRv2 内容冲突时的第三证据

**不是**：
- 复杂页面几何主职责
- 默认每页调用的模型

**当前状态**：
- 服务在 **8000** 端口运行
- 客户端 Adapter 待 T0408 实现

### 2.3 PP-StructureV3 子模型

**当前端口**：**8080**

#### 全局与复杂版面

| 模型 | 用途 |
|---|---|
| PP-DocLayout_plus-L | 全局布局分析 |
| PP-DocBlockLayout | 块级布局 |

#### OCR

| 模型 | 用途 |
|---|---|
| PP-OCRv6_medium_det | 文字检测 |
| PP-OCRv6_medium_rec | 文字识别 |
| PP-LCNet_x1_0_textline_ori | 文本行方向 |

#### 表格

| 模型 | 用途 |
|---|---|
| PP-LCNet_x1_0_table_cls | 表格分类 |
| RT-DETR-L_wired_table_cell_det | 有线表格单元格检测 |
| RT-DETR-L_wireless_table_cell_det | 无线表格单元格检测 |
| SLANeXt_wired | 有线表格结构 |
| SLANet_plus | 表格结构增强 |

#### 公式

| 模型 | 用途 |
|---|---|
| PP-FormulaNet_plus-L | 公式识别 |

#### 按需预处理

| 模型 | 用途 |
|---|---|
| PP-LCNet_x1_0_doc_ori | 文档方向 |
| UVDoc | 文档去扭曲 |

#### 当前不进入 MVP 主流程

- 印章识别模型
- PP-Chart2Table

**处理策略**：图表和印章默认保留为图片，除非后续专项任务明确启用。

### 2.4 当前模型能力映射

Windows Core 应只感知抽象能力：

```
PaddleProvider
  ├─ full_pipeline
  ├─ layout_global
  ├─ layout_block
  ├─ text_ocr
  ├─ table_parse
  ├─ formula_parse
  ├─ orientation（按需，默认关闭）
  └─ unwarping（按需，默认关闭）

MonkeyProvider
  ├─ layout_complex
  └─ end_to_end

OvisProvider
  └─ content_review
```

**具体子模型组合由 Ubuntu 服务内部处理**。

**重要约束**：
- `orientation` 和 `unwarping` 当前服务端具备能力，但是否暴露独立远程 HTTP 端点仍为 **unknown**
- 默认关闭，仅在输入质量判断需要时启用
- 不得假定本地 PaddleX `create_model()` 等于远程 HTTP API

---

## 3. DFlash 客户端透明原则

### 3.1 当前部署事实

- DFlash 是服务端加速配置
- 对外模型名仍为 `MonkeyOCRv2`
- 客户端无需、也不应感知 DFlash 是否启用

### 3.2 架构约束

- **禁止**：建立独立的 `MonkeyOCRv2-DFlashAdapter`
- **禁止**：在配置中暴露 DFlash 细节
- **允许**：服务端内部通过 profile 选择是否启用 DFlash 加速

---

## 4. PP 子模型本地能力与远程 HTTP 能力的区别

### 4.1 本地能力（Ubuntu 服务器）

- 通过 PaddleX Python API 或 CLI 直接调用
- 可以单独加载和运行每个子模型
- 显存共享，按需加载

### 4.2 远程 HTTP 能力（当前状态）

**已知端点**：
- 端口 **8080** 已有服务运行

**HTTP 契约状态**：**✅ 已冻结（T0015 / P0-GATE-001A）**

实测结果（2026-08-29）：
- **端点路径**：`/layout-parsing`
- **HTTP Method**：`POST`
- **Transport**：`application/json`（JSON + Base64）
- **文件字段**：`file`（Base64 编码字符串）
- **文件类型字段**：`fileType`（0=PDF, 1=图片）
- **OpenAPI**：服务未暴露 `/openapi.json`

**请求示例**：
```json
{
  "file": "<base64_encoded_image>",
  "fileType": 1
}
```

**成功响应字段**：
- `logId`：请求 ID
- `result.layoutParsingResults`：布局解析结果列表
- `result.dataInfo`：输入文件元信息
- `errorCode`：错误码（0 表示成功）
- `errorMsg`：错误消息

**详细契约**：见 `specs/discovered-model-contracts.json`

### 4.3 当前部署事实 vs 假设

| 内容 | 状态 |
|---|---|
| PP 服务在 **8080** 运行 | ✅ 已部署 |
| 具体 HTTP 端点和 Schema | ✅ 已冻结（T0015） |
| 每个子模型有独立 HTTP 端点 | ❌ 未验证，目前使用聚合端点 |

---

## 5. 临时权威关系（Gate B 完成前）

### 5.1 当前权威优先级（临时）

在 **T0016 / P0-GATE-001B** 完成前，采用以下临时权威关系：

#### 文字内容

```
电子 PDF 有效原生文字（最高权威）
  > PP-OCRv6 高置信度结果
  > 多模型一致结果
  > MonkeyOCRv2 单独内容
  > OvisOCR2 单独内容
```

#### 几何与阅读顺序

```
有效 PDF 原生对象几何
  > Geometry Arbitration {
      PP-DocLayout_plus-L / PP-DocBlockLayout 候选,
      MonkeyOCRv2 布局候选
    }
  > 规则推断
```

**重要**：
- PP 新版布局和 MonkeyOCRv2 **均为独立候选，不预设永久唯一权威**
- 调用顺序不代表权威顺序
- 所有选择必须保存 `geometry_source`、`candidate_ids`、`selection_reason`、`engine_confidence`、`system_confidence`

#### 表格

```
PP-StructureV3（主候选）
  > OvisOCR2 复核候选
  > MonkeyOCRv2 候选
  > 区域图片降级
```

#### 公式

```
PP-FormulaNet
  > OvisOCR2 复核候选
  > MonkeyOCRv2 候选
  > 原公式图片
```

### 5.2 Gate 完成后的权威确定

Gate B/C 完成后，根据实测结果决定是否形成新的终局 ADR。

---

## 6. 当前已知端点状态

### 6.1 已验证服务

**当前直接模型服务**：

| 端口 | 服务 | 状态 |
|---:|---|---|
| 9000 | MonkeyOCRv2 | ✅ 运行中 |
| 8000 | OvisOCR2 | ✅ 运行中 |
| 8080 | PP-StructureV3 | ✅ 运行中 |

**目标统一网关**：

| 端口 | 服务 | 状态 |
|---:|---|---|
| 8100 | 统一网关 | ❌ **尚未部署** |

**历史/待验证端口**：
- 8102 / 8104 / 8106：早期目标架构设计或历史方案，**不是当前部署事实**，只能在 `CHANGELOG.md`、已标记 `Historical/Superseded` 的 ADR、或迁移对照表中出现

### 6.2 目标架构

**统一网关 8100 的职责**：
- API Key 鉴权
- 来源 IP 限制
- 请求队列
- 任务级超时
- 统一错误码
- 统一结果 Schema
- 模型版本和哈希回传

**当前状态**：统一网关架构已设计，但尚未实现和部署。

**当前直接服务访问**（Gate 阶段允许）：
- MonkeyOCRv2：`http://MODEL_SERVER_IP:9000`
- OvisOCR2：`http://MODEL_SERVER_IP:8000`
- PP-StructureV3：`http://MODEL_SERVER_IP:8080`

---

## 7. 未冻结事项

以下事项必须通过 Gate 任务实测验证后才能冻结：

### 7.1 Gate A（T0015）

- [x] PP 完整流水线端点 → `/layout-parsing`
- [x] PP Transport → `json_base64`
- [x] PP 请求参数和响应 Schema → 已冻结
- [x] Monkey 和 Ovis 的 `/v1/models` 响应 → 已验证
- [x] Multipart 与 JSON-Base64 两种上传方式的差异 → 使用 JSON-Base64

### 7.2 Gate B（T0016）

- [ ] JPG/PNG 输入一致性
- [ ] 数学试卷几何回归结果
- [ ] PP 新版布局 vs Monkey 布局的几何质量对比
- [ ] 决定是否形成新的几何权威 ADR

### 7.3 Gate C（T0017）

- [ ] 旋转检测与纠正能力
- [ ] UVDoc 文档去扭曲能力
- [ ] 多栏布局处理能力
- [ ] 有线/无线表格检测能力
- [ ] 公式密集页处理能力

---

## 8. Gate A/B/C 决策点

### 8.1 T0015 / P0-GATE-001A：服务契约发现

**目标**：冻结 HTTP 契约

**决策点**：
- 选择 PP 端点和 Transport
- 冻结请求/响应 Schema
- 确认模型版本和 revision

**阻塞**：
- 真实模型 HTTP 契约固化
- 模型 Adapter 集成
- PP Transport/Schema
- 模型路由集成

**不阻塞**：
- T0002–T0009 中模型无关部分
- P1 纯电子 PDF MVP
- 正常电子 PDF 的零模型调用路径

### 8.2 T0016 / P0-GATE-001B：JPG/PNG 与数学试卷回归

**目标**：验证图像输入质量和几何能力

**决策点**：
- JPG/PNG 默认策略
- PP 新版布局 vs Monkey 几何质量对比
- 是否形成新的几何权威 ADR

**阻塞**：
- 复杂几何仲裁策略固化
- JPG/PNG 默认策略确定

### 8.3 T0017 / P0-GATE-001C：专项能力矩阵

**目标**：验证预处理和专项能力

**决策点**：
- 方向检测启用策略
- 展平启用策略
- 多栏处理策略
- 表格类型路由
- 公式专项路由

**阻塞**：
- 方向/展平/多栏/表格/公式专项路由策略

---

## 9. 配置和秘密管理

### 9.1 当前配置结构

**Windows 应用配置以能力为中心**，不直接编排 15 个 PP 子模型名。

**能力键**：
```yaml
model_policy:
  paddle.full_pipeline:
    endpoint_path: ""  # UNRESOLVED - 待 T0015 验证
    transport: auto    # UNRESOLVED - 待 T0015 验证
  paddle.layout_global: auto
  paddle.layout_block: auto
  paddle.text_ocr: auto
  paddle.table_parse: auto
  paddle.formula_parse: auto
  paddle.orientation:
    default_enabled: false
  paddle.unwarping:
    default_enabled: false
  monkey.layout_complex: monkeyocrv2-b-parsing
  monkey.end_to_end: monkeyocrv2-b-parsing
  ovis.content_review: ovis-ocr2
```

### 9.2 秘密管理

- 真实 IP、API Key、用户名、密码**仅存于** `.env.local`
- `.env.local` 已被 `.gitignore` 忽略
- 仓库中 `.env.example` 和 `config/example.env` 仅含占位符
- 不得在任何源码、日志或 Layout IR 中写入 API Key

---

## 10. 当前部署与目标统一网关架构的区别

### 10.1 当前部署状态

```
Windows 客户端（目标架构骨架已初始化）
  │
  └─ 尚未连接模型服务（需要开发 Model Gateway Client）

Ubuntu 模型服务器
  ├─ 9000: MonkeyOCRv2（运行中）
  ├─ 8000: OvisOCR2（运行中）
  └─ 8080: PP-StructureV3（运行中）
```

### 10.2 目标统一网关架构

```
Windows Core
  │
  └─ Model Gateway Client
       │
       ▼
    统一网关 :8100（尚未部署）
       ├─ 路由到 8080 (Paddle)
       ├─ 路由到 8000 (Ovis)
       └─ 路由到 9000 (Monkey)
```

### 10.3 关键区别

| 方面 | 当前状态 | 目标架构 |
|---|---|---|
| 统一网关 8100 | ❌ 未部署 | ✅ 计划实现 |
| 当前服务端口 | 9000/8000/8080 | 统一网关代理 |
| 客户端直连模型服务 | ⚠️ Gate 验证阶段允许 | ❌ 生产环境禁止 |
| Windows Core 是否感知模型端口 | ⚠️ Gate 阶段需要 | ❌ 仅感知抽象能力 |
| API Key 管理 | 直接传给各服务 | 统一网关鉴权 |

### 10.4 迁移路径

1. **Gate 阶段（T0015-T0017）**：允许直连 9000/8000/8080 进行契约验证
2. **Adapter 实现阶段（T0401 等）**：仍可直连，但需为统一网关预留接口
3. **生产就绪阶段（T0708）**：实现并部署统一网关 8100

---

## 11. 模型名称对照（已完成迁移）

以下名称已在活动文档中更新，仅在 `CHANGELOG.md`、`ADR-003` 历史正文、或迁移对照表中出现：

| 历史名称 | 当前部署 | 文档状态 |
|---|---|---|
| PP-DocLayout-M | PP-DocLayout_plus-L / PP-DocBlockLayout | ✅ 已更新 |
| PP-OCRv6 Small | PP-OCRv6_medium_det/rec | ✅ 已更新 |
| PP-FormulaNet-S | PP-FormulaNet_plus-L | ✅ 已更新 |
| Monkey 唯一几何权威 | PP 和 Monkey 均为候选 | ✅ ADR-003 已标记 Superseded |

---

## 12. 下一步行动

1. **T0014（本文档）**：完成文档和配置对齐
2. **T0015 / P0-GATE-001A**：服务契约发现
3. **T0016 / P0-GATE-001B**：JPG/PNG 与数学试卷回归
4. **T0017 / P0-GATE-001C**：专项能力矩阵
5. **并行路径**：T0002-T0009 模型无关部分、P1 纯电子 PDF MVP

---

## 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.1.0 | 2026-08-28 | 初始版本：记录当前部署事实（9000/8000/8080）、目标架构和待验证事项 |