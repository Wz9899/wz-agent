# 项目进度 & Agent 行为规范

> 这份文档专门写给 AI coding agent 看。每次会话开始时先读这里。

---

## 对 Agent 的要求

1. **一步一步写代码**——每一步都要解释实现了什么、用了什么函数、为什么这样写
2. **中文回复**
3. **Agent 来写代码**——每次由 agent 直接编写代码，不需要用户动手
4. **每次写完一个模块**，更新本文档的"已完成"和"待完成"
5. **按方法/属性为单位编写**——一次只写一个方法或一个属性，写完立即解释：用了什么、为什么这样写。不需要提前问用户，写完后解释即可
6. **改动代码前先读相关源文件**，接上进度再动手

---

## 已完成

| 模块 | 文件 | 状态 |
|---|---|---|
| 项目骨架 | `CONTEXT.md`, `docs/adr/` | ✅ |
| Git 仓库 | `.git`, GitHub: `Wz9899/wz-agent` | ✅ |
| Python 环境 | `requirements.txt`（全局安装，不用 venv） | ✅ |
| ReAct 循环 v1 | `src/agent/loop.py` — 最简 API 调用（无工具） | ✅ 已验证 |
| 测试脚本 | `test_api.py` | ✅ 通过 |
| README | `README.md` | ✅ |
| 入口脚本 | `src/main.py` | ✅ |
| 依赖列表 | `requirements.txt` | ✅ |
| .gitignore | 清理完毕，区分公开文件和内部文件 | ✅ |
| 工具: base | `src/agent/tools/base.py` — 抽象基类，自动推断参数 schema | ✅ |
| 工具: read | `src/agent/tools/read.py` — 读文件 + 错误处理 + 截断 | ✅ |
| 工具: write | `src/agent/tools/write.py` — 写文件 + 自动创建目录 | ✅ |
| 工具: edit | `src/agent/tools/edit.py` — 精确匹配替换 + 唯一性校验 | ✅ |
| 工具: bash | `src/agent/tools/bash.py` — 执行命令 + 30s 超时 + 危险命令拦截 | ✅ |
| 工具注册表 | `src/agent/tools/__init__.py` — ALL_TOOLS 字典 | ✅ |
| ReAct 循环 v2 | `src/agent/loop.py` — 完整 ReAct 循环 + 工具调用 | ✅ |
| Bash 安全模式 | `src/agent/tools/bash.py` — auto/plan 双模式（计划收集->批量执行）| ✅ |
| Prompt: 需求澄清 | `src/agent/prompts/clarify.py` — 阶段一，主动追问用户需求 | ✅ |
| Prompt: 编码执行 | `src/agent/prompts/code.py` — 阶段二，按 spec.md 编码 | ✅ |
| CLI 入口 | `src/main.py`（click + rich，参数自动校验） | ✅ |
| 错误重试逻辑 | `src/agent/loop.py` — `run_with_retry()` 失败回喂 LLM，最多 3 次 | ✅ |
| 上下文管理 | `src/agent/context.py` — spec.md 定位/读写 + 编码阶段自动注入 | ✅ |
| Issue 文件操作 | `src/agent/issues.py` — .scratch/ 定位、编号分配、Status 行读写、目标解析 | ✅ |
| 工具: triage | `src/agent/tools/triage.py` — list_issues + set_issue_status（五标签状态机） | ✅ |
| 工具: to-tickets | `src/agent/tools/tickets.py` — allocate_issue（编号唯一性由代码保证） | ✅ |
| Prompt: triage | `src/agent/prompts/triage.py` — 分诊状态机，issue → 五档标签 | ✅ |
| Prompt: to-tickets | `src/agent/prompts/to_tickets.py` — spec → 垂直切片 tickets | ✅ |
| CLI v2 子命令 | `src/main.py` — triage / to-tickets 分发 + chdir 锚定项目根 | ✅ |
| 路径常量收敛 | `src/agent/paths.py` — PROJECT_ROOT 等单一事实来源 | ✅ |
| issue 引用歧义处理 | `src/agent/issues.py` — 精确匹配优先 + 歧义抛 ValueError | ✅ |
| API 错误不重试 | `src/agent/loop.py` — [API-ERR] 直接返回，不浪费重试轮次 | ✅ |
| 单元测试 | `tests/` + `pytest.ini` — issues/edit/bash/base/loop 五组 48 例 | ✅ |
| 惰性 client | `src/agent/loop.py` — _get_client() 修复 .env 加载时序 | ✅ |
| 环境变量模板 | `.env.example` — 复制为 .env 即可配置 Key | ✅ |
| 安全边界文档 | README「安全边界」+ .env 用法说明 | ✅ |
| 历史压缩 | `src/agent/loop.py` — _maybe_compact 超预算时裁剪早期轮次 | ✅ |
| 流式输出 | `src/agent/loop.py` + `src/main.py` — stream 参数 + `--no-stream`，实时打印思考与工具过程 | ✅ |
| 监督式执行 | `interactive.py` + `tools/interact.py` + `loop.py` — ask_user（澄清问答）/ checkpoint（非阻塞进度汇报）/ Ctrl-C 中断 | ✅ |
| 运行工作区 | `runtime.py` — 每次运行 runs/<时间戳>/，spec/代码/session.log（流式回放） | ✅ |
| 示例项目 | `examples/nba-wordle/` — NBA Wordle（wz-agent 全流程产物） | ✅ |
| 子 agent 派发 | `tools/task.py` — task 工具（investigator/coder），LLM 自主决策、独立上下文、递归防线 | ✅ 已验证（DeepSeek 全链路） |
| 工具集注入 | `loop.py` — run()/_run_loop() 新增 tools 参数，支持受限注册表 | ✅ |
| Windows bash 修复 | `tools/bash.py` — Windows 下用 git-bash 执行（临时脚本法），POSIX 语法不再撞 cmd 墙 | ✅ 已验证 |
| 单循环会话重构 | `prompts/base.py` + `loop.py:continue_turn` + `session.py` 重写 —— 删意图分类器与三层会话，澄清/编码/修改在同一对话模型自路由；[DONE] 协议退役 | ✅ 129 测试全绿 |
| 播种会话 | `main.py` —— 命令行任务参数直接进 REPL（pi 式），删 --phase；--no-interactive 保留 headless 出口 | ✅ |
| 目标项目锚定 | `paths.set_target` + `main.py -C` —— agent 直接在目标项目工作，spec/.scratch/落目标根；runs/ 只留转录（目录名带项目名）；删 output/ 沙箱 | ✅ |
| 进度文档（项目快照） | `base.py` prompt 纪律 + `/progress` 命令 —— 编码时同步维护目标项目 PROGRESS.md，会话启动先读它接上进度；跨会话状态 = spec + PROGRESS，零记忆机制 | ✅ |
| 工具工厂 | `tools/__init__.py` —— TOOL_CLASSES 目录 + make_tools() 每循环全新实例，删 ALL_TOOLS 单例；plan 生命周期对齐一次 _run_loop | ✅ |
| schema 类型修复 | `tools/base.py` —— eval_str 求值注解 + list→array + X\|None 解包（append 的 boolean 此前一直误判 string） | ✅ |
| 并行扇出 | `tools/task.py` —— fan_out 线程池并行调查，按序聚合；只读护栏 + MAX_FAN_OUT=4；Ctrl-C 走中断菜单 | ✅ 144 测试全绿 |
| git 边界 | harness 零 git 调用；agent 可读不可写（prompt 级）；/clear 只删 spec 不碰项目文件 | ✅ 136 测试全绿 |

## 待完成

✅ **v2.0 目标（triage + to-tickets）已全部完成**
✅ **v2.1 目标（子 agent 派发 + Windows bash 修复）已全部完成**

## 版本规划

| 版本 | 功能 | 状态 |
|---|---|---|
| v2.1 | 子 agent 派发（task 工具）+ Windows bash 修复 | ✅ |
| v2.2 | 单循环会话重构：删意图分类器，基座提示模型自路由 | ✅ |
| v2.3 | 目标项目锚定（-C + set_target，删 output/ 沙箱）+ git 边界（harness 零 git） | ✅ |
| v2.4 | 工具工厂化（修共享单例竞态）+ task 并行扇出（fan_out，只读护栏） | ✅ |
| v2.5 | triage 批量评论模板、ticket ↔ code 自动衔接 | 📋 |

## 技术选型

- 语言: Python 3.12
- LLM: DeepSeek (`deepseek-chat`, OpenAI 兼容 API)
- CLI: click
- UI: rich
