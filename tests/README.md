# 测试目录

```text
tests/
├── unit/          # 单元测试：不访问网络、不调用模型、不依赖 GPU、不依赖真实 PDF/图片
├── integration/   # 集成测试（后续 Ticket 建立）
├── golden/        # 黄金样本回归（T0012 建立框架）
└── fixtures/      # 可提交的精简测试夹具
```

## Fixture 规则（T0001 冻结）

1. **原始模型响应**（`*.raw.json`、含 Base64 图片的响应、临时裁剪图）只能放在
   仓库根 `tmp/model-smoke/`；该目录已被 `.gitignore` 忽略，永不提交。
2. **可提交 Fixture** 放在 `tests/fixtures/model_api/<样本名>/`，必须精简、
   去敏并经人工确认后提交，建议结构：

   ```text
   math_exam_scan_page_001/
   ├─ README.md                    # 样本说明与来源
   ├─ ground-truth.json            # 期望结果
   ├─ monkey.content.txt           # MonkeyOCRv2 文本内容
   ├─ ovis.content.md              # OvisOCR2 文本内容
   ├─ pp-structure.summary.json    # PP-StructureV3 摘要
   └─ pp-structure.pruned.json     # 必须移除 markdown.images、所有 Base64 图片内容和无关日志字段
   ```

3. `*.raw.json` 在任何位置（包括本目录）都不允许提交（`.gitignore` 已强制）。
4. 当前 `tests/fixtures/model_api/math_exam_page_01/` 为历史遗留的未追踪内容，
   尚未按上述规则完成精简与确认；在任何提交前必须先审查。
5. 现有数学试卷样本（JPG、纯图像输入、中文为主、含公式与多图）不能替代
   P1 所需的纯电子 PDF Fixture。

## 完整门禁与平台策略（P2W-S1-02）

最终使用 `uv run --locked python scripts/quality.py`，直接 pytest 仍用于局部开发。
默认 collection/执行阶段禁止真实 Python HTTP/socket 网络；进程内 MockTransport/TestClient 可用。
五个 JavaScript 处理器测试必须有 Node 24.18.0，缺失为错误。
平台跳过仅允许[精确白名单](quality-skip-allowlist.json)；其他 skip、XFAIL、XPASS 使完整门禁失败。
POSIX 权限与 Windows 应用访问隔离分别验证，不能以 chmod 位替代 Windows ACL。
详见[质量门禁](../docs/26_QUALITY_GATE.md)。
