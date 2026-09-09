# apps/desktop — Tauri + React 桌面应用（占位）

T0001 仅建立工作区占位：本目录当前没有任何代码，也不包含 `package.json`，
未做任何脚手架初始化。

## 规划技术栈（见 docs/04_TECH_STACK.md）

- Tauri 2
- React + TypeScript（strict）
- Tailwind CSS

## 版本待确认项

以下版本在现有技术栈文档中未指定，冻结前不做任何初始化决策
（当前开发机已安装 Node.js，但未安装 Rust 工具链与 pnpm）：

- Node.js 版本
- pnpm 版本
- Rust 工具链版本
- Tauri 2.x 具体版本

## 硬性边界

- Desktop UI 不得直接访问 Ubuntu GPU 模型服务器（禁止 Tauri → 模型机直连）；
- 所有模型调用必须经由 本地 Core（macOS / Windows） → 模型网关；
- UI 不承载业务识别规则（见 `AGENTS.md` 第 9 节）；
- PDF 选择、转换进度、模型设置、人工复核界面均属后续 Ticket 范围，T0001 不实现。
