# P2 — 混合 PDF 与局部 OCR

## 阶段目标

完成页面/区域分流、PP 新版布局、局部 PP-OCRv6、隐藏层去重和配图保留。

**重要说明**：PP 模型已升级为新版本，详见 `docs/23_MODEL_DEPLOYMENT_BASELINE_V1_1.md`。旧任务标题中的模型名称保留为历史记录。

## 具体任务

### T0201 PP 新版布局网关 Adapter

- 优先级：`P0`
- 依赖：T0010, T0102
- 目标：实现 layout.fast / layout.global / layout.block 任务和归一化。
- 交付：
  - FastLayoutAdapter
  - label map
- 验收：
  - 通过统一网关或当前直接服务
  - bbox 转换正确
  - 未知标签保留
- **历史任务标题**：PP-DocLayout-M 网关 Adapter（旧模型名）

### T0202 页面复杂度与路由评分

- 优先级：`P0`
- 依赖：T0104, T0201
- 目标：计算何时 native、fast、complex、specialist。
- 交付：
  - Router
  - RoutingDecision
- 验收：
  - 决策可解释
  - 配置版本写入报告

### T0203 区域切分与覆盖合并

- 优先级：`P0`
- 依赖：T0105, T0106, T0201
- 目标：融合原生对象、PP Layout 和图片对象形成区域。
- 交付：
  - RegionPartitioner
  - overlap resolver
- 验收：
  - 无明显空洞/重复
  - 普通图不误判 raster_text

### T0204 高质量区域裁剪

- 优先级：`P0`
- 依赖：T0102, T0203
- 目标：按任务选择 DPI、padding、颜色和去旋转。
- 交付：
  - RegionCropper
  - image metadata
- 验收：
  - 裁剪可逆映射
  - 不过度裁掉上下标

### T0205 PP-OCRv6_medium Adapter

- 优先级：`P0`
- 依赖：T0010, T0204
- 目标：实现 ocr.text、文字框、行和置信度。
- 交付：
  - TextOcrAdapter
  - normalizer
- 验收：
  - 中文英文正常
  - 置信度保留
  - 无自动纠错
- **历史任务标题**：PP-OCRv6 Small Adapter（旧模型名）

### T0206 OCR 坐标归一化

- 优先级：`P0`
- 依赖：T0204, T0205
- 目标：像素坐标映射回页面 PDF point。
- 交付：
  - CoordinateMapper tests
- 验收：
  - 旋转/裁剪/缩放属性测试通过

### T0207 隐藏文字层检测与去重

- 优先级：`P0`
- 依赖：T0104, T0205, T0206
- 目标：对原生/OCR 几何和内容匹配。
- 交付：
  - HiddenTextResolver
  - supersedes relations
- 验收：
  - 无双层重复
  - 损坏原生可被有证据替换

### T0208 栅格文字替换为可编辑段落

- 优先级：`P0`
- 依赖：T0205, T0207
- 目标：将 raster_text OCR 内容聚合并插入 IR。
- 交付：
  - RasterTextAssembler
- 验收：
  - 与周围原生顺序正确
  - 原裁剪图保留

### T0209 普通配图与内部文字元数据

- 优先级：`P0`
- 依赖：T0203, T0205
- 目标：区分 figure_with_internal_text 和 raster_text。
- 交付：
  - FigureClassifier rules
  - metadata OCR policy
- 验收：
  - 实验图不拆
  - 内部文字不进入正文重复

### T0210 混合页面融合

- 优先级：`P0`
- 依赖：T0207, T0208, T0209
- 目标：合并原生、OCR、图片和布局证据。
- 交付：
  - MixedFusion v1
- 验收：
  - 来源完整
  - 无重复块
  - 阅读顺序合理

### T0211 混合 PDF 端到端与回归

- 优先级：`P0`
- 依赖：T0210, T0110
- 目标：完成混合文档作业和黄金集。
- 交付：
  - Pipeline mixed
  - Golden set P2
- 验收：
  - 局部OCR准确
  - 配图关系保留
  - 不全文OCR

## 阶段退出门槛

- [ ] 混合 PDF 原生文字未被替换
- [ ] 局部扫描文字可编辑
- [ ] 普通配图整体保留
- [ ] 隐藏层无重复
- [ ] 所有区域有来源和路由记录
