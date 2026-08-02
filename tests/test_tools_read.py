"""read（按行范围）与 write（append 分块）工具测试。"""

from agent.tools.read import ReadTool
from agent.tools.write import WriteTool


# ---------- read 按行范围 ----------


def _write_lines(tmp_path, n: int):
    p = tmp_path / "big.py"
    p.write_text("\n".join(f"line{i}" for i in range(1, n + 1)), encoding="utf-8")
    return p


def test_read_lines_range(tmp_path):
    p = _write_lines(tmp_path, 100)
    out = ReadTool().run(str(p), lines="1-5")
    assert "1: line1" in out
    assert "5: line5" in out
    assert "line6" not in out
    assert "显示第 1-5 行" in out


def test_read_single_line(tmp_path):
    p = _write_lines(tmp_path, 10)
    out = ReadTool().run(str(p), lines="2")
    assert "2: line2" in out


def test_read_lines_out_of_range(tmp_path):
    p = _write_lines(tmp_path, 5)
    out = ReadTool().run(str(p), lines="50")
    assert "超出文件总行数" in out


def test_read_lines_beyond_end_clamps(tmp_path):
    p = _write_lines(tmp_path, 5)
    out = ReadTool().run(str(p), lines="3-999")
    assert "3: line3" in out
    assert "5: line5" in out  # 钳到文件末尾


def test_read_no_lines_truncates(tmp_path):
    p = tmp_path / "big.txt"
    p.write_text("x" * 5000, encoding="utf-8")
    out = ReadTool().run(str(p))
    assert "以上为前" in out  # 超长自动截断


def test_read_gbk_file(tmp_path):
    """GBK 编码文件可读（Windows 下 agent 生成/重定向的文件常是 GBK）。"""
    p = tmp_path / "gbk.txt"
    p.write_bytes("中文内容".encode("gbk"))
    out = ReadTool().run(str(p))
    assert "中文内容" in out  # 用 GBK 解码


def test_read_undecodable_bytes_uses_replace(tmp_path):
    """含非法字节的文件用 errors=replace 读，不报错、能读到部分内容。"""
    p = tmp_path / "mixed.txt"
    p.write_bytes(b"abc\xae\xff\xfe def")  # 非 UTF-8/GBK 合法序列
    out = ReadTool().run(str(p))
    assert "abc" in out  # 至少读到部分，不抛"不是 UTF-8"错误


# ---------- write append 分块 ----------


def test_write_append(tmp_path):
    p = tmp_path / "data.txt"
    WriteTool().run(str(p), "part1\n")
    WriteTool().run(str(p), "part2\n", append=True)
    assert p.read_text(encoding="utf-8") == "part1\npart2\n"


def test_write_append_creates_file(tmp_path):
    p = tmp_path / "new.txt"
    WriteTool().run(str(p), "content", append=True)
    assert p.read_text(encoding="utf-8") == "content"


def test_write_overwrites_by_default(tmp_path):
    p = tmp_path / "data.txt"
    WriteTool().run(str(p), "old")
    WriteTool().run(str(p), "new")
    assert p.read_text(encoding="utf-8") == "new"
