# 自有合成故障集

`generate.py` 创建 20 个自有故障资产和 catalog.json；目标目录必须不存在，输出含 SHA-256。
所有内容为合成，不是用户 PDF、真实 GT 或产品验收。默认 pytest 会验证关键文件性质，
不运行模型。生成器只使用项目已有 Pillow 和标准库；encrypted-pdf.json 是自行生成的空白加密 PDF 字节，
由本机 bundled pypdf 一次制作后固定，不是敏感文档或模型响应。密码 synthetic-only 仅用于测试。

```sh
uv run --locked python -c "from pathlib import Path; from tests.productization.synthetic.generate import generate; generate(Path('tmp/productization/synthetic-new'))"
```

| 资产 | 性质/用途 |
|---|---|
| native/blank/title.pdf | 原生文字、零字符空白、标题页 |
| crop.pdf、rotation-0/90/180/270.pdf | 非零 CropBox 与四方向 |
| hidden.pdf | 同位置可见与不可见文字对象；PDFium 可合并字符输出，不能以重复转录计数证明对象不存在 |
| overlap.pdf、transparent.png | 真正的图像对象覆盖文字、全透明 alpha |
| damaged/encrypted.pdf | 不可解析与确需密码；带正确密码可打开合成空白页 |
| text-faults.json | PUA、XML 控制符、HTML/URL 注入、货币/LaTeX、长公式、Unicode 编辑 |
| invalid-table/wrong-edge.json | 非法表跨度、不存在的题图锚点 |
| partial-request/started-request.json | 半成功、STARTED 未知结果；只作协议故障输入，不是真实推理 |
| corrupt-cache/cross-job.json | 损坏 JSON 与跨作业路径 |

对不支持场景只提供故障输入，不声称现有转换器已经正确处理全部资产。
已实测属性由 test_synthetic.py 指明，已有原型回归继续独立运行。
损坏、遮挡、不可见文字等是有意构造的故障，不能为了视觉美观将其修掉。
