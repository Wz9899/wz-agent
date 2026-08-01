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

# .scratch/ 根目录名（固定在项目根目录下）
SCRATCH_DIRNAME: str = ".scratch"

# 五个标准 triage 标签（与 docs/agents/triage-labels.md 保持一致）
VALID_LABELS: tuple[str, ...] = (
    "needs-triage",
    "needs-info",
    "ready-for-agent",
    "ready-for-human",
    "wontfix",
)

# 项目根目录 = src/agent/ 的上一级的上一级
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent

# 匹配 "Status: xxx" 行（行首，允许多余空白）
_STATUS_RE = re.compile(r"^Status:\s*(.+?)\s*$", re.MULTILINE)


# ============================================================
# 路径定位
# ============================================================


def scratch_root() -> Path:
    """返回 .scratch/ 根目录路径。"""
    return PROJECT_ROOT / SCRATCH_DIRNAME


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

    支持的引用格式（均可）:
        - "01"          → 数字前缀匹配
        - "01-auth"     → stem 前缀匹配
        - "01-auth.md"  → 完整文件名

    返回 None 表示未找到匹配的 issue 文件。
    """
    d = issues_dir(slug)
    if not d.is_dir():
        return None

    target = issue.strip()
    # 纯数字引用补一个 "-" 前缀，避免 "1" 同时命中 "01-xxx" 和 "10-xxx"
    if target.isdigit():
        target = target + "-"

    for p in d.iterdir():
        if p.suffix == ".md" and p.name.startswith(target):
            return p
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
    if not sp.is_file():
        raise FileNotFoundError(
            f"未找到 spec 文件：{sp}\n"
            f"请先运行需求澄清阶段把 spec 放到该位置，"
            f"或直接传 spec 文件路径（python src/main.py to-tickets <spec路径>）。"
        )
    return target, sp
