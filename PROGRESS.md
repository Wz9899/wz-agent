# 项目进度 & Agent 行为规范

> 这份文档专门写给 AI coding agent 看。每次会话开始时先读这里。

---

## 对 Agent 的要求

1. **一步一步写代码**——每一步都要解释实现了什么、用了什么函数、为什么这样写
2. **中文回复**
3. **用户手搓代码**——agent 只指导，不替用户写。除非用户明确说"你来写"
4. **每次写完一个模块**，更新本文档的"已完成"和"待完成"

---

## 已完成

| 模块 | 文件 | 状态 |
|---|---|---|
| 项目骨架 | `CONTEXT.md`, `docs/agents/`, `docs/adr/` | ✅ |
| Git 仓库 | `.git`, GitHub: `Wz9899/wz-agent` | ✅ |
| Python 环境 | `requirements.txt`, `venv/`, `src/` 目录结构 | ✅ |
| ReAct 循环 v1 | `src/agent/loop.py` — 最简 API 调用（无工具） | ✅ 已验证 |
| 测试脚本 | `test_api.py` | ✅ 通过 |
| README | `README.md` | ✅ |
| 入口脚本 | `src/main.py` | ✅ |
| 依赖列表 | `requirements.txt` | ✅ |

## 待完成

| 优先级 | 模块 | 说明 |
|---|---|---|
| 1 | ReAct 循环 v2 | 加入工具调用、消息循环 |
| 2 | 工具: read | 读取文件 |
| 3 | 工具: write | 创建/覆盖文件 |
| 4 | 工具: edit | 精确文本匹配替换 |
| 5 | 工具: bash | 执行 shell 命令（含 auto/plan 双模式） |
| 6 | Prompt: 需求澄清（阶段一） | 追问用户需求 |
| 7 | Prompt: 编码执行（阶段二） | ReAct + 工具编码 |
| 8 | CLI 入口 | `main.py`（click） |
| 9 | 错误重试逻辑 | 自动修复最多 3 次 |
| 10 | 上下文管理 | spec.md + 文件系统 + read 工具 |

## 后续版本

| 版本 | 功能 |
|---|---|
| v2 | 集成 `/triage`（issue 状态机）+ `/to-tickets`（任务拆解） |

## 技术选型

- 语言: Python 3.12
- LLM: DeepSeek (`deepseek-chat`, OpenAI 兼容 API)
- CLI: click
- UI: rich
