# wz-agent

一个从零手搓的通用编码助手——主动追问需求，自动生成代码。

> 🚧 开发中 | 当前版本：v0.2 — ReAct 循环 + 工具调用已实现

## 功能规划

| 阶段 | 功能 | 状态 |
|---|---|---|
| v0.1 | DeepSeek API 连通 | ✅ |
| v0.2 | ReAct 循环 + 工具调用（read/write/edit/bash） | ✅ |
| v0.3 | 需求澄清 —— Agent 主动追问用户 | ⏳ |
| v0.4 | 编码执行 —— 根据 Spec 自动生成代码 | ⏳ |
| v1.0 | CLI 完整交互 + bash 安全模式 | ⏳ |
| v2.0 | 集成 triage（issue 管理）+ to-tickets（任务拆解） | 📋 |

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
python src/main.py "帮我写一个猜人游戏"
```

## 项目结构

```
wz-agent/
├── CONTEXT.md              # 术语表 & 技术选型
├── PROGRESS.md             # 开发进度（AI agent 读这个）
├── README.md               # 你正在看的
├── requirements.txt        # Python 依赖
├── test_api.py             # API 连通性测试
└── src/
    ├── main.py             # 入口脚本
    └── agent/
        ├── loop.py         # ReAct 循环引擎（v2：完整工具调用）
        ├── tools/
        │   ├── base.py     # 工具抽象基类
        │   ├── read.py     # 读取文件
        │   ├── write.py    # 创建/覆盖文件
        │   ├── edit.py     # 精确文本匹配替换
        │   └── bash.py     # 执行 Shell 命令
        └── prompts/        # 系统提示词（需求澄清 / 编码执行）
```
