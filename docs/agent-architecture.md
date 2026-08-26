# wz-agent 架构 —— 按 harness 机制逐章拆解

> 本文按 [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) 的课程结构（s01–s17）组织，
> 逐章说明 wz-agent 对该机制**实现了什么、在哪里实现、为什么这样设计（或为什么明确不做）。
>
> 全部代码约 3.3k 行 Python。写作时状态：v2.5（154 测试全绿）。

---

## 0. 一页总览

先给结论：wz-agent 是一个**刻意裁剪**的 agent harness。Agency 来自模型（DeepSeek），
harness 只负责四件事，浓缩为四句格言：

| 格言 | 含义 | 对应课程 |
|---|---|---|
| **单循环** | 一个 REPL、一份持久 messages[]、一份基座提示，阶段切换由模型路由 | s01, s15 |
| **文件即状态** | spec.md（需求）+ PROGRESS.md（进度）+ 票（任务），零记忆机制、零 git 调用 | s05, s09, s10 |
| **agent 即工具** | 子 agent 就是一次普通的 tool_call（task 工具），无独立运行时 | s06, s13 |
| **票即任务** | `.scratch/` 里的 markdown 票是可执行单元，编码指令逐票消费 | s10 |

三条设计原则（源自 pi 的启发，贯穿全文）：

- **P1 判断归模型，不归代码**——永远不写"替模型做判断"的路由代码；软路由（prompt）错判还能 ask_user 找回来，硬路由（if-else）错判直接丢功能。
- **P2 能组合出来的，不新增机制**——新能力优先表现为"一个新工具"或"一个文件"，很少是一个新运行时。
- **P3 内核极小，接缝明确**——循环 + 工具集 + 少数边界（锚定、安全模式、防自噬），其余一切可变性都在边界之外。

机制覆盖一览（✅ 有 / ⚠️ 简化版 / ❌ 明确不做）：

| 课程 | 机制 | wz-agent |
|---|---|---|
| s01 | Agent Loop | ✅ `loop.py` |
| s02 | Tool Use | ✅ 四件套 + 工厂 |
| s03 | Permission | ⚠️ bash 双模式 + git 边界 |
| s04 | Hooks | ❌（组合代替插口） |
| s05 | TodoWrite | ⚠️ PROGRESS.md（文件版） |
| s06 | Subagent | ✅ task 工具 + 并行扇出 |
| s07 | Skill Loading | ❌（提示按流程内置） |
| s08 | Context Compact | ⚠️ 字符预算裁剪 |
| s09 | Memory | ❌（文件即状态） |
| s10 | Task System | ⚠️ 票即任务（无依赖图） |
| s11 | Background Tasks | ❌ |
| s12 | Cron | ❌ |
| s13 | Agent Teams | ❌（L2 并行为止） |
| s14 | MCP | ❌（同 pi） |
| s15 | 集成 Harness | ✅ wz-agent 本身 |
| s16 | Workflow Runtime | ⚠️ CLI 子命令 + 单循环 |
| s17 | Goal Loop | ⚠️ 失败自动重试 |

---

## s01 Agent Loop —— `src/agent/loop.py`

**课程要义**：一个循环 + Bash = 一个 agent。模型决定何时调工具、何时停止，代码只执行模型的要求。

**wz-agent 实现**：`_run_loop()` 是标准 ReAct 循环——调 DeepSeek（OpenAI 兼容 API）→ 解析 tool_calls → 逐个执行 → 结果 append 回 messages → 直到模型返回纯文本。外围设施：

- **流式输出**：`_call_stream` 把文本增量实时打印，工具调用与结果同步显示（并写入 session.log 转录）。
- **哨兵错误协议**：结果以 `[ERR]/[WARN]/[API-ERR]/[ABORT]` 开头区分四类终态——前两类可自动修复重试，后两类（基础设施故障/用户中止）不重试。糙，但让错误对模型可读、对调用方可判。
- **硬上限**：`max_steps`（会话轮 30）防死循环；工具结果超 2000 字符截断并注明原始长度。
- **Ctrl-C 中断菜单**（`interactive.handle_interrupt`）：回车=继续 / 输入=注入指令 / stop=停止。中断点在 LLM 生成中和工具执行中分别处理（工具中断时先补齐 tool 消息保住 API 成对约束）。

**考虑**：
- 循环属于 agent，机制属于 harness——wz-agent 的循环刻意保持"笨"：没有阶段判断、没有工作流分支，所有聪明事都发生在工具和提示里。
- v2.2 重构把三层嵌套会话（REPL → 阶段函数 → loop 对话循环）塌缩成一层。`continue_turn(messages, user_input)` 是唯一会话入口：append 用户输入 → 带自动修复跑循环。**messages 跨轮持久**是单循环架构的核心不变量（有专门测试守护）。
- 旧的 `[DONE]` 阶段边界协议随之退役——单循环下模型返回纯文本即本轮自然结束，无边界可标。

---

## s02 Tool Use —— `src/agent/tools/`

**课程要义**：加一个工具只加一个 handler；dispatch map 注册，循环不动。

**wz-agent 实现**：`BaseTool` 抽象基类，子类只写 `name`/`description`/`run()`，参数 JSON Schema 从 `run()` 签名**反射自动生成**（无默认值=必填，docstring 里的 `参数名: 说明` 行自动提取为描述）。

工具清单（`TOOL_CLASSES` 目录）：

| 工具 | 说明 |
|---|---|
| read / write / edit / bash | 四件套，与 pi 默认工具集一致 |
| ask_user / checkpoint | 人机交互：阻塞提问 / 非阻塞进度汇报 |
| task | 子 agent 派发（见 s06） |
| list_issues / set_issue_status / allocate_issue | issue 线三工具（见 s10） |

**v2.4 工厂化**：`make_tools(names)` 每次调用构造一组**全新实例**。此前是全局单例 `ALL_TOOLS`——bash 的 mode/plan 是实例状态，单例意味着所有循环共享，一上线程就是竞态。工厂化后每个循环（主循环每次 `_run_loop`、子 agent 每线程）各自一份。

**考虑**：
- 反射生成 schema 是典型的"少写一行是一行"，但它埋过一个 bug：`from __future__ import annotations` 下注解全是字符串，`_TYPE_MAP` 从未真正匹配过（旧工具恰好全是 string 参数所以没暴露）。v2.4 用 `eval_str=True` + `list→array` + `X | None` 解包修复——`write(append=...)` 的 boolean 此前一直误报 string。教训：便利设施的盲区会在它第一次被新用法触碰时爆雷。
- 工厂的生命周期对齐很有讲究：plan 模式（见 s03）的计划存在 bash 实例里、由 LLM 经同一实例触发执行，所以"实例作用域 = 一次 `_run_loop` 调用"正是正确粒度——跨循环零泄漏，重试轮次互不污染。
- edit 是精确文本匹配替换（oldText 唯一性校验），与 pi 一致——避免行号脆弱性。

---

## s03 Permission —— `src/agent/tools/bash.py`

**课程要义**：先划边界再给自由；操作前判断能不能做、要不要问用户。

**wz-agent 实现**（诚实分层的防护）：

1. **防呆层**（bash 工具内置，README 明说"不是安全边界"）：危险命令黑名单（`rm -rf /` 等少量模式，可绕过）+ 30 秒超时（命令不无限挂起）+ Windows 下经 git-bash 执行（临时脚本法，POSIX 语法不撞 cmd 墙）。
2. **真正的闸门——plan 模式**：`--safety-mode plan` 时命令不执行而是收集到计划，`__execute_plan__` 一次性批量执行（人工确认后）。auto 模式下安全完全依赖模型自律，文档明示不要在含重要数据的环境跑不受信任的任务。
3. **git 边界**（v2.3 决策，prompt 级软约束）：
   - harness 零 git——Python 代码不执行任何 git 命令（对任意目录可用）；
   - agent 经 bash 可读不可写：查 `status/log/diff` 理解项目允许，`commit/push/reset/checkout` 等写操作禁止；
   - 版本控制、快照、回滚完全由用户自己管理；`/clear` 只删 spec.md + 重置对话，绝不碰项目文件。

**考虑**：
- 这是与 pi 立场最接近的一章：pi 说"No permission popups——run in a container, or build your own"。信任边界是**用户的部署决策，不是产品功能**。wz-agent 曾计划过"还原点"（运行边界自动 commit + `/restore` 回滚），被用户否决后改为上述三条边界——否决的理由比原方案更 pi：自动 commit 是 harness 替用户做决定。
- 软约束（prompt 级 git 边界）不如黑名单硬，但方向正确：它约束的是**行为意图**而非**字符串模式**，与模型的语义理解同向，不玩猫鼠游戏。

---

## s04 Hooks —— ❌ 未实现

**课程要义**：挂在循环上、不写进循环里；工具前后留插口，不改主循环也能扩展。

**wz-agent 的"不做"是有替代物的**：它的扩展接缝不是 hook，而是**工具本身**（P2：组合优先）。想加能力→加一个工具（task 工具就是"子 agent 能力"的全部接缝）；想在工具前后做事→写进工具或写进提示纪律。

**考虑**：单人维护的 3k 行项目里，hook 系统的抽象税（注册、顺序、错误传播）买不回等值灵活性。等真出现"多个工具共享横切逻辑"的需求再引入不迟——目前唯一接近横切的（转录写入）是在 `print_human` 里一并完成的。

---

## s05 TodoWrite —— PROGRESS.md（文件版）

**课程要义**：先列步骤再动手，完成率翻倍。

**wz-agent 实现**：目标项目根一个 `PROGRESS.md`，由 agent 用**现有的 write/edit 工具**维护（编码时每完成一个模块更新"已完成/待完成/关键决策"；会话启动先读它接上进度）。REPL 提供 `/progress` 查看。

**考虑**：
- pi 的立场："No built-in to-dos——they confuse models. Use a TODO.md file." wz-agent 从了这个立场：**不造工具、不造机制，prompt 纪律 + 文件**。
- 这个设计最初来自用户需求"项目快照"（编码时同步更新开发文档让别人知道进度）——它与 wz-agent 自己仓库的 PROGRESS.md（"这份文档专门写给 AI coding agent 看"）同构，等于把开发者自己的习惯做成了 agent 纪律。
- 关键性质：进度是**项目工件**，与代码同生死——`/clear` 不删它，换会话/换人都能接上。这也是"文件即状态"格言的一半（另一半是 spec.md）。

---

## s06 Subagent —— `src/agent/tools/task.py`

**课程要义**：给子任务全新的 `messages[]`，最终文本作为一条工具结果返回。

**wz-agent 实现**：task 工具是 s06 的教科书式实现，外加 v2.4 的并行扩展：

- **静态注册表** `SUBAGENTS`：`investigator`（只读：read+bash，20 步）/ `coder`（read/write/edit/bash，15 步）。LLM 只能按名选用，不能自创角色——能力边界是工程决定。
- **上下文隔离**：子 agent 只见自己的 system prompt + 任务描述；主对话只收最终回复（天然摘要），几十 KB 中间输出不占主上下文。
- **双防线禁递归**：子 agent 工具集不含 task（结构性）+ 运行时 `_DEPTH` 深度守卫（防配置失误）。
- **并行扇出**（v2.4）：`fan_out=["子问题1", "子问题2", ...]` 时线程池并行，每线程独立 messages + `make_tools()` 全新实例；结果**按子问题原序聚合**（不按完成序，保证可读性）。两道护栏：只读护栏（工具集含 write/edit 的 agent 拒绝并行——并行写需 worktree 隔离）、成本护栏（`MAX_FAN_OUT=4`）。Ctrl-C 取消未启动线程、不等在跑的（只读无副作用），上抛给中断菜单。

**考虑**：
- 多 agent 做到 **L2（并行扇出）为止**，L3（持久队友/邮箱/任务板）明确不做——那是 s13 的全家桶，需要全新运行时，违反 P2/P3。需要时用 tmux 起多实例，或到时候再评估。
- 并行的结构前提是 s02 的工厂化：先修共享单例竞态，再加扇出——顺序不可颠倒（这也是它分两步提交的原因）。
- 典型收益场景：改不熟悉的模块前，一次 fan_out 同时摸清调用链/数据流/测试覆盖。

---

## s07 Skill Loading —— ❌ 未实现

**课程要义**：用到时再加载；技能先列目录，用到时再展开（渐进披露）。

**wz-agent 实现**：提示按流程**内置**——基座提示（base.py，交互会话）+ triage/to-tickets 两份专用提示（headless 流程）。没有按需加载机制。

**考虑**：
- wz-agent 的"知识面"目前很窄（四种流程），全部前置也塞不满一个 system 消息，渐进披露解决的是"知识多到装不下"的问题——问题不存在，机制就不该存在。
- 若将来技能数量膨胀（比如用户自带的领域提示），s07 的渐进披露是现成的第一站：目录 + 描述常驻，正文按需 read。在那之前，它是 YAGNI。

---

## s08 Context Compact —— `loop.py: _maybe_compact`

**课程要义**：上下文总会满，要有办法腾地方；先整理工具结果，超限再生成历史摘要。

**wz-agent 实现**（简化版）：总量超 40,000 字符（粗估：content + 序列化 tool_calls）时，**就地裁剪**——保留 system + 首条 user（任务定义）+ 最近 6 轮，中间已完成的早期操作丢弃，压缩点插入一条 system 提示告知模型记录已裁剪。每条工具结果追加后检查。

**考虑**：
- 教程的四步压缩（先整理工具结果、再 LLM 生成摘要）成本是"多一次模型调用"；wz-agent 的单字符预算裁剪是"零额外调用"。对 DeepSeek + 中小项目，后者性价比更高。
- 裁剪**会静默丢信息**——对冲手段在提示层（见 base.py 通用纪律）：spec.md 是需求唯一权威、PROGRESS.md 是进度唯一权威，"历史被压缩后先重读两者恢复现状，不要凭记忆编造"。**文件即状态**同时是压缩的保险丝：能丢的都已在盘上。
- 轮为单位裁剪（assistant/user 封轮成对保留）是为了不产生 OpenAI API 拒绝的孤立 tool 消息。

---

## s09 Memory —— ❌ 未实现（文件即状态）

**课程要义**：记住该记的，忘掉该忘的；筛选、提取、整理三子系统。

**wz-agent 的替代方案**（这是全项目最重要的"不做"之一）：

| 记忆系统会造的东西 | wz-agent 的免费替代 |
|---|---|
| 跨会话项目状态 | 目标项目的文件系统本身 |
| "agent 上次做到哪" | PROGRESS.md（会话启动先读） |
| 需求的持久化 | spec.md（澄清产物，编码唯一权威） |
| 工作过程存档 | `runs/<时间戳>_<项目名>/session.log`（纯转录，观测用，不作上下文源） |

**考虑**：
- 来自用户的直接决策："不设记忆系统，只用项目快照"。它恰好与 pi 的立场重合（pi 无记忆，靠会话文件 + context files + 文件系统）。
- 跨会话状态 = spec.md + PROGRESS.md 两个文件，**零记忆代码**。这是 P2 的极致应用：记忆的全部功能由"文件 + read 工具 + prompt 纪律"组合出来。
- 边界也诚实：会话内的对话记忆仍靠 messages[]（受 s08 压缩约束），跨会话才走文件。不做向量库、不做摘要记忆——那是在问题出现之前先付复杂度。

---

## s10 Task System —— 票即任务（`.scratch/` issue 线）

**课程要义**：大目标拆成小任务，排好序，持久化；文件任务图是多 agent 协作的基础。

**wz-agent 实现**（s10 的裁剪版，issue 线全流程）：

```
会话澄清 → spec.md → to-tickets 拆票 → triage 分诊 → /code 按票实现
                        （垂直切片）    （六档标签）      （消费端，v2.5）
```

- **拆解**（`to_tickets.py` 提示 + allocate_issue 工具）：tracer-bullet 垂直切片——每票一条贯穿所有层的完整路径，可独立演示验证，一票一个 context window。票文件：`.scratch/<feature>/issues/NN-<slug>.md`，含 `Type:`/`Status:`/`Blocked by:` 行 + 背景/要做的事/验收标准。
- **分诊**（`triage.py` 提示 + list_issues/set_issue_status 工具）：六档标签（needs-triage / needs-info / ready-for-agent / ready-for-human / wontfix / **done**——v2.5 新增，由实现流程置入）；判定评论走统一模板（判定/理由/建议）。
- **执行**（v2.5，base.py 按票流程）：编码指令先 `list_issues`——有 ready-for-agent 的票就逐票实现：按票号顺序 + `Blocked by:` 行跳过未就绪（`issues.get_blocked_by` 解析）→ 每票串行派 coder 子 agent（一票一任务，票内容自包含）→ 验收通过置 done + 评论 → 同步 PROGRESS.md（按票记账）→ 失败 3 次退回 needs-info 并把所缺信息问用户。无票则回落按 spec 整体实现。

**考虑**——与 s10 的三处刻意差距：

| s10 | wz-agent | 为什么 |
|---|---|---|
| `blockedBy` 依赖图 + ready 判定 | 票号顺序 + Blocked by 行跳过 | 垂直切片的设计初衷就是尽量独立；依赖图是 s10 最重的部分 |
| `claim_task` + owner | 无 | 单人场景没有"谁认领"，只有"做完没做完" |
| JSON 任务文件 | markdown 票 | 票是人也要读写的（分诊评论、验收标准），markdown 是人机共用格式 |

一句话：**票即任务 = s10 的消费端，嫁接在 s06 的子 agent 派发上，用文件即状态替代任务图、用串行替代认领。** 单人场景下这个裁剪覆盖了大部分价值，只花了两成的机制。

---

## s11 Background Tasks / s12 Cron —— ❌ 未实现

**课程要义**：慢操作丢后台完成后注入通知；按时间自动触发任务。

**考虑**：wz-agent 是同步交互工具，长命令有 30 秒超时兜底（超时返回错误让模型自行决策）。后台线程/定时器都是"无人值守运行"的前提设施，而 wz-agent 的定位（监督式执行、随时 Ctrl-C）恰好相反。pi 的对应立场："No background bash——use tmux"（需要时在 tmux 里跑 wz-agent 本身就是后台实例）。

## s13 Agent Teams —— ❌ 未实现（L2 为止）

**课程要义**：持久队友、邮箱消息总线、任务认领、worktree 隔离。

**考虑**：多 agent 路线分了三级——L1 一次性子 agent（v2.1 ✅）、L2 并行扇出（v2.4 ✅）、L3 持久团队（明确 ❌）。L3 需要的每个部件（MessageBus、WORK/IDLE 生命周期、共享任务板、worktree）都是新运行时，违反 P2/P3。**worktree 单独说明**：v2.4 的只读护栏把并行写挡在了门口——等真实写冲突出现（多 coder 并行改同一项目）再付 worktree 的复杂度，现在它是写进 CONTEXT.md _Avoid_ 的"到时再议"。

## s14 MCP —— ❌ 未实现

**考虑**：与 pi 同立场："No MCP——build CLI tools with READMEs"。wz-agent 的外部能力扩展路径是"加一个工具类"（TOOL_CLASSES 一行 + 一个文件），不需要协议层。bash 工具本身就是万能逃生舱（任何 CLI 都是事实上的工具）。

---

## s15 Integrated Harness —— wz-agent 本身

**课程要义**：多种机制，一个循环。

**wz-agent 的集成形态**（单循环会话，`session.py` 约 200 行）：

```
REPL（读输入 + 斜杠命令 + 转录）
  └─ messages[]（跨轮持久，system = 基座提示 + 运行环境路径）
       └─ loop.continue_turn → _run_loop（工具工厂现场构造）
            └─ 工具：四件套 / ask_user / checkpoint / task(扇出) / issue 三件
```

- **基座提示**（`prompts/base.py`）：开头五条路由规则（需求①/修改②/提问③/编码④/无实质内容⑤）+ 三个模式章节（澄清/编码/修改）+ 按票流程 + 通用纪律（双权威文件、git 边界、大文件分块、错误自修 3 次）。`build_system_prompt()` 动态注入目标根/spec/PROGRESS/.scratch 绝对路径——放 system 消息是因为 `_maybe_compact` 永不裁它。
- **锚定**（`paths.set_target` + `-C`）：目标项目 = 显式指定或启动目录，chdir 过去，spec/票/代码全落目标根；runs/ 只留转录（目录名带项目 slug）。
- **防自噬护栏**（`main.is_self_harness` + `--allow-self`）：目标落在 wz-agent 自身仓库内 → 拒绝。事故实录：agent 无自我模型，锚到自己的源码树会把 harness 当"用户项目"，提议把新需求"接入你现有的 main.py"。pi 无此护栏是结构使然（全局安装、配置在 ~/.pi 与工作区物理分离）；wz-agent 住在自己仓库里，护栏是对安装方式的正确补偿——若将来全局化（pip install + ~/.wz 配置），此护栏可删。
- **启动**：命令行 / 双击 run.bat（弹文件夹选择框）/ 拖拽到图标 / 右键"发送到 wz-agent-here"。纯外壳层，零新 Python 机制。

**考虑**：v2.2 之前这里是三层嵌套会话 + 约 150 行关键词意图分类器（`_is_question`/`_is_requirement`/...）替模型选阶段函数——正是 learn-claude-code README 批评的"提示词水管"。重构后分类器整体删除，每条判断都在基座提示里找到新家（文档里有逐条搬家对照表）。**删掉的判断去了哪**是这次重构最重要的工程记录。

---

## s16 Workflow Runtime —— ⚠️ CLI 子命令 + 单循环

**课程要义**：编排形状固定时就把它写进代码；保存好的 workflow 用 journal 续跑。

**wz-agent 的两种编排**：

1. **固定形状 → 代码**：triage / to-tickets 是全自动 headless 流程，管线写死在 click 子命令里，阶段间交接物是文件（spec → 票 → Status）。
2. **形状不定 → 模型路由**：澄清/编码/修改不做编排，交给单循环 + 基座提示。

**考虑**：没有 journal/续跑，恢复机制是播种消息——检测到目标已有 spec.md/PROGRESS.md 时注入"先读它们接上进度，不要重复已完成的工作"。对单人工具，"文件 + 播种"覆盖了 journal 的核心价值（断点续作），没付序列化格式的成本。与 pi 的精神一致："adapt pi to your workflows, not the other way around"——wz-agent 把"哪种编排值得固化"留给使用频率说话。

---

## s17 Goal Loop —— ⚠️ 失败自动重试

**课程要义**：目标决定循环什么时候真正结束；独立判断器审查每次"准备停止"。

**wz-agent 实现**（原始版）：`_run_with_retry_on_messages`——一轮结束若以 `[ERR]/[WARN]` 开头，把失败详情作为新 user 消息回喂，让模型分析修复，最多 3 次；`[API-ERR]/[ABORT]` 不重试（LLM 修不了基础设施故障）。按票流程里还有票级重试（失败 3 次退回 needs-info 问用户）。

**考虑**：与教程的差距是**没有独立判断器**——"任务是否真的完成"仍由执行模型自己说了算（自检 + 验收标准跑 bash 是提示级约束）。独立判断器（第二个模型审查停止决定）解决的是执行模型"自以为完成"的欺骗性问题；wz-agent 用"票内验收标准 + bash 实际运行"做廉价替代。等真实场景出现"agent 说做完了但没做完"的痛，再考虑引入——它是整张地图上最值得看的下一站。

---

## 附：版本演进与决策记录

| 版本 | 内容 | 关键决策 |
|---|---|---|
| v0.1–v2.1 | 循环/工具/安全模式/澄清/编码/triage/to-tickets/task 串行派发 | 阶段架构形成（后来被推翻） |
| v2.2 | 单循环会话：删意图分类器与三层会话，基座提示模型自路由 | P1 的第一次大规模执行；[DONE] 协议退役 |
| v2.3 | 目标锚定（-C）+ 进度文档 PROGRESS.md + git 边界 | 用户否决"还原点"（自动 commit）→ harness 零 git；"项目快照"澄清为进度文档 |
| v2.4 | 工具工厂化 + task 并行扇出 | 先修竞态再并行（顺序不可颠倒）；只读护栏挡并行写 |
| v2.5 | 票即任务（done 标签 + 按票实现）+ triage 评论模板 | s10 消费端裁剪版：无依赖图/claim/owner |
| 补丁 | 防自噬护栏 + GUI 启动 | 事故驱动；"能用结构消灭的问题不要留给运行时"的反面教材 |

每个决策的 _Avoid_ 边界（防止将来手痒重新引入）都记录在 `CONTEXT.md` 术语表：不做记忆系统、不做邮箱式团队、不做 MCP、不做自动 commit、不回沙箱模型。
