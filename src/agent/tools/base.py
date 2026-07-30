"""工具基类 —— 所有工具的统一抽象。"""

import inspect
from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """工具抽象基类。

    每个子类必须提供 name、description 和 run()。

    使用方式:
        class MyTool(BaseTool):
            @property
            def name(self) -> str:
                return "my_tool"

            @property
            def description(self) -> str:
                return "一句话描述工具的作用。"

            def run(self, path: str, content: str) -> str:
                # 参数的类型注解会自动生成 JSON Schema
                # 没有默认值的参数 = required
                ...
    """

    # ------------------------------------------------------------
    # 子类必须实现的抽象成员
    # ------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称，如 'read'、'write'。LLM 通过它来调用工具。"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """工具的一句话描述，LLM 据此判断何时使用该工具。"""
        ...

    @abstractmethod
    def run(self, **kwargs) -> str:
        """执行工具逻辑。参数由子类的 run 签名决定。返回纯文本结果。"""
        ...

    # ------------------------------------------------------------
    # to_openai_function —— 自动从 run() 签名生成 OpenAI function 定义
    # ------------------------------------------------------------

    # Python 类型 → JSON Schema type 的静态映射表
    _TYPE_MAP: dict[type, str] = {
        int: "integer",
        float: "number",
        bool: "boolean",
        str: "string",
    }

    def to_openai_function(self) -> dict[str, Any]:
        """生成 OpenAI 兼容的 function 定义。

        自动检查子类 run() 的参数签名，生成对应的 JSON Schema。
        子类无需手动编写参数描述 —— 参数名、类型、必填信息全部由反射推导。

        工作原理:
            1. 用 inspect.signature() 拿到 run() 的签名
            2. 遍历每个参数（跳过 self）
            3. 根据类型注解映射到 JSON Schema type
            4. 没有默认值的参数加入 required 列表
            5. 组装为 OpenAI function calling 格式返回
        """
        sig = inspect.signature(self.run)

        properties: dict[str, dict] = {}
        required: list[str] = []

        for param_name, param in sig.parameters.items():
            # 跳过 self —— 它不是 LLM 需要传入的参数
            if param_name == "self":
                continue

            # 根据类型注解推断 JSON Schema 类型，默认 fallback 为 string
            json_type = "string"
            if param.annotation is not inspect.Parameter.empty:
                json_type = self._TYPE_MAP.get(param.annotation, "string")

            # 从 run() 的 docstring 中提取参数说明（如果有的话）
            param_desc = f"{param_name} 参数"
            run_doc = self.run.__doc__ or ""
            for line in run_doc.split("\n"):
                # 匹配形如 "path: 文件路径" 的参数文档行
                stripped = line.strip()
                if stripped.startswith(f"{param_name}:") or stripped.startswith(f"{param_name}："):
                    param_desc = stripped.split(":", 1)[-1].split("：", 1)[-1].strip()
                    break

            properties[param_name] = {
                "type": json_type,
                "description": param_desc,
            }

            # 没有默认值的参数视为必填
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
