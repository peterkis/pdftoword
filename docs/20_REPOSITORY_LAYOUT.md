# 20. 推荐仓库结构

```text
pdf2word-local/
├── AGENTS.md
├── apps/
│   └── desktop/                 # Tauri + React
├── services/
│   └── core-api/                # FastAPI 本地服务
├── packages/
│   ├── core-domain/             # IR、规则、状态机
│   ├── pdf-native/              # pdf-inspector/PDFium Adapter
│   ├── model-client/            # 8100 网关客户端
│   ├── model-normalizers/       # Paddle/Monkey/Ovis 归一化
│   ├── fusion/                  # 候选选择和冲突
│   ├── structure/               # 题目、图文关系
│   ├── docx-builder/            # Planner/Builder
│   ├── qa/                      # QA 与指标
│   └── review/                  # 审校服务
├── schemas/
├── configs/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── golden/
│   └── fixtures/
├── scripts/
├── docs/
└── pyproject.toml
```

## 依赖方向

```text
UI → Core API → Application Services → Domain
Adapters → Domain Protocols
DOCX/QA → Layout IR
Domain 不依赖 UI、SDK、FastAPI 或具体模型
```

## 禁止

- 单个超大 pipeline.py 包含全部流程；
- 在前端实现识别规则；
- 在 Adapter 中直接写数据库或 DOCX；
- 模型输出 Schema 渗透到核心层；
- 测试资产与生产资产混放。
