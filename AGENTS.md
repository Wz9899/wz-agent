## Agent skills

### Issue tracker

Issues 以本地 markdown 文件形式存放在 `.scratch/` 下。详见 `docs/agents/issue-tracker.md`。

### Triage labels

使用默认的五个标准 triage 标签：`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix`。详见 `docs/agents/triage-labels.md`。

### Domain docs

单上下文（single-context）布局——根目录 `CONTEXT.md` + `docs/adr/`。详见 `docs/agents/domain.md`。

### 会话流程

1. 会话开始先读 `PROGRESS.md` 接上进度
2. 改动代码前先读相关源文件，理解现状再动手
3. 每完成一个模块，更新 `PROGRESS.md` 的"已完成/待完成"
4. 开发中踩的坑记入 `docs/开发问题记录.md`
5. **写或改 agent 消费的文本前**（系统提示词 `prompts/*.py`、本文件、CONTEXT.md、
   PROGRESS.md 约定），先读 skill `writing-for-agents`（~/.claude/skills/ 或
   ~/.pi/agent/skills/），按它的杠杆自检：context pointer 措辞（must-have 目标
   配强指针）、分支显式化、正向表述而非禁止、单一事实源、逐句无 no-op。

### 文档写作规范

写培训/教学类文档（如 `docs/Agent实现原理与选型-v2.md`）时遵守：

1. **术语必须规范**：不生造叫法（如"学界四模块"），引用学术/权威框架时用规范名称与出处；拿不准先查原文
2. **知识源优先级**：Agent 相关知识优先从 ai-agent-book 获取（本地 `D:/AI-learning/ai-agent-book`）；不参考 learn-claude-code
3. **结构框架**：讲解类文档的结构以 ai-agent-book 的框架为准，wz-agent 只作为示例演示（文件路径 + 关键实现 + 踩坑），不参与定义结构
4. **不显式标注来源关系**：正文中不要出现"ai-agent-book 第 X 章说……"这类表述，直接陈述内容；出处只在附录/延伸阅读出现
5. **概念关系必须自洽**：如 harness 与 agent 的边界（上下文、工具、ReAct 循环、约束验证纠正均属 harness，仅 LLM 除外）——全文图表与正文不能互相矛盾
6. **写作前先对齐受众与定位**：给谁看、读完能干什么；同类文档已存在时先问"它哪里不对"而不是推倒重写
