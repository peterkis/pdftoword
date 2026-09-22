# P2W-F2-03：显式候选配置接回用户入口

实际 HEAD：`e1eef44`。承接 F1-04 未提交切片，本轮新增改动也未提交、未推送。
工程入口与有限 Word 闭环已核验；用户/产品接受 PENDING，生产默认不变。

## 修改

- `config/profiles/fidelity-v3.1.json`、`output_profiles.py`：新增显式输出候选，配置快照随 Layout IR 保存。启用既有 Flow 与可编辑基础样式，承接 F1-01/F1-04；不改识别、网关或授权。
- `pipeline.py`：convert/replay 接受独立 output_profile；finish 在既有结构结果上规划输出，reviewed 沿用候选与用户样式。QA/render-manifest 显示实际配置；旧默认仍 legacy。
- `style_replay.py`：复用原有离线重导出，支持 auto/reviewed 来源；验证资产/源图，拒绝输出写入源目录，记录 parent job/revision/layout hash，派生作业有独立 ID。冻结结果不重复调用 DocVortex 处理，worker/锁定依赖未升级。
- `scripts/docx_demo.py`：既有 convert/replay 新增 `--output-profile`；新增薄入口 `replay-job`，内部调用同一重导出函数；可选 `--style-profile`。serve 支持指定 output-root，status 显示配置。
- `server.py` 与既有 static 页面：上传/回放使用相同候选；已有任务增加候选重导出按钮，沿用 session/origin/单队列保护。状态显示实际输出配置、导出状态、限制与来源；网页结构预览和实际 Word 仍明确分开。
- `tests/demo/test_candidate_profile.py`：5 个集成测试覆盖 CLI 默认/候选、真实上传处理链、已有作业派生、API 审校、reviewed 再导出、父来源、资产漂移/嵌套目录拒绝，以及禁止重复结构处理和网络连接。

没有新增解析器、渲染内核或业务数据库。F1-04 六个未提交文件哈希保持，不覆盖其改动。

## 可执行入口与回滚

```sh
# 新原生输入，不触发模型（页码按实际文档填写）
uv run scripts/docx_demo.py convert --input /path/to/source.pdf --mode native \
  --pages 1 --output-profile fidelity-v3.1

# 已有冻结结果；源目录只读，无需用户手工输入 hash
uv run scripts/docx_demo.py replay-job --source-job /path/to/existing-job \
  --revision auto --output-profile fidelity-v3.1

# reviewed 来源也可派生；样式 JSON 示例为 {"body_size_pt":15}
uv run scripts/docx_demo.py replay-job --source-job /path/to/existing-job \
  --revision reviewed --output-profile fidelity-v3.1 --style-profile /path/to/style.json

# 在现有页面查看本轮真实产物
uv run scripts/docx_demo.py serve --port 8873 --output-root tmp/docx-demo/f2-03-20260921/jobs
```

回滚/退出候选：新输入省略 output-profile（或选择“原有输出”）；保留原始旧作业 auto 作为回退。
不要把候选 IR 上的配置删除理解成自动还原旧布局；使用原作业。没有更改生产默认需要撤销。
本轮临时 8873 测试服务和浏览器已结束，上述命令可重新打开。

## 真实闭环与证据

私有目录：`tmp/docx-demo/f2-03-20260921/`。

1. **新原生输入**：用户提供的 WS/T 306—2023 原 PDF，物理第 4 页，通过当前 CLI convert/native 生成候选。有效原生文字优先，不读取标注生成；真实输入是新作业，不冒充扫描推理。`native.docx` 与 `execution.json` 中的 native_job 保存结果。
2. **旧扫描结果**：复用 F1/F2 同一数学试卷第 1 页冻结作业，通过 CLI replay-job 导出 `scan.docx`。图组四列能力经用户入口生效。没有第二次识别或结构重处理。
3. **审校**：既有 `/api/review` 将标题追加明确诊断标记，实际保存 `reviewed.docx`；再通过 CLI export 及 reviewed 来源 replay-job 导出。该标记只证明审校闭环，不计识别成绩；原 auto 哈希不变，人工修改/锁保留。
4. **样式再导出**：同一自动试卷经 CLI `--style-profile` 改为 15pt、Arial/Songti SC，生成 `styled.docx`；源 blocks/关系不变，正文、数学文本、书签和图片与 scan.docx 相同。15pt 是显式用户样式诊断，不声称扫描源字号为 15pt。
5. **实际页面**：本机浏览器打开既有审校页，确认候选名称、已导出待复核、0 请求和已知限制；实际点击按钮生成新候选作业，下载链接有效。`candidate-ui.png` 保存当前页面，不能当 Word 视觉证据。
6. **实际 Word**：styled 的独立 `word-edit.docx` 在 Word 中打开，选项图保持 1×4；插入 F203 → 保存 `word-inserted.docx` → 撤销保存 → 关闭重开。`word-page-1.png`、`word-reopened.png` 为实际屏幕；磁盘复核正文、数学文本、书签和图片恢复一致。源一页仍排为两页，未声称整页保真。

`execution.json` 记录实际 CLI argv/退出码与 API 状态；`entries.log` 是执行记录。
`verification.json` 核验五组 auto/reviewed 的 source-map 书签包围真实文字/OMML/图像 payload，
并核验源作业、前三轮证据和 F1-04 工作区改动保持。`jobs/` 保存实际 auto/reviewed、IR、RenderPlan、来源图、QA、父来源与审校轨迹。

## 验证

|命令/检查|结果|
|---|---|
|`uv run pytest -q`|退出 0；1698 passed，1 个既有 Starlette 弃用警告|
|最终 `uv run pytest tests/demo/test_candidate_profile.py tests/productization/test_style_profile.py tests/productization/test_renderer_boundary.py -q`|退出 0；47 passed；覆盖后续 CLI 样式/serve 参数接线后的相关链路|
|`uv run ruff check .`|退出 0|
|`uv run mypy prototypes/docx_output/output_profiles.py prototypes/docx_output/pipeline.py prototypes/docx_output/style_replay.py prototypes/docx_output/server.py scripts/docx_demo.py tests/demo/test_candidate_profile.py`|退出 0；6 files|
|`node --check prototypes/docx_output/static/app.js`|退出 0|
|`uv sync --locked --offline`|退出 0；无下载|
|`PYTHONPATH=. uv run python tmp/docx-demo/f2-03-20260921/run-entries.py`|退出 0；公共 CLI parser + 实际业务链、API 审校，阻断 socket connect/connect_ex；连接尝试 0|
|`PYTHONPATH=. uv run python tmp/docx-demo/f2-03-20260921/verify.py`|退出 0；来源/内容/锁/资产及实际 payload 范围检查|
|实际本机 UI 与 Word|页面候选派生成功；Word 编辑保存重开已执行，未签用户接受|
|`git diff --check`|退出 0|

mypy 初次因测试使用 `scripts.docx_demo` 与项目的 `docx_demo` 模块路径重复而失败，已按现有项目导入方式修正并复验。
全仓历史 tmp 的类型问题未删除或隐藏，本轮运行的是定向类型检查。

## 风险与下一步

- 未选择 F2-02：A 修复无需新模型；B 的表格拓扑/复合图结构缺口仍需有界本地归因，不借本轮增加模型或宣布已经解决。
- 输出配置不补缺失的单元格结构，不承诺扫描原字体和原分页；实际 Word 两页仍是已知限制。原生样本本轮以 CLI/包与来源检查为主，未把它计为完整 Word 视觉验收。
- 新扫描/混合真实请求 NOT_RUN；本轮模型调用 0。已有模型、服务、FRP、DocVortex worker、权重和锁定依赖保持。
- U1 INCONCLUSIVE/PENDING、SDK NOT_RUN、probe_c=false 均不倒改。候选接回入口不等于生产默认获批。
- 本轮到 F2-03 停止。下一主线建议 F3-03，用现有两 case 划定内容与布局的实际可用范围；F3-01/F3-02 仅按具体样本选入，不自动开启。
