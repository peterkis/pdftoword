# 05. PDF 页面与区域路由

## 1. 页面分类不是文档分类的附属字段

每页独立计算：

- 原生文字有效率；
- 原生文字视觉覆盖率；
- 替换字符/乱码比例；
- 图片面积比例；
- 隐藏文字与背景图重叠；
- 文本顺序异常；
- 页面对象数量；
- 多栏、表格、公式、题图密度；
- 旋转、倾斜和拍照特征。

## 2. 页面类型

### native

原生文字有效、覆盖合理、无明显隐藏层冲突。

### mixed

原生文字有效，但存在需要识别或结构分析的栅格区域。

### scanned

页面主要由扫描图构成，无有效原生文字。

### hidden_text_scan

扫描图上叠加隐藏 OCR 文字层。必须比较质量并去重。

### broken_encoding

存在文字对象，但 Unicode、顺序或字体映射不可用。

### image_dominant

主要内容是图片/图形，文字较少；不得自动把所有图片视为栅格文字。

### unknown

证据不足，进入保守路线并创建问题。

## 3. 页面路由

```text
native
  ├─ 简单：原生提取
  └─ 复杂：PP-DocLayout_plus-L / PP-DocBlockLayout；必要时 Monkey 几何候选

mixed
  ├─ 原生文字保留
  ├─ 普通图保留
  ├─ 栅格文字 → PP-OCRv6
  ├─ 表格 → PP-StructureV3
  ├─ 公式 → PP-FormulaNet
  └─ 复杂组合 → Monkey

scanned
  ├─ fast/balanced：PP-DocLayout_plus-L / PP-DocBlockLayout + 专项模型
  └─ accurate：PP 与 Monkey 几何仲裁 + 专项模型精识别

hidden_text_scan
  ├─ 隐藏层质量高：保留并对齐
  └─ 质量差：OCR 替换并去重

broken_encoding
  ├─ 正常区域保留
  └─ 损坏区域局部 OCR
```

## 4. Monkey 调用条件

满足任一条件可调用 `monkey.layout_complex`：

- 多栏阅读顺序冲突；
- 题目、选项和图片密集；
- PP-DocLayout_plus-L / PP-DocBlockLayout 低可信或块大量重叠；
- 页面类型为拍照、倾斜或变形；
- 表格/公式/图片相互嵌套；
- 快速布局和原生对象几何冲突；
- 高精度模式下的纯扫描页；
- 结构 QA 发现疑似遗漏或顺序异常。

**重要**：Monkey 为几何候选，不预设永久唯一权威（见 ADR-006）。

## 5. Ovis 复核条件

- 表格候选冲突；
- 公式候选冲突；
- Monkey 与 PP-OCR 内容差异超过阈值；
- 关键数字、单位、上下标存在风险；
- 整页内容覆盖明显不足；
- 用户选择“高精度复核”。

## 6. 禁止路由

- `native` 页面默认整页 OCR；
- 普通插图默认 `replace_image`；
- Monkey 每页默认调用；
- Ovis 每页默认调用；
- 低可信表格/公式直接生成可编辑对象；
- 模型失败时丢弃原始区域图像。
