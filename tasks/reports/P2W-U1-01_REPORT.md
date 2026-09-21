# P2W-U1-01 实际报告

状态：**BLOCKED（本地实现与合成契约测试已执行；真实 MinerU / B.docx 未运行）**。

## 实际 HEAD / 范围

- 开始/结束 HEAD：`32b9e13d9ef752fc6c945ec62e58abb031da837f`。
- 分支：`codex/r2-03-columns-order`；开工工作区干净。未 reset、amend、提交、推送或修改旧报告。
- 只执行 U1-01；v3.0 计划包校验后按 `START_HERE` 初始化缺失的 `work/progress.json`，调度返回 U1-01 READY，无前置。未执行旧 ALL_PHASES 或 U1-02。
- 本轮用户授权本地代码/测试。安装、权重下载、模型处理、服务/FRP 与 Git 发布没有新增授权。

## 修改

新增文件及原因：

- `experiments/mineru_replacement/run_direct.py`：独立 `inspect-env / parse / export` 入口。显式开关控制本地解析，恰好一次调用、无重试；保存全部公共 `ParseResult.save` 输出，封存完整素材哈希，调用公共 `mineru.render.render_docx`。
- `experiments/mineru_replacement/requirements.in`：MinerU 4.0.4 / DocVortex 0.4.17 请求版本。声明范围兼容，但**不是已安装环境或传递依赖锁收据**。
- `experiments/mineru_replacement/README.md`：授权后可执行的独立安装/解析/重导出命令、主机只读检查项目与真实验证边界。
- `tests/experiments/test_mineru_direct.py`：23 项合成契约测试；由仓库默认 tests 路径发现。

不接默认转换路由，不改 Layout IR、自有文字、样式保存/导出或原有 Writer。
直接 MiddleJson→上游 DOCX 仅作为本任务明确要求的独立比较实验。

## 验证

| 命令 | 退出码 | 实际结果 |
| --- | --- | --- |
| 计划包 `python3 scripts/validate_package.py` | 0 | 包结构检查正常，不是产品检查 |
| 计划包 `python3 scripts/init_state.py` | 0 | 创建缺失状态，没有重置既有记录 |
| 计划包 `python3 scripts/next_task.py` | 0 | 初始 U1-01 READY |
| `.venv/bin/python -m pytest tests/experiments/test_mineru_direct.py -q` | 0 | 23 项成功，合成与 API 替身 |
| `.venv/bin/python -m ruff check experiments/mineru_replacement tests/experiments/test_mineru_direct.py` | 0 | 新增代码检查正常 |
| `.venv/bin/python -m mypy experiments/mineru_replacement tests/experiments/test_mineru_direct.py` | 0 | 2 个文件无类型问题 |
| `.venv/bin/python experiments/mineru_replacement/run_direct.py --help` | 0 | 三个独立子命令 |
| `.venv/bin/python experiments/mineru_replacement/run_direct.py inspect-env` | 0 | Python 3.12.13；两个新包均 NOT_INSTALLED |
| 真实候选 `parse` 预检（不带授权开关） | 1 | LOCAL_PARSE_AUTHORIZATION_REQUIRED，parse_calls=0 |
| `git diff --check` | 0 | tracked diff 检查正常；新增文件仍未跟踪，以 Ruff/实际文件审查补充 |

首次 unqualified `python3 ... inspect-env` 退出 1：本机默认 Python 3.9 无 `datetime.UTC`；入口要求 Python 3.12，运行说明已使用明确解释器。早期 Ruff 格式检查和 mypy socket 替换类型检查曾退出 1，已修正；最终结果见上表。

未执行 `uv sync --locked` 或任何安装/下载，未运行整仓 pytest/mypy：本轮停止在独立实验阻断点，没有进入 PR/阶段门禁。不重验 T0015/T0016/S1/R1。历史私有 tmp 的 mypy 问题沿用旧报告，不声称整仓绿。

## 证据 / 真实产物

- 私有证据根（相对 REPO_DIR）：`tmp/mineru-u1-01/`。
- `sample-selection.json`：匹配既有真实 native4 原文件哈希，物理第 4 页；没有使用 golden 或人工修订替代自动输出。新模型处理授权仍未发生。
- `real-preflight/run-receipt.json`：实际阻断收据；任务总收据为 `run-receipt.json`。
- `command-receipts.json`、`checks/`：最终命令和退出码。
- `preservation-before.json` / `preservation-after.json`：7,014 个既有作业/历史证据与原依赖清单文件哈希，变化 0。旧 DocVortex 0.4.9 清单与 `uv.lock` 未变；未调用旧环境安装命令。
- `upstream/`：公共接口/包元数据查阅副本，非已安装依赖。公开源码确认 MinerU 公共解析、save 及 DOCX 入口；无私有样本网络传输。
- **真实 B.docx：不存在；完整 MinerU ResultBundle：不存在；真实 ZIP/XML/可编辑对象清单：NOT_RUN。**
- 合成测试执行保存/封印/两次导出，验证 parser 未导入、parse_calls=0、Python socket 被拒绝、原包未改；不冒充断开物理网络后的真实上游重导出。
- 新真实模型调用、提交/轮询/metadata GET、重试：均 0。Word 打开、图片/公式回退目视、agent_visual：NOT_RUN；用户接受：PENDING。

## 失败 / 回退 / 未验证与停止原因

1. `LOCAL_PARSE_AUTHORIZATION_REQUIRED`：没有对真实候选在新 MinerU 环境中的模型处理授权。
2. `PINNED_RUNTIME_NOT_INSTALLED`：只读发现本机开发环境缺 MinerU 4.0.4 / DocVortex 0.4.17。独立安装、兼容运行时/权重准备与实际传递依赖锁：NOT_RUN。
3. 模型机访问目标/授权通道没有从当前工作区得到可用配置；GPU UUID/数量/空闲显存、RAM、端口/服务实时快照：NOT_RUN。历史双 16GB 不能替代当前检查。未连接或变更任何模型服务/FRP。
4. 实际后端、设备、tier、模型 revision/文件哈希均 unknown；请求默认 standard，未用 flash 伪装成功。
5. 上游真实运行兼容性、内容/数字/公式/题号守恒、阅读顺序、图题关系、素材完整性、Word 打开与真实离线重导出均未验证。没有更改历史质量结论。
6. Python socket 禁用只是进程内保护，不是 native library/subprocess 的 OS 网络隔离；实际离线验收仍须在禁网 worker/container 执行。

AC01 未达标；AC02 仅确认零样本外发/零模型调用，实际 tier 未验证；AC03 的本地历史与依赖清单保全有哈希证据。

下一步只恢复本项：获得明确的独立环境安装/权重准备与所选真实材料处理授权，并给出模型机访问目标后，先只读检查，再按 README 在新环境生成 B.docx、同包离线重导出并实际打开核验。不继续 U1-02。

工时按本轮墙钟近似计入工程时间（含环境检查与公共接口查阅），写入计划状态与私有总收据；软件/权重下载等待为 0。未以计划估计的 3–6 小时冒充实际投入，未触及 6 小时硬上限。
