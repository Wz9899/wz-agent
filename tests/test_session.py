"""交互会话单元测试：意图识别、命令分发、会话主循环。"""

from agent import interactive, session


# ---------- is_code_intent ----------


def test_code_intent_exact_triggers():
    for t in ("编码", "开始编码", "实现", "开始实现", "开工", "写代码", "code", "build"):
        assert session.is_code_intent(t), t


def test_code_intent_strips_punctuation():
    assert session.is_code_intent("编码。")
    assert session.is_code_intent(" 实现！")
    assert session.is_code_intent(" 开始 ")


def test_code_intent_not_triggered_by_long_text():
    """长需求描述（含触发词）不被误判为编码意图。"""
    assert not session.is_code_intent("帮我实现一个猜人游戏")
    assert not session.is_code_intent("这个功能需要实现吗？")
    assert not session.is_code_intent("我想开始一个新项目")


# ---------- _handle_command ----------


def test_handle_command_exit():
    for c in ("/exit", "/quit", "/bye"):
        assert session._handle_command(c) == "exit", c


def test_handle_command_help(monkeypatch):
    printed = []
    monkeypatch.setattr(session.console, "print", lambda *a, **k: printed.append(a))
    assert session._handle_command("/help") == "continue"
    assert any("可用命令" in str(x) for x in printed)


def test_handle_command_spec_missing(monkeypatch):
    monkeypatch.setattr(session, "spec_exists", lambda: False)
    printed = []
    monkeypatch.setattr(session.console, "print", lambda *a, **k: printed.append(a))
    assert session._handle_command("/spec") == "continue"
    assert any("还没有 spec.md" in str(x) for x in printed)


def test_handle_command_unknown(monkeypatch):
    printed = []
    monkeypatch.setattr(session.console, "print", lambda *a, **k: printed.append(a))
    assert session._handle_command("/nope") == "continue"
    assert any("未知命令" in str(x) for x in printed)


# ---------- run_interactive_session ----------


def test_session_clarify_then_exit(monkeypatch):
    """无 spec、无已生成代码：输入需求 → clarify；再 /exit → 退出。"""
    answers = iter(["帮我写一个猜人游戏", "/exit"])
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: next(answers))
    monkeypatch.setattr(session, "spec_exists", lambda: False)
    monkeypatch.setattr(session, "has_generated_code", lambda: False)
    called = {"clarify": [], "code": [], "modify": []}
    monkeypatch.setattr(session, "run_clarify", lambda req, sm, st: called["clarify"].append(req))
    monkeypatch.setattr(session, "run_code", lambda ins, sm, st: called["code"].append(ins))
    monkeypatch.setattr(session, "run_modify", lambda ins, sm, st: called["modify"].append(ins))

    session.run_interactive_session()
    assert called["clarify"] == ["帮我写一个猜人游戏"]
    assert called["code"] == []
    assert called["modify"] == []


def test_session_code_intent_dispatches_to_code(monkeypatch):
    """有 spec：输入"编码" → run_code。"""
    answers = iter(["编码", "/exit"])
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: next(answers))
    monkeypatch.setattr(session, "spec_exists", lambda: True)
    monkeypatch.setattr(session, "has_generated_code", lambda: False)
    called = {"clarify": [], "code": [], "modify": []}
    monkeypatch.setattr(session, "run_clarify", lambda req, sm, st: called["clarify"].append(req))
    monkeypatch.setattr(session, "run_code", lambda ins, sm, st: called["code"].append(ins))
    monkeypatch.setattr(session, "run_modify", lambda ins, sm, st: called["modify"].append(ins))

    session.run_interactive_session()
    assert called["code"] == ["编码"]
    assert called["clarify"] == []
    assert called["modify"] == []


def test_session_exit_word(monkeypatch):
    """输入 exit 直接退出，不触发任何执行。"""
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: "exit")
    called = []
    monkeypatch.setattr(session, "run_clarify", lambda req, sm, st: called.append("clarify"))
    session.run_interactive_session()
    assert called == []


def test_session_ctrl_c_exits(monkeypatch):
    """会话空闲时 Ctrl-C → 退出，不抛异常。"""
    def _ctrl_c(prompt):
        raise KeyboardInterrupt
    monkeypatch.setattr(interactive, "prompt_human", _ctrl_c)
    session.run_interactive_session()


def test_session_eof_exits(monkeypatch):
    """输入流结束（EOF）→ 退出，不死循环。"""
    def _eof(prompt):
        raise EOFError
    monkeypatch.setattr(interactive, "prompt_human", _eof)
    session.run_interactive_session()


def test_session_modify_intent_dispatches_to_modify(monkeypatch):
    """有已生成代码时，输入修改意见 → run_modify（而非新需求澄清）。"""
    answers = iter(["把范围改成 1-1000", "/exit"])
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: next(answers))
    monkeypatch.setattr(session, "spec_exists", lambda: True)
    monkeypatch.setattr(session, "has_generated_code", lambda: True)
    called = {"clarify": [], "code": [], "modify": []}
    monkeypatch.setattr(session, "run_clarify", lambda req, sm, st: called["clarify"].append(req))
    monkeypatch.setattr(session, "run_code", lambda ins, sm, st: called["code"].append(ins))
    monkeypatch.setattr(session, "run_modify", lambda ins, sm, st: called["modify"].append(ins))

    session.run_interactive_session()
    assert called["modify"] == ["把范围改成 1-1000"]
    assert called["clarify"] == []


def test_has_generated_code_true(monkeypatch, tmp_path):
    """output/ 下有 .py 文件 → True。"""
    out = tmp_path / "output"
    out.mkdir()
    (out / "game.py").write_text("print('hi')", encoding="utf-8")
    monkeypatch.setattr(session, "PROJECT_ROOT", tmp_path)
    assert session.has_generated_code() is True


def test_has_generated_code_false(monkeypatch, tmp_path):
    monkeypatch.setattr(session, "PROJECT_ROOT", tmp_path)
    assert session.has_generated_code() is False


def test_handle_command_clear_cancel(monkeypatch):
    """/clear 且用户不确认（N）→ 取消，不执行清理。"""
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: "n")
    printed = []
    monkeypatch.setattr(session.console, "print", lambda *a, **k: printed.append(a))
    assert session._handle_command("/clear") == "continue"
    assert any("已取消" in str(x) for x in printed)
