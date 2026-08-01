"""edit 工具单元测试：精确匹配替换 + 唯一性校验。"""

import pytest

from agent.tools.edit import EditTool


@pytest.fixture
def tool() -> EditTool:
    return EditTool()


def _write(tmp_path, content) -> str:
    p = tmp_path / "f.txt"
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_replace_success(tool, tmp_path):
    path = _write(tmp_path, "hello world\n")
    msg = tool.run(path, "hello", "HELLO")
    assert "完成替换" in msg
    assert open(path, encoding="utf-8").read() == "HELLO world\n"


def test_replace_reports_line_number(tool, tmp_path):
    path = _write(tmp_path, "one\ntwo\nthree\n")
    msg = tool.run(path, "two", "TWO")
    assert "第 2 行" in msg


def test_replace_not_found_keeps_file(tool, tmp_path):
    path = _write(tmp_path, "abc\n")
    msg = tool.run(path, "xyz", "ABC")
    assert msg.startswith("错误：未在")
    assert open(path, encoding="utf-8").read() == "abc\n"  # 拒绝时文件不变


def test_replace_ambiguous_keeps_file(tool, tmp_path):
    path = _write(tmp_path, "abc\nabc\n")
    msg = tool.run(path, "abc", "ABC")
    assert "必须唯一" in msg
    assert open(path, encoding="utf-8").read() == "abc\nabc\n"


def test_replace_noop_rejected(tool, tmp_path):
    path = _write(tmp_path, "abc\n")
    msg = tool.run(path, "abc", "abc")
    assert "完全相同" in msg


def test_replace_missing_file(tool, tmp_path):
    msg = tool.run(str(tmp_path / "nope.txt"), "a", "b")
    assert "文件不存在" in msg
