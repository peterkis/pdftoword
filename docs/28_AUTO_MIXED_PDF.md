# 自动入口与混合 PDF

运行 `uv run --locked python scripts/docx_demo.py serve`，上传时选择“自动”。应用先在本地提取有效文字，保留插图并生成区域计划。页面中的待处理区域可定位查看；批准后识别并生成独立新版本。不批准仍可下载含原生正文和局部原图的文档。

## CLI

```sh
uv run --locked python scripts/docx_demo.py convert --input YOUR.pdf --pages 1-2 --mode auto --dry-run-route
uv run --locked python scripts/docx_demo.py execute-route --job-id JOB_ID --plan-hash PLAN_HASH --budget REQUEST_LIMIT --confirm-no-auth
```

第一条命令打印本地 `route-plan.json` 路径，并生成可打开的初始 DOCX；没有模型请求。第二条须使用该计划的真实哈希和请求上限。若使用自定义 output-root，两条命令都须指定相同目录。每区域最多 PP/Ovis各一次；遇普通配图只保图，遇未知标签保留原图待审校。

`native` 与 `raster` 手动路径保留；auto 不继承上传表单的整页 live 授权勾选，须批准实际区域计划。页码为 PDF 物理页码，最多三页；输入≤25MiB。源文件不修改。

## 输出与检查

- `observation-N.json`：原生文字、对象、页框、变换和未知信息。
- `route-plan.json` / `layout.prepared.json`：不可变的输入/区域/预算绑定。
- `request-manifest.json`：真实尝试、失败及显式复用记录。
- `region-results.json`：每区域结果；失败不影响其他原生正文。
- `auto.docx` / `layout.auto.json`：当前作业自动结果。
- Pages检查另存副本；应用内 reviewed 仍通过原审校路径保存。

后续执行生成新作业，保留 parent_job_id。旧计划不自动重试；超时或中断的请求保留 STARTED/失败状态。保存、预览和导出不请求模型。文件、原图、识别内容与原始响应留在忽略的私有作业目录。

## 限制

复杂图文重叠、未验证字体几何、多栏和多个不能唯一定位的表格继续提示审校。单个可定位表格允许局部保图，不表示已经实现可编辑表格。上游文字run不是逐字符精确框；未知透明度/遮挡不能靠文字数量猜测。

真实扫描页、真实电子页、受控混合合成页和真实混合页的验证分别记录；Pages打开不代表Microsoft Word验收。实现决策见 [后端与profile](decisions/auto-mixed-native-backend-v1.md)。

## 常见状态与错误

- `PARTIAL`：存在未识别/待审校区域，可先下载保留源图的结果。
- `PDF_PASSWORD_REQUIRED` / `PDF_FORMAT_ERROR`：密码与损坏分别报告，本轮不提供解密入口。
- `ROUTE_PLAN_CHANGED` / `ROUTE_INPUT_CHANGED` / `ROUTE_PREPARED_CHANGED`：计划或输入已变化，旧批准无效。
- `ROUTE_PLAN_EXPIRED` / `ROUTE_TARGET_CHANGED`：需要生成新计划。
- `ROUTE_ALREADY_ATTEMPTED`：已有执行记录，不隐式重试。
- `REVIEWED_SOURCE_REQUIRES_NEW_PLAN`：已有人工版本，拒绝让旧计划忽略人工选择；保留并继续使用reviewed，不对其自动重跑。
- `AUTO_PROFILE_OVIS_PP_REQUIRED`：auto采用本阶段固定配置；其他模型方案使用手动入口。

[本轮交付与验证](../tasks/reports/P2W-S2-01_TO_06_REPORT.md)列出实际样本、检查与限制。
