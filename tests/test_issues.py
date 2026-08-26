"""agent.issues 文件操作层单元测试。

测试覆盖：issue 文件枚举/编号分配、路径解析（精确/前缀/歧义）、
Status 行读写、CLI 目标解析。所有文件系统操作都重定向到 pytest
临时目录，避免污染仓库真实的 .scratch/。
"""

import pytest

from agent import issues, paths


# ---------- 辅助 & 隔离 ----------


def _make_feature(slug: str = "demo", files: tuple[str, ...] = ()) -> None:
    """在临时 .scratch/<slug>/issues/ 下创建一组 issue 文件。"""
    d = issues.issues_dir(slug)
    for name in files:
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# {name}\nStatus: needs-triage\n", encoding="utf-8")


@pytest.fixture(autouse=True)
def _isolate_scratch(tmp_path, monkeypatch):
    """把目标项目重定向到临时目录，使 .scratch/ 与根 spec 落在临时目录下。"""
    monkeypatch.setattr(paths, "TARGET_ROOT", tmp_path)


# ---------- list_issue_files ----------


def test_list_issue_files_empty():
    assert issues.list_issue_files("demo") == []


def test_list_issue_files_filters_and_sorts():
    _make_feature(files=("03-b.md", "01-a.md", "10-c.md", "notes.md", "readme.txt"))
    names = [p.name for p in issues.list_issue_files("demo")]
    # 只含数字开头的 .md 文件，且按文件名排序
    assert names == ["01-a.md", "03-b.md", "10-c.md"]


# ---------- next_issue_number ----------


def test_next_issue_number_empty():
    assert issues.next_issue_number("demo") == 1


def test_next_issue_number_sequential():
    _make_feature(files=("01-a.md", "02-b.md"))
    assert issues.next_issue_number("demo") == 3


def test_next_issue_number_skips_gaps():
    # 编号空洞按最大编号 + 1 计算，不补空洞
    _make_feature(files=("01-a.md", "05-b.md"))
    assert issues.next_issue_number("demo") == 6


# ---------- issue_path ----------


def test_issue_path_full_filename():
    _make_feature(files=("01-auth.md", "01-auth-flow.md"))
    p = issues.issue_path("demo", "01-auth.md")
    assert p is not None and p.name == "01-auth.md"


def test_issue_path_stem_exact():
    # stem 精确匹配优先，不误命中前缀更长的 "01-auth-flow"
    _make_feature(files=("01-auth.md", "01-auth-flow.md"))
    p = issues.issue_path("demo", "01-auth")
    assert p is not None and p.name == "01-auth.md"


def test_issue_path_numeric_prefix():
    _make_feature(files=("01-auth.md",))
    p = issues.issue_path("demo", "01")
    assert p is not None and p.name == "01-auth.md"


def test_issue_path_numeric_prefix_avoids_cross_decades():
    # "1" 补 "-" 成 "1-"，只匹配 "1-*"，不把 "10-*" 当候选
    _make_feature(files=("1-auth.md", "10-other.md"))
    p = issues.issue_path("demo", "1")
    assert p is not None and p.name == "1-auth.md"


def test_issue_path_ambiguous_raises():
    # "01-*" 命中两个文件 → 拒绝静默选择，抛 ValueError
    _make_feature(files=("01-auth.md", "01-auth-flow.md"))
    with pytest.raises(ValueError):
        issues.issue_path("demo", "01")


def test_issue_path_missing():
    _make_feature(files=("01-auth.md",))
    assert issues.issue_path("demo", "99") is None


def test_issue_path_unknown_slug():
    # issues 目录不存在 → 返回 None
    assert issues.issue_path("nope", "01") is None


# ---------- get_status / set_status ----------


def test_get_status_missing_file(tmp_path):
    assert issues.get_status(tmp_path / "nope.md") is None


def test_get_status_parses_line(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("# Title\n\nStatus: needs-triage\nbody\n", encoding="utf-8")
    assert issues.get_status(f) == "needs-triage"


def test_set_status_replaces_existing(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("# Title\nStatus: needs-triage\nbody\n", encoding="utf-8")
    msg = issues.set_status(f, "ready-for-agent")
    assert "ready-for-agent" in msg
    assert issues.get_status(f) == "ready-for-agent"


def test_set_status_inserts_when_missing(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("# Title\nbody\n", encoding="utf-8")
    issues.set_status(f, "wontfix")
    assert issues.get_status(f) == "wontfix"


def test_set_status_invalid_label(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("# Title\n", encoding="utf-8")
    msg = issues.set_status(f, "bad-label")
    assert msg.startswith("[ERR]")
    assert issues.get_status(f) is None  # 非法标签不落盘


def test_set_status_appends_comment(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("# Title\nStatus: needs-triage\n", encoding="utf-8")
    issues.set_status(f, "needs-info", comment="缺验收标准")
    content = f.read_text(encoding="utf-8")
    assert "## Comments" in content
    assert "缺验收标准" in content


# ---------- resolve_issue_target ----------


def test_resolve_issue_target_feature_slug():
    assert issues.resolve_issue_target("demo") == ("demo", None)


def test_resolve_issue_target_file_path(tmp_path):
    f = tmp_path / ".scratch" / "demo" / "issues" / "01-auth.md"
    f.parent.mkdir(parents=True)
    f.write_text("# x", encoding="utf-8")
    feature, ref = issues.resolve_issue_target(str(f))
    assert feature == "demo"
    assert ref == "01-auth"


# ---------- resolve_spec_target ----------


def test_resolve_spec_target_feature_spec():
    sp = issues.spec_path("demo")
    sp.parent.mkdir(parents=True)
    sp.write_text("# spec", encoding="utf-8")
    feature, path = issues.resolve_spec_target("demo")
    assert feature == "demo"
    assert path == sp


def test_resolve_spec_target_root_spec_fallback():
    # feature 级 spec 缺失时回退到目标项目根 spec.md
    root = paths.target_root() / "spec.md"
    root.write_text("# spec", encoding="utf-8")
    feature, path = issues.resolve_spec_target("demo")
    assert feature == "demo"
    assert path == root


def test_resolve_spec_target_missing_raises():
    with pytest.raises(FileNotFoundError):
        issues.resolve_spec_target("demo")


def test_resolve_spec_target_file_path(tmp_path):
    f = tmp_path / "some" / "spec.md"
    f.parent.mkdir(parents=True)
    f.write_text("# spec", encoding="utf-8")
    feature, path = issues.resolve_spec_target(str(f))
    assert feature == "some"  # 非 .scratch 形态时兜底取父目录名
    assert path == f
