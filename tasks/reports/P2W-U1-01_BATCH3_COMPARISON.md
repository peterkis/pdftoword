# P2W-U1-01 — Batch3 三路真实比较简报

状态：PARTIAL。实际执行和 Word 产物已交付；不能等同于全量内容准确率或用户接受。

## 实际记录

- 开始/结束 HEAD：`32b9e13d9ef752fc6c945ec62e58abb031da837f`，分支不变，未提交、未推送。
- 激活依据：用户明确要求实施29页三路比较，授权指定材料发送官网v4 API；运行中又授权修改三页上限。
- 改动：新增隔离实验 `experiments/recognition_compare/` 与合成测试；PDF/CLI入口新增显式 `page_limit` / `--page-limit`，默认仍3页。未改模型提示词、默认路由、几何选择或Renderer算法。
- 6份同源选页副本，29页，物理页映射及像素校验保留。22条修订和2项确认在独立参考中合并。辅助初标与用户确认项分列；非全量人工金标签署。
- 18份真实DOCX：A六份、B六份、C六份。B/C原始官网DOCX字节封存，没有本地重排版替换。
- 原始02运行保留A的G2/G3阻断；03运行继承其余16份，不重新推理。G2/G3在授权后首次推理，分别显式允许12页/9页。保留前后源码指纹和冻结请求清单。
- A实际300次请求/533上限：5、252、26、6、2、9。官网12个文件解析任务/58页次；每个文件设置 `is_ocr=true`。HTTP调用另记；线上内部模型调用数unknown。在线收据的本地 `model_calls=0` 不表示官网零推理。
- A Renderer：FlowRenderer v1。官网v4 API结果自报后端3.4.4；B pipeline，C hybrid。C自报effort medium，请求未设置effort。官网内部DOCX Renderer身份unknown；不冒称本地MinerU4.0.4或standard。
- Mac Word 16.113.1实际打开18份、导出18份PDF，共164页。A纸张不匹配的打印PDF保留为环境异常证据；主对比改用本地另存PDF。未使用Microsoft在线转换。
- 17份正文编辑探针；8份表格/公式代表性编辑；G5-A无可编辑正文。G2-A虽有2个OMML对象，实际公式编辑未证明。保存副本存在数学run拆分/字符归一化，原件未被修改。探针污染导出隔离，不进入质量比较。
- 164输出页及29源页完成接触表级版式巡检，代表性缺陷另看原尺寸图；非全部逐字/公式精查。用户接受PENDING。

## 两层结果

识别层：几何对齐存在大量歧义。B/C辅助参考共同文本子集274单位；用户确认共同子集仅5单位/96字符。复杂公式结构实际评分覆盖B 4项、C 2项，其余未评分明确保留。不能将不同覆盖分母的CER直接排名。扫描续表三列要求已记录，旧两区域网格未被冒充修订金标。

Word层：

|组|源页|A|B|C|
|---|---:|---:|---:|---:|
|G1|2|2|3|2|
|G2|12|34|34|33|
|G3|9|10|7|7|
|G4|2|2|3|3|
|G5|1|1|5|6|
|G6|3|3|4|5|

A局部保图能保留源页外观但牺牲编辑能力；G2大量公式/行片段散开，G6封面主图遗漏。B/C多栏与题图被重排为长篇流式内容，存在跨源页表格拼接、表格公式保留LaTeX和列宽失真。C扫描教学表出现严重的长字符串撑列及跨页问题。未生成加权总分，证据不足以指定唯一赢家。

## 命令与退出码

|命令（参数占位，不含私有路径）|结果|
|---|---|
|`run_compare.py prepare`|首次预检路径错误exit1，修正后新目录prepare exit0；无推理重跑|
|`run_compare.py run --arm A/B/C --group G1…G6`|最初A G2/G3 exit1；其余exit0，A均PARTIAL|
|`run_compare.py extend-page-limit`|exit0，冻结新增509请求上限|
|`run_compare.py run --arm A --group G2/G3`（03）|均exit0、PARTIAL、首次推理|
|`run_compare.py evaluate/report`|exit0；离线重评1807个冻结/原始文件哈希不变，模型调用0|
|`.venv/bin/python -m pytest -q`|exit0，1672 passed、1既有警告|
|`.venv/bin/python -m pytest tests/experiments tests/demo/test_output.py -q`|exit0，99 passed|
|`.venv/bin/python -m ruff check .`|exit0|
|`.venv/bin/python -m mypy .`|exit1，最终全仓63错误/11个历史私有tmp文件（221文件）；不是整仓绿|
|定向mypy（实验及3个实现入口）|修复实验命名空间/报告类型问题后exit0，12 source files|
|本地报告链接核验|exit0，517链接、0缺失|

全仓mypy错误来自历史临时脚本和此前保存的上游源码片段；未删除或抑制。开发过程的失败收据保留。未运行安装/环境同步，旧依赖清单保持不变。

## 私有证据定位

相对仓库：

- `tmp/docx-demo/compare-batch3-20260921-03/reports/final/index.html`
- 同运行目录 `conclusion.md`、`delivery-receipt.json`、`frozen/`、`runs/G*/A|B|C/receipt.json`
- 同运行目录 `runs/G*/A/artifacts/A.docx`、`runs/G*/B|C/artifacts/B.docx`
- 同运行目录 `analysis/final/`、`evaluations/full-v1/`、`visual-review.json`
- 同运行目录 `word-audit/final/`、`word-review/`、`word-render-pristine/`
- `tmp/compare-batch3-audit/checks/` 与 `preservation-final.json`

原有7542个文件哈希均未变化。公共文件不含样本文字、原始响应、Token、签名URL、个人路径、字体文件或私有拓扑。

## 失败、回退和停止范围

A的历史页数阻断仍保留；实际推理中的降级不标成可编辑成功。Word首次被锁屏/捕获失败阻断，解锁后执行；打开过多检查窗口引起卡顿，已关闭27窗口，此后逐份导出即关闭。打印纸张裁切与辅助渲染器中文字体问题分别记录，未误归为模型遗漏。

剩余限制：复杂公式结构覆盖不足、部分几何匹配需裁决、图题语义关系未提供或未完全核验、系统字体清单未在首个Word打开前完整封存、逐字/公式精查非全量、用户接受PENDING。本轮固定矩阵已用尽，不追加识别或边测边修。未切换生产路线，不激活U1-02。

本地MinerU4.0.4 SDK链路仍NOT_RUN，本轮官网v4比较不能代替原SDK验收。有效工程时间约1.7小时（保守按全部墙钟计入，模型/下载等待未扣减；最终精确墙钟见私有交付收据）。

A的300条请求中，PP 252条、Ovis 19条，Monkey 29条；Monkey有7条NO_VALID_GEOMETRY、5条INVALID_CANDIDATE_WIRE_TYPE，其余17条COMPLETE。原始响应全部保留；这些是几何候选/适配结果，不归为网络失败，也不据此断言裸模型识别能力。
