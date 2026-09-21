# P2W-U1-01 MinerU v4 在线验证与视觉验收

## Agent 读取摘要

本文件记录一次已授权的 MinerU 官方 v4 Precision Extract API 验证。它产出了两份真实 DOCX，并在 Microsoft Word 16.113.1 中逐页检查。结果是：正文在 Word 中可见且顺序连续；两份输出都存在版式保真缺陷，不能作为最终布局接受结果。保留 pipeline 与 VLM 两个候选，不强行产生唯一赢家。

读取本文件时，先看“结论与边界”，再看“证据路径”。`result.zip`、JSON 和 DOCX 属于私有作业证据；本报告不复制原始响应、正文、Token 或签名 URL。

## 结论与边界

- 任务：`P2W-U1-01`，只执行官方在线 API 对比，不安装本地 MinerU，不调用 v1，不改变默认转换路由。
- 路线：`https://mineru.net/api/v4` Precision Extract API。
- 外发授权：用户明确授权将选定真实 PDF 发送到 MinerU 官方在线服务。
- 输入：`tmp/docx-demo/s2-electronic-real/demo-14b937038e1240e68f193ec97ddd6578/input.pdf`。
- 输入 SHA-256：`b62f243a99eed98a318cb4d5c79fed01fe2a7e427a0532b2ab17c346f6948442`。
- 解析范围：物理第 4 页；服务结果中的 `*_origin.pdf` 为 1 页 A4。
- 请求固定项：`is_ocr=true`、`enable_formula=true`、`enable_table=true`、`page_ranges="4"`、`extra_formats=["docx"]`。
- 模型候选：`pipeline` 与 `vlm`。官方 v4 文档没有 `standard` 模型值，也没有公开 `effort` 请求字段；VLM 结果中的 `_effort="medium"` 视为服务端元数据，不当作可写参数。
- 视觉结论：**代理视觉验收完成，但版式保真不接受**。
- 人工接受：`PENDING`；本次代理检查不伪造用户签字或产品接受。

官方接口说明：[MinerU v4 API](https://mineru.net/apiManage/docs)；英文参数说明：[MinerU Extract API](https://mineru.net/doc/docs/index_en/)。

## 实际执行协议

1. 使用 v4 `/api/v4/file-urls/batch` 申请本地文件的签名上传 URL。
2. 通过返回的签名 URL PUT 同一个 PDF；上传后由服务自动创建 batch 解析任务。
3. 轮询 `/api/v4/extract-results/batch/{batch_id}`，直到 `state=done`。
4. 下载 `full_zip_url`，保存完整结果 ZIP；安全解压 `full.docx`、JSON、Markdown 和服务生成的 `*_origin.pdf`。
5. 将服务生成的 `full.docx` 复制为各候选目录的 `result/B.docx`，不改 DOCX 内容。
6. 运行仓库文档验收规范要求的 `render_docx.py`，为每份 DOCX 生成 2 页 PNG 和 PDF。
7. 用 Word 16.113.1 只读打开 pipeline 与 VLM 两份 DOCX，逐页查看第一页、第二页顶部和底部；未插字、未保存、未修改。

pipeline 的首次签名 PUT 因客户端自动附加默认 `Content-Type` 返回 403；没有新建解析任务，随后复用同一个签名 URL 以仅含 `Content-Length` 的 PUT 成功。VLM 上传一次成功。两次均没有重复提交解析任务。

## 产物与哈希

### pipeline，`is_ocr=true`

- DOCX：`tmp/mineru-online-u1-01-v4-ocr/pipeline/result/B.docx`
- 结果包：`tmp/mineru-online-u1-01-v4-ocr/pipeline/result.zip`
- 结果包 SHA-256：`918495f1b637ac9676771b9513777a73d5fa7a894ac6aa07e2679cd6f380df9a`
- DOCX SHA-256：`e9ba478ca73f9dcf50518fa8c0b33ed97a62fbf0bc8e5c3e8717e06ce0b5ef6a`
- 布局元数据：`_backend=pipeline`，`_version_name=3.4.4`。
- DOCX 包检查：ZIP/XML 有效；31 个段落、43 个文本节点、0 个表格、0 个 OMML、0 个 drawing、0 个媒体对象。
- 自动渲染：`tmp/mineru-online-u1-01-v4-ocr/pipeline/rendered-skill/`。

### VLM，`is_ocr=true`

- DOCX：`tmp/mineru-online-u1-01-v4-ocr/vlm/result/B.docx`
- 结果包：`tmp/mineru-online-u1-01-v4-ocr/vlm/result.zip`
- 结果包 SHA-256：`0acf989e7be42c5b980f192b16627a4b2fcd1a98afa10f4efe80679203a5e643`
- DOCX SHA-256：`71315f672e1f5b1e527a1c9d1bcae2bea4242be0f7d9c5f44511b74e66244fde`
- 布局元数据：`_backend=hybrid`，`_version_name=3.4.4`，`_effort=medium`，`_ocr_enable=true`。
- DOCX 包检查：ZIP/XML 有效；31 个段落、43 个文本节点、0 个表格、0 个 OMML、0 个 drawing、0 个媒体对象。
- 自动渲染：`tmp/mineru-online-u1-01-v4-ocr/vlm/rendered-skill/`。

### 验收收据

- 代理视觉验收：`tmp/mineru-online-u1-01-v4-ocr/visual-acceptance.json`。
- 源页视觉证据：`tmp/mineru-online-u1-01-v4/source-render/origin-page-1.png`。
- 源页服务副本：`tmp/mineru-online-u1-01-v4/result/62758034-3865-4f25-b688-74c28696e75a_origin.pdf`。
- 源文件、结果 ZIP、DOCX、渲染 PNG 和 Word 观察属于同一私有作业链；没有用合成样例代替真实输入。

## Word 代理视觉验收结果

### 共同观察

- Word 能打开两份 DOCX，标题栏显示兼容性模式。
- 两份均为 2 页；源服务副本为 1 页。
- 中文正文在 Word 中可见，段落顺序连续；没有观察到正文裁切或文本重叠。
- 第 2 页下半部有较大空白，内容没有填满源页同等范围。
- 源页右上角 `WS 196—2017` 页眉没有出现在 DOCX 中。
- 源页右下角页码 `2` 没有出现在 DOCX 中。
- `3.2.4`、`3.2.5`、`3.3` 等标题在 Word 中带有黑色方块项目符号；源页标题没有该项目符号。
- pipeline 与 VLM 的主要缺陷相同，因此不选择唯一赢家。

### 模型差异

- pipeline 在 Word 工具栏显示 `Aptos (正文)`。
- VLM 在 Word 工具栏显示 `等线 (中文正文)`，中文观感更接近源页，但没有消除分页、页眉页码和标题项目符号缺陷。
- “VLM 更适合继续比较”只能作为后续实验假设，不能写成已经接受或质量胜出。

## 证据等级

| 证据 | 状态 | 能支持的结论 |
| --- | --- | --- |
| v4 HTTP 上传/轮询/下载 | 已执行 | 两个模型候选均得到服务结果；未调用 v1 |
| 结果 ZIP 校验 | 已执行 | 下载包可解压，包含 DOCX/JSON/Markdown/源页副本 |
| DOCX ZIP/XML 检查 | 已执行 | 包结构可读；对象数量不是准确率或视觉质量 |
| `render_docx.py` PNG | 已执行 | 可复现的本地渲染图，不能替代 Word |
| Word 16.113.1 逐页观察 | 已执行 | 正文可见、顺序连续、缺陷可见 |
| 源页与 DOCX 版式保真 | 未接受 | 共同缺陷导致布局验收不接受 |
| 用户人工接受 | 未发生 | 保持 `PENDING` |

## 不要推断

- 不要把 `pipeline` 称作在线 `standard`；官方 v4 请求值是 `pipeline`/`vlm`/`MinerU-HTML`。
- 不要把输出 JSON 的 `_effort=medium` 改写为可配置的 `effort`，也不要自行提交未公开的 `effort=high/max`。
- 不要把 ZIP/XML 有效、段落数量或 Word 能打开写成版式保真成功。
- 不要把正文在 Word 中可见写成页眉、页码、分页和标题样式已守恒。
- 不要把 `full.docx` 说成本地 `render_docx` 重新生成；它是官方在线服务 ZIP 中的 DOCX。
- 不要把当前结果写成已修复生产路由；本次只验证外部在线候选，默认转换路由未变。

## 当前停止点与后续入口

当前停止在 U1-01 的在线候选和视觉证据。若继续，应先决定是否接受在线 DOCX 的版式缺陷，再选择以下单一范围之一：

1. 调查官方 API DOCX 转换是否有文档化的页眉/页码/分页选项；
2. 保存在线 JSON/布局结果，在已批准的兼容本地 Renderer 中做离线重导出对照；
3. 保留当前两候选为外部 baseline，回到项目自己的 Layout IR/Writer 路线。

不要在没有新的 API 契约或用户决策时重跑同一模型任务、伪造 effort 档位或把共同缺陷标成已修复。
