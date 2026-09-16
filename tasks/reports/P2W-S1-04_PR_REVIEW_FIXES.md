# PR 4：首轮外部 Codex 审查修复

审查版本：269083058e69881da0f24ccda2498e1f49e683b3。

1. 部分未评分指标误判 FAIL：只将 correct < scored 视为实际错误，
   其余存在未评分项时为 REVIEW_REQUIRED，完全未评分仍为 NOT_SCORED。
   指标值继续使用完整 eligible 分母，不因不支持的公式而抬高覆盖率。
2. 默认 Office OMML 属性误报：接受空的 fPr/sSupPr/sSubPr/sSubSupPr、
   它们的 ctrlPr 纯样式内容，以及显式的普通分数 type=bar。
   未知属性和 noBar/skw 等非默认属性继续保留，不能等同于普通分数。

新增 9 个实际 DOCX 回归：混合支持/不支持公式并分别含正确或错误的支持项；
分数默认值、无分数线、斜线分数与三种上下标默认属性。
修复前 6 failed / 3 passed；修复后目标 41 passed。
独立检出的最终全量：544 passed，1 个既有 Starlette 弃用警告；
Ruff、mypy（58 个文件）、任务目录与模型基线校验全部通过。

只修改评估器与对应测试，不重算或改写封存样本、旧 DOCX 和既有报告。
外部审核需要对新提交重新完成，本记录不代表该新审核已经通过。
