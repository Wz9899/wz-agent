# wz-agent

一个从零手搓的通用编码助手——主动追问需求，自动生成代码。

> ✅ 当前版本：v2.0 — triage（issue 分诊）+ to-tickets（任务拆解）

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
| v2.1 | ticket ↔ code 阶段自动衔接 | 📋 |

## 技术栈

- **语言**: Python 3.12
- **LLM**: DeepSeek (deepseek-chat, OpenAI 兼容 API)
- **CLI**: click + rich

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

### 3. 运行

```bash
# 阶段一：需求澄清（默认）
python src/main.py "帮我写一个猜人游戏"

# 阶段二：编码执行（需要先有 spec.md）
python src/main.py --phase code "请根据 spec.md 实现项目"

# 阶段三：issue 分诊（triage 状态机，五档标签）
python src/main.py triage <feature-slug 或 issue 文件路径>

# 阶段四：任务拆解（spec → 垂直切片 tickets）
python src/main.py to-tickets <feature-slug 或 spec 文件路径>

# plan 模式：先收集命令，再批量执行
python src/main.py "帮我写一个猜人游戏" --safety-mode plan
```

## 项目结构

```
wz-agent/
├── CONTEXT.md              # 术语表 & 技术选型
├── PROGRESS.md             # 开发进度（AI agent 读这个）
├── README.md               # 你正在看的
├── requirements.txt        # Python 依赖
├── test_api.py             # API 连通性测试
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
        ├── tools/          # read/write/edit/bash + triage/tickets 工具
        └── prompts/        # clarify / code / triage / to-tickets 四套 prompt
```
