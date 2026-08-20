<!-- 注：本文件于 2026-08-20 在公司电脑重建（基础版）。家里电脑有更完整的版本，合并后删除本注释。 -->

# 项目进度 & Agent 行为规范

> 这份文档专门写给 AI coding agent 看。每次会话开始时先读这里。

---

## ⚠️ 待办任务：多机文档合并（2026-08-20，由家里电脑的 agent 执行）

**背景**：公司电脑重建了本项目的基础文档并推送（commit `67f7707`）。家里本机有更完整的旧版本，它们当时被 `.gitignore` 忽略、未被 git 跟踪。本任务把家里版本合并上传，完成后两台机器文档一致。

**执行步骤**（在项目根目录，Git Bash）：

1. **备份家里本地版本**——它们未被跟踪，直接 `git pull` 会被拒绝（untracked files would be overwritten）：
   ```bash
   mv PROGRESS.md PROGRESS.home.md
   mv AGENTS.md AGENTS.home.md
   mv docs/开发问题记录.md docs/开发问题记录.home.md
   mv docs/agents docs/agents.home        # 若不存在则跳过
   ```
2. **拉取公司版本**：`git pull`
3. **逐个合并**——家里版本为主体（更完整），公司版本为参考：
   - `PROGRESS.md` / `AGENTS.md`：以 `*.home.md` 内容为准；公司版若有新增的规范条目则吸收进来
   - `docs/开发问题记录.md`：家里版本为准（含全部历史问题记录）
   - `docs/agents/`：把 `docs/agents.home/` 中的 `domain.md`、`issue-tracker.md`、`triage-labels.md` 复制进 `docs/agents/`，然后删除占位的 `docs/agents/README.md`
4. **清理**：删除每个合并后文件顶部的 `<!-- 注：…2026-08-20 公司电脑重建… -->` 标记；确认无误后删除所有 `*.home.md` 和 `docs/agents.home/` 备份
5. **提交推送**：
   ```bash
   git add -A
   git commit -m "docs: 合并家里电脑的开发文档（多机同步完成）"
   git push
   ```
6. 完成后，公司电脑 `git pull` 即可拿到合并版。此任务完成后**删除本节**。

---

## 对 Agent 的要求

1. **一步一步写代码**——每一步都要解释实现了什么、用了什么函数、为什么这样写
2. **中文回复**
3. **用户手搓代码**——agent 只指导，不替用户写。除非用户明确说"你来写"
4. **每次写完一个模块**，更新本文档的"已完成"和"待完成"
5. **改动代码前先读相关源文件**，接上进度再动手

---

## 已完成

| 版本 | 模块 | 状态 |
|---|---|---|
| v0.1 | DeepSeek API 连通 | ✅ |
| v0.2 | ReAct 循环 + 工具调用（read/write/edit/bash） | ✅ |
| v0.3 | Bash 安全模式——auto/plan 双模式 | ✅ |
| v0.4 | 需求澄清——Agent 主动追问用户 | ✅ |
| v0.5 | 编码执行——根据 Spec 自动生成代码 | ✅ |
| v1.0 | CLI 完整交互 + bash 安全模式 | ✅ |
| v2.0 | triage（issue 分诊）+ to-tickets（任务拆解） | ✅ |
| — | 示例项目 examples/nba-wordle（全流程产物） | ✅ |

## 进行中 / 待完成

| 优先级 | 模块 | 说明 |
|---|---|---|
| 1 | v2.1 ticket ↔ code 阶段自动衔接 | 拆解出的 ticket 自动流转到编码阶段 |

## 技术选型

- 语言： Python 3.12
- LLM: DeepSeek（`deepseek-chat`，OpenAI 兼容 API）
- CLI: click；UI: rich
