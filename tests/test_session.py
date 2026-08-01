"""交互会话单元测试：意图识别、命令分发、会话主循环。"""

from pathlib import Path

import pytest

from agent import interactive, runtime, session


@pytest.fixture(autouse=True)
def _isolate_run_dir(tmp_path, monkeypatch):
    """把 runs/ 重定向到临时目录，避免测试创建真实运行产物。"""
    monkeypatch.setattr(runtime, "RUNS_DIR", tmp_path)


# ---------- is_code_intent ----------


def test_code_intent_exact_triggers():
    for t in ("编码", "开始编码", "实现", "开始实现", "开工", "写代码", "code", "build"):
        assert session.is_code_intent(t), t


def test_code_intent_strips_punctuation():
    assert session.is_code_intent("编码。")
    assert session.is_code_intent(" 实现！")
    assert session.is_code_intent(" 开始 ")


def test_code_intent_short_instruction():
    """短指令（≤8 字且含触发词）识别为编码意图，如"开始编码吧"。"""
    assert session.is_code_intent("开始编码吧")
    assert session.is_code_intent("去实现")
    assert session.is_code_intent("现在开始")


def test_code_intent_not_triggered_by_long_text():
    """长需求描述（含触发词）不被误判为编码意图。"""
    assert not session.is_code_intent("帮我实现一个猜人游戏")
    assert not session.is_code_intent("这个功能需要实现吗？")
    assert not session.is_code_intent("我想开始一个新项目")
    assert not session.is_code_intent("加一个计分系统")


def test_done_requirements_phrases():
    """识别"需求已完整、无需补充"的表达，不误判补充内容。"""
    assert session._is_done_requirements("没有补充了")
    assert session._is_done_requirements("就这样吧")
    assert session._is_done_requirements("不用了，可以了")
    assert not session._is_done_requirements("没有做计分系统")  # 补充内容不误判


def test_is_question():
    """识别提问（直接回答），不把需求/指令误判为提问。"""
    assert session._is_question("数据来源是啥")
    assert session._is_question("用什么语言？")
    assert session._is_question("为什么这样做")
    assert session._is_question("这个怎么运行的")
    assert not session._is_question("帮我写一个猜数字游戏")
    assert not session._is_question("把范围改成 1-1000")
    assert not session._is_question("编码吧")
    assert not session._is_question("加一个计分系统")


def test_session_question_dispatches_to_qa(monkeypatch):
    """输入提问 → run_qa，不当作需求澄清。"""
    answers = iter(["数据来源是啥", "/exit"])
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: next(answers))
    monkeypatch.setattr(session, "spec_exists", lambda: False)
    monkeypatch.setattr(session, "has_generated_code", lambda: False)
    called = {"qa": [], "clarify": []}
    monkeypatch.setattr(session, "run_qa", lambda q, sm, st: called["qa"].append(q))
    monkeypatch.setattr(session, "run_clarify", lambda r, sm, st: called["clarify"].append(r))
    session.run_interactive_session()
    assert called["qa"] == ["数据来源是啥"]
    assert called["clarify"] == []


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


def test_has_generated_code_true(monkeypatch):
    monkeypatch.setattr(session, "_generated_code_files", lambda: [Path("game.py")])
    assert session.has_generated_code() is True


def test_has_generated_code_false(monkeypatch):
    monkeypatch.setattr(session, "_generated_code_files", lambda: [])
    assert session.has_generated_code() is False


def test_handle_command_clear_cancel(monkeypatch):
    """/clear 且用户不确认（N）→ 取消，不执行清理。"""
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: "n")
    printed = []
    monkeypatch.setattr(session.console, "print", lambda *a, **k: printed.append(a))
    assert session._handle_command("/clear") == "continue"
    assert any("已取消" in str(x) for x in printed)


# ---------- 需求确认环节 _confirm_requirements ----------


def test_confirm_no_extra_then_prompt_code(monkeypatch):
    """用户回车（无补充）→ 提示输入编码，不再次跑 agent。"""
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: "")
    printed = []
    monkeypatch.setattr(session.console, "print", lambda *a, **k: printed.append(a))
    called = {"n": 0}

    def fake(sp, um, **kw):
        called["n"] += 1
        return "[DONE]"

    monkeypatch.setattr(session, "run_interactive", fake)
    session._confirm_requirements("auto", True)
    assert called["n"] == 0
    assert any("需求确认完毕" in str(x) for x in printed)


def test_confirm_with_extra_integrates_then_prompt_code(monkeypatch):
    """用户补充内容 → 让 agent 整合进 spec；再回车 → 结束。"""
    answers = iter(["加一个计分系统", ""])
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: next(answers))
    called = {"n": 0}

    def fake(sp, um, **kw):
        called["n"] += 1
        assert "加一个计分系统" in um  # 补充内容传给 agent
        return "[DONE] 已整合"

    monkeypatch.setattr(session, "run_interactive", fake)
    session._confirm_requirements("auto", True)
    assert called["n"] == 1


def test_confirm_ctrl_c_exits(monkeypatch):
    """确认环节 Ctrl-C → 正常提示，不抛异常。"""
    def _ctrl_c(prompt):
        raise KeyboardInterrupt
    monkeypatch.setattr(interactive, "prompt_human", _ctrl_c)
    printed = []
    monkeypatch.setattr(session.console, "print", lambda *a, **k: printed.append(a))
    session._confirm_requirements("auto", True)
    assert any("需求确认完毕" in str(x) for x in printed)


def test_confirm_code_intent_starts_coding(monkeypatch):
    """确认环节用户说"编码吧" → 直接进入编码，不当作补充需求。"""
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: "编码吧")
    code_called = []
    monkeypatch.setattr(session, "run_code", lambda ins, sm, st: code_called.append(ins))
    monkeypatch.setattr(session, "run_interactive", lambda *a, **k: "[DONE]")
    session._confirm_requirements("auto", True)
    assert code_called == ["编码吧"]


def test_confirm_done_phrase_exits(monkeypatch):
    """确认环节用户说"没有补充了" → 退出确认，不当作补充整合。"""
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: "没有补充了")
    printed = []
    monkeypatch.setattr(session.console, "print", lambda *a, **k: printed.append(a))
    integrate_called = []
    monkeypatch.setattr(session, "run_interactive", lambda *a, **k: integrate_called.append(1))
    session._confirm_requirements("auto", True)
    assert integrate_called == []  # 未触发整合
    assert any("需求确认完毕" in str(x) for x in printed)
