# 19. 已确认决策

## 当前决策（V1.1，2026-08-28 更新）

1. Word 允许自然重分页。
2. 有效原生文字优先于 OCR/VLM。
3. 普通配图、几何图、实验装置图、化学结构图整体保留。
4. 混合 PDF 使用区域级 OCR。
5. Layout IR 是唯一主中间模型。
6. PP 新版布局（PP-DocLayout_plus-L / PP-DocBlockLayout）负责全局和块级布局分析。
7. **MonkeyOCRv2-B-Parsing 为复杂页几何候选，不预设永久唯一权威**（见 ADR-006）。
8. PP-OCRv6_medium 负责细粒度文字主结果。
9. RT-DETR-L + SLANeXt/SLANet_plus 负责表格主结果。
10. PP-FormulaNet_plus-L 负责公式主结果。
11. OvisOCR2 负责高风险内容复核。
12. Monkey/Ovis 原始输出不得直接进入 DOCX Builder。
13. 模型机统一通过 8100 网关暴露（目标架构，尚未部署）。
14. Monkey 无原始概率时不得伪造模型置信度。
15. 低可信内容优先图片降级。
16. 不允许模型静默纠正试题内容。
17. 第一开发里程碑不依赖模型。

## 历史决策（已替换）

**原决策 6**：PP-DocLayout-M 负责快速布局。
- **状态**：已升级为 PP-DocLayout_plus-L / PP-DocBlockLayout

**原决策 7**：MonkeyOCRv2-B-Parsing 负责复杂页几何和阅读顺序。
- **状态**：已修订，现为几何候选（见 ADR-006）

## 部署基线变更

详见 `docs/23_MODEL_DEPLOYMENT_BASELINE_V1_1.md`：
- 当前直接服务：Monkey :9000 / Ovis :8000 / PP :8080
- 目标统一网关：8100（尚未部署）
- 旧设计端口：8102 / 8104 / 8106（不是当前部署事实）
