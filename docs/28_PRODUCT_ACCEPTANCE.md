# P2W-S1-04：离线上传到 Word 验收

状态：实现待审查；工程工具通过不代表产品或人工验收通过。

## 入口与证据

```sh
uv run --locked python scripts/product_acceptance.py run \
  --dataset tmp/productization/frozen-v1 \
  --sample-id <冻结的development电子样本ID> --entry cli \
  --output-dir tmp/product-acceptance/<新的运行目录>
# 同一参数改为 --entry api，使用新的运行目录。
uv run --locked python scripts/product_acceptance.py evaluate-only \
  --bundle tmp/product-acceptance/<运行目录> --output tmp/product-acceptance/<新评分文件>.json
uv run --locked python scripts/product_acceptance.py import-reviewed \
  --bundle tmp/product-acceptance/<自动运行目录> --docx <实际修改后的DOCX> \
  --output-dir tmp/product-acceptance/<新的人工修改版本目录>
```

`run` 验证冻结清单全部成员，限定 initial/development/N 类和已授权本地读取的样本；
不消耗 holdout/reserve，不执行扫描模型。转换子进程只收到输入副本、页码、入口和新作业目录，
不收到标注路径，不导入比较器。CLI 执行原 `docx_demo.py`；API 通过 TestClient 实际上传和下载，
并使用同一个 `pipeline.convert`。API 是进程内 HTTP 路径，不能称为真实浏览器或网络服务验收。
记录实际共享函数调用次数（必须 1），禁止 Internet socket 连接，模型预算为 0；这不是系统级网络沙箱。

返回码：0 表示没有已检出 FAIL；1 表示质量 FAIL；2 表示输入、执行或证据错误。
0 不代表人工接受：必须同时看 NOT_SCORED、REVIEW_REQUIRED、渲染和人工状态。
所有结果目录必须新建。失败诊断、PDF、DOCX、页图、标注只存私有目录，不上传。
公共摘要只含哈希、计数、单位 ID、错误分类、版本和状态，不含正文。

每次运行保留 input.pdf、auto.docx、truth.json、source-map.json、run.json、seal.json、result.json；
有真实渲染器时另保留 rendered PDF/PNG 及哈希。manifest 自身由外部 seal 哈希，避免自指。
`evaluate-only` 不转换、不渲染、不调用模型，生成新评分文件；保留原转换源码指纹，另记当前评分器指纹。
相同证据和相同评分器生成相同语义哈希。不同运行的 DOCX、渲染 PDF 字节哈希可能不同。

`import-reviewed` 新建完整版本包，原 auto 字节保留；新 DOCX 使用保留下来的来源书签对齐。
不猜测新段落的来源，不把原 auto 的渲染证据移植给 reviewed。人工修改次数、耗时未知时留 null；
人工验收一直 PENDING，不能用脚本修改替代真实 Office 操作。

## 对齐与指标边界

新 Writer 增加空来源书签及独立 `source-map.<revision>.json`，仅记录来源页、框、块类型、
图片哈希及关系，不含人工参考答案。原 Layout IR 合同和历史作业不迁移。
比较器独立读取 ZIP/OOXML、正文 w:t、物理逻辑 cell、OMML、媒体和书签。
几何来源只能证明输出绑定到哪个声明的来源区域，不能替代人工验证来源框和裁剪本身。

- 以源页和 bbox 重叠对齐；重叠/较小框面积至少 0.5。一个段落覆盖多条标注时聚成连通组，
  每个实际段落只计一次。无来源文字登记异常，漏页/漏段保留删除分母。
- CER 使用 Unicode 码点，不做 NFC、大小写、数字或数学等价修正。
  raw 不归一化；light 只删除 Unicode 空白；matched 仅诊断已匹配区域。
  精确可编辑覆盖采用整组忠实的保守口径，不用输出字符数作为分母。
- 图内文字不要求独立可编辑，不进入 editable CER；它保留在必要内容分母，通过完整源图另验。
  与 table/formula 共用锚点的重复 text 标注不再次进入正文 CER，并列出排除数量。
- 必要内容包含确认 text/table/formula。图片哈希匹配且源框包含参考框才登记源图保留，
  这种几何保留仍是 REVIEW_REQUIRED，视觉裁剪验收单列 PENDING。
- data_table 按 gridSpan/vMerge 重建逻辑 cell，空 cell 也计分；无边框布局表不因是 w:tbl 就被当作数据表。
  当前比较各标注的表格片段；跨页 continuation 与重复表头的全局语义仍需人工核对，不宣称已验收。
- 公式支持字面 token、分组、分数、上下标和明确列举的符号命令；独立解析参考结构与 OMML。
  支持的命令见 `scripts/acceptance/formula.py`。矩阵、分段、未知命令显式 unsupported，
  全公式分母保留；不称为完整数学 AST、视觉或化学语义验收。
- 关系比较绑定两端的预测边及确认边；无法唯一绑定的端点不得算正确。
  阅读顺序分别记录正确、错误和缺失；同一段落内无法独立定位的锚点对记未评分。
- 降级面积按真实放置并核对哈希的图片源 bbox 并集计算；普通 figure 排除。
  越界框报错，不裁剪后假装合法。合成/旧来源映射只能登记声明面积。

结果 Schema：`specs/product-quality/result.schema.json`。
文件结构合法、自动内容、可编辑性、真实渲染、人工验收是不同状态。
LibreOffice PDF/PNG 是真实渲染；HTML 从不作为 Word 渲染证据。

## 回归与后续人工验收

`tests/productization/test_acceptance_harness.py` 使用手写参考与实际 DOCX，包含超过 12 种损坏。
它不从转换器生成预期答案。另运行真实 CLI/API、证据篡改拒绝、重复评分、版本隔离和 Schema 正反例。

人工仍须在实际 Word/LibreOffice 打开 auto 副本，插入/删除两行并修改公式、表格（若存在），
记录应用版本、版式变化和实际耗时，然后导入 reviewed。仅运行脚本与查看页图不完成这一步。
本项不关闭 T0012/T0602/T0603/T0604/T0605/T0610，不执行 S1-05，不推送、不合并。
