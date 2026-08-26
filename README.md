# wz-agent

一个从零手搓的通用编码助手——主动追问需求，自动生成代码。

> ✅ 当前版本：v2.3 — 目标项目锚定 + 进度文档（agent 直接在你的项目里工作，同步维护 PROGRESS.md）

## 功能规划

| 阶段 | 功能 | 状态 |
|---|---|---|
| v0.1 | DeepSeek API 连通 | ✅ |
| v0.2 | ReAct 循环 + 工具调用（read/write/edit/bash） | ✅ |
| v0.3 | Bash 安全模式 — auto/plan 双模式 | ✅ |
| v0.4 | 需求澄清 —— Agent 主动追问用户 | ✅ |
| v0.5 | 编码执行 —— 根据 Spec 自动生成代码 | ✅ |
| v1.0 | CLI 完整交互 + bash 安全模式 | ✅ |
| v2.0 | triage（issue 分诊）+ to-tickets（任务拆解） | ✅ |
| v2.1 | 子 agent 派发（task 工具，LLM 自主决策）+ Windows bash 修复 | ✅ |
| v2.2 | 单循环会话重构：删意图分类器，基座提示模型自路由 | ✅ |
| v2.3 | 目标项目锚定（-C，删 output/ 沙箱）+ 进度文档 PROGRESS.md + git 边界（harness 零 git） | ✅ |
| v2.4 | 工具工厂化（修共享单例竞态）+ task 并行扇出（fan_out，只读护栏） | ✅ |
| v2.5 | 按票实现（票即任务：逐票派 coder、置 done、PROGRESS 记账）+ triage 评论模板 | ✅ |

## 技术栈

- **语言**: Python 3.12
- **LLM**: DeepSeek (deepseek-chat, OpenAI 兼容 API)
- **CLI**: click + rich

## 示例项目：NBA 神秘球员猜猜乐

一个由 **wz-agent 自动生成**的纯前端游戏示例——完整走通了「需求澄清 → 编码执行 → 修改反馈」全流程的产物。

```
examples/nba-wordle/
├── index.html   # 完整游戏（内联样式 + 逻辑 + 球员数据，单文件）
└── spec.md      # 游戏的需求规格（澄清阶段产出）
```

**玩法**：系统随机选定一名现役 NBA 球员作为"神秘目标"，玩家最多 7 次机会猜球员，每次猜完读取属性对比提示（数值属性：高于/低于/相同；分类属性：匹配/不匹配）缩小范围，猜中获胜，7 次未中揭晓答案。

**运行**：浏览器直接打开 `examples/nba-wordle/index.html` 即可（纯前端，无后端、无网络依赖，球员数据内置）。

**它怎么来的**：`python src/main.py` → 输入需求 → agent 澄清写 spec → 编码生成 → 按你的反馈修改。想生成你自己的项目，见下方[快速开始](#快速开始)。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 设置 API Key

**PowerShell:**
```powershell
$env:DEEPSEEK_API_KEY="sk-你的key"
```

**Git Bash / Linux / Mac:**
```bash
export DEEPSEEK_API_KEY="sk-你的key"
```

**或使用 `.env` 文件**（推荐，自动加载）:
```bash
cp .env.example .env   # 然后编辑 .env 填入 Key
```

### 3. 运行

```bash
# 锚定目标项目后进入会话（agent 直接在该项目里工作；默认目标 = 启动时所在目录）
python src/main.py -C /path/to/your-project

# 或直接把任务写进命令（播种进会话，后续照常对话）
python src/main.py -C /path/to/your-project "帮我加一个计分功能"

# 会话内：说需求 → agent 逐轮问清写 spec.md → 输入 /code 开始编码
#         → 直接说修改意见，agent 精准修改 —— 全程同一个对话上下文
# 按票实现：to-tickets 拆票 + triage 分诊后，/code 自动逐票实现（票即任务）
#         ready-for-agent 的票逐张派 coder 子 agent，验收置 done，PROGRESS.md 记账

# issue 分诊（triage 状态机，五档标签，全自动）
python src/main.py -C /path/to/your-project triage <feature-slug 或 issue 文件路径>

# 任务拆解（spec → 垂直切片 tickets，全自动）
python src/main.py -C /path/to/your-project to-tickets <feature-slug 或 spec 文件路径>

# headless：不进会话，带任务参数一次性跑完（脚本化场景）
python src/main.py "帮我写一个猜人游戏" --no-interactive

# plan 模式：先收集命令，再批量执行
python src/main.py "帮我写一个猜人游戏" --safety-mode plan
```

> 💡 默认**流式输出**：agent 的思考与工具调用过程会实时打印，方便观察与随时 `Ctrl-C` 中断；
> 加 `--no-stream` 可关闭（等待完整结果后一次性返回）。
>
> 💡 **单循环会话（v2.2）**：澄清、编码、修改、问答在同一个对话里，由 agent 根据对话
> 状态自行路由（需要确定性时用 `/code` 显式触发）。需求澄清时 agent 会问你问题
> （`ask_user`）；编码时按模块自主执行、每完成一个模块汇报进度（`checkpoint`，不停下
> 等待）；**随时 `Ctrl-C` 中断**（继续 / 注入指令 / 停止）。triage / to-tickets 始终全自动。
>
> 💡 **进度文档（v2.3，项目快照）**：编码时 agent 同步维护目标项目的 `PROGRESS.md`
> （已完成/待完成/关键决策）——任何人在任何时候打开它就知道开发到哪了；下次会话
> agent 先读它接上进度，不建记忆系统。`/progress` 随时查看。

## 安全边界

> bash 工具内置的两道防护只是**防呆，不是安全边界**。

- **危险命令黑名单**：只拦截少数已知模式（如 `rm -rf /`），黑名单可轻易绕过
  （`rm -r -f /`、`rm -rf ~/x` 等变体都不在名单内）。
- **30 秒超时**：命令不会无限挂起。

真正可靠的闸门是 **plan 安全模式**（`--safety-mode plan`）：命令先收集到计划，
人工确认后批量执行。在 **auto 模式**下命令直接执行，安全完全依赖模型自律。
**不要**在含重要数据的环境用 auto 模式运行不受信任的任务。

### git 边界（v2.3）

- harness **零 git**：wz-agent 的 Python 代码不执行任何 git 命令，对任意目录可用
- agent 经 bash **可读不可写**（提示词级约束）：查 `git status/log/diff` 理解项目
  允许；`commit/push/reset/checkout` 等写操作不做
- 版本控制、快照、回滚完全由你自己管理——**agent 动手前自己 commit 一下**
  就是最好的还原点；`/clear` 只删 spec.md 与对话历史，绝不碰项目文件

## 项目结构

```
wz-agent/
├── CONTEXT.md              # 术语表 & 技术选型
├── PROGRESS.md             # 开发进度（AI agent 读这个）
├── README.md               # 你正在看的
├── requirements.txt        # Python 依赖
├── .env.example            # 环境变量模板（复制为 .env）
├── test_api.py             # API 连通性测试
├── examples/nba-wordle/    # 示例项目：agent 生成的 NBA 猜球员游戏
├── runs/                   # wz-agent 自己的观测记录：<时间戳>_<项目名>/session.log（产物在目标项目里，不在这）
├── .scratch/               # 本地 issue tracker（issue-tracker.md 约定）
│   └── <feature-slug>/
│       ├── spec.md         # 该 feature 的需求规格
│       └── issues/         # 一个 ticket 一个文件：NN-<slug>.md
└── src/
    ├── main.py             # 入口脚本（click + rich + 子命令分发）
    └── agent/
        ├── loop.py         # ReAct 循环引擎（工具调用 + 自动重试）
        ├── context.py      # spec.md 定位/读写/注入
        ├── issues.py       # .scratch/ issue 文件操作层（v2.0）
        ├── tools/          # read/write/edit/bash/task + triage/tickets 工具
        └── prompts/        # base（单循环基座）/ triage / to-tickets 提示
```
