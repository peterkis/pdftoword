# 11. 题目、图片和图题关系

## 1. 目标

PDF 页坐标只是输入。Word 中必须形成稳定逻辑结构：

```text
Section
  └─ MajorQuestion
      └─ Question
          ├─ Stem
          ├─ Figure
          ├─ Caption
          ├─ SubQuestion
          └─ Option
```

## 2. 题号识别

支持中文、英文、全角、半角和圈号；结合字体、缩进、纵向位置和阅读顺序，避免将公式序号误判为题号。

## 3. 图片候选

图片来源可为：

- PDF 原图；
- 矢量区域渲染；
- Monkey Picture Block；
- PP Layout 图像区域；
- 扫描页裁剪。

多个检测框应通过 IoU 和来源融合为同一资产，不得重复输出。

## 4. 锚定评分

权重集中配置。核心证据：

- 图片位于当前题起始和下一题起始之间；
- 同栏；
- 与题干距离；
- 阅读顺序；
- “如下图”“according to the figure”等提示；
- 图题；
- 图片不得跨越下一题边界；
- 子题范围。

## 5. Word 输出

- below：题干后行内图片；
- right：无边框 1×2 表格；
- option_grid：1×N 或 2×2；
- caption：和图片同容器；
- complex_local_group：整体区域图片。

## 6. 跨页

若题干和图片跨 PDF 页：

- 通过 `continuation_of` 连接；
- Word 可自然合并；
- 保留原页来源；
- 不因为原分页强制拆开。

## 7. 不确定处理

低于自动阈值时禁止强行锚定。创建 Issue，审校界面显示当前题、下一题、图片和候选分数。
