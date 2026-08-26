# Coding Agent

一个通用的编码助手——主动追问需求，然后自动生成代码。能写任何项目，猜人游戏只是其中一个 demo。

## 核心概念

**Agent（编码助手）**：
能自主使用工具、在 ReAct 循环中完成编码任务的 AI 代理。

**ReAct 循环**：
思考 → 行动 → 观察 → 再思考的执行模式。每轮 LLM 输出推理 + 工具调用，执行工具后把结果喂回，循环直到任务完成。

**单循环会话（v2.2 重构）**：
一次交互会话 = 一份基座提示 + 一份跨轮持久的 messages[] + 每轮调 continue_turn。澄清、编码、修改、问答在同一对话里由**模型自行路由**（基座提示的"每轮先路由"），不再由 Python 关键词分类器选阶段函数。旧三层会话（REPL → 阶段函数 → loop 对话循环）与 [DONE] 阶段边界协议已退役。原则：判断归模型，不归代码——软路由（prompt）错判还能 ask_user 找回来，硬路由（if-else）错判直接丢功能。

**需求澄清（会话内模式一）**：
Agent 主动追问用户需求（ask_user 阻塞式，一轮一个聚焦问题），逐轮深入直到需求明确，写入 spec.md，然后问用户是否补充（替代旧 _confirm_requirements 确认环节）。

**编码执行（会话内模式二）**：
用户 /code 或明确要求后，Agent 根据 spec.md 编码实现：分模块自主执行、checkpoint 汇报不停顿、写完即测、错误自修。开始后不再 ask_user。

**修改反馈（会话内模式三）**：
项目里已有代码时，用户直接说修改意见；Agent 先 read 现状，用 edit 精准修改，绝不 write 重写整个文件。

**Spec 文档**：
需求澄清的输出物，自由格式的自然语言描述完整需求（游戏玩法、规则、技术栈等）。是编码执行的唯一权威输入；对话历史被压缩后，Agent 靠重读 spec.md 恢复状态（文件即状态）。

**上下文管理**：
spec.md 提供项目级上下文，文件系统即代码索引，通过 read 工具按需读取已生成文件。与 pi 的策略一致——不做预索引，靠工具探索。

**工具**：
Agent 可调用的四个基础能力：

- **read** — 读取文件内容
- **write** — 创建或覆盖文件
- **edit** — 精确文本匹配替换（oldText → newText）
- **bash** — 执行 shell 命令

**Edit 策略**：
精确文本匹配替换——LLM 输出 oldText 和 newText，在目标文件中精确查找 oldText 并替换。与 pi 的编辑模式一致。

**工具工厂（v2.4）**：
make_tools() 每次调用构造一组全新工具实例（名字→类的目录 TOOL_CLASSES 为单一事实来源），全局单例 ALL_TOOLS 退役。每个循环（主循环每次 _run_loop、子 agent 每线程）各自一份，bash 的 mode/_plan 等可变状态零共享——这是并行派发的线程安全前提。plan 模式生命周期天然对齐"一次 _run_loop 调用"。

**并行扇出（v2.4）**：
task 工具的 fan_out 参数传多个互不依赖的子问题，线程池并行调查、结果按子问题原序聚合返回。只读护栏（工具集含 write/edit 的 agent 拒绝并行——并行写需 worktree 隔离，暂不引入）+ 成本护栏（MAX_FAN_OUT=4）。Ctrl-C 中断由 _run_loop 的中断菜单接管。
_Avoid_: 持久队友/邮箱/任务板（L3 团队机制）——需要时用 tmux 起多实例，或到时候再评估；worktree 隔离——等真实写冲突出现再付这个复杂度。

**按票实现（v2.5，票即任务）**：
编码指令到达时，若目标项目有 .scratch/ 且存在 Status=ready-for-agent 的票，则逐票实现：按票号顺序 + Blocked by 行跳过未就绪票 → 每票串行派 coder 子 agent（一票一任务，票内容自包含）→ 验收通过则 set_issue_status 置 done + 评论 → 同步 PROGRESS.md（按票记账）。失败 3 次的票退回 needs-info 并问用户。标签表新增 done（由实现流程置入，分诊不主动打）。这是 .scratch/ issue 线的消费端：to-tickets（拆解）→ triage（分诊）→ 按票实现（执行）→ PROGRESS（记账）闭环。
_Avoid_: 任务依赖图/claim/owner（s10 全家桶）——垂直切片刻意无依赖，票号顺序 + Blocked by 行已够；并行实现多票——写操作不并行（同 v2.4 只读护栏），等真实需求再评估 worktree。

**自动修复**：
编码执行时遇到错误（测试失败、编译报错），自动将错误信息喂给 LLM，让其自行修复，最多 3 次。超过 3 次停下来问用户。

**Bash 安全模式**：

- **自动模式** — agent 直接执行命令，适合低风险操作（安装依赖、跑测试）
- **计划模式** — agent 列出命令清单，用户确认后批量执行，适合高风险操作
_Avoid_: 无限制直接执行

**进度文档（项目快照，v2.3）**：
目标项目根的 `PROGRESS.md`，agent 编码时用 write/edit 同步维护（每完成一个模块更新已完成/待完成/关键决策），会话启动时先读它接上进度。它是项目进度的对外窗口：任何人在任何时候打开就能知道开发到哪了。这就是"不建记忆系统"的替代物——跨会话状态 = spec.md（需求）+ PROGRESS.md（进度），文件即状态，零记忆机制。命名沿用 wz-agent 自身仓库的 PROGRESS.md 惯例。
_Avoid_: 用 Python 自动生成（判断归模型：agent 用现有 write/edit 维护）；把进度记到对话历史里（压缩即丢）；与 git 版本快照混淆（那是用户自己的 git 的事）。

**git 边界（v2.3 决策）**：
harness 零 git —— Python 代码不执行任何 git 命令，对任意目录可用；agent 经 bash 可读不可写（查 status/log/diff 帮助理解项目允许，commit/push/reset/checkout 等写操作禁止，prompt 级软约束）；版本控制、快照、回滚完全由用户自己用 git 管理，/clear 绝不碰项目文件。
_Avoid_: 自动 commit/还原点/权限弹窗类"安全功能"——那是用户的部署决策，不是产品功能（与 pi 立场一致）。

**目标项目（target，v2.3）**：
agent 直接在其上工作的项目目录，`-C` 显式指定或默认取启动时所在目录（`paths.set_target` 锚定 + chdir）。spec.md、.scratch/、生成的代码全部落在目标项目里；wz-agent 自己只保留 runs/ 转录（目录名带项目名，不含任何产物）。
_Avoid_: 重新引入 runs/<ts>/output/ 沙箱 —— 那会把 wz-agent 退化回"项目生成器"。
