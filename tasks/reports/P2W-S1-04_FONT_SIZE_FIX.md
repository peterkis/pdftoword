# S1-04 反馈修复：原生 PDF 正文字号过小

用户实际打开 auto.docx 后反馈无法阅读。本次修复该问题，不改写原验收报告或封存输出。

## 原因与修复

旧输出 747 个正文字符全部被写成 1 pt。真实输入的文字使用局部字号 1，
文字矩阵中另有约 9–10.5 倍缩放；原生 Adapter 直接将 FPDFText_GetFontSize 当成页面磅值。
实测字符矩阵 `[10.5, 0, 0, 10.5]` 与局部字号 1 共同表示 10.5 pt，而不是 1 pt。

`native_pdf.py` 现在用局部字号乘字符矩阵纵向基向量长度，得到页面实际磅值，
再用于行分组和 Layout IR 字号。矩阵不可用或结果无效时保留未知字号、使用默认样式并登记审校原因。
不设任意最小字号，不把源文档真正的 1 pt 文本强行放大。

## 证据

- 新增 `tests/demo/test_native_font_scale.py`：均匀缩放、非均匀缩放、图形变换叠加、真实 1 pt 四例。
- 修复前两个变换样例均在真实 native→DOCX 流程输出 1 pt，测试失败；修复后四例通过。
- 相关回归 86 passed；最终全量 **594 passed**，1 个既有 Starlette 弃用警告。
- 全仓 Ruff、两个变更 Python 文件的 mypy、git diff --check 通过。
- 同一冻结样本第 25 页重新执行离线原生转换：
  `uv run --locked python scripts/product_acceptance.py run --dataset tmp/productization/frozen-v1 --sample-id d8e3e546cdc145e18e0bfd873b32fbee --entry cli --output-dir tmp/product-acceptance/s1-04-font-size-fix`
- 新输出 747 个可编辑字符，文字内容与旧输出完全相同；字号为 9、10、10.5 pt。
- LibreOffice 实际渲染 1 页，代理查看页图确认正文可读；不声称完成用户的人工 Office 编辑验收。
- 新文件：`tmp/product-acceptance/s1-04-font-size-fix/auto.docx`。
- 旧 `s1-04-cli-final/auto.docx` 哈希仍与原 seal 一致。

整体验收 runner 仍退出 1，既有严格文本/关系评分问题保留；本次仅确认字号缺陷修复。
无模型调用，无提交或远端写操作。原 S1-01/02/03 未提交改动保持原状。
