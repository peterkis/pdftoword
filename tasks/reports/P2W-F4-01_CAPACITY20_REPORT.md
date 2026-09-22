# F4-01 真实20页容量探测补充记录

2026-09-22。用户指令：“提交，windows不用校验，授权20页容量样本”。
F4-01实现已提交为 `9166f41`，未推送。Windows改记 **SKIPPED_BY_USER**；旧报告保留原时间点结论，不改写。

**一份真实原生PDF的20页连续转换及保存结果离线导出已执行，退出码均0。
这是Core容量探测，不是20页产品质量验收，也没有把常规队列默认3页提高为20页。**

## 修改与固定条件

本轮没有修改转换器、运行包、默认profile、容量常量、模型配置或依赖，仅增加本补充记录。
使用已安装macOS arm64包中原有 `docx_demo.py convert --page-limit 20` 接缝；
主输入转换仅执行一次，不拆页拼接、不重复择优。常规 `pdf2word convert`/UI队列的3页限制保持。

样本在执行前固定：WS/T305—2023物理第6–25页，20个独立物理页，原PDF372,763 bytes。
技术标准属于一般文档；不冒充合同或操作手册。输入包含先前调试页，不作为独立质量泛化样本。
未使用标注作为转换输入。没有50MiB边界测试，不以文件补零模拟实际容量。

安装包自带Python3.12.13及原依赖，cwd为 `/`，精简环境仅PATH；私有探测脚本配置包内路径，
调用未经修改的已打包CLI。输出使用新的Application Support目录，运行证据另存私有tmp。
本次绕过常规队列的native容量守卫，只在既有Core接口显式传20；不能据此宣称队列提交/取消20页已验证。

## 验证

| 项目 | 实测 |
|---|---|
| 环境 | macOS26.6.2 arm64，Mac17,8，64GiB RAM；同一台机器的仓库外安装环境 |
| 原生20页转换 | 退出0，墙钟11.059秒；Core探测计时11.009秒 |
| 物理页范围 | IR及source-map均为6–25，无缺源页、无重复页索引；20份observation |
| 自动DOCX | 988,254 bytes；ZIP CRC与XML语法检查无错误 |
| 来源关联 | 775个来源对象，对应bookmark无缺失、无重复；引用资产均存在 |
| 模型/连接 | 模型调用0；Python审计钩子观测connect/getaddrinfo尝试0，尝试即拒绝；非全系统网络抓包 |
| 内存 | 主转换进程ru_maxrss峰值236.25MiB；约0.1秒间隔采样进程树RSS峰值223.625MiB |
| 离线再导出 | 安装包常规reexport入口，退出0，6.512秒；全部word/ XML及媒体哈希与原auto一致，原auto未变 |
| 保留检查 | 原PDF、旧F4报告、已安装应用文件集合与哈希保持 |

采样进程树峰值不是连续测量，可能漏掉短时峰值；不能用其小于主进程高水位证明内存下降。
不推导P99、吞吐量、20页上限之外的容量或更多文档的性能。页资源原路径按页关闭；IR和原生提取结果
仍随文档累积，未将单次峰值写成恒定内存或分块能力。

本轮未改代码/环境，复用9166f41前的1766项pytest、ruff及228源文件mypy收据，未重复全仓测试。
新增核对是实际20页运行、独立OOXML读取、来源/资产核验及离线导出守恒。

## 未关闭质量项

管线QA为COMPLETE并保留8项未关闭issue，这仅指输出产出。
独立DOCX reader返回 **UNSUPPORTED_TEXT_POSITION**：段落缩进触发其支持守卫，
定位到 `docx_reader.py` 的check_background；108段至少一个缩进属性超过1800 twips，
首个p5-native0（源物理第6页）的left为2294 twips。完整逐对象定位保存在私有诊断中。

这是独立检查未获支持的明确结果；尚未证明发生裁切，也未证明视觉无损。
未放宽检查器、调整样式或重跑换样来消除告警。Word实际输出页数、全页显示、文字遮挡/裁切及跨页关系：**NOT_RUN / NOT_MEASURED**。
20个源页保留不能替代每个字符或全部视觉范围验收。表格可编辑性仍UNSUPPORTED，布局LIMITED，用户接受PENDING。

## 证据与产物

私有根：`tmp/docx-demo/f4-01-capacity20-20260922/`。

- `baseline.json`：提交、原PDF哈希、固定物理页、授权边界。
- `capacity_probe.py`、`execution.json`：完整执行命令、cwd、环境、进程树RSS采样及退出码。
- `probe-receipt.json`、`stdout.log`、`stderr.log`：耗时、主进程RSS、连接尝试及实际产物路径。
- `validation.json`、`independent-docx-reader.json`、`reader-position-diagnostic.json`：完整检查及缩进拒绝依据。
- `offline-export.json`、`preservation-and-export.json`：离线导出与保留哈希核验。
- 真实自动作业：`~/Library/Application Support/PDF2Word/f4-01-capacity20-20260922/jobs/demo-12945ae34acb469090657dcb2af1b3f6/auto.docx`。
- auto SHA256：`cb3dc952dfa6777f16238a47c39078557fe87552ab57322f7e595b0c662f645f`。

## 风险与下一步

本次支持“该样本20页Core转换能产出且来源对象可定位”的运行结论；不能声明20页版式/内容验收通过。
Windows按用户要求跳过，不再作为待执行项；50MiB未测，常规队列仍3页。
下一步建议只针对这份已生成DOCX核验Word中的缩进、裁切与分页，然后决定是否修布局或开放20页常规入口。
本轮未自动扩容、进入下一阶段或批准Beta。
