# P2W-S1-04 — 上传到 Word 离线验收工具

状态：**READY_FOR_REVIEW**。不表示任务已 ACCEPTED，也不表示当前产品质量通过。

## 范围与变更

基点 `3241f10804a899f8ec2b0bdb6512e1f6cd5e456a`，当前分支 `codex/p2w-s1-03`。
S1-02/03 本地成果作为实施依赖；不更改其验收状态，不运行后续阶段。

- `scripts/product_acceptance.py`：CLI/API 原生运行、封存、离线重算及独立 reviewed 版本导入。
- `scripts/acceptance/`：转换子进程、独立 OOXML 读取、CER、表格、OMML、关系、阅读顺序和降级面积。
- `prototypes/docx_output/writer.py`：新增来源书签与来源映射，保留已有资产错误码。
- `specs/product-quality/result.schema.json`：结果状态、分母、错误与哈希合同。
- `tests/productization/test_acceptance_harness.py`：32 个目标用例，包含 15 个参数化实际 DOCX 故障。
- `docs/28_PRODUCT_ACCEPTANCE.md`、本报告及 `P2W-S1-04_CHECKS.json`：使用方式、边界与实测证据。

开始时已有的 S1-01/02/03 未提交文件均保持原字节。起点全文件指纹比对：
唯一被修改的既存文件为本项授权的 Writer，无既存文件丢失。
原 97 Ticket、DEMO 私有既存作业、T0015/T0016、冻结数据与人工标注未改写。
只暂存/提交本项文件；不推送、合并、修改 FRP 或调用识别模型。

## 真实执行

```sh
uv run --locked python scripts/product_acceptance.py run \
  --dataset tmp/productization/frozen-v1 \
  --sample-id d8e3e546cdc145e18e0bfd873b32fbee --entry cli \
  --output-dir tmp/product-acceptance/s1-04-cli-final
uv run --locked python scripts/product_acceptance.py run \
  --dataset tmp/productization/frozen-v1 \
  --sample-id d8e3e546cdc145e18e0bfd873b32fbee --entry api \
  --output-dir tmp/product-acceptance/s1-04-api-final
uv run --locked python scripts/product_acceptance.py evaluate-only \
  --bundle tmp/product-acceptance/s1-04-cli-final \
  --output tmp/product-acceptance/s1-04-rescore-1.json
# 第二次仅换为 s1-04-rescore-2.json，语义哈希相同。
uv run --locked python scripts/quality.py --output-dir tmp/quality/s1-04-final
```

两个入口使用同一个冻结 development/N 文档的第 25 页：源字节哈希、页码、profile 一致；
每入口实测共享 pipeline 调用 1 次、模型请求 0，评分 metrics 完全一致。
API 经过真实 multipart 上传、后台转换和 DOCX 下载，为进程内 TestClient，未声称浏览器实测。

两个自动输出均真实经过 **LibreOfficeDev 26.8.0.0.alpha0**
（版本标识 `2c87e51eeaa2b413ff4ae097b2705eea1995d8e5`）渲染。
实际字体探测为 Songti SC / Arial；DOCX、渲染 PDF/PNG、源码和参考哈希保留在独立包及检查 JSON。
此为开发版 LibreOffice 证据，不冒称 Microsoft Word 或稳定版 Office 验收。

真实验收 runner 均退出 **1**：执行 COMPLETE，内容/结构 **FAIL**。
正文目标参考 788 码点，raw CER 为 `29/788 = 0.03680203045685279`；
仅去空白后 light CER 为 `0/747 = 0`，故不将这些原始差异全部描述为实质漏字。
16 个图内文字单元从可编辑正文分母分离，仍在必要内容分母。
必要内容 22 项中 15 项有源图保留证据（15/22），裁剪视觉状态仍 PENDING。
图关系与严格原始文字比较的失败均保留；不通过改写 GT 获得通过。

代理查看了实际渲染页图：正文显示过小，视觉仍需修正；该页图与两个最终运行的 PNG 哈希一致。
这是 **agent visual observation**，不是人工 Office 验收；本项未修改原生字体/排版算法。
初次诊断运行及后续评分均保留，不覆盖早期失败记录。

## 验证结果

| 检查 | 实测结果 |
| --- | --- |
| 全量 pytest（最终运行一次） | **590 passed**，0 failed，0 skipped；1 个既有 Starlette 弃用警告 |
| 新增目标文件 | **32 passed** |
| 全仓 Ruff | PASS |
| 本项 9 个 Python 文件定向 mypy | PASS |
| 全仓 mypy / 完整 quality | **FAIL**：既有两份私有复核脚本共 19 个类型错误 |
| validate_task_catalog / validate_model_baseline | PASS |
| 既有 Schema 样例、实际新结果 Schema、非法结果反例 | PASS |
| 篡改拒绝、输出拒绝覆盖、auto/reviewed 隔离 | PASS |
| 相同封存证据重复评分语义哈希 | PASS；两次退出 1 正确保留质量失败 |
| CLI/API metrics 相等、实际调用预算 | PASS |
| 开始时既存文件指纹、冻结清单成员哈希 | PASS（仅 Writer 为本项预期修改） |
| git diff --check | PASS |

既有 mypy 问题位于 `tmp/productization/source-review-20260915/build_review.py` 和
`tmp/productization/review-v5/build_private_review.py`，本轮未改动，也未扩大扫描排除来获得通过。
质量结果见 `tmp/quality/s1-04-final/public/summary.json`；原始诊断保留于同运行的 private 目录。

## Standards

初审 2 项（总体 FAIL 传播、资产错误码），均修复并补实际回归。复查剩余 **0 项**。

## Spec

累计发现 4 项（额外错误边、未消费普通文字、OMML 语义属性、未消费额外数学节点），
均修复并经复查；剩余阻塞发现 **0 项**。

两轴结论不替代人工产品验收。AC01–04 的具体证据见检查 JSON；15 个故障 DOCX 均按预期检出。

## 未确认与下一项

- **PENDING**：人工在真实 Office 内插入/删除两行，修改公式和表格（若存在）并检查版式。
  reviewed 导入已测试，但不能把合成修改当成该人工步骤。
- **NOT_SCORED**：跨页数据表 continuation 全局语义、支持范围外的公式语法；分母不丢弃。
  表格重复表头从 cell 分母去重，局部拓扑与内容仍独立检查。
- **PENDING**：完整源图的视觉裁剪验收、Microsoft Word / Windows / macOS 多 Office 环境接受。
- 当前原生输出正文字号问题及关系失败属于后续产品修正，不在评估器里补答案。
- 后续建议 **P2W-S1-05**：先审阅本项及其依赖，按该任务范围处理真实运行暴露的问题；本轮不执行。

本次按用户明确调用的 implement 技能提交至当前分支。既有未提交成果保持原状；无远端写操作。
