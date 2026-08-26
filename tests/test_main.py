"""main.py 入口测试 —— 防自噬护栏。

用 click 的 CliRunner 测锚定层行为（不进 REPL、不调 API）：
目标落在 wz-agent 自身仓库内 → 拒绝并退出（exit 1）；
--allow-self 显式放行（自举开发）。
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

import main
from agent import paths


@pytest.fixture(autouse=True)
def _reset_target_root(monkeypatch):
    """护栏测试会用真实 set_target 锚定（含 chdir）——
    每个测试后恢复 TARGET_ROOT 与 cwd，防止污染其他测试的回退路径。"""
    import os
    monkeypatch.setattr(paths, "TARGET_ROOT", None)
    cwd = os.getcwd()
    yield
    os.chdir(cwd)


def test_is_self_harness_covers_repo_and_subdirs():
    """wz-agent 根及其任意子目录（src/ 等）都算自身仓库。"""
    assert main.is_self_harness(main.PROJECT_ROOT)
    assert main.is_self_harness(main.PROJECT_ROOT / "src")
    assert main.is_self_harness(main.PROJECT_ROOT / "src" / "agent")
    assert not main.is_self_harness(Path("C:/tmp/some-other-project"))


def test_launch_inside_repo_is_rejected(tmp_path):
    """从 src/ 里裸启（无 -C）→ 目标默认 = 启动 cwd = wz-agent 自身 → 拒绝。"""
    runner = CliRunner()
    result = runner.invoke(main.main, [], standalone_mode=False)
    assert result.exit_code == 1
    assert "自身仓库" in result.output


def test_dash_c_inside_repo_is_rejected(tmp_path):
    """显式 -C 到 wz-agent 子目录同样拒绝（护栏不因显式指定而绕过）。"""
    runner = CliRunner()
    result = runner.invoke(main.main, ["-C", str(main.PROJECT_ROOT / "src")])
    assert result.exit_code == 1
    assert "--allow-self" in result.output  # 提示里给出放行途径


def test_allow_self_passes_guard(tmp_path, monkeypatch):
    """--allow-self 放行自举：护栏通过后走到会话启动（桩掉防真跑）。"""
    called = {}

    def _fake_session(**kw):
        called.update(kw)

    # main.py 用 from-import 绑定，须补 main 命名空间里的名字
    monkeypatch.setattr(main, "run_interactive_session", _fake_session)
    runner = CliRunner()
    result = runner.invoke(main.main, ["--allow-self"])
    assert result.exit_code == 0
    assert called  # 会话被启动（护栏没拦）


def test_normal_target_unaffected(tmp_path, monkeypatch):
    """普通目标目录不受护栏影响（回归保护：护栏只在自噬场景生效）。"""
    called = {}

    def _fake_session(**kw):
        called.update(kw)

    monkeypatch.setattr(main, "run_interactive_session", _fake_session)
    runner = CliRunner()
    result = runner.invoke(main.main, ["-C", str(tmp_path)])
    assert result.exit_code == 0
    assert called
