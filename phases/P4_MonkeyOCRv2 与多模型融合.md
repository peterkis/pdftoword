# P4 — MonkeyOCRv2 与多模型融合

## 阶段目标

接入 MonkeyOCRv2 复杂版面主链路，加入 Ovis 内容复核和候选融合。

## 具体任务

### T0401 MonkeyOCRv2 网关 Adapter

- 优先级：`P0`
- 依赖：T0010, T0006
- 目标：实现 layout.complex 请求、鉴权、超时和幂等。
- 交付：
  - MonkeyAdapter
  - mock fixtures
- 验收：
  - 只通过8100
  - 原始响应引用保存

### T0402 Monkey 标签与内容归一化

- 优先级：`P0`
- 依赖：T0401
- 目标：实现标签映射、未知标签和内容格式解析。
- 交付：
  - MonkeyNormalizer
  - mapping config
- 验收：
  - 未知标签不丢
  - HTML/LaTeX安全处理

### T0403 Monkey 坐标归一化

- 优先级：`P0`
- 依赖：T0401, T0102
- 目标：归一化/像素/区域/PDF point 变换。
- 交付：
  - MonkeyCoordinateMapper
- 验收：
  - 属性测试通过
  - 越界产生Issue

### T0404 复杂页升级策略

- 优先级：`P0`
- 依赖：T0202, T0401
- 目标：基于复杂度、冲突、文档模式和准确档调用 Monkey。
- 交付：
  - ComplexLayoutPolicy
- 验收：
  - 简单页不调用
  - 决策可解释

### T0405 几何权威仲裁

- 优先级：`P0`
- 依赖：T0402, T0403, T0203
- 目标：原生对象、Monkey、PP Layout 和规则之间选择 geometry_source。
- 交付：
  - GeometryArbitrator
- 验收：
  - PP 与 Monkey 作为并列候选
  - 选择理由可解释
  - 不得无实测证据固化固定主导关系
  - 原生有效几何不被无证据覆盖

### T0406 Monkey End-to-End 内容候选

- 优先级：`P0`
- 依赖：T0008, T0402
- 目标：将 Monkey 内容加入候选但不直接选择。
- 交付：
  - Candidate importer
- 验收：
  - engine_confidence为空时保持null
  - 来源版本完整

### T0407 系统置信度计算

- 优先级：`P0`
- 依赖：T0405, T0406
- 目标：实现几何、覆盖、一致性和风险综合评分。
- 交付：
  - SystemConfidenceCalculator
  - weight config
- 验收：
  - 与模型置信度分离
  - 权重版本化

### T0408 OvisOCR2 内容复核 Adapter

- 优先级：`P0`
- 依赖：T0010, T0006
- 目标：实现 review.content，解析 Markdown/HTML/LaTeX 候选。
- 交付：
  - OvisReviewer
  - safe parser
- 验收：
  - 不承担geometry_source
  - 只按策略调用

### T0409 复核触发和冲突融合

- 优先级：`P0`
- 依赖：T0308, T0407, T0408
- 目标：文字、表格、公式和覆盖冲突时调用 Ovis 并融合。
- 交付：
  - ReviewPolicy
  - FusionEngine v2
- 验收：
  - 候选全部保留
  - 低可信可图片降级

### T0410 GPU 队列与客户端背压

- 优先级：`P0`
- 依赖：T0010, T0401, T0408
- 目标：限制 Monkey/Ovis 并发、处理429/503、退避。
- 交付：
  - Backpressure client
  - metrics
- 验收：
  - 不并发轰炸16GB GPU
  - 取消可传播

### T0411 Monkey/Ovis 影子模式

- 优先级：`P0`
- 依赖：T0409, T0309
- 目标：同一黄金集运行 A/B/C/D 路线并比较。
- 交付：
  - Shadow runner
  - comparison report
- 验收：
  - 不影响主输出
  - 指标和显存/延迟记录

### T0412 复杂页回归门禁

- 优先级：`P0`
- 依赖：T0411
- 目标：建立多栏、拍照、题图密集和低质量复杂页门禁。
- 交付：
  - Golden set P4
  - release thresholds
- 验收：
  - 阅读顺序/几何不低于基线
  - 无新增静默纠正

## 阶段退出门槛

- [ ] Monkey 经 8100 网关调用
- [ ] 坐标和标签归一化通过
- [ ] engine/system confidence 分离
- [ ] 复杂页阅读顺序改善
- [ ] Ovis 只按策略复核
- [ ] 影子评测报告完成
