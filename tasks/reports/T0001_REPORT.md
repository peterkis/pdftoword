# T0001 完成报告：初始化 Monorepo 与工具链

- Ticket：`T0001 初始化 Monorepo 与工具链`（P0，无依赖）
- 分支：`feat/p0-foundation`（该分支上无任何新提交）
- 最终建议状态：**ACCEPTED**（含两轮：初始实现 + 强制收尾修复，全部完成标准满足，见第 14 节）
- 验收环境：Windows 11 + Windows PowerShell 5.1（原生执行，非 Git Bash）

## 0. 收尾修复记录（第二轮）

1. **清除真实模型服务器地址**：`scripts/smoke_models.py` 不再包含任何真实 IP、真实端口组合或可运行的内网默认 URL；`MONKEY_CHAT_URL`、`OVIS_CHAT_URL`、`PP_STRUCTURE_URL` 改为必须从环境变量读取（新增 `require_env`，缺失时立即以清晰错误退出）；模型名保留非敏感默认值。
2. **新增真实 Windows 文件系统测试**：`test_real_file_roundtrip_with_chinese_names_and_spaces`——在 `tempfile` 真实目录中创建含中文和空格的子目录与文件，UTF-8 写入/读回断言一致，退出后自动清理。
3. **Windows 原生 PowerShell 验收**：四项验收命令在 Windows PowerShell 5.1 中全部通过（见第 4 节）。
4. **完整 Git 状态与忽略规则证据**：见第 10、11 节。
5. **敏感内容扫描**：见第 12 节；报告中此前的真实 IP 字面量已全部清除。

## 0.1 复验修正记录（第三轮，外部复验反馈）

1. **测试可移植性修复**：`test_import_does_not_load_model_sdks` 改为“导入前后 `sys.modules` 差集”判定——运行环境预加载的模块（sitecustomize、IDE 注入、遥测、发行版默认）不再造成假失败，只判定核心包导入新拉起的禁止模块；`subprocess.run` 增加 `timeout=30`。
2. **`EndpointProfile` 契约统一**：`base_url` 定义为“协议 + 主机 + 端口 + 可选稳定 API 前缀（如 `/v1`）”，不得包含 query、fragment 或具体操作路径；校验改用 `urllib.parse.urlsplit`（scheme ∈ {http, https}、host 必填、无 query/fragment）；`endpoint_path` 定义为具体操作路径（如 `/chat/completions`、`/models`）。docstring、测试与 `.env.example`（`http://MODEL_SERVER_IP:9000/v1`）三处已一致。
3. **PP 接口权威性澄清**：现有资料对 PP 端点存在两种不一致说明（`/layout-parsing` 与区分大小写 `/PP-StructureV3` + multipart 文件上传）；冻结前以服务器 `GET /openapi.json` 实测为准，不按文档猜测——`PP_STRUCTURE_ENDPOINT_PATH` 保持空。
4. **PP 原始结果交付边界确认**：PP raw 响应含大量内嵌 Base64（`markdown.images`），交付中只允许 `pp-structure.pruned.json` / `pp-structure.summary.json` / `ground-truth.json`；raw 全域忽略已由 `.gitignore` 强制并实测（见第 9 节）。

## 0.2 第四轮修正记录（外部复核：文件名冲突与失效清单）

1. **`agents.md` → `AGENTS.md` 大小写冲突消除**：仓库实际只存在小写 `agents.md`，而大量引用使用 `AGENTS.md`；Windows 文件系统无法可靠维护两个仅大小写不同的文件。已按复核指令通过两步 `git mv`（经 `agents.__rename_tmp__.md`）将规范名定为 `AGENTS.md`；README 目录中独立的 `agents.md` 条目已删除；全仓库已无任何小写 `agents.md` 引用，根目录仅存在 `AGENTS.md` 一个文件。
2. **失效完整性清单移除**：`MANIFEST.sha256` 与 `PACKAGE_MANIFEST.md` 为原 PRD 压缩包时期清单（外部实测 `sha256sum -c` 失败：AGENTS.md 不存在、CHANGELOG/README/agents.md/config/example.env 哈希不匹配；81 文件计数失效，且同时列出 `AGENTS.md` 与 `agents.md` 两项）。处理原则：不手工修补哈希——两者已从开发仓库移除（`git rm`）；正式交付包由发布脚本根据 Git commit 自动重新生成清单与 SHA-256，开发 Ticket 不再手工维护全仓库哈希。
3. **Gate 依赖表述修正**（本报告原第 16 节“其后才可继续 T0002–T0013”有误）：P0-GATE 仅阻塞模型相关任务（HTTP Adapter、PP Transport/响应 Schema 固化、模型路由与能力检测），**不阻塞**模型无关任务（配置加载、日志与错误模型、作业状态机、本地任务目录、PDF 原生分类与提取、P1 纯电子 PDF MVP）。见修订后的第 16 节。

## 1. 修改和新增的文件

### 新增（21 个）

| 文件 | 类型 |
|---|---|
| `pyproject.toml`、`.python-version`、`uv.lock` | Python 工具链 |
| `.env.example`、`.editorconfig`、`.gitattributes` | 工程规范 |
| `packages/core-domain/src/pdf2word_core_domain/__init__.py`、`config/__init__.py`、`config/providers.py` | 基础 Python 包 |
| `packages/core-domain/src/pdf2word_core_domain/raster_io/__init__.py`、`image_normalization/__init__.py` | 预留空模块 |
| `tests/unit/test_package_boundary.py`、`test_provider_config.py`、`test_windows_compat.py` | 最小测试（含真实 FS 测试） |
| `tests/README.md`、`tests/integration/.gitkeep`、`tests/golden/.gitkeep` | 测试目录规范 |
| `services/core-api/README.md`、`apps/desktop/README.md`、`scripts/README.md` | 占位骨架 |

### 修改（5 个）

- `.gitignore`：扩充忽略规则（含 fixture 例外）
- `README.md`：新增第 7 节“工程与开发”
- `CHANGELOG.md`：T0001 条目
- `config/example.env`：内网 IP 替换为占位符 `MODEL_SERVER_IP`
- `scripts/smoke_models.py`：收尾修复——三处服务地址改为 `require_env` 强制环境变量读取（并含此前两处 lint 空白修复），逻辑无其他改动

## 2. 项目目录树

```text
.
├── pyproject.toml / uv.lock / .python-version     # 新增：uv 工具链（Python 3.12）
├── .env.example / .gitignore / .editorconfig / .gitattributes   # 新增
├── apps/desktop/README.md                         # 新增：Tauri 2 + React 占位
├── packages/core-domain/src/pdf2word_core_domain/ # 新增：核心域包
│   ├── config/providers.py                        #   Provider 配置 Schema 骨架
│   ├── raster_io/ 、 image_normalization/         #   预留空模块边界
├── services/core-api/README.md                    # 新增：本地 API 占位（T0011）
├── tasks/reports/T0001_REPORT.md                  # 本报告（验证证据落盘）
├── tests/
│   ├── unit/（3 个测试文件）、 integration/、 golden/
│   ├── README.md                                  # 新增：Fixture 规则
│   └── fixtures/model_api/math_exam_page_01/      # 历史遗留未追踪内容，未迁移、不随 T0001 提交
├── scripts/（README.md 新增；smoke_models.py 已修改）
├── specs/ config/ docs/ phases/ tasks/ adr/ checklists/ prompts/ samples/ sources/   # 已有
└── .env.local                                     # 本地真实配置，已被忽略、未追踪
```

目录命名遵循 `docs/20_REPOSITORY_LAYOUT.md`：`packages/`=core、`services/`=api、`apps/`=desktop；仓库既有 `specs/` 即推荐结构中的 `schemas/`，`config/` 即 `configs/`，不再新建重复目录。

## 3. 每个文件的作用

- **`pyproject.toml`**：单一根项目 `pdf2word-local`（Python 3.12，零运行时依赖）；dev 组固定 pytest/ruff/mypy；内置 pytest（`testpaths`/`pythonpath`）、ruff、mypy 配置。
- **`config/providers.py`**：声明式数据结构 `ModelProviderConfig`、`EndpointProfile`、`ProviderCapability`（值对齐网关任务名 layout.fast/parse.table 等）、`ProviderStatus`、`ProviderType`、`TransportProfile`，以及超时/并发安全默认值和 `default_endpoint_profile()` 工厂。frozen dataclass + `__post_init__` 校验；`base_url` 用 `urllib.parse.urlsplit` 校验（允许稳定 API 前缀如 `/v1`，拒绝 query/fragment）。**无任何运行时行为**（无 HTTP、无探测、无路由、无健康检查）。
- **`raster_io/`、`image_normalization/`**：空占位包，docstring 记录未来职责（EXIF 旋转、Alpha、ICC、DPI、RGB 转换、原图哈希、统一页面坐标），T0001 不实现任何解码。
- **`tests/unit/`**：
  1. 包导入隔离（子进程验证导入不加载 openai/httpx/paddle/torch 等 14 个禁止模块；占位模块无公开可调用对象）；
  2. 配置结构（默认加载、endpoint_path 可空、transport=auto、非法值拒绝、不可变性）；
  3. Windows 兼容（PureWindowsPath 解析含中文+空格路径、tempfile 临时目录、包源码静态扫描禁止 `/tmp` `/opt` `/home` 字面量、**真实文件系统中文/空格路径 UTF-8 读写往返测试**）。
- **占位 README**：`apps/desktop`（版本待确认清单 + UI 不直连模型机边界）、`services/core-api`（T0011 职责）、`scripts/`（smoke 脚本处置说明）、`tests/`（Fixture 目录规范，见第 9 节）。

## 4. 验收命令（Windows 原生 PowerShell 执行）

执行环境（`powershell.exe -NoProfile` 输出）：

```text
PSVersion    : 5.1.28000.2704（Windows PowerShell 5.1）
OSVersion    : Microsoft Windows NT 10.0.28000.0
Get-Location : C:\Projects\pdf2word-agent-prd-v1.1.0
```

| 命令 | 结果 |
|---|---|
| `uv sync` | Resolved 14 packages in 2ms / Checked 14 packages in 1ms——**全部来自本地缓存与既有 .venv，本轮无互联网下载**（首轮曾发生一次：下载托管 CPython 3.12.13 与 PyPI 依赖） |
| `uv run pytest` | **23 passed** in 0.24s |
| `uv run ruff check .` | **All checks passed!** |
| `uv run mypy .` | **Success: no issues found in 8 source files** |

> 第三轮契约修正与第四轮文件名/清单修正后均已在同一 PowerShell 5.1 环境复跑，最新结果：23 passed（0.29s）/ lint 通过 / mypy 8 文件无问题；第四轮无网络下载。

## 5. 测试、lint 和类型检查结果

- **pytest**：23 passed（初始 18 + 真实文件系统测试 1 + `base_url` 契约测试 4），不访问网络、不调用模型、不依赖 GPU/PDF/图片。SDK 隔离测试对环境预加载模块免疫（前后差集判定）。
- **ruff**：All checks passed（规则集 E/F/W/I/UP/B/C4/SIM/RUF，忽略中文全角标点告警 RUF001-003）。
- **mypy**：8 个源文件（包 5 个 + 测试 3 个）无问题，`disallow_untyped_defs` 全开。`scripts/smoke_models.py` 因依赖未安装的 `httpx` 被 mypy 配置显式排除（预存手工工具，由 P0-GATE-001 取代）。

## 6. Windows 11 兼容性处理

全部代码使用 `pathlib`/`tempfile`/`PureWindowsPath`；新增**真实文件系统测试**（不再只做字符串解析）：在 `tempfile.TemporaryDirectory()` 中创建 `中文 测试目录/数学 试卷样本.txt`，`pathlib.Path` 写入 UTF-8 内容并读回断言一致，验证存在性，退出后自动清理。测试静态扫描保证包源码无 `/tmp`、`/opt`、`/home` 硬编码；不依赖 POSIX 权限、符号链接、Bash、make、WSL；`.gitattributes` 将 `.ps1/.bat/.cmd` 固定 CRLF、`*.sh` 固定 LF，其余文本 `text=auto`。验收已在 Windows 原生 PowerShell 5.1 中执行（本机未安装 PowerShell 7，按指令直接使用 5.1）。

## 7. 模型配置边界

`.env.example` 仅含占位符（`MODEL_SERVER_IP`），包含统一网关占位 `MODEL_GATEWAY_BASE_URL=http://MODEL_SERVER_IP:8100` 与三个直连服务占位（供 P0-GATE-001 探测用）。领域层（`providers.py`）**零硬编码**：无 IP、无端口、无模型名——地址必须显式传入，超时（10s/600s）与并发（1）默认值与 `.env.example` 对齐。`scripts/smoke_models.py` 收尾修复后**不含任何默认服务器地址**（必须环境变量）。真实密钥仅存于 `.env.local`（未被追踪）。

## 8. PP 接口路径和 Transport 尚未冻结的处理方式

多层表达“未冻结”：

1. `EndpointProfile.endpoint_path` 允许为空并有测试锁定；
2. `TransportProfile.AUTO` 为默认值并有测试锁定；
3. `.env.example` 中 `PP_STRUCTURE_ENDPOINT_PATH=`（留空）、`PP_STRUCTURE_TRANSPORT=auto`；
4. 现有资料对 PP 端点存在两种不一致说明（`/layout-parsing` 与区分大小写 `/PP-StructureV3` + multipart 文件上传），**冻结前以服务器 `GET /openapi.json` 实测 Schema 为准**，不按文档猜测；该探测属 P0-GATE-001 范围，本轮未执行。

本轮未做任何 OpenAPI 探测，不做任何假设。

## 9. Fixture 与原始 smoke 输出的隔离策略

`.gitignore` 规则及实测证据（`git check-ignore -v` / `git add -n` 干跑）：

- `tmp/` 忽略（实测同时覆盖 `scripts/tmp/model-smoke/` 及其 `results/` 下全部 raw 输出）；
- `*.raw.json` 全局忽略；例外 `!tests/fixtures/**/*.json` 保证精简 fixture 可提交，其后 `tests/fixtures/**/*.raw.json` 再忽略——**raw 响应在任何位置（含 fixtures 内）都不可提交**；
- 实测：`tests/fixtures/.../pp-structure.raw.json` 被 `git add -n` 拒绝（规则 `tests/fixtures/**/*.raw.json`）；`ground-truth.json` 未被忽略且可 add；
- `tests/README.md` 冻结目录规范（pruned.json 必须移除 markdown.images/Base64/无关字段）；
- **PP 原始结果交付边界**：PP raw 响应含大量内嵌 Base64 图片（`markdown.images`），交付中只允许 `pp-structure.pruned.json` / `pp-structure.summary.json` / `ground-truth.json`，完整 raw 永不进入交付；
- 现有 `math_exam_page_01/` 未追踪内容**未迁移、未暂存、不随 T0001 提交**；该数学试卷 JPG 样本不能替代 P1 纯电子 PDF Fixture。

## 10. 精确 Git 状态（本轮验收时点）

**工作区存在未提交变更。** 按类别：

- **committed（已提交）**：无——`feat/p0-foundation` 分支上无任何 T0001 提交；
- **staged（已暂存）**：`agents.md` → `AGENTS.md` 重命名（两步 git mv）；删除 `MANIFEST.sha256`、删除 `PACKAGE_MANIFEST.md`（均为第四轮复核指令要求的暂存操作，未提交）；
- **modified（已追踪、已修改、未暂存）**：`.gitignore`、`CHANGELOG.md`、`README.md`、`config/example.env`、`scripts/smoke_models.py`；
- **untracked（未追踪、未被忽略，待提交候选）**：`.editorconfig`、`.env.example`、`.gitattributes`、`.python-version`、`pyproject.toml`、`uv.lock`、`packages/`、`services/`、`apps/`、`scripts/README.md`、`tasks/reports/T0001_REPORT.md`、`tests/`（unit/integration/golden/README）；
  - 另有历史遗留未精简 fixture（`tests/fixtures/model_api/math_exam_page_01/` 下 5 个未忽略文件）属未追踪但**不准备**在精简确认前提交；
- **ignored（已忽略）**：`.env.local`、`.venv/`、`__pycache__/`、`tmp/`（含 `scripts/tmp/model-smoke/` 全部 raw 输出）、`data/jobs/`、所有 `*.raw.json`。

## 11. Git 状态与忽略规则验证证据

```text
$ git ls-files .env.local
（空 = 未追踪）
$ git ls-files "tests/fixtures/**"
（空 = tests/fixtures 下无任何已追踪文件，raw JSON 未被追踪）
$ git check-ignore -v .env.local
.gitignore:3:.env.local	.env.local
$ git check-ignore -v scripts/tmp/model-smoke/pp-structure.raw.json
.gitignore:19:tmp/	scripts/tmp/model-smoke/pp-structure.raw.json
$ git check-ignore -v tests/fixtures/model_api/math_exam_page_01/pp-structure.raw.json
.gitignore:33:tests/fixtures/**/*.raw.json	tests/fixtures/model_api/math_exam_page_01/pp-structure.raw.json
$ git add -n tests/fixtures/model_api/math_exam_page_01/ground-truth.json
add 'tests/fixtures/model_api/math_exam_page_01/ground-truth.json'   （精简 JSON 可提交）
$ git add -n tests/fixtures/model_api/math_exam_page_01/pp-structure.raw.json
The following paths are ignored by one of your .gitignore files: ...  （raw 被拒绝）
$ git diff --check
（exit=0，无空白错误；仅有 autocrlf 的 LF/CRLF 提示性 warning，非错误）
```

## 12. 敏感内容扫描结果

扫描范围：全部已追踪文件 + 未忽略的未追踪文件（共 101 个文本文件；跳过 10 个二进制/不可解码文件；排除 `.git`、`.venv`、被忽略文件；`uv.lock` 仅按 IP/私钥模式扫描以排除哈希误报）。

- 真实模型服务器 IP（私网段）：**待提交文件中无残留**（本轮发现并清除了本报告初稿中的 2 处 IP 字面量）；
- API Key / Bearer Token / 私钥块 / 用户名密码组合：**未发现**（唯一模式命中 `scripts/smoke_models.py:31` 为 `os.getenv` 环境变量读取代码，非硬编码值）；
- `.env.local` 值泄露检查（7 个非占位值，含真实 URL 与密钥）：**无任何值出现在待提交文件中**（命中的 `MonkeyOCRv2`/`ovis-ocr2` 为模型名，属允许的非敏感默认值，广泛存在于既有文档）。

## 13. 未执行事项及原因

- **Desktop/TS 脚手架与 TS 构建检查**：`docs/04_TECH_STACK.md` 未指定 Node/pnpm/Rust/Tauri 具体版本（不得静默决定），且本机无 pnpm、无 Rust 工具链；仅建占位 README。
- **与 TICKETS.md T0001 的范围差异**：TICKETS 中“前端 workspace / Python-TS 构建通过”按实施 Prompt 收窄为占位骨架；Python 侧全部通过，TS 侧未执行。
- **P0-GATE-001 探测、任何模型调用、T0002+**：明确禁止，未执行。
- **Git commit**：按收尾指令明确禁止，未执行；工作区保持未提交状态。

## 14. 完成标准核对（收尾清单）

1. smoke_models.py 不再包含真实服务器默认地址 ✓
2. 待提交文件中不存在真实服务器 IP 和凭据 ✓
3. 增加真实 Windows 中文、空格路径文件读写测试 ✓
4. PowerShell 原生执行的 pytest、ruff、mypy 全部通过 ✓
5. .env.local 未被追踪 ✓
6. raw JSON 未被追踪或暂存 ✓
7. 精简 Fixture JSON 仍允许提交 ✓
8. git diff --check 通过 ✓
9. T0001_REPORT.md 与实际 Git 状态一致 ✓
10. 未访问模型服务器 ✓
11. 未实现 T0002 或后续功能 ✓
12. 未执行 Git commit ✓

## 15. 当前仍存在的风险

1. **TICKETS.md 缺失两个前置任务**——`P0-BASELINE-001 模型部署基线与架构文档对齐`（升级前文档模型名全部待对齐，含 ADR-003 临时决策修订）与 `P0-GATE-001 模型服务契约与图像能力基线`；本轮未修改 TICKETS.md，仅记录缺口（详见第 16 节）。
2. 遗留 `tests/fixtures/model_api/math_exam_page_01/`（含 `source-page.jpg` 业务样本）与 `scripts/tmp/model-smoke/` 内容待精简/清理审查后才可提交（当前均未追踪/被忽略）。
3. `.env.local` 含真实 API Key（仅本地、已忽略、未追踪）；若任何凭据曾外泄于共享材料，需按实施 Prompt 安全节轮换。
4. Python 3.12.13 依赖 uv 托管下载（离线机器需预先 `uv python install 3.12`）。

## 16. 下一可执行任务（依赖模型已按外部复核修正）

**P0-GATE 不阻塞模型无关任务。** P0-GATE-001A 仅阻塞：模型 HTTP Adapter、PP Transport 固化、模型响应 Schema 固化、模型路由与能力检测；不阻塞：配置加载、日志与错误模型、作业状态机、本地任务目录、PDF 原生分类与提取、P1 纯电子 PDF MVP。可并行推进两条路线：

- **路线 A**：`P0-BASELINE-001` → `P0-GATE-001A/B/C` → 模型 Adapter；
- **路线 B**：T0002 及后续模型无关 P0 任务 → P1 纯电子 PDF MVP（正常电子 PDF 路径原则上不调用模型）。

### 待补入 TICKETS.md 的前置缺口（本轮未修改 TICKETS.md，不混入 T0001）

1. **`P0-BASELINE-001 模型部署基线与架构文档对齐`**：仓库文档仍为升级前版本（PP-DocLayout-M、PP-OCRv6 Small、PP-FormulaNet-S、“MonkeyOCRv2 复杂页唯一几何权威”），实际部署已升级为 PP-DocLayout_plus-L、PP-DocBlockLayout、PP-OCRv6 Medium 系列、表格系列（RT-DETR-L 有线/无线单元格检测、SLANeXt_wired、SLANet_plus 等）、PP-FormulaNet_plus-L，及按需启用的 PP-LCNet_x1_0_doc_ori / UVDoc。需废止或修订 `ADR-003-MONKEY-GEOMETRY-AUTHORITY.md`，临时决策：**P0-GATE-001B 完成前，PP-StructureV3 新版布局结果与 MonkeyOCRv2 布局结果均为独立候选，不预设永久唯一权威**。涉及文件：`AGENTS.md`、`README.md`、`START_HERE.md`、`docs/01/03/04/05/07/08/19`、`ADR-003`、`phases/P2`、`phases/P4`、`tasks/TICKETS.md`、`tickets.json`、`tickets.csv`、三档模型路由 YAML、`sample-job-config.json`。Windows Core 继续面向抽象能力（`PaddleProvider`：layout / block_layout / text_ocr / table / formula / orientation / unwarping），不直接编排 15 个子模型名——T0001 的 Provider 配置 Schema 已符合该抽象（能力枚举 + 单一 PP 端点，无子模型名）。
2. **`P0-GATE-001 模型服务契约与图像能力基线`**：`GET /openapi.json`（PP 端点以实测为准：`/layout-parsing` 与区分大小写 `/PP-StructureV3` + multipart 两种说明不一致，不按文档猜测）、Monkey/Ovis `/v1/models`、Multipart 与 JSON-Base64 差异、JPG/PNG 一致性、旋转/UVDoc/多栏/有线与无线表格/公式密集页/试卷高风险符号，并记录 Schema、版本 fingerprint、延迟、GPU、超时、文件上限等。

---

## 最终声明

- 本轮（第四轮）仅执行**文件名冲突消除与失效清单移除**两项复核指令（`git mv` / `git rm` 均为暂存操作），未启动 P0-BASELINE-001、P0-GATE-001，未实现 T0002 或任何后续功能。
- **网络访问**：第四轮无网络下载（验收复跑 `uv sync` 全部来自本地缓存）；未访问任何模型服务，未访问模型服务器。
- **未进行任何模型调用**。
- **未执行 Git commit**；工作区存在未提交变更（staged：重命名与清单删除；unstaged：5 个修改；untracked：T0001 新增文件，见第 10 节分类）。
