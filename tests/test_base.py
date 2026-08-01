"""BaseTool 反射 schema 生成单元测试。

验证 to_openai_function() 能正确从 run() 签名推导 JSON Schema：
类型映射、required 推断、docstring 参数描述提取。
"""

from agent.tools.base import BaseTool


class FakeTool(BaseTool):
    """带类型注解与 docstring 参数说明的工具。"""

    @property
    def name(self) -> str:
        return "fake"

    @property
    def description(self) -> str:
        return "Fake tool for schema tests"

    def run(self, path: str, count: int = 1, verbose: bool = False) -> str:
        """执行一个假操作。

        参数:
            path: 目标文件路径
        """
        return f"{path}:{count}:{verbose}"


class UntypedTool(BaseTool):
    """无类型注解、无 docstring 参数说明的工具。"""

    @property
    def name(self) -> str:
        return "untyped"

    @property
    def description(self) -> str:
        return "Untyped tool"

    def run(self, arg) -> str:
        """任意参数。"""
        return arg


def test_schema_shape():
    schema = FakeTool().to_openai_function()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "fake"
    assert schema["function"]["description"] == "Fake tool for schema tests"


def test_type_mapping():
    props = FakeTool().to_openai_function()["function"]["parameters"]["properties"]
    assert props["path"]["type"] == "string"
    assert props["count"]["type"] == "integer"
    assert props["verbose"]["type"] == "boolean"


def test_required_only_params_without_default():
    required = FakeTool().to_openai_function()["function"]["parameters"]["required"]
    assert required == ["path"]  # count / verbose 有默认值，非必填


def test_param_description_from_docstring():
    props = FakeTool().to_openai_function()["function"]["parameters"]["properties"]
    assert props["path"]["description"] == "目标文件路径"
    # 无 docstring 说明的参数 → 默认 "<name> 参数"
    assert props["count"]["description"] == "count 参数"


def test_untyped_falls_back_to_string():
    props = UntypedTool().to_openai_function()["function"]["parameters"]["properties"]
    assert props["arg"]["type"] == "string"
