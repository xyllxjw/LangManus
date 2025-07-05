from langgraph.graph import StateGraph, START

from .types import State
from .nodes import (
    supervisor_node,
    research_node,
    code_node,
    coordinator_node,
    browser_node,
    reporter_node,
    planner_node,
)

# 构建工作流图
def build_graph():
    """
    构建并返回Agent工作流图。

    这个函数定义了整个Agent团队的工作流程结构，包括所有成员（节点）
    以及他们之间的基本连接关系。

    @returns {CompiledGraph} 编译好的、可执行的LangGraph图实例。
    """
    # 初始化一个状态图，状态的结构由State类定义
    builder = StateGraph(State)

    # 定义工作流的入口点，第一个被调用的节点是'coordinator'
    builder.add_edge(START, "coordinator")

    # 向图中添加各个Agent节点
    # 每个节点都对应一个在nodes.py中定义的函数
    builder.add_node("coordinator", coordinator_node)  # 协调员：与用户初步沟通，决定是否启动规划
    builder.add_node("planner", planner_node)  # 规划师：制定详细的行动计划
    builder.add_node("supervisor", supervisor_node)  # 监督员：决策中枢，决定下一步由谁执行
    builder.add_node("researcher", research_node)  # 研究员：执行研究任务
    builder.add_node("coder", code_node)  # 程序员：编写和执行代码
    builder.add_node("browser", browser_node)  # 浏览器：执行网页浏览任务
    builder.add_node("reporter", reporter_node)  # 报告员：撰写最终报告

    # 编译图，使其成为一个可执行的对象
    # 注意：这里的路由逻辑是隐式的，在每个节点函数内部通过返回的Command对象的goto字段来指定，每个节点之间的跳转关系。
    return builder.compile()
