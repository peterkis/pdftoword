# P2W-S1-03 数据集准备与标注规范

本工具准备离线评测数据，不运行转换、模型、指标评分或 Word 验收。
生产 Schema/原 T0015/T0016 保持不变。私有数据清单使用独立 `product-dataset/1.1`，
计划包 `product-dataset/1.0` 只是宽松提案模板；不原地替换计划包 Schema。

## 入口与状态

```sh
# 建立新的空私有工作目录，返回 3/BLOCKED_INPUT 是预期结果
uv run --locked python scripts/product_dataset.py init --root tmp/productization/new-dataset
# 校验既有清单，授权字段通过后才读取 corpus 中的源文件
uv run --locked python scripts/product_dataset.py validate --manifest tmp/productization/manifest.v4.json
# 仅当真实输入、来源和标注均 READY 时可创建新的冻结版本
uv run --locked python scripts/product_dataset.py freeze --manifest tmp/productization/manifest.v4.json --output tmp/productization/frozen-v1
```

退出 0 表示数据准备条件 READY，不代表识别质量通过；2 为结构/授权/hash/引用等错误；
3 为 BLOCKED_INPUT、BLOCKED_PROVENANCE 或 BLOCKED_ANNOTATION。默认输出仅含聚合计数/错误码，
不含源路径、正文、转录或图片。命令的创建目标限定在仓库忽略的 tmp/productization 下。
路径相对于清单所在目录的 corpus/ 或 annotations/，禁止绝对路径、穿越和符号链接。

## 真实输入与许可

每份源文件登记 sample_id、document_family、source_sha256、original_sha256、
input_type、连续 selected_pages（最多 3 页）、许可依据、local_read_authorized、敏感性、
允许发送的 Provider、调试参与状态、family 审查状态、标注路径和状态。
ID 使用不含文件名的随机 32 位十六进制标识。用户原始文件名只保留在私有 intake 记录。

许可 CONFIRMED 表示用户明确授权本地评测使用，并登记其声明依据；不是工具对版权/作者身份的法律认证。
本轮用户允许本地读取、声明无敏感内容；可见出版物/标准的署名保持原样，不改写为合成或原创内容。
model_send_authorized=false、allowed_providers=[]。本项从未批准外发、再分发或模型推理。

SHA-256 可发现相同字节，但不能识别所有未申报的重采样/截图/版本关系。
original_sha256 和 family 仍须来源记录及人工核对；family_review=PENDING、调试历史=null 会阻止 READY。
不得因为有 PDF 图片对象就把正常图文电子页标 M，也不得把纯扫描页默认标混合页。

## 分类、分组与来源防泄漏

目标至少 12 个独立 family、24 页；N6/R6/M4/T4/C4，development12/validation6/holdout6。
N 是正常电子内容，R 是清晰扫描，M 需要真实局部扫描/隐藏层等混合证据，T 是普通数据表，
C 是数学/英语/化学图文。每页只记一个类别；多特征不重复凑数。UNCLASSIFIED 不计入类别配额。

- 同 family、同 source hash 或同 original hash 不能跨 split；派生物必须声明 original_sha256。
- 一个原稿的多格式/页段不能充当多个初始独立文档。独立文档数按 family 统计，文件数另列。
- initial 进入首批计数，reserve 留待选择，regression 只作已知回归；后两者不计初始配额。
- 已调试数学试卷的已知 JPG/PNG hash 单独登记于 development-only-sources，仅可 development/regression。
- 已参与调试的材料禁止进入 holdout；tuning=true 必须有事件。
- 已访问/标注的 holdout 必须有 holdout_access 事件，区分标注准备与实际规则调试。
- 同系列分册和同一标准新旧版在本轮先保守归组；来源核对后可在新版本中说明拆分理由，不能无记录换集。

## 标注合同

使用 `product-annotation/1.0`。每份标注保留 sample_id、source_sha256、annotation_version、
reviewer_type（human/agent_visual）、reviewer_id、coverage_complete、anchors、units。
每个 unit 包含稳定 unit_id、1-based 源页、kind、confirmed/uncertain、reference、note。

| kind | reference 内容 | 确认规则 |
|---|---|---|
| text | text 原样转录 | 不能空白，不修正原文 |
| formula | text 原表达式 | 空展示定界符不能充当参考，不化简数学 |
| table | rows/cols/cells，每 cell 有 row/col/rowspan/colspan/text | 0-based 网格；跨度合法、无重叠、完整覆盖，空单元格 text 可为空 |
| reading_order | anchors ID 有序列表 | 至少两个不同且已登记的锚点 |
| figure_edge | from/to/relation | 两端锚点存在，belongs_to 为图到题、caption_of 为图题到图、references 为题到图 |
| route | native/scan/ordinary_figure/mixed/blank | 未确定则 uncertain，不把未知路由记为确认 |

anchor 记录 id/page/kind/bbox；bbox 为 PDF point、左上原点，[x0,y0,x1,y1]。
几何未确认时 bbox=null，不能猜框。校验检查合法范围顺序和引用，不取代人工判断边界是否真实。
覆盖完成的非空正文页必须有内容单元；T 类完成标注必须有 table。仅 route 观察不能冒充全文 GT。

REVIEWED_HUMAN 需要 human 标注且 coverage_complete=true；agent_visual 不能升级成人工结果。
真实人工来源只能由实际参与者确认，工具不能从字符串证明现实中的人已审阅。
至少每类一份人工核对。分母只计确认参考，不确定项单列，尚无输出时 scored_count=0、value=null、NOT_SCORED。
当前 metrics 的单位计数只面向真实 initial，reserve 和 synthetic 不混入分母。

## 访问、修正与冻结

私有 events 登记 event_id/sample_id/action/actor/timestamp/reason。action 支持 holdout_access、
tuning、reassign、replace、human_review。变更 split、纳入调试或换样本必须在新清单版本中记录理由。
采用版本文件而非覆写：manifest.vN.json 与 annotations/<id>.vN.json；保留旧版和对应 SHA。

freeze 只有 READY 才执行，创建新目录，复制经 hash 校验的 corpus/annotations，写 FROZEN manifest
和外置 seal.json。seal 不自指；验证检查文件集合与全部 SHA，篡改/缺失/额外文件均失败。
创建目标已存在即拒绝；失败时保留不完整目录作为诊断，不将缺 seal 的目录当成功冻结。
不提供覆盖旧冻结版本的接口。冻结是工具协议，不宣称能防止有权限的用户在工具外重写并重算 hash。

转换工具不导入本清单标注模块；本轮也未向既有转换 pipeline 接入 GT。
S1-04 后续转换进程只获得输入/profile，不获得 annotations 路径；评测进程独立读取已冻结版本。

## 合成故障集

公开的是 [生成器与说明](../tests/productization/synthetic/README.md)，实际生成文件位于忽略目录。
包括损坏/加密、空白/标题、CropBox/四方向、透明/重叠/隐藏层、字符与公式/HTML/URL、
非法表跨度/题图关系、请求半成功/STARTED、坏缓存、跨作业路径。
这些验证是合成故障性质与校验器回归，不能替代真实 OCR、N/R 上传闭环或 Office 验收。

## 当前私有准备记录

本轮私有入口为 tmp/productization/manifest.v4.json；原始接收记录保留 intake.private.json、
intake.v2.private.json；每份授权源文件复制为 opaque-id.pdf，原 Downloads 文件不修改。
分组和标注仍为草稿，未冻结。当前数量、限制和命令证据见 [S1-03 报告](../tasks/reports/P2W-S1-03_REPORT.md)。
