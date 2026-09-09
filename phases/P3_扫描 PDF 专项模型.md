# P3 — 扫描 PDF 专项模型

## 阶段目标

完成纯扫描页面的文字、表格、公式和图片分区处理，以及安全降级。

## 具体任务

### T0301 PP-OCRv6 Medium 升级策略

- 优先级：`P0`
- 依赖：T0205, T0008
- 目标：低置信度/高风险区域升级复识别。
- 交付：
  - EscalationPolicy
  - candidate compare
- 验收：
  - 旧候选保留
  - 升级次数有限

### T0302 PP-StructureV3 表格 Adapter

- 优先级：`P0`
- 依赖：T0010, T0204
- 目标：实现表格识别、单元格、跨度和坐标。
- 交付：
  - TableAdapter
  - table normalizer
- 验收：
  - 简单/合并表格正确
  - 错误可降级

### T0303 表格质量与图片降级

- 优先级：`P0`
- 依赖：T0302
- 目标：计算网格、覆盖和内容质量，决定 native/review/image。
- 交付：
  - TableQuality
  - fallback asset
- 验收：
  - 低可信不强制输出表格
  - 原因记录

### T0304 PP-FormulaNet Adapter

- 优先级：`P0`
- 依赖：T0010, T0204
- 目标：公式区域识别和候选。
- 交付：
  - FormulaAdapter
  - LaTeX result
- 验收：
  - 原图保留
  - 异常不吞掉

### T0305 公式 OMML 与回渲染

- 优先级：`P0`
- 依赖：T0304
- 目标：LaTeX/MathML/OMML 转换和视觉验证。
- 交付：
  - FormulaConverter
  - render comparator
- 验收：
  - 通过才输出OMML
  - 失败自动图片

### T0306 化学与复杂图形保留规则

- 优先级：`P0`
- 依赖：T0209, T0304
- 目标：区分纯文本化学式、结构图、装置图和流程图。
- 交付：
  - DomainFigurePolicy
  - fixtures
- 验收：
  - 结构图不误转公式
  - 方程式可处理

### T0307 扫描页快速流水线

- 优先级：`P0`
- 依赖：T0201, T0301, T0303, T0305, T0306
- 目标：PP Layout → OCR/Table/Formula/Figure。
- 交付：
  - ScannedFastPipeline
- 验收：
  - 正文可编辑
  - 图片完整
  - 区域无重复

### T0308 扫描页专项融合

- 优先级：`P0`
- 依赖：T0303, T0305, T0307
- 目标：按任务权威合并表格、公式、文字和图。
- 交付：
  - SpecialistFusion
- 验收：
  - 表格/公式选择规则可解释

### T0309 扫描 PDF 回归集

- 优先级：`P0`
- 依赖：T0308, T0012
- 目标：建立扫描、倾斜、公式、表格和中英样本。
- 交付：
  - Golden set P3
  - 指标报告
- 验收：
  - 关键指标基线记录
  - 降级正确

## 阶段退出门槛

- [ ] 扫描正文可编辑
- [ ] 表格可重建或图片降级
- [ ] 公式可 OMML 或图片降级
- [ ] 图形区域不被误拆
- [ ] 专项模型失败不破坏作业
