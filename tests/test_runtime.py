"""运行上下文测试 —— 转录目录 + 目标项目产物定位（v2.3 锚定模型）。"""

import os
from pathlib import Path

import pytest

from agent import paths, runtime


def test_start_run_creates_transcript_dir(monkeypatch, tmp_path):
    """runs/ 下只有 session.log（无 output/ 沙箱）。"""
    monkeypatch.setattr(runtime, "RUNS_DIR", tmp_path)
    run_dir = runtime.start_run()
    assert run_dir.is_dir()
    assert (run_dir / "session.log").is_file()
    assert not (run_dir / "output").exists()  # v2.3 起不再创建沙箱


def test_run_dirname_contains_target_slug(monkeypatch, tmp_path):
    """转录目录名带目标项目名 —— 多项目可分辨。"""
    monkeypatch.setattr(runtime, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(paths, "TARGET_ROOT", tmp_path / "my-game")
    (tmp_path / "my-game").mkdir()
    run_dir = runtime.start_run()
    assert "my-game" in run_dir.name


def test_spec_path_at_target_root(monkeypatch, tmp_path):
    """spec.md 固定在目标项目根（项目工件随项目走，不随运行目录搬家）。"""
    monkeypatch.setattr(runtime, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(paths, "TARGET_ROOT", tmp_path / "proj")
    (tmp_path / "proj").mkdir()
    runtime.start_run()
    assert runtime.spec_path() == tmp_path / "proj" / "spec.md"


def test_spec_path_falls_back_to_project_root(monkeypatch, tmp_path):
    """未锚定目标时回退 wz-agent 自身根（兼容路径）。"""
    monkeypatch.setattr(runtime, "RUNS_DIR", tmp_path)
    runtime.start_run()
    assert runtime.spec_path() == paths.PROJECT_ROOT / "spec.md"


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
    """start_run(existing) 复用指定转录目录，追加写入。"""
    existing = tmp_path / "prev_run"
    existing.mkdir()
    (existing / "session.log").write_text("旧内容\n", encoding="utf-8")
    monkeypatch.setattr(runtime, "RUNS_DIR", tmp_path / "runs")

    run_dir = runtime.start_run(existing)
    assert run_dir == existing
    assert "旧内容" in (existing / "session.log").read_text(encoding="utf-8")
    assert runtime.current() == existing


# ---------- paths.set_target ----------


def test_set_target_anchors_and_chdir(tmp_path, monkeypatch):
    """set_target 锚定目标并切换工作目录；相对路径随目标走。"""
    target = tmp_path / "proj"
    target.mkdir()
    result = paths.set_target(target)
    try:
        assert result == target.resolve()
        assert Path(os.getcwd()) == target.resolve()
    finally:  # 恢复现场，避免污染其他测试
        monkeypatch.setattr(paths, "TARGET_ROOT", None)
        os.chdir(paths.PROJECT_ROOT)


def test_set_target_rejects_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        paths.set_target(tmp_path / "no-such-dir")
