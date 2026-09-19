# R1-07 reconstruction-v2 完整导出链

2026-09-19。基线 HEAD `4e2c952`，分支 `codex/r1-07-reconstruction-chain`。该提交已按用户授权保存 R1-04/R1-06；本轮 R1-07 改动尚未提交。状态：工程接入已实现，有离线集成及实物证据；**不签署完整产品接受**。

## 修改

- `reconstruction.py`、`pipeline.py`：CLI/API/UI 共用 finish 接通逐页仲裁、共享结构、Flow 计划、实际写出；保留来源 hash、单次结构 stage、reviewed 优先和显式 renderer 能力回退。
- `geometry_arbitration.py`：提取共用逐页执行，校验响应 hash，页级失败保留原页；原封存回放入口复用此实现。修正该入口结构处理器记录为实际 DocVortex。
- `writer.py`：来源 marker 包围实际文字/公式/图片，不再是空书签；分组图文分别界定内容范围，未闭合范围拒绝输出。
- `renderers/capabilities.py`：明确 Legacy/DocVortex/Flow 支持的计划模式；无公开 section/style 能力时显式采用 Flow，不绕过契约。
- `static/app.js`、`scripts/docx_demo.py`：现有 UI 与新增只读 `status` CLI 显示逐页选型、布局状态、输出器、问题，优先 reviewed。
- `reconstruction_replay.py`：封存证据四组消融，独立输出，不调用模型。
- `test_reconstruction_vertical_slice.py`：7 个新回归覆盖真实 convert/execute-route/finish、逐页 Monkey/PP 混用的合成证据、范围书签、reviewed、不重复后处理、失败隔离、输出器回退及 API/CLI 状态。
- [输出能力决定](../../docs/decisions/reconstruction-v2-profile.md)。

## 验证

日志：私有 `tmp/docx-demo/r1-07/checks/`。

- `uv run pytest -q`：最终 **1559 passed**，1 个既有 Starlette 弃用警告；见 `pytest-final.txt`。
- `uv sync --locked`：成功，无新增依赖。
- `uv run ruff check .`：成功。
- `uv run mypy prototypes/docx_output scripts/docx_demo.py tests/productization/test_reconstruction_vertical_slice.py`：62 个源文件无错误。
- `uv run mypy .`：2 个既有错误，均在历史未跟踪 `tmp/docx-demo/r1-05/trace-public-calls.py:15–16`；未遮蔽或改写。
- `node --check prototypes/docx_output/static/app.js`：成功。API/CLI 实际调用有回归；本轮没有额外浏览器人工交互验收。
- 四组 DOCX 实际由 LibreOffice 转 PDF/PNG；固定 IR 完全相同、全部图片 hash 相同、来源 47 个文件 hash 不变、17 个来源范围非空均有断言收据。

执行入口（已实际运行）：

```sh
uv run python -m prototypes.docx_output.reconstruction_replay --source-job tmp/docx-demo/r1-03/real-dry-run/demo-d1bffe644d8e44a68a9a881015295cff --source-seal tmp/docx-demo/r1-03/real-dry-run/live-validation-receipt.json --output-root tmp/docx-demo/r1-07/final
uv run python scripts/docx_demo.py status --job-id demo-2252d8a647a04d3a86ca1dce0f473076 --output-root tmp/docx-demo/r1-07/final
```

## 证据

私有最终根 `tmp/docx-demo/r1-07/final/`：

| 消融组 | 作业 |
| --- | --- |
| 旧布局旧 renderer | `demo-329b73d50e0644a89b39d5af054c562c` |
| 新布局同 renderer | `demo-661301994ee744f29c2b0b489d3acf5b` |
| 固定 IR 两个 renderer | 上一作业与 `demo-18b6de99031d4284a0b98fe96334c935` |
| 最终共用链 | `demo-2252d8a647a04d3a86ca1dce0f473076` |

比较、渲染、文件 hash、逐来源范围收据位于 `demo-1e5bf65672044e8eb158ff0be97ac51d/` 的 `comparison.json`、`render-verification.json`、`evidence-verification.json`。输出作业包含 auto.docx、IR、RenderPlan、source-map、来源绑定 ledger、结构执行与版本、mapping-loss-report、QA 和实际渲染。每组 489 个可编辑字符、2 张图片，执行状态均 PARTIAL。真实两页均 ABSTAIN，无人为构造赢家。

独立编辑副本 `tmp/docx-demo/r1-07/edit/demo-b4df43fb567c43e8b1cfb5f6859ef1b0/`：在真实 IR 副本插入一段明确标为合成的人工正文，再删除，通过实际 finish/replan/render；删除后 pages/relations 恢复原值，旧作业不变。真实样本没有已确认题图关系边（0 条），因此不能把“空关系集合守恒”写成题图归属验收。

模型真实请求 0；复用 R1-03 封存的 6 条请求记录及已有候选。两批消融及诊断复验均为本地回放，不重试模型、不更改原文/GT。

## 风险与验收条款

- AC01：source_id→IR→计划→DOCX 范围可贯通；Monkey/PP 混用已有合成回归。**真实 Monkey 最终采用 NOT_VERIFIED**，该条不完整接受，不降低 R1-04 门槛。
- AC02：同源消融零新请求，图片字节及既有普通插图/公式局部保图保护保留；固定 IR 对照有实物证据。
- AC03：执行、布局、人工接受分开。最终候选为 PARTIAL，第 46 页图像回退继续保留；Word 人工打开/编辑/视觉为 NOT_RUN。
- AC04：公共结构实际执行和版本有记录；reviewed 再导出为 REUSED_FINALIZED，不重复 Model 后处理。
- 预览标为 **IR preview（实际 LibreOffice DOCX→PDF→PNG，不是 Microsoft Word 输出）**。代理查看了最终第 47 页，中文可见、图形完整；不签署人工接受。
- 第一批最终 Flow 预览发生中文缺字。DOCX 除书签位置外正文 XML 与 R1-06 相同；单段范围/空书签均正常，完整文档未经语义修改的副本复验亦正常（29 个中文字符），未能确认根因。第一批失败产物、最小/完整探针都保留在 `real/`、`bookmark-debug/` 和检查日志；不得因最终复验正常而把渲染稳定性写成已解决。
- 默认兼容路径可回滚；不 push/merge、不改旧产物、不自动进入 R1-08。建议以这些明确缺口决定 R1-07 的接受范围，再进入 R1-08 实物验收。
