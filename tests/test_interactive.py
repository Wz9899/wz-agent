"""interactive 基础设施单元测试：完成判定、人机 I/O、Ctrl-C 中断菜单。"""

import pytest

from agent import interactive


# ---------- is_terminal ----------


def test_is_terminal_empty():
    assert interactive.is_terminal("")


def test_is_terminal_done_prefix():
    assert interactive.is_terminal("[DONE] 需求已整理完毕，写入 spec.md。")


def test_is_terminal_error_prefixes():
    for prefix in ("[ERR]", "[WARN]", "[API-ERR]", "[ABORT]"):
        assert interactive.is_terminal(f"{prefix} xxx"), prefix


def test_is_terminal_plain_question_is_not_terminal():
    assert not interactive.is_terminal("用什么语言？")


# ---------- prompt_human ----------


def test_prompt_human_eof_raises(monkeypatch):
    """输入流结束（EOF）抛 EOFError，由调用方决定如何处理。"""
    def _raise_eof(prompt=""):
        raise EOFError
    monkeypatch.setattr("builtins.input", _raise_eof)
    with pytest.raises(EOFError):
        interactive.prompt_human("> ")


def test_prompt_human_returns_stripped(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "  Python  ")
    assert interactive.prompt_human("> ") == "Python"


def test_prompt_human_ctrl_c_propagates(monkeypatch):
    def _raise_kbi(prompt=""):
        raise KeyboardInterrupt
    monkeypatch.setattr("builtins.input", _raise_kbi)
    with pytest.raises(KeyboardInterrupt):
        interactive.prompt_human("> ")


# ---------- strip_surrogates ----------


def test_strip_surrogates_keeps_normal_text():
    assert interactive.strip_surrogates("正常中文 abc") == "正常中文 abc"


def test_strip_surrogates_removes_surrogates():
    # \udcae 是 Windows 管道输入可能引入的孤立 surrogate
    assert interactive.strip_surrogates("a\udcae b") == "a b"


def test_strip_surrogates_empty():
    assert interactive.strip_surrogates("") == ""


# ---------- handle_interrupt ----------


def test_interrupt_enter_resumes(monkeypatch):
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: "")
    assert interactive.handle_interrupt([]) == "resume"


def test_interrupt_stop_aborts(monkeypatch):
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: "stop")
    assert interactive.handle_interrupt([]) == "abort"


def test_interrupt_inject_appends_user_message(monkeypatch):
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: "先解释这个逻辑")
    msgs: list[dict] = []
    assert interactive.handle_interrupt(msgs) == "inject"
    assert msgs == [{"role": "user", "content": "先解释这个逻辑"}]


def test_interrupt_second_ctrl_c_aborts(monkeypatch):
    def _raise(prompt=""):
        raise KeyboardInterrupt
    monkeypatch.setattr(interactive, "prompt_human", _raise)
    assert interactive.handle_interrupt([]) == "abort"


# ---------- print_human 编码兜底 ----------


def test_print_human_falls_back_on_encode_error(monkeypatch):
    """print 抛 UnicodeEncodeError 时降级为 ascii replace，不崩溃。"""
    real_print = print
    state = {"calls": 0}

    def _flaky_print(*args, **kwargs):
        state["calls"] += 1
        if state["calls"] == 1:
            raise UnicodeEncodeError("gbk", "", 0, 1, "nope")
        real_print(*args, **kwargs)

    monkeypatch.setattr("builtins.print", _flaky_print)
    interactive.print_human("中文测试")  # 不应抛异常
    assert state["calls"] == 2  # 第一次抛错，第二次兜底成功
