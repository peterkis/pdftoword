# F4-01 本地运行候选与恢复

2026-09-22。仅 macOS arm64 内部候选；原生 PDF 新输入和保存结果离线导出。
表格/图内文字可能保图，布局受限；没有新增扫描识别能力。生产 CLI 的 legacy 默认不变。

## 安装与使用

解压完整 `PDF2Word-F4-01.tar.gz`，保持目录结构。双击 `Start.command`，或在包目录执行：

```sh
./pdf2word serve --port 8765
```

浏览器打开 `http://127.0.0.1:8765`。关闭终端前用 Ctrl-C 停止服务。
包自带 Python、运行依赖、隔离的 DocVortex 依赖和许可文件；不需要 uv/pip、源码 checkout。
这是未签名/未公证的内部包，不自动更改系统 Gatekeeper 设置。不打包系统字体或 Office XSLT。

```sh
./pdf2word convert --input /absolute/input.pdf --pages 1-3
./pdf2word reexport --source-job /absolute/saved-job --revision auto
./pdf2word reexport --source-job /absolute/saved-job --revision reviewed
./pdf2word status
```

默认数据目录为 `~/Library/Application Support/PDF2Word/runtime`；可在启动前用
`P2W_PRIVATE_ROOT` 指定新的绝对路径。`--output-root` 必须在该私有目录内。
导入保存作业要复制完整目录，包含 IR、来源文件和全部资产，不能只导入 DOCX。
CLI 返回真实 DOCX 路径，UI 可下载自动原件及独立 reviewed 稿。
当前限制：单输入 25MiB、最多 3 个选定物理页、串行 1、最多 8 个待处理/运行操作。
20页/50MiB和Windows未验证，不承诺扩容。

## 作业事实源

只有 `jobs/queue.json` 是运行队列事实源。原管线 `state.json` 是诊断记录，不驱动第二套调度。
请求快照和最终 receipt 保留在 `jobs/requests/op-*`；实际输出保持原有 `demo-*` 目录。
文件锁阻止第二实例；转换子进程与审校导出共用执行锁，父进程退出后子进程仍持有锁。
上传和 DOCX 替换原子落盘，完成收据最后写入；不存在网络下载流程。

缓存键包含输入字节、选页、预处理版本、native provider、模块/配置/schema和依赖版本。
输出键另包含样式、自动/审校版本及其完整文件清单。文件名改变不触发重算。
同一未结束/失败请求返回原操作；用户必须显式重试，生成新的操作/输出。
完成结果复用前校验 immutable 自动产物和资产，人工稿不进入自动产物清单。

## 失败与恢复

- QUEUED 重启后继续等待；RUNNING/CANCEL_REQUESTED 无有效最终收据变为 INTERRUPTED，不自动重跑。
- 已落盘且验证有效的收据可在重启后认领，避免重复解析。
- 取消由唯一工作线程停止自己创建的本地进程组。保留输入、已存在输出和人工稿。
- 已有 remoteID 或提交状态未知记录保持 SUBMISSION_UNKNOWN，不盲重试。本候选不支持远端续查/下载，也不会伪造远端已取消；原开发入口的受信模型配置未更改。
- 缺页和 PARTIAL 在队列显示；已有有效输出仍可下载。远端部分失败场景未在该包实测。
- 磁盘满/权限错误：先保留目录，修复环境后显式重试。若收据也无法写入，可能只得到 WORKER_INTERRUPTED_OR_DISK_FULL，不能断言唯一原因。
- 资产校验失败：OUTPUT_ASSET_DAMAGED；不要覆盖旧证据，可重新导入完整保存作业。
- Word 锁文件：关闭 reviewed.docx 后重试。锁文件检测及 OS 拒绝均报告；不能保证探测所有 Office/同步软件锁实现。
- 损坏 queue.json 不被自动重置；备份整个数据目录后由人工定位损坏。不要删除人工稿来恢复队列。
- 不提供自动清理；预览沿用现有引用检查，仅清理无引用预览资产，拒绝符号链接越界。

## 隔离与观测边界

服务仅监听 127.0.0.1，沿用 Host/Origin/session 防护；运行包禁用 live/replay-provider/模型路由接口。
转换进程禁用 Python socket connect/connect_ex/create_connection，记录可观测连接尝试；
隔离 DocVortex 保留原有网络及外部进程守卫。不是系统级抓包，不声称覆盖全部 C 扩展网络活动。
每作业记录模型数、缺页、耗时与当前 worker 的峰值 RSS；不把 worker RSS 说成进程树/整机峰值。

自动收据的 SUCCEEDED 只表示文件产出，界面显示“待复核”。实际 Word 视觉验收和用户接受另记；
运行机制验证不能证明普通表格已可编辑、原版分页已还原或 Beta 已获批准。
