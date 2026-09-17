# Productization profile v1：受限扫描配置与交付边界

日期：2026-09-15。任务：P2W-S1-01。状态：READY_FOR_REVIEW，等待审阅接受。
依据：DEMO-001 0.5.0 与基线 `3241f10804a899f8ec2b0bdb6512e1f6cd5e456a`。
本记录接入后续计划的范围配置；不修改运行时代码、生产角色矩阵或历史 ADR。

## 决策及原因

复用现有共享 pipeline、Layout IR 1.1、Writer、Review、Render，继续逐项产品化。
这里的 profile 指限定输入类别、内容来源、几何候选和调用约束的一组配置。
正常电子文字始终原生优先；扫描单栏默认延续 demo 的 Ovis 内容＋PP 几何，
因为现有 Replay 与上传已经共用该重建路径，适合在相同边界建立新文档基线。
该选择不构成 OCR 质量已达标或几何唯一权威结论。

| 输入/配置 | 内容与几何来源 | 当前边界 |
|---|---|---|
| 简单电子 PDF / native | PDFium 原生字符、字体、几何，普通配图整体保留 | 正常编码、单栏、水平、选择 1–3 页；模型调用 0 |
| 有限单栏扫描试卷 / ovis-pp | Ovis 正文/公式，PP 区域标签、行框、公式框等几何 | PP 的 block_content、rec_texts、rec_formula 不进入此配置正文；不泛化到任意扫描文档 |
| ovis | Ovis 独立内容与模型图标签 | 显式可选；缺正文精确 bbox 不伪造定位 |
| pp | 旧 PP-content 基线，保留其候选审阅路径 | 显式 `--content-provider pp`；不移除或自动替换 |
| Monkey | 按需增加几何/阅读顺序候选 | 不默认请求；当前可选入口不等于自动风险路由已实现 |

混合 PDF、低质隐藏层、多栏、旋转、复杂普通数据表格、复杂公式不属于此扫描配置的已确认范围。
当前 convert 仅 native/raster 二选一，自动区域 OCR 尚未接入。未知情况保留来源与审校项，
有可靠局部几何才局部降级，否则明确父区域/整页降级，不猜内容或伪造坐标。

## 与旧生产矩阵的关系

[生产约束](../24_PRODUCT_AND_MODEL_RULES.md)中的 PP 专项主候选、Ovis 按需复核仍是生产规范。
本记录把 demo 中 Ovis 主内容的差异限定在上述扫描 profile；不以该例外替换全部文档策略。
[ADR-006](../../adr/ADR-006-MULTI-CANDIDATE-GEOMETRY-UNTIL-GATE.md)已经 Gate B 复审并延续：
PP 与 Monkey 保留独立几何候选，下一复审结合 T0017 和代表性多页、多类型样本。
调用顺序不代表权威顺序；任何后续生产调整需要独立决策与证据，不倒改历史。

`pipeline.reconstruct` 中 Ovis 主结果缺失时保留源页并标记 PRIMARY_CONTENT_MISSING，
不会静默切换到 PP 正文；PP 布局关联失败保留 Ovis 内容并要求审校。
自动版与 reviewed 分开，候选、来源、选择理由和未知置信度继续保留。
普通表格的可编辑拓扑不能用无边框选项布局表抵充。

## 网络授权

本项 network_policy=offline，推理预算 0，服务探测 0。
计划接入不授权 FRP、模型服务或云配置修改。未来 live 仅在已登记输入、目标 endpoint、
profile、任务范围与本次预算获得授权后执行；包内阶段上限只是提案，不是本轮额度。
Native、Replay、导出不需要模型调用。未知/失败结果不隐式重试，不以新解析代码倒改封存 hash。

已有 demo 开发直连例外限定于 raster_bridge 与显式授权；浏览器只访问本机 backend。
正式 UI/Core 只连接目标 8100 网关。网关未部署是文档基线，本轮未探测其当前运行状态。
PP 冻结接口为 `/layout-parsing` JSON Base64，必填 `file`，图片 `fileType=1`；
仅消费几何不等于服务端不做识别，也不表示已部署独立检测端点。

## 三层交付与验收

| 层级 | 交付边界 | 当前结论 |
|---|---|---|
| Alpha | 本地开发环境 CLI＋网页，有限支持范围，新文档闭环与质量基线 | 原型已存在；S1 产品 Gate 未通过，S1-06 才冻结支持阈值 |
| Beta | 可安装、可靠本机应用；CLI＋网页可以先交付，含依赖、状态、缓存、安全等证据 | 尚待产品化，不能把开发目录或当前 wheel 当完整安装版 |
| Release | S4 跨平台分发，Tauri2＋React 薄桌面、资源/依赖、签名公证、许可证和 Office 验收 | 本轮未实现；缺平台证据不能承诺正式包 |

当前优先 macOS；保留 Windows 兼容与真实 Microsoft Word 打开、编辑、另存及视觉验收。
LibreOffice 渲染不等于 Word 验收，HTML 也不等于 DOCX 渲染。现有 499 项是历史测试记录，
不代表新 holdout、远端 CI、Windows 或 Release 通过。

详见[本轮报告](../../tasks/reports/P2W-S1-01_REPORT.md)与[计划映射](../development-plan/README.md)。
