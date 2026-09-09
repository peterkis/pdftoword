# 04. 技术栈

## 1. 本地应用

| 层 | 技术 | 用途 |
|---|---|---|
| 桌面 | Tauri 2 | 本地窗口、文件选择、系统集成 |
| 前端 | React + TypeScript | 作业、预览、问题审校、导出 |
| UI | Tailwind CSS | 轻量样式 |
| Core | Python 3.12 | PDF、结构、DOCX、QA |
| 依赖 | uv | 虚拟环境和锁定 |
| API | FastAPI / 本地 IPC | UI 与 Core 通信 |
| 数据 | SQLite | 作业、问题、审计、模型元数据 |
| PDF | pdf-inspector | 分类、原生文字与编码 |
| PDF | pypdfium2 / PDFium | 渲染、页面对象、区域裁剪 |
| DOCX | python-docx | 段落、表格、图片、分节 |
| OOXML | lxml | 浮动对象、分页、复杂属性 |
| 公式 | MathML/OMML 转换 | Word 原生公式 |
| Schema | pydantic + jsonschema | 契约和验证 |
| 图像 | Pillow + OpenCV | 裁剪、几何、质量检测 |
| 测试 | pytest + hypothesis | 单元、属性和集成测试 |

## 2. 模型机

**当前直接服务**：

| 服务 | 模型/组件 | 端口 |
|---|---|---:|
| Paddle | PP-DocLayout_plus-L、PP-DocBlockLayout、PP-OCRv6_medium、RT-DETR-L、SLANeXt/SLANet_plus、PP-FormulaNet_plus-L | 8080 |
| Ovis | ATH-MaaS/OvisOCR2 | 8000 |
| Monkey | zenosai/MonkeyOCRv2-B-Parsing | 9000 |

**目标架构**：

| 服务 | 端口 | 状态 |
|---|---|---:|
| 统一网关 | 8100 | 尚未部署 |

**旧设计端口**：8102 / 8104 / 8106（**不是当前部署事实**）

## 3. 基础设施

- Ubuntu 26；
- NVIDIA Driver；
- Docker Engine + Compose；
- NVIDIA Container Toolkit；
- NVIDIA RTX 5060 Ti 16GB；
- 可选 Nginx/TLS；
- systemd 管理 Compose；
- 模型缓存和日志独立卷。

## 4. 版本策略

- 锁定 Python、Node、Rust、PaddleOCR、vLLM、模型 revision 和镜像 digest。
- MonkeyOCRv2 如使用 `trust_remote_code=True`，必须锁定 commit/revision，禁止自动更新。
- DFlash 仅作为可选加速 profile，不作为首个可运行版本的硬依赖。
- 模型升级必须经过影子评测，不能直接替换生产默认。

## 5. 许可证策略

优先采用 Apache-2.0、MIT、BSD 等宽松许可证。构建时生成 SBOM、依赖许可证清单和模型卡快照。任何 AGPL 或商业授权依赖必须单独评估，不作为不可替换核心。
