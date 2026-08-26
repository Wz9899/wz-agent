"""Issue 管理 —— .scratch/ 本地 markdown issue tracker 的文件操作层。

对应约定（docs/agents/issue-tracker.md）：
    - 每个 feature 一个目录：.scratch/<feature-slug>/
    - spec 在 .scratch/<feature-slug>/spec.md
    - 实现 issue 一个文件一个 ticket：.scratch/<feature-slug>/issues/NN-<slug>.md（从 01 编号）
    - 分诊状态记录在文件顶部附近的 `Status:` 行
    - 评论追加到文件末尾的 `## Comments` 区块下

triage 状态机的标签见 docs/agents/triage-labels.md。
"""

from __future__ import annotations

import re
from pathlib import Path

from agent import paths
from agent.paths import SCRATCH_DIRNAME

# 六个标准 triage 标签（与 docs/agents/triage-labels.md 保持一致；
# done 为 v2.5 新增：实现完成，与五个分诊档位共同构成完整生命周期）
VALID_LABELS: tuple[str, ...] = (
    "needs-triage",
    "needs-info",
    "ready-for-agent",
    "ready-for-human",
    "wontfix",
    "done",
)

# 匹配 "Status: xxx" 行（行首，允许多余空白）
_STATUS_RE = re.compile(r"^Status:\s*(.+?)\s*$", re.MULTILINE)

# 匹配 "Blocked by: 01, 03" 行（无依赖写法不限，如 "（无）"；解析不到返回空）
_BLOCKED_BY_RE = re.compile(r"^Blocked by:\s*(.+?)\s*$", re.MULTILINE)


# ============================================================
# 路径定位
# ============================================================


def scratch_root() -> Path:
    """返回 .scratch/ 根目录路径（目标项目根下）。"""
    return paths.target_root() / SCRATCH_DIRNAME


def feature_dir(slug: str) -> Path:
    """返回 feature 目录路径：.scratch/<slug>/"""
    return scratch_root() / slug


def spec_path(slug: str) -> Path:
    """返回 feature 的 spec 文件路径：.scratch/<slug>/spec.md"""
    return feature_dir(slug) / "spec.md"


def issues_dir(slug: str) -> Path:
    """返回 feature 的 issues 目录路径：.scratch/<slug>/issues/"""
    return feature_dir(slug) / "issues"


# ============================================================
# issue 文件枚举与定位
# ============================================================


def list_issue_files(slug: str) -> list[Path]:
    """列出 feature 下所有 issue 文件（按文件名排序）。

    目录不存在或为空时返回空列表。
    """
    d = issues_dir(slug)
    if not d.is_dir():
        return []
    return sorted(
        (p for p in d.iterdir() if p.suffix == ".md" and p.name[0].isdigit()),
        key=lambda p: p.name,
    )


def next_issue_number(slug: str) -> int:
    """计算下一个可用的 issue 编号（从 01 开始，跳过已占用编号）。

    编号由文件名的数字前缀决定，以最大编号 + 1 递增。
    """
    numbers: list[int] = []
    for p in list_issue_files(slug):
        m = re.match(r"^(\d+)", p.name)
        if m:
            numbers.append(int(m.group(1)))
    return (max(numbers) + 1) if numbers else 1


def issue_path(slug: str, issue: str) -> Path | None:
    """根据 issue 引用解析出完整文件路径。

    支持的引用格式（按优先级）:
        - "01-auth.md"  → 完整文件名精确匹配
        - "01-auth"     → stem 精确匹配
        - "01"          → 编号前缀匹配（要求唯一命中）

    解析规则:
        1. 先尝试精确匹配（完整文件名 / stem），避免 "01-auth" 误命中 "01-auth-flow"。
        2. 无精确匹配时退化为前缀匹配；若多个文件命中则抛 ValueError（歧义，
           绝不静默选第一个）。

    返回:
        匹配的 issue 文件路径。

    抛出:
        ValueError: 引用匹配到多个文件，存在歧义。
    """
    d = issues_dir(slug)
    if not d.is_dir():
        return None

    target = issue.strip()
    files = [p for p in d.iterdir() if p.suffix == ".md"]

    # ---- 1. 精确匹配（文件名 / stem）----
    for p in files:
        if p.name == target or p.stem == target:
            return p

    # ---- 2. 编号/前缀匹配：收集所有命中，要求唯一 ----
    # 纯数字引用补 "-" 前缀，避免 "1" 同时命中 "01-xxx" 和 "10-xxx"
    prefix = target + "-" if target.isdigit() else target
    matches = [p for p in files if p.name.startswith(prefix)]

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(
            f"issue 引用 '{issue}' 匹配到多个文件，存在歧义: "
            + ", ".join(sorted(p.name for p in matches))
            + "。请用完整文件名精确指定。"
        )
    return None


# ============================================================
# Status 行读写（triage 状态机）
# ============================================================


def get_status(path: Path) -> str | None:
    """读取 issue 文件的 Status 值；无 Status 行或读取失败时返回 None。"""
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    m = _STATUS_RE.search(content)
    return m.group(1).strip() if m else None


def get_blocked_by(path: Path) -> list[str]:
    """读取 issue 的 Blocked by 依赖列表（票号字符串，如 ["01", "03"]）。

    解析 "Blocked by: 01, 03" 行：逗号/顿号/空白分隔，只保留纯数字项；
    无依赖行、行内无有效编号（如 "（无）"）→ 空列表。
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    m = _BLOCKED_BY_RE.search(content)
    if not m:
        return []
    parts = [p.strip() for p in re.split(r"[,，、\s]+", m.group(1)) if p.strip()]
    return [p for p in parts if p.isdigit()]


def ticket_stem(path: Path) -> str:
    """issue 文件名去后缀的编号（如 02-auth-flow → "02"）。"""
    return path.stem.split("-", 1)[0]


def set_status(path: Path, label: str, comment: str = "") -> str:
    """更新 issue 的 Status 行，可选追加评论到 ## Comments 区块。

    行为:
        - Status 行已存在 → 整行替换为新标签
        - Status 行不存在 → 在标题行（首个 # 行）之后插入
        - comment 非空 → 追加到文件末尾的 ## Comments 区块（不存在则创建）

    返回:
        成功时返回操作描述；失败时返回以 [ERR] 开头的消息（供工具层直接返回）。
    """
    # 标签合法性校验 —— 状态机只能落在五个已知状态上
    if label not in VALID_LABELS:
        return (
            f"[ERR] 非法标签 '{label}'。必须是: {', '.join(VALID_LABELS)}"
        )

    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"[ERR] issue 文件不存在 —— {path}"
    except (OSError, UnicodeDecodeError) as e:
        return f"[ERR] 读取 issue 失败 —— {e}"

    lines = content.split("\n")

    # ---- 1. 替换已存在的 Status 行；找不到则插入 ----
    replaced = False
    for i, line in enumerate(lines):
        if re.match(r"^Status:\s*", line):
            lines[i] = f"Status: {label}"
            replaced = True
            break

    if not replaced:
        # 在首个标题行之后插入（保持"顶部附近"的约定）；无标题则插到最前
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("#"):
                insert_at = i + 1
                break
        lines.insert(insert_at, f"Status: {label}")

    content = "\n".join(lines)

    # ---- 2. 可选：追加评论到 ## Comments ----
    if comment:
        comment = comment.strip()
        if "## Comments" not in content:
            content += "\n\n## Comments\n"
        content += f"\n- {comment}"

    try:
        path.write_text(content, encoding="utf-8")
    except OSError as e:
        return f"[ERR] 写入 issue 失败 —— {e}"

    result = f"✅ {path.name} 状态已更新为 '{label}'"
    if comment:
        result += "，已追加评论到 ## Comments"
    return result


# ============================================================
# CLI 目标解析（main.py 使用）
# ============================================================


def resolve_issue_target(target: str) -> tuple[str, str | None]:
    """把 triage 的目标解析为 (feature_slug, issue 引用或 None)。

    支持两种输入:
        - issue 文件路径（如 .scratch/guessing-game/issues/01-auth.md）
          → 定位到具体 issue，feature 从路径推断
        - feature-slug（如 guessing-game）→ 处理该 feature 下全部 issues
    """
    p = Path(target)
    if p.is_file() and p.suffix == ".md":
        # 路径形态：.../.scratch/<feature>/issues/NN-xxx.md
        try:
            if p.parents[2].name == SCRATCH_DIRNAME:
                return p.parents[1].name, p.stem
        except IndexError:
            pass
    return target, None


def resolve_spec_target(target: str) -> tuple[str, Path]:
    """把 to-tickets 的目标解析为 (feature_slug, spec 文件路径)。

    支持两种输入:
        - feature-slug → 读 .scratch/<slug>/spec.md（不存在则抛 FileNotFoundError）
        - spec 文件路径 → 直接读该文件；
          .scratch/<slug>/spec.md 形态时 slug 取父目录名，否则取文件所在目录名兜底
    """
    p = Path(target)
    if p.is_file():
        # 已是文件路径
        try:
            if p.name == "spec.md" and p.parents[1].name == SCRATCH_DIRNAME:
                return p.parent.name, p
        except IndexError:
            pass
        return p.parent.name, p

    # 当作 feature-slug：读 .scratch/<slug>/spec.md
    sp = spec_path(target)
    if sp.is_file():
        return target, sp

    # fallback：feature 级 spec 不存在时，回退到目标项目根 spec.md
    # （澄清阶段把 spec 写到项目根，拆解阶段也应收得到这份 spec）
    root_spec = paths.target_root() / "spec.md"
    if root_spec.is_file():
        return target, root_spec

    raise FileNotFoundError(
        f"未找到 spec 文件：{sp}（也未见项目根 spec.md）\n"
        f"请先运行需求澄清阶段把 spec 放到其中一处，"
        f"或直接传 spec 文件路径（python src/main.py to-tickets <spec路径>）。"
    )
