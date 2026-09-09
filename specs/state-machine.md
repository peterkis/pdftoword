# 作业状态机 V1.1

```text
created
→ preflight
→ extracting_native
→ routing
→ waiting_model? / recognizing
→ fusing
→ structuring
→ building_docx
→ qa
→ review_required? / completed
```

终止状态：`failed`、`cancelled`、`completed`。

`waiting_model` 可恢复；`review_required` 允许用户导出带警告版本或修正后重建。
