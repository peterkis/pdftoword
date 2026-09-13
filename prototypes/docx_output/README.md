# DEMO-001：PDF → Word 输出审阅原型

当前 demo 版本为 0.5.0，已支持有限 LaTeX → 可编辑 Word 原生 OMML 公式（分式、平方根、上下标及常用符号）；不支持或关键符号冲突的表达式才保留源图。

这是独立的本机输出验证工具。目标是打开真实 DOCX、检查内容与题图关系、留下人工修正记录；不代表生产转换链路、T0002、T0017 或完整 P1/P2/P3 已验收。边界见 [prototype-scope.md](prototype-scope.md)。

在仓库根目录使用 Python 3.12 和现有 uv 环境：

```sh
uv sync --locked
uv run --locked python scripts/docx_demo.py replay \
  --run-dir tmp/raster-regression/runs/t0016-mac-20260911T030753Z-r2 \
  --variant jpg --repeat-index 1 --output-root tmp/docx-demo/jobs
uv run --locked python scripts/docx_demo.py serve --host 127.0.0.1 --port 8765
```

浏览器打开 <http://127.0.0.1:8765>。端口冲突时服务退出，工具不会杀死已有进程。CLI 输出真实 DOCX 的本机绝对路径。所有作业都分配新 `demo-<uuid>`，不覆盖非空目录。`--output-root` 只能位于忽略目录 `tmp/docx-demo/` 内；非默认根的作业在后续 CLI 命令中须传相同 `--output-root`。网页展示默认 jobs 根。

## 三个入口

- **Replay**：只读校验历史 seal、输入、request、response 和 prediction 的已存字节哈希，按 provider + variant + repeat 选择完整响应。默认使用 Ovis 的 JPG 第 1 轮正文/公式与 PP 同轮几何；PP 识别文本不进入正文，不挑最好轮次。指定 --content-provider ovis 可恢复独立回放。使用 `--content-provider pp` 才运行三家响应参与的旧 PP 基线。私有响应是采集工具保存的 `strip_media(body)`，不会当作发现工具的 `response` 包装。不会调用 evaluate/promote 或读取 GT 正文。没有私有 run 时明确报出缺少文件；公开脱敏夹具不可替代真实正文。网页使用固定 run；CLI 可显式指定其他已封存的 COMPLETE run（仍校验指定样本的 JPG 哈希）。
- **Native PDF**：1–3 页正常编码、单栏、水平文字的简单电子 PDF。原生字符、字体、字号、bbox 和源页渲染来自 PDFium；临近矢量组件成组裁剪，图内文字只保留在图中。字符、重复、几何、图像占比异常进入 `NEEDS_ROUTE_REVIEW`；没有模型请求。页码从 1 开始，IR 使用原始 PDF 的 0-based page_index。
- **Raster live**：JPG/PNG，或由用户明确确认的扫描 PDF 页面。必须勾选发送授权和无 Authorization 确认；PDF 还须确认扫描页。默认 Ovis 内容＋PP 几何，每页各一次；可选 Ovis 独立或 PP 旧基线。Monkey 可选一次；额外 Ovis 复核仅用于 PP 旧基线。串行、无重试；成功、失败及未完成请求均有缓存，预览、保存、导出不再次识别。服务配置只从进程环境读取，见下方；不更改 FRP，不访问图片 URL。

```sh
uv run --locked python scripts/docx_demo.py convert \
  --input '/本机已授权文档.pdf' --pages 1-2 --mode native \
  --output-root tmp/docx-demo/jobs

# 此命令明确允许向既有本机 FRP 服务发送输入；默认每页串行调用 Ovis、PP 各一次。
uv run --locked python scripts/docx_demo.py convert \
  --input '/本机已授权试卷.jpg' --mode raster \
  --allow-model-calls --confirm-no-auth --output-root tmp/docx-demo/jobs

# 扫描 PDF 需要额外 --confirm-scan；可选 --ovis / --monkey 分别增加每页一次调用。
uv run --locked python scripts/docx_demo.py convert \
  --input '/本机已授权扫描.pdf' --pages 1 --mode raster \
  --allow-model-calls --confirm-no-auth --confirm-scan
```

默认配置：`PP_BASE_URL=http://127.0.0.1:8080`、`OVIS_BASE_URL=http://127.0.0.1:8000`、`OVIS_MODEL=ovis-ocr2`、`MONKEY_BASE_URL=http://127.0.0.1:9000`、`MONKEY_MODEL=MonkeyOCRv2`。仅允许既定回环端口和冻结模型标识。补齐 NO_PROXY/no_proxy，HTTP 客户端禁用代理继承、重定向和隐式重试，不发送 Authorization。不会读取或修改 `.env.local` 中的秘密；需要覆盖地址时在启动命令前设置上述进程环境。

## 审阅与人工修正

1. 选择已有作业或点击 Replay（默认 Ovis 文字＋PP 布局，可切换 Ovis 独立回放或 PP 旧基线）。左侧是原始页面；右侧是**结构重建预览**。它不是 Word 渲染。
2. 点击右侧块，查看左侧对应橙色框、候选原文、来源和差异。选择源页与缩放可检查局部。
3. 填写操作原因，再编辑文字、显式接受 Ovis 候选，或将光标放在文本边界点击“拆分”。支持与下一段合并、上移/下移。公式不能从表达式内部拆开；在表达式之间拆分会保留两侧图片且不重复。
4. 在左侧按下并拖出区域，或填写 point bbox，再点击“应用裁剪框”。也可选择图引用题目、图题属于图、标签属于图等关系。语义关联与物理展示位置分开记录；需要改变展示顺序使用移动。移动分组中的单块会解除该展示组，须检查标签和图片是否仍相邻。
5. editable 要有明确文字；preserve_image 使用源图区域；review_required 保留结果并提示复核。有明确原因的编辑/候选接受会重新生成支持语法的 OMML，不再继承旧图片降级；只有不支持的语法且没有对应源区域时，才回退原段区域图，不猜坐标或输出裸 LaTeX。
6. 待保存操作显示在修正记录中，可撤销最后一步。点击“保存修正并导出”产生 `overrides.json`、`layout.reviewed.json`、`reviewed.docx`、`qa.reviewed.json`，不覆盖 auto。再次保存会归档此前 overrides 账本。预览临时使用 `layout.preview.json`，不算正式人工修正产物。
7. “实际 DOCX 渲染”以独立 LibreOffice profile 转为 PDF，再由 PDFium 渲染逐页图片。未保存修正先保存；无渲染器或失败时明确提示 `DOCX_VISUAL_REVIEW_PENDING`。

Ovis 是候选，尤其合并块与短段匹配时可能只有部分内容。接受前必须对照完整原块与候选，不能把候选相似度当正确率。`<`/`≤` 差异保持待复核；图内原符号随公式区域图片保留，不把模型候选自动“纠正”为真值。

CLI 可重现保存后的修正：

```sh
uv run --locked python scripts/docx_demo.py export --job-id '<实际job-id>' --revision reviewed
uv run --locked python scripts/docx_demo.py render --job-id '<实际job-id>'
uv run --locked python scripts/docx_demo.py render --job-id '<实际job-id>' --revision reviewed
```

没有 LibreOffice 时，仍有真正的 DOCX 和包结构检查。请用 Finder 打开作业目录中的 auto.docx 和 reviewed.docx，在本机 Word 逐页对照：文字与符号、选项顺序、七个图域完整性、图与图题分页、公式大小、图片和表格越界。未运行 Word 不代表 Word 视觉验收通过。工具不会下载 Office 或调用云转换。

## 私有文件与指标

每个成功作业包含 `input-manifest.json`、`request-manifest.json`、`layout.auto.json`、`auto.docx`、`issues.json`、`assets/`、`review/index.html`、`qa.json`。实际渲染另存 `rendered/<revision>/`，失败尝试保留诊断，不拿旧渲染当新结果。目录 0700、文件 0600；不得将原图、原文、候选、DOCX、rendered 或 overrides 加入 Git。

QA 分别记录执行、内容复核、结构复核、包合法性、实际渲染与视觉复核状态，以及模型调用、可编辑字符、图域、公式图片、区域降级、人工操作和未解决 issue 数量。`fallback_area_ratio` 的分子是每页已引用公式/降级原 bbox 的矩形并集，分母是全部选中页的 point 面积；普通配图不算文字降级，不将图片数量当准确率。可编辑字符计数排除各段/内嵌片段首尾空白，包内文字计数另列。Schema 要求非空数值的 system/classification score 使用明确的未评分哨兵 0，不是模型概率；engine_confidence 未提供时始终 null。

## 可复现的合成 Native PDF

以下测试生成器只使用自有短句与普通图形，写入私有目录，不替代真实试卷：

```sh
uv run --locked python - <<'PY'
from prototypes.docx_output.common import PRIVATE, private_dir
from tests.demo.synthetic import make_pdf
private_dir(PRIVATE / 'synthetic')
make_pdf(PRIVATE / 'synthetic' / 'native-bilingual.pdf')
PY
uv run --locked python scripts/docx_demo.py convert \
  --input tmp/docx-demo/synthetic/native-bilingual.pdf --pages 1 --mode native --synthetic
```

## 开发验证

```sh
uv sync --locked
uv run --locked pytest
uv run --locked ruff check .
uv run --locked mypy .
uv run --locked python scripts/validate_task_catalog.py
uv run --locked python scripts/validate_model_baseline.py
git diff --check
```

默认测试全部离线。MockTransport/模拟 HTTP 只证明 bridge 契约和失败处理，不能冒充本轮真实 live 识别。历史源目录不作为测试输出目录。新增开发依赖仅用于 demo：python-docx、pypdfium2、FastAPI、uvicorn、python-multipart、lxml 及类型存根；不回填历史运行的锁文件哈希。


## 0.3.0 Ovis 独立输出验证

```sh
uv run --locked python scripts/docx_demo.py replay \
  --content-provider ovis --variant jpg --repeat-index 1 \
  --output-root tmp/docx-demo/jobs
# 明确选择旧 PP 基线用于对照
uv run --locked python scripts/docx_demo.py replay --content-provider pp
```

Ovis 的 LaTeX 直接进入 OMML，普通图片取自其 `images/bbox_...` 标签的 normalized_1000 坐标，按原图裁剪；正文和公式没有精确 bbox 时标明未知，整页框仅为来源参照。图选项标签按明确的相邻模型输出成组；图题引用与展示位置分离，缺少题干仍提示。局部图片、未知 HTML、无法解析且没有几何的公式会明确拒绝，不获取外部图片或伪造精确框。

0.3.0 当时仅改变 Replay；0.5.0 已统一 Replay 与上传重建路径。没有修改生产角色矩阵或历史 Gate 证据。实际 Ovis 对照产物及限制见 DEMO001_REPORT 的 0.3.0 更新。

## 0.4.0 Ovis 内容＋PP 几何

当前 CLI/UI 默认 Replay 为 Ovis 文字与公式＋PP 几何。复现：

    uv run --locked python scripts/docx_demo.py replay --content-provider ovis-pp

PP 只贡献区域标签/框、OCR 行框与公式框几何；block_content、rec_texts、rec_formula 不进入文本匹配或输出。图域唯一重叠匹配后采用 PP 框裁剪；正文按缩进、垂直行框和类型顺序关联，歧义时保留审阅项。共享行框不能冒充四个选项的精确边界。

选项恢复横排，第一题四图可为一行，第六题为两行两列；仍使用正常段落/OMML/无边框表格，自然分页，不用绝对定位文本框。纯文字列宽分配不修改来源 bbox，也不缩小字体。人工拆分/合并/移动解除受影响的文本布局组。

0.4.0 当时只验证回放；0.5.0 已调整 demo live 默认方案，生产角色矩阵未改，也未部署单独的 PP 检测服务。Ovis 独立模式仍可通过 --content-provider ovis 使用，PP 旧基线为 --content-provider pp。


## 0.5.0 通用布局规则与失败保护

规则集中于 layout_rules.py（layout-rules/1.0），以 PDF point 和典型文字行高计算容差，支持有限单栏试卷中的题干、2/4 选项、单行/双行及题图组。不含题号坐标、样本哈希分支或人工改写正文。曾经视觉检查发现的列宽问题已修入通用 writer 规则；规则来源有样本视觉反馈，不能据此宣称对任意文档泛化。

先检查几何尺寸、越界、重复区域、多栏与旋转，再在副本中关联；内容、候选、公式、图片顺序、映射完整性和放置唯一性全部通过才应用。否则保留 Ovis 内容与流式输出，创建 LAYOUT_RULES_FALLBACK 审校项。qa.json 记录规则版本、有效参数和逐页 APPLIED/FALLBACK，混合结果为 PARTIAL。此检查不评价 OCR 正确率。

Replay 与授权上传共用 reconstruct。上传默认 Ovis→PP 串行各一次；PP 失败保留 Ovis，Ovis 失败标记 PRIMARY_CONTENT_MISSING 与输出不足，不静默换成 PP 正文。缓存失败不重试，Native 不调用模型。PP 请求仍使用冻结的 layout-parsing 参数，服务仍可能识别文本，但本方案只消费几何。

新增测试为合成响应的尺寸/题数/选项排列变化及故障注入，不是不同真实图片的模型验收。复杂表格、多栏、旋转、未知公式语法和低清晰度内容仍需单独验证。
