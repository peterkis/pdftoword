# 引擎 Adapter 协议

核心原则：领域层只认识标准 DTO。

## LayoutResult

- blocks：标准 bbox、类型、阅读顺序；
- engine_confidence 可空；
- raw_response_ref；
- model metadata；
- warnings。

## TextOcrResult

- lines/words；
- bbox_pdf_pt；
- text；
- confidence；
- language hints。

## TableResult

- table bbox；
- rows/columns；
- cells；
- spans；
- content；
- structure confidence；
- fallback asset。

## FormulaResult

- latex/mathml；
- confidence；
- source asset；
- render validation state。

## ReviewResult

- candidates；
- coverage；
- conflicts；
- raw response ref；
- 不包含“直接覆盖最终结果”动作。
