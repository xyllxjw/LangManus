from typing import Literal, TypedDict, Annotated, List, Union
from langchain_core.messages import BaseMessage
import operator
from langgraph.graph import MessagesState

from src.config import TEAM_MEMBERS

# Define routing options
OPTIONS = TEAM_MEMBERS + ["FINISH"]


class Router(TypedDict):
    """
    定义了监督员(Supervisor)进行路由决策时返回的数据结构。
    """

    # 'next'字段表示下一个应该被调用的Agent节点的名称。
    next: Literal[*OPTIONS]


class State(TypedDict):
    """
    定义了在整个工作流中传递和共享的状态。
    这个状态对象是一个字典，包含了所有Agent执行任务所需的信息。
    """

    # messages: 对话历史记录，是所有Agent交互的基础。
    # 使用operator.add可以在每次更新时向列表中追加消息，而不是替换。
    messages: Annotated[List[BaseMessage], operator.add]

    # next: 下一个要执行的Agent的名称，由supervisor决定。
    next: str

    # TEAM_MEMBERS: 当前团队所有成员的列表。
    TEAM_MEMBERS: List[str]

    # full_plan: 由规划师(Planner)生成的完整JSON格式计划。
    full_plan: Union[str, None]

    # deep_thinking_mode: 是否启用深度思考模式（可能调用更强大的LLM）。
    deep_thinking_mode: bool

    # search_before_planning: 在规划前是否进行网络搜索。
    search_before_planning: bool

    # intermediate_steps: 用于存储Agent在执行任务过程中的中间步骤（例如工具调用和其返回结果）。
    # 这对于调试和让Agent拥有短期记忆至关重要。但是其它地方好像都没有用的。
    intermediate_steps: Annotated[list, operator.add]
