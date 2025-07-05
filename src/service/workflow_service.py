import logging
import json # 确保导入json模块
from src.config import TEAM_MEMBERS
from src.graph import build_graph
from langchain_core.messages import BaseMessage # 导入BaseMessage用于类型检查
from langchain_community.adapters.openai import convert_message_to_dict
import uuid

# Configure logging
# 配置日志记录器
logging.basicConfig(
    level=logging.INFO,  # 默认日志级别为INFO
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


def enable_debug_logging():
    """为src记录器启用DEBUG级别的日志记录，以获取更详细的执行信息。"""
    logging.getLogger("src").setLevel(logging.DEBUG)


logger = logging.getLogger(__name__)

# Create the graph
# 在模块加载时构建并编译LangGraph图
graph = build_graph()

# Cache for coordinator messages
# 为协调员(coordinator)的消息设置缓存，用于处理特殊的"handoff"逻辑
coordinator_cache = []
MAX_CACHE_SIZE = 2


async def run_agent_workflow(
    user_input_messages: list,
    debug: bool = False,
    deep_thinking_mode: bool = False,
    search_before_planning: bool = False,
):
    """
    根据给定的用户输入运行Agent工作流。
    这个函数是工作流的核心驱动器，它调用LangGraph图并处理产生的事件流。

    @param {list} user_input_messages - 用户的请求消息列表。
    @param {bool} debug - 如果为True，则启用DEBUG级别的日志记录。
    @param {bool} deep_thinking_mode - 是否启用深度思考模式。
    @param {bool} search_before_planning - 是否在规划前进行搜索。
    @returns {AsyncGenerator} 一个异步生成器，持续产生符合SSE格式的事件字典。
    """
    if not user_input_messages:
        raise ValueError("输入不能为空")

    if debug:
        enable_debug_logging()

    logger.info(f"使用用户输入启动工作流: {user_input_messages}")

    # 为本次工作流生成一个唯一的ID
    workflow_id = str(uuid.uuid4())

    # 定义哪些Agent的LLM调用需要被流式传输，TEAM_MEMBERS包括了四种Agent：researcher、coder、browser、reporter，
    # 另外，planner和coordinator也需要被流式传输，因为它们是工作流的入口和出口。
    # 那为什么supervisor不需要被流式传输呢？
    streaming_llm_agents = [*TEAM_MEMBERS, "planner", "coordinator"]

    # 在每次工作流开始时重置缓存
    global coordinator_cache
    coordinator_cache = []
    global is_handoff_case
    is_handoff_case = False

    # 异步地流式执行图，并处理每个产生的事件
    # TODO: 优化消息内容的提取，特别是针对 on_chat_model_stream 事件
    async for event in graph.astream_events(
        {
            # 传入图的常量
            "TEAM_MEMBERS": TEAM_MEMBERS,
            # 传入图的运行时变量
            "messages": user_input_messages,
            "deep_thinking_mode": deep_thinking_mode,
            "search_before_planning": search_before_planning,
        },
        version="v2",  # 指定要运行的图的版本
    ):
        kind = event.get("event")
        data = event.get("data")
        name = event.get("name")
        metadata = event.get("metadata")
        node = (
            ""
            if (metadata.get("checkpoint_ns") is None)
            else metadata.get("checkpoint_ns").split(":")[0]
        )
        langgraph_step = (
            ""
            if (metadata.get("langgraph_step") is None)
            else str(metadata["langgraph_step"])
        )
        run_id = "" if (event.get("run_id") is None) else str(event["run_id"])

        # 根据事件类型(kind)和来源节点(name/node)，将LangGraph的原生事件
        # 转换为前端可以理解的、标准化的事件格式。
        if kind == "on_chain_start" and name in streaming_llm_agents:
            if name == "planner":
                # 当planner开始时，认为是整个工作流的开始
                yield {
                    "event": "start_of_workflow",
                    "data": {"workflow_id": workflow_id, "input": user_input_messages},
                }
            ydata = {
                "event": "start_of_agent",
                "data": {
                    "agent_name": name,
                    "agent_id": f"{workflow_id}_{name}_{langgraph_step}",
                },
            }
        elif kind == "on_chain_end" and name in streaming_llm_agents:
            ydata = {
                "event": "end_of_agent",
                "data": {
                    "agent_name": name,
                    "agent_id": f"{workflow_id}_{name}_{langgraph_step}",
                },
            }
        elif kind == "on_chat_model_start" and node in streaming_llm_agents:
            ydata = {
                "event": "start_of_llm",
                "data": {"agent_name": node},
            }
        elif kind == "on_chat_model_end" and node in streaming_llm_agents:
            ydata = {
                "event": "end_of_llm",
                "data": {"agent_name": node},
            }
        #如果事件类型
        elif kind == "on_chat_model_stream" and node in streaming_llm_agents:
            content = data["chunk"].content
            if content is None or content == "":
                if not data["chunk"].additional_kwargs.get("reasoning_content"):
                    # 跳过空消息或不包含推理内容的消息
                    continue
                ydata = {
                    "event": "message",
                    "data": {
                        "message_id": data["chunk"].id,
                        "delta": {
                            "reasoning_content": (
                                data["chunk"].additional_kwargs["reasoning_content"]
                            )
                        },
                    },
                }
            else:
                # 对coordinator的特殊处理，用于识别"handoff"指令
                if node == "coordinator":
                    if len(coordinator_cache) < MAX_CACHE_SIZE:
                        coordinator_cache.append(content)
                        cached_content = "".join(coordinator_cache)
                        if cached_content.startswith("handoff"):
                            is_handoff_case = True
                            continue
                        if len(coordinator_cache) < MAX_CACHE_SIZE:
                            continue
                        # 缓存满了，发送缓存的消息
                        ydata = {
                            "event": "message",
                            "data": {
                                "message_id": data["chunk"].id,
                                "delta": {"content": cached_content},
                            },
                        }
                    elif not is_handoff_case:
                        # 对于非handoff情况，直接发送消息
                        ydata = {
                            "event": "message",
                            "data": {
                                "message_id": data["chunk"].id,
                                "delta": {"content": content},
                            },
                        }
                else:
                    # 对于其他Agent，直接发送消息
                    ydata = {
                        "event": "message",
                        "data": {
                            "message_id": data["chunk"].id,
                            "delta": {"content": content},
                        },
                    }
        elif kind == "on_tool_start" and node in TEAM_MEMBERS:
            ydata = {
                "event": "tool_call",
                "data": {
                    "tool_call_id": f"{workflow_id}_{node}_{name}_{run_id}",
                    "tool_name": name,
                    "tool_input": data.get("input"),
                },
            }
        elif kind == "on_tool_end" and node in TEAM_MEMBERS:
            ydata = {
                "event": "tool_call_result",
                "data": {
                    "tool_call_id": f"{workflow_id}_{node}_{name}_{run_id}",
                    "tool_name": name,
                    # "tool_result": data["output"].content if data.get("output") else "",
                    "tool_result": data.get("output", ""),
                },
            }
        else:
            # 忽略其他不关心的事件
            continue
        yield ydata

    # 在工作流正常结束后，发送工作流结束事件
    # 之前的逻辑只在 is_handoff_case 为 True 时发送此事件，导致正常流程下连接中断
    final_messages = []
    # 从最终的输出中提取消息
    # 'data' 变量来自 stream 事件循环的最后一个事件，其中包含了图的最终输出
    messages_to_process = data.get("output", {}).get("messages", [])
    for msg in messages_to_process:
        if isinstance(msg, BaseMessage):
            # 如果是LangChain的消息对象，则进行转换
            final_messages.append(convert_message_to_dict(msg))
        elif isinstance(msg, dict) and "role" in msg and "content" in msg:
            # 如果已经是我们期望的字典格式，则直接使用
            final_messages.append(msg)
    
    yield {
        "event": "end_of_workflow",
        "data": {
            "workflow_id": workflow_id,
            "messages": final_messages,
        },
    }
