"""交互会话单元测试：单循环 REPL、斜杠命令、消息持久化。

v2.2：意图分类器与阶段函数（run_clarify/run_code/run_modify/run_qa）
已删除——路由交给模型，不再有可测试的 Python 分类逻辑。这里测的是
REPL 的确定性部分：输入分发、messages 跨轮持久、斜杠命令、播种、
哨兵收尾。
"""

from pathlib import Path

import pytest

from agent import interactive, paths, runtime, session


@pytest.fixture(autouse=True)
def _isolate_run_dir(tmp_path, monkeypatch):
    """runs/ 与目标项目都重定向到临时目录，避免测试相互污染。"""
    monkeypatch.setattr(runtime, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(paths, "TARGET_ROOT", tmp_path)  # spec/项目文件落临时目录
    runtime.start_run()  # 重置 _current 指向当前测试的临时目录


def _feed(monkeypatch, *lines: str) -> None:
    """把 REPL 的用户输入序列喂给 prompt_human（按序耗尽）。"""
    answers = iter(lines)
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: next(answers))


def _fake_turn(recorder: list):
    """造一个行为等价于真 continue_turn 的桩：记录历史快照并追加消息。

    必须真的 append——否则无法验证"messages 跨轮持久"这一核心不变量。
    """

    def fake_continue_turn(messages, line, **kwargs):
        messages.append({"role": "user", "content": line})
        recorder.append([m["content"] for m in messages if m["role"] == "user"])
        messages.append({"role": "assistant", "content": "ok"})
        return "ok"

    return fake_continue_turn


# ---------- 会话启动 / 退出 ----------


def test_session_exit_command(monkeypatch):
    """/exit 退出，不触发任何模型调用。"""
    _feed(monkeypatch, "/exit")
    called = []
    monkeypatch.setattr(session, "continue_turn", lambda *a, **k: called.append(a))
    session.run_interactive_session()
    assert called == []


def test_session_exit_words(monkeypatch):
    """退出词（exit/quit/q/退出）是 REPL 层确定性出口。"""
    for word in ("exit", "quit", "q", "退出"):
        _feed(monkeypatch, word)
        called = []
        monkeypatch.setattr(session, "continue_turn", lambda *a, **k: called.append(a))
        session.run_interactive_session()
        assert called == []


def test_session_eof_exits_cleanly(monkeypatch):
    """EOF（输入流结束）→ 干净退出，不抛异常。"""
    def _eof(prompt):
        raise EOFError
    monkeypatch.setattr(interactive, "prompt_human", _eof)
    session.run_interactive_session()  # 不抛即通过


def test_session_uses_provided_run_dir(monkeypatch):
    """传 run_dir 时复用指定目录（调试 agent），不新建运行目录。"""
    _feed(monkeypatch, "/exit")
    provided = runtime.RUNS_DIR / "prev_run"
    session.run_interactive_session(run_dir=provided)
    assert runtime.current() == provided


# ---------- 单循环核心：自由输入 → continue_turn，messages 持久 ----------


def test_free_text_goes_to_continue_turn(monkeypatch):
    """任何非命令输入都交给 continue_turn（模型路由），不做本地分类。"""
    _feed(monkeypatch, "帮我写游戏", "/exit")
    seen = []

    def fake(messages, line, **kwargs):
        seen.append(line)
        return "ok"

    monkeypatch.setattr(session, "continue_turn", fake)
    session.run_interactive_session()
    assert seen == ["帮我写游戏"]


def test_messages_persist_across_turns(monkeypatch):
    """messages 跨轮持久：第 2 轮能看到第 1 轮的历史（单循环核心不变量）。"""
    _feed(monkeypatch, "帮我写游戏", "改成网页版", "/exit")
    snapshots: list[list[str]] = []
    monkeypatch.setattr(session, "continue_turn", _fake_turn(snapshots))
    session.run_interactive_session()

    assert snapshots[0] == ["帮我写游戏"]
    assert snapshots[1] == ["帮我写游戏", "改成网页版"]


def test_system_prompt_contains_runtime_paths():
    """系统提示含目标项目根与 spec.md 绝对路径（权威声明）。"""
    prompt = session.build_system_prompt()
    assert str(paths.target_root()) in prompt
    assert str(runtime.spec_path()) in prompt


def test_seed_runs_first_turn(monkeypatch):
    """命令行任务参数（seed）作为第一轮直接执行。"""
    _feed(monkeypatch, "/exit")
    seen = []

    def fake(messages, line, **kwargs):
        seen.append(line)
        return "ok"

    monkeypatch.setattr(session, "continue_turn", fake)
    session.run_interactive_session(seed="帮我写一个猜人游戏")
    assert seen == ["帮我写一个猜人游戏"]


def test_seed_message_on_reused_target(monkeypatch):
    """目标项目已有 spec.md 时，播种现状消息（不跑模型）。"""
    runtime.spec_path().write_text("# spec", encoding="utf-8")

    _feed(monkeypatch, "继续", "/exit")
    captured: dict[str, list] = {}

    def fake(messages, line, **kwargs):
        captured["users"] = [m["content"] for m in messages if m["role"] == "user"]
        return "ok"

    monkeypatch.setattr(session, "continue_turn", fake)
    session.run_interactive_session()

    # 播种消息在历史里（read spec 指引），且未消耗模型轮次
    assert any("spec.md" in c for c in captured["users"])


# ---------- 斜杠命令 ----------


def test_code_command_translates_to_input(monkeypatch):
    """/code 不走本地路由，翻译成对话输入交给模型（prompt 模板，非分支）。"""
    _feed(monkeypatch, "/code", "/exit")
    seen = []

    def fake(messages, line, **kwargs):
        seen.append(line)
        return "ok"

    monkeypatch.setattr(session, "continue_turn", fake)
    session.run_interactive_session()
    assert len(seen) == 1
    assert "spec.md" in seen[0] and "编码" in seen[0]


def test_spec_command_shows_spec(monkeypatch):
    """/spec 显示当前 spec.md 内容。"""
    runtime.spec_path().write_text("# 我的 spec", encoding="utf-8")
    printed = []
    _feed(monkeypatch, "/spec", "/exit")
    monkeypatch.setattr(session, "Panel", lambda *a, **k: a[0])  # 桩掉 rich Panel，取原始文本
    monkeypatch.setattr(session.console, "print", lambda *a, **k: printed.append(str(a)))
    session.run_interactive_session()
    assert any("我的 spec" in x for x in printed)


def test_spec_command_without_spec(monkeypatch):
    """/spec 无 spec 时提示先输入需求。"""
    printed = []
    _feed(monkeypatch, "/spec", "/exit")
    monkeypatch.setattr(session.console, "print", lambda *a, **k: printed.append(str(a)))
    session.run_interactive_session()
    assert any("还没有 spec.md" in x for x in printed)


def test_unknown_command_hint(monkeypatch):
    """未知命令 → 提示 /help，不进模型。"""
    _feed(monkeypatch, "/foo", "/exit")
    called = []
    monkeypatch.setattr(session, "continue_turn", lambda *a, **k: called.append(a) or "ok")
    printed = []
    monkeypatch.setattr(session.console, "print", lambda *a, **k: printed.append(str(a)))
    session.run_interactive_session()
    assert called == []
    assert any("未知命令" in x for x in printed)


def test_clear_resets_history_keeps_project_files(monkeypatch):
    """/clear 只删 spec + 重置对话；项目文件绝不动（回滚是用户的 git 的事）。"""
    runtime.spec_path().write_text("# spec", encoding="utf-8")
    game = paths.target_root() / "game.js"
    game.write_text("// 项目里的代码", encoding="utf-8")

    _feed(monkeypatch, "帮我写游戏", "/clear", "y", "再来一个", "/exit")
    total_lengths: list[int] = []

    def fake(messages, line, **kwargs):
        total_lengths.append(len(messages))
        messages.append({"role": "user", "content": line})
        messages.append({"role": "assistant", "content": "ok"})
        return "ok"

    monkeypatch.setattr(session, "continue_turn", fake)
    session.run_interactive_session()

    assert not runtime.spec_path().exists()   # spec 已删
    assert game.exists()                      # 项目文件保留！
    # 第 1 轮开局 = system + 播种消息（spec 已存在时注入现状）；
    # /clear 重置后第 2 轮只剩 system —— 历史确实被清了
    assert total_lengths == [2, 1]


# ---------- 哨兵收尾 ----------


def test_error_sentinel_prints_footer(monkeypatch):
    """流式模式下错误哨兵给一句收尾提示（正常回复已实时显示）。"""
    _feed(monkeypatch, "帮我写游戏", "/exit")
    monkeypatch.setattr(session, "continue_turn", lambda m, l, **k: "[ERR] 某工具执行失败")
    printed = []
    monkeypatch.setattr(session.console, "print", lambda *a, **k: printed.append(str(a)))
    session.run_interactive_session()
    assert any("[ERR]" in x for x in printed)


def test_empty_input_ignored(monkeypatch):
    """空行/纯空白不触发任何动作。"""
    _feed(monkeypatch, "  ", "", "/exit")
    called = []
    monkeypatch.setattr(session, "continue_turn", lambda *a, **k: called.append(a) or "ok")
    session.run_interactive_session()
    assert called == []
