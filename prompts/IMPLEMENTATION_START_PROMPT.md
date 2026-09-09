# Coding Agent 启动 Prompt

你正在实现 PDF2Word Local V1.1。先完整阅读根目录 `AGENTS.md`、`START_HERE.md`、`docs/01_PRD.md`、`docs/03_TECHNICAL_ARCHITECTURE_V1_1.md`、`docs/06_RECOGNITION_CONVERSION_RULES.md`、`docs/10_LAYOUT_IR.md`、`phases/PHASES_OVERVIEW.md`。

执行规则：

1. 从尚未完成且依赖已满足的最小 Ticket 开始。
2. 本次只实现一个 Ticket 或一个紧密相关的小组，不擅自实现整个系统。
3. 先写测试，再实现。
4. 不改变产品边界。
5. 不把模型原始 JSON 传给 DOCX Builder。
6. 不对有效原生文字 OCR。
7. 不静默修正试卷内容。
8. 所有模型必须通过 8100 网关和 Adapter。
9. 完成后输出：修改文件、测试命令、测试结果、未解决风险、下一可执行 Ticket。

从 `T0001` 开始，除非仓库已有对应实现。已有实现时先审计与 Ticket 验收标准的差距，再补齐。
