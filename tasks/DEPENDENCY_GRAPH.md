# 任务依赖主链

```text
P0 契约
  ├─ T0001（已完成）
  ├─ T0014（基线文档对齐）
  ├─ T0015（Gate A：服务契约发现）
  │   ├─ T0016（Gate B：几何回归）
  │   └─ T0017（Gate C：能力矩阵）
  ├─ T0002-T0009（模型无关任务，可并行）
  └─ T0010-T0013（模型网关相关，部分阻塞）
      ↓
P1 原生电子 PDF
  ↓
P2 混合 PDF / PP Layout / PP OCR
  ↓
P3 表格 / 公式 / 扫描专项
  ↓
P4 Monkey / Ovis / Fusion
  ↓
P5 Question / Figure / DOCX
  ↓
P6 QA / Review
  ↓
P7 性能 / 安全 / 发布
```

## Gate 阻塞关系

**T0015 阻塞**：
- 模型 HTTP 契约固化
- PP Transport / Schema
- 生产模型 Adapter 集成
- 模型路由集成

**T0015 不阻塞**：
- T0002-T0009 模型无关任务
- P1 纯电子 PDF MVP
- 正常电子 PDF 的零模型调用路径

**T0016 阻塞**：
- 复杂几何仲裁策略
- JPG/PNG 默认策略

**T0017 阻塞**：
- orientation / unwarping 启用策略
- 多栏布局处理策略
- 表格类型路由
- 公式专项路由

## 可并行

- P0 的 CI、日志、Schema、Mock；
- P3 的表格和公式 Adapter；
- P5 的题号解析与图片去重；
- P6 的 DOCX 完整性和 Issue 规则。

## 不得并行绕过

- 没有 IR 1.1 就写 Fusion；
- 没有基础电子 DOCX 就写复杂模型；
- 没有专项模型就让 Monkey/Ovis 直接成为内容权威；
- 没有题图关系就使用浮动图片”凑位置”。
