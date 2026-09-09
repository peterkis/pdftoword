# 06. 识别与转换详细规则

## 1. 总原则

1. 先判断来源，再判断内容。
2. 先保留证据，再选择最终候选。
3. 先恢复逻辑结构，再生成 Word。
4. 不确定时保图，不猜测。
5. 模型只识别，不擅自改写。

## 2. 原生文字规则

有效原生文字必须保留：

- 原字符；
- 字体和字号；
- 粗体、斜体、下划线、颜色；
- 上标、下标；
- 坐标和阅读顺序；
- 原始对象引用。

可判定为不可用的证据：

- Unicode 替换字符过多；
- CID/字体映射产生乱码；
- 视觉文字区域与原生框覆盖严重不一致；
- 字符顺序异常；
- 隐藏文字层重复或错位；
- 大量不可见字符；
- 同一视觉位置存在重复文本对象。

不得仅因为 OCR 结果“更像自然语言”而替换原生文字。

## 3. 图片区域规则

### ordinary_figure

普通配图、几何图、实验图、化学结构图。Word 中整体保留。图片内部 OCR 只作为元数据。

### raster_text

图片本质是扫描段落、截图文字。OCR 后转换为可编辑段落，可保留原裁剪图作为证据。

### table_image

调用表格模型。结构低可信时输出图片。

### formula_image

调用公式模型。转 OMML 失败时输出图片。

### complex_composite

文字、线条、图形高度耦合，拆分会破坏关系。整体图片保留，可附内部文本元数据。

## 4. PP-OCRv6 规则

- 默认 Small；
- 低置信度、高密度小字、上下标、音标、数字单位区域升级 Medium；
- 保留检测框、行、内容和原始置信度；
- 识别语言提示为 `zh-CN`、`en`，不得自动翻译；
- 禁止语言模型式拼写纠正；
- 关键字符差异创建 `content_conflict` Issue。

## 5. MonkeyOCRv2 规则

### 输入

- 整页图像或复杂区域；
- 页面/区域 ID；
- 原始像素尺寸和 PDF bbox；
- 任务模式 `layout` 或 `end_to_end`；
- 可选文档类型提示，不提供预期答案。

### 输出处理

- 将归一化坐标转换为 PDF point；
- 标准化标签到 IR 类型；
- 保留原始标签、原始文本和模型版本；
- 按模型阅读顺序形成候选顺序；
- 结果没有概率时 `engine_confidence = null`；
- 通过几何合法性、多模型一致性、覆盖和回渲染生成 `system_confidence`。

### 标签映射示例

| Monkey 标签 | IR 类型 |
|---|---|
| Text | paragraph/text_line |
| Title | heading |
| Picture | figure |
| Table | table |
| Formula | formula |
| Page-header | header |
| Page-footer | footer |
| List-item | list_item |
| Caption | caption |
| Unknown | unknown |

实际标签以 Adapter 映射表为准；未知标签不得丢弃。

## 6. OvisOCR2 规则

- 默认只复核指定区域或高风险整页；
- Markdown 仅解析为候选，不成为主 IR；
- 表格 HTML、公式 LaTeX、图片 bbox 分别进入对应候选；
- 不使用其自然语言补全替代视觉证据；
- 与专项模型冲突时不自动覆盖，进入融合或审校。

## 7. 表格规则

1. PP-StructureV3 为主结构。
2. 校验行列、单元格覆盖、合并、文字归属和 bbox。
3. 结构可信且回渲染可接受时生成 Word 原生表格。
4. 中等可信生成 `native_with_review`。
5. 低可信保留表格图片。
6. Monkey/Ovis 结果只作为漏检、结构和内容候选。

## 8. 公式规则

1. PP-FormulaNet 主识别；
2. 生成 LaTeX/MathML；
3. 转 OMML；
4. 将 OMML 回渲染与原图比对；
5. 通过则输出 OMML；
6. 失败输出原公式图片；
7. Ovis/Monkey 可作为候选，不静默替换。

化学结构式、实验图和复杂反应流程默认保留图片。纯文本化学方程式可按公式处理。

## 9. 隐藏文字层去重

对原生框和 OCR 框计算：

- 几何重合；
- 文本相似；
- 阅读顺序；
- 视觉覆盖；
- 乱码比例。

位置和内容一致时只保留质量更高候选。原生层损坏时 OCR 可替换，但必须保留 `supersedes`。

## 10. QuestionBlock 规则

题号模式至少支持：

```text
1.  1．  1、  （1）  (1)  ①  一、  （一）  A.  A、
```

层级：

```text
section → major_question → question → subquestion → option
```

不得只依赖正则；结合缩进、字体、纵向范围、阅读顺序和邻近块。

## 11. 图片归属评分

```text
score =
  vertical_interval
+ same_column
+ distance
+ reading_order_proximity
+ cue_phrase
+ caption_relation
- crossing_next_question
- column_conflict
```

- `>= auto_threshold`：自动建立 `anchored_to`；
- `review_threshold <= score < auto_threshold`：建立候选并创建 Issue；
- `< review_threshold`：不归属，等待人工处理。

## 12. Word 转换规则

- 标题：Word Heading 或自定义样式；
- 正文：流式段落；
- 题号和题干：同一逻辑容器；
- 图片在题干下：独立行内图片段落；
- 图片在题干右：无边框 1×2 布局表格；
- 选项图：1×N 或 2×2 无边框表格；
- 图片与图题：同一单元格或同一 keep 组；
- 表格：Word 原生表格或图片；
- 公式：OMML 或图片；
- 复杂局部：整体图片；
- 禁止默认大量浮动文本框。

## 13. 禁止静默纠正

禁止自动修改：

- 试卷故意错误的选项；
- 数字、小数点和正负号；
- 单位；
- 英文拼写；
- 上标、下标；
- 数学和化学公式；
- 人名、编号和标准号。

可以创建疑似错误提示，但最终文字必须基于视觉/原生证据。
