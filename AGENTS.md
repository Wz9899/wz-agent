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
