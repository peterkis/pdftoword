# PDF2Word Local — Agent 项目开发启动包 V1.1

版本：`1.1.0`  
日期：`2026-08-20`  
状态：产品边界和 V1.1 技术路线已确认，可进入分阶段开发  
默认语言：简体中文

## 1. 项目目标

**当前最终需求（用户于2026-09-21确认）**：以试卷、合同、手册和一般文档为主要识别对象，
力求还原原布局与排版；杂志、网络期刊不属于目标。后续选型和验收以
[项目最终需求](docs/PRODUCT_REQUIREMENTS.md)为准，以下历史技术说明不代表当前质量已达标。

构建一款本地优先、可连接院内 GPU 模型机的 PDF → DOCX 应用，支持中文、英文及中英文混排：

1. **纯电子 PDF**：优先读取原生文字、字体、坐标、图片及矢量对象，不对正常原生文字执行 OCR。
2. **混合 PDF**：保留有效原生文字；只对局部扫描文字、图片表格、公式或编码损坏区域调用模型；普通配图、几何图、实验装置图、化学结构图原则上整体保留。
3. **纯图像 PDF**：执行版面分析、区域 OCR、表格和公式识别，再重建逻辑结构。
4. 输出为主要内容可编辑、阅读顺序正确、题图关系稳定、版式高度相似的流式 DOCX。
5. 力求保留原页布局、分页、分栏与排版；Word自然重分页导致的差异须显式评价，
   不能以流式输出为由放弃原布局目标。内容准确性和可编辑性仍须同时满足。

## 2. V1.1 最终架构

**重要说明**：以下为目标架构。当前部署状态见 `docs/23_MODEL_DEPLOYMENT_BASELINE_V1_1.md`。

```text
本地桌面应用 / CLI
  ├─ pdf-inspector：分类、原生文字、编码质量
  ├─ pypdfium2 / PDFium：页面对象、图片、矢量区域、渲染
  ├─ Layout IR 1.1：统一坐标、来源、候选、关系和审校信息
  ├─ Question / Figure 关系引擎
  ├─ DOCX Builder：python-docx + lxml + OOXML / OMML
  └─ QA / Review
              │
              │ HTTPS + API Key
              ▼
GPU 模型网关 :8100（目标架构，尚未部署）
  ├─ Paddle 服务 :8080（当前已运行）
  │    ├─ PP-DocLayout_plus-L：全局布局
  │    ├─ PP-DocBlockLayout：块级布局
  │    ├─ PP-OCRv6_medium：文字检测与识别
  │    ├─ RT-DETR-L 表格单元格检测
  │    ├─ SLANeXt / SLANet_plus：表格结构
  │    └─ PP-FormulaNet_plus-L：公式识别
  ├─ OvisOCR2 :8000（当前已运行）：高风险内容与完整性复核
  └─ MonkeyOCRv2-B-Parsing :9000（当前已运行）：复杂版面几何与阅读顺序候选
```

**当前部署状态**：
- **当前直接服务**：MonkeyOCRv2 :9000 / OvisOCR2 :8000 / PP-StructureV3 :8080
- 统一网关 8100 **尚未部署**
- 旧设计端口：8102 / 8104 / 8106（**不是当前部署事实**）

本地应用只面向 `8100` 网关编程。模型端口、模型原始输出和推理框架差异必须在模型网关或 Adapter 内被隔离。

**重要变更（ADR-006）**：PP 新版布局和 MonkeyOCRv2 均为几何候选，不预设永久唯一权威。详见 `adr/ADR-006-MULTI-CANDIDATE-GEOMETRY-UNTIL-GATE.md`。

## 3. 目录

```text
.
├── START_HERE.md
├── AGENTS.md
├── docs/                 # PRD、架构、识别规则、模型策略、注意事项
├── phases/               # 每个阶段的目标、范围、任务与退出门槛
├── tasks/                # Epic、Ticket、依赖、完成定义、测试计划
├── specs/                # Layout IR、作业配置、模型网关和适配器契约
├── config/               # 默认配置、模型路由和三档运行配置
├── samples/              # 机器可读样例
├── prompts/              # 可直接交给 Agent 的实施提示词
├── adr/                  # 已确认架构决策记录
├── checklists/           # 会话、模型、阶段和发布检查表
└── sources/              # 官方资料索引
```

## 4. Agent 开始顺序

开发 Agent 必须先读 `AGENTS.md`，然后按 `START_HERE.md` 的顺序读取。禁止跳过 Layout IR 直接编写 DOCX；禁止将 MonkeyOCRv2、OvisOCR2 或 Paddle 的原始输出直接传递给 DOCX Builder。

## 5. 里程碑

- `P0`：工程基础与契约
- `P1`：纯电子 PDF MVP
- `P2`：混合 PDF 与局部 OCR
- `P3`：扫描 PDF 专项识别
- `P4`：MonkeyOCRv2 复杂版面与多模型融合
- `P5`：题目结构与高保真 DOCX
- `P6`：QA、人工审校与回渲染
- `P7`：性能、安全、部署和发布

详见 `phases/PHASES_OVERVIEW.md`。

## 6. 不可改变的原则

- 内容保真高于像素级排版一致。
- 结构和图文关系高于原分页。
- 有效原生文字高于任何 OCR/VLM。
- PP 新版布局和 MonkeyOCRv2 **均为几何候选**，不预设永久唯一权威（见 ADR-006）。
- 专项模型结果优先于通用 VLM 的对应专项结果。
- 模型不得静默纠正试卷选项、数字、英文拼写、单位、公式或化学式。
- 不确定时保留原区域图片并创建审校项，不得猜测。

## 7. 工程与开发（自 T0001 起）

本仓库自 T0001 起包含可运行的工程骨架。当前开发环境为 **macOS + zsh**，保留 Windows 路径兼容测试。
跨机器复制后必须重建 `.venv`，不能复用 Windows 虚拟环境。
完整操作见 [本机调试与 FRP](docs/25_LOCAL_DEVELOPMENT.md)。
当前可运行领域配置、Gate 契约工具及下述 DEMO-001 本机输出审阅原型；生产 Core API、桌面 UI 和完整转换流水线尚未实现。

### 目录

```text
packages/core-domain/   # Python 核心域包（当前仅 Provider 配置 Schema 骨架与预留模块）
services/core-api/      # 本地 API 服务占位（T0011 实现）
apps/desktop/           # Tauri 2 + React 桌面应用占位（后续 Ticket 实现）
tests/                  # unit / integration / golden / fixtures
scripts/                # 辅助脚本
specs/                  # JSON Schema 与契约（即推荐结构中的 schemas/）
config/                 # 默认配置、模型路由与三档运行配置
docs/                   # 产品与工程文档
```

依赖方向：`UI → Core API → Application Services → Domain`；核心层不依赖
模型 SDK、HTTP 客户端或 UI 框架。

### 工具链

- Python 3.12（由 uv 管理，见 `.python-version`）
- uv（虚拟环境与依赖锁定，产出 `uv.lock`）
- pytest / ruff / mypy

### 常用命令（macOS zsh / Windows PowerShell 7）

```sh
uv sync --locked                # 创建/同步 .venv（首次会自动下载 Python 3.12）
uv run pytest          # 单元测试
uv run ruff check .    # lint
uv run mypy .          # 类型检查
```

### 配置与秘密

模型服务地址等敏感配置只放 `.env.local`（已被忽略，永不提交）；仓库内
`.env.example` 使用安全的本地回环示例，`config/example.env` 保留目标网关占位符。禁止在任何源码、日志
或 Layout IR 中写入 API Key。

本机 Gate 服务通过 FRP visitor 访问：`MONKEY_BASE_URL=http://127.0.0.1:9000`、
`OVIS_BASE_URL=http://127.0.0.1:8000`、`PP_BASE_URL=http://127.0.0.1:8080`。
工具自动补齐 OpenAI `/v1`；配置优先级和诊断步骤见本机调试文档。

### 公开仓库边界

仓库保留源码、规范、配置模板和脱敏契约夹具。本地 `.env*`（除 `.env.example`）、FRP 配置、密钥、运行数据和原始文档样本不上传。新克隆运行 Gate 工具时须通过 `--test-image` 提供自有样本。旧开发机 Git 历史保留在本地，公开 `main` 从经过检查的源码快照开始。

### DEMO-001 本机输出审阅原型

独立原型已提供真实 T0016 结果的零模型回放 DOCX、有限 Native PDF 转换、
本机对照与修正另存，以及显式授权的 raster live 开发入口。
运行 `uv run --locked python scripts/docx_demo.py serve`，打开 `http://127.0.0.1:8765`。
详见 [启动与审阅说明](prototypes/docx_output/README.md) 和
[原型边界](prototypes/docx_output/prototype-scope.md)。它不代表完整生产转换链路或阶段验收。


### 增量产品化计划（P2W）

从 DEMO-001 继续开发，独立计划位于仓库外 `~/Plans/pdftoword-development-plan/`。
[计划入口与旧任务映射](docs/development-plan/README.md)、
[受限 profile 与交付边界](docs/decisions/productization-profile-v1.md)、
[P2W-S1-01 基线报告](tasks/reports/P2W-S1-01_REPORT.md)已接入。
新 P2W-S1–S4 编号与原 97 项 Ticket 分开维护；本次只交付 P2W-S1-01 待审阅。

### S2 自动入口与混合区域识别

已新增 pdf-inspector 原生提取、auto 本地路由、按计划授权的区域识别与独立结果作业。使用方式见[自动入口说明](docs/28_AUTO_MIXED_PDF.md)。功能验证与尚缺验收见后续 S2 交付记录；不自动改变 S1 接受状态。
