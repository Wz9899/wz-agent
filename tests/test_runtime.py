"""运行工作区与输出转录测试。"""

from agent import runtime


def test_start_run_creates_dirs(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "RUNS_DIR", tmp_path)
    run_dir = runtime.start_run()
    assert run_dir.is_dir()
    assert (run_dir / "output").is_dir()
    assert (run_dir / "session.log").is_file()  # 转录文件已创建


def test_spec_and_output_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "RUNS_DIR", tmp_path)
    runtime.start_run()
    assert runtime.spec_path().name == "spec.md"
    assert runtime.spec_path().parent == runtime.current()
    assert runtime.output_dir().name == "output"
    assert runtime.output_dir().parent == runtime.current()


def test_write_transcript_writes_file(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "RUNS_DIR", tmp_path)
    runtime.start_run()
    runtime.write_transcript("agent 说：你好\n")
    runtime.write_transcript("  -> 工具 read(spec.md)\n")
    content = (runtime.current() / "session.log").read_text(encoding="utf-8")
    assert "agent 说：你好" in content
    assert "工具 read" in content


def test_close_run(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "RUNS_DIR", tmp_path)
    runtime.start_run()
    runtime.write_transcript("x")
    runtime.close_run()
    assert runtime._transcript is None


def test_start_run_reuses_existing(monkeypatch, tmp_path):
    """start_run(existing) 复用指定目录，不新建、不删除已有 spec/代码。"""
    existing = tmp_path / "prev_run"
    existing.mkdir()
    (existing / "spec.md").write_text("# spec", encoding="utf-8")
    (existing / "output").mkdir()
    (existing / "output" / "game.js").write_text("// game", encoding="utf-8")
    monkeypatch.setattr(runtime, "RUNS_DIR", tmp_path / "runs")

    run_dir = runtime.start_run(existing)
    assert run_dir == existing
    assert (existing / "spec.md").is_file()          # 已有文件保留
    assert (existing / "output" / "game.js").is_file()  # 代码保留
    assert runtime.current() == existing
