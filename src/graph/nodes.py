from __future__ import annotations

import logging
import json
from copy import deepcopy
from typing import Literal
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from langgraph.graph import END

from src.agents import research_agent, coder_agent, browser_agent
from src.agents.llm import get_llm_by_type
from src.config import TEAM_MEMBERS
from src.config.agents import AGENT_LLM_MAP
from src.prompts.template import apply_prompt_template
from src.tools.search import tavily_tool
from src.tools.decorators import track_node
from .types import State, Router

logger = logging.getLogger(__name__)

# 定义一个标准的消息格式，用于将Agent的执行结果包装后添加到状态中
RESPONSE_FORMAT = "Response from {}:\n\n<response>\n{}\n</response>\n\n*Please execute the next step.*"


def research_node(state: State) -> Command[Literal["supervisor"]]:
    """
    研究员Agent节点。负责执行研究任务。

    @param {State} state - 当前工作流的共享状态。
    @returns {Command} 一个命令对象，包含状态更新和下一个节点的名称。
                       固定将流程交回给'supervisor'。
    """
    logger.info("研究员Agent开始执行任务")
    result = research_agent.invoke({"messages": state["messages"]})
    logger.info("研究员Agent完成任务")
    logger.debug(f"研究员Agent的响应: {result['output']}")
    # 返回一个Command，更新messages状态，并将流程固定地交给supervisor
    return Command(
        update={
            "messages": [
                HumanMessage(
                    content=RESPONSE_FORMAT.format(
                        "researcher", result["output"]
                    ),
                    name="researcher",
                )
            ]
        },
        goto="supervisor",
    )


def code_node(state: State) -> Command[Literal["supervisor"]]:
    """
    程序员Agent节点。负责执行Python代码生成和执行任务。

    @param {State} state - 当前工作流的共享状态。
    @returns {Command} 一个命令对象，包含状态更新和下一个节点的名称。
                       固定将流程交回给'supervisor'。
    """
    logger.info("程序员Agent开始执行任务")
    result = coder_agent.invoke({"messages": state["messages"]})
    logger.info("程序员Agent完成任务")
    logger.debug(f"程序员Agent的响应: {result['output']}")
    return Command(
        update={
            "messages": [
                HumanMessage(
                    content=RESPONSE_FORMAT.format(
                        "coder", result["output"]
                    ),
                    name="coder",
                )
            ]
        },
        goto="supervisor",
    )


def browser_node(state: State) -> Command[Literal["supervisor"]]:
    """
    浏览器Agent节点。负责执行网页浏览和信息提取任务。

    @param {State} state - 当前工作流的共享状态。
    @returns {Command} 一个命令对象，包含状态更新和下一个节点的名称。
                       固定将流程交回给'supervisor'。
    """
    logger.info("浏览器Agent开始执行任务")
    result = browser_agent.invoke({"messages": state["messages"]})
    logger.info("浏览器Agent完成任务")
    logger.debug(f"浏览器Agent的响应: {result['output']}")
    return Command(
        update={
            "messages": [
                HumanMessage(
                    content=RESPONSE_FORMAT.format(
                        "browser", result["output"]
                    ),
                    name="browser",
                )
            ]
        },
        goto="supervisor",
    )


def supervisor_node(state: State) -> Command[Literal[*TEAM_MEMBERS, "__end__"]]:
    """
    监督员Agent节点，是整个工作流的决策中枢。
    它根据当前的状态决定下一步应该由哪个Agent执行，或者结束流程。

    @param {State} state - 当前工作流的共享状态。
    @returns {Command} 一个命令对象，不更新状态，但指定了下一个要跳转的节点名称。
    """
    logger.info("监督员正在评估下一步行动")
    # 应用supervisor的prompt模板
    messages = apply_prompt_template("supervisor", state)
    # 调用一个具有结构化输出能力的LLM，强制其返回Router格式的决策
    response = (
        get_llm_by_type(AGENT_LLM_MAP["supervisor"])
        .with_structured_output(Router)
        .invoke(messages)
    )
    # 获取决策结果
    goto = response["next"]
    logger.debug(f"当前状态的消息: {state['messages']}")
    logger.debug(f"监督员的决策: {response}")

    # 如果决策是'FINISH'，则将流程导向结束节点'__end__'
    if goto == "FINISH":
        goto = "__end__"
        logger.info("工作流完成")
    else:
        logger.info(f"监督员指派任务给: {goto}")

    # 返回只包含路由指令的Command
    return Command(goto=goto, update={"next": goto})


@track_node("planner")
def planner_node(state: State) -> Command[Literal["supervisor", "__end__"]]:
    """
    规划师Agent节点。负责根据用户意图生成详细的、结构化的行动计划。

    @param {State} state - 当前工作流的共享状态。
    @returns {Command} 一个命令对象，更新状态（添加计划），并指定下一步跳转到'supervisor'或'__end__'。
    """
    logger.info("规划师正在生成完整计划")
    messages = apply_prompt_template("planner", state)
    # 根据是否启用'deep_thinking_mode'选择不同能力的LLM，(basic, reasoning，vision三种llm模型)
    llm = get_llm_by_type("basic")
    if state.get("deep_thinking_mode"):
        llm = get_llm_by_type("reasoning")
    # 如果需要，在规划前先进行网络搜索
    if state.get("search_before_planning"):
        searched_content = tavily_tool.invoke({"query": state["messages"][-1]["content"]})
        messages = deepcopy(messages)
        messages[-1]["content"] += f"\n\n# Relative Search Results\n\n{json.dumps([{'title': elem['title'], 'content': elem['content']} for elem in searched_content if elem.get('content')], ensure_ascii=False)}"
    stream = llm.stream(messages)
    full_response = ""
    for chunk in stream:
        full_response += chunk.content
    logger.debug(f"当前状态的消息: {state['messages']}")
    logger.debug(f"规划师的响应: {full_response}")

    # 清理LLM可能返回的多余格式
    if full_response.startswith("```json"):
        full_response = full_response.removeprefix("```json")

    if full_response.endswith("```"):
        full_response = full_response.removesuffix("```")

    goto = "supervisor"
    # 验证计划是否为有效的JSON，如果不是，则异常结束流程
    try:
        json.loads(full_response)
    except json.JSONDecodeError:
        logger.warning("规划师的响应不是一个有效的JSON")
        goto = "__end__"

    return Command(
        update={
            "messages": [HumanMessage(content=full_response, name="planner")],
            "full_plan": full_response,
        },
        goto=goto,
    )


def coordinator_node(state: State) -> Command[Literal["planner", "__end__"]]:
    """
    协调员Agent节点，作为工作流的入口。
    负责与用户进行初步沟通，并决定是否需要启动规划流程。

    @param {State} state - 当前工作流的共享状态。
    @returns {Command} 一个命令对象，不更新状态，但指定下一步跳转到'planner'或'__end__'。
    """
    logger.info("协调员正在与用户沟通")
    messages = apply_prompt_template("coordinator", state)
    response = get_llm_by_type(AGENT_LLM_MAP["coordinator"]).invoke(messages)
    logger.debug(f"当前状态的消息: {state['messages']}")
    logger.debug(f"协调员的响应: {response}")

    goto = "__end__"
    # 如果LLM的响应包含特定关键词，则将任务移交给规划师
    if "handoff_to_planner" in response.content:
        goto = "planner"

    return Command(
        goto=goto,
    )


def reporter_node(state: State) -> Command[Literal["supervisor"]]:
    """
    报告员Agent节点。负责撰写最终的报告。

    @param {State} state - 当前工作流的共享状态。
    @returns {Command} 一个命令对象，包含状态更新和下一个节点的名称。
                       固定将流程交回给'supervisor'。
    """
    logger.info("报告员正在撰写最终报告")
    messages = apply_prompt_template("reporter", state)
    response = get_llm_by_type(AGENT_LLM_MAP["reporter"]).invoke(messages)
    logger.debug(f"当前状态的消息: {state['messages']}")
    logger.debug(f"报告员的响应: {response}")

    return Command(
        update={
            "messages": [
                HumanMessage(
                    content=RESPONSE_FORMAT.format("reporter", response.content),
                    name="reporter",
                )
            ]
        },
        goto="supervisor",
    )
