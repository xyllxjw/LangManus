"""
FastAPI application for LangManus.
"""

import json
import logging
from typing import Dict, List, Any, Optional, Union

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
import asyncio
from typing import AsyncGenerator, Dict, List, Any

from src.graph import build_graph
from src.config import TEAM_MEMBERS
from src.service.workflow_service import run_agent_workflow

# Configure logging
logger = logging.getLogger(__name__)

# Create FastAPI app
# 创建FastAPI应用实例，并设置API文档的标题、描述和版本
app = FastAPI(
    title="LangManus API",
    description="API for LangManus LangGraph-based agent workflow",
    version="0.1.0",
)

# Add CORS middleware
# 添加CORS中间件，允许所有来源、所有方法、所有头部的跨域请求
# 这在开发阶段很方便，但在生产环境中应配置更严格的策略
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Create the graph
# 在应用启动时，构建并编译LangGraph工作流图
graph = build_graph()

# 根据 type 字段的值来决定是填充 text 字段还是 image_url 字段，从而支持多模态内容（如文本和图片）。
class ContentItem(BaseModel):
    """定义了多模态内容项的数据结构。

    1. type 的属性，
    必须是字符串类型。是必填项，不能省略。
    在 API 文档中会显示它的描述为 "The type of content (text, image, etc.)"，用来指明内容的具体类型，比如是文本 ('text') 还是图片 ('image')。

    2. text：用于存储文本内容，可以不提供，默认为 None。
    3. image_url：用于存储图片的URL，也可以不提供，默认为 None。
    这种设计使得 ContentItem 模型非常灵活，可以根据 type 字段的值来决定是填充 text 字段还是 image_url 字段，从而支持多模态内容（如文本和图片）。
    """

    type: str = Field(..., description="The type of content (text, image, etc.)")
    text: Optional[str] = Field(None, description="The text content if type is 'text'")
    image_url: Optional[str] = Field(
        None, description="The image URL if type is 'image'"
    )

# 单条聊天消息的数据结构
class ChatMessage(BaseModel):
    """定义了单条聊天消息的数据结构。
    巧妙地定义了一个 content 字段，使其能够同时接受两种不同结构的数据：
    对于简单的纯文本聊天，可以直接传入一个字符串。
    对于需要发送文本、图片或未来其他类型媒体组合的复杂消息，可以传入一个 ContentItem 对象的列表。
    这种设计使得 ChatMessage 模型既简单易用又能满足复杂场景的需求，是构建现代聊天 API 时非常实用的一种模式。
    """

    role: str = Field(
        ..., description="The role of the message sender (user or assistant)"
    )
    content: Union[str, List[ContentItem]] = Field(
        ...,
        description="The content of the message, either a string or a list of content items",
    )

# 聊天请求的完整数据结构
class ChatRequest(BaseModel):
    """定义了聊天请求的完整数据结构。
    
    """

    messages: List[ChatMessage] = Field(..., description="The conversation history")
    debug: Optional[bool] = Field(False, description="Whether to enable debug logging")
    deep_thinking_mode: Optional[bool] = Field(
        False, description="Whether to enable deep thinking mode"
    )
    search_before_planning: Optional[bool] = Field(
        False, description="Whether to search before planning"
    )


@app.post("/api/chat/stream")
async def chat_endpoint(request: ChatRequest, req: Request):
    """
    处理聊天请求的核心API端点，使用流式响应(SSE)。

    @param {ChatRequest} request - 包含了对话历史和配置选项的请求体。
    @param {Request} req - FastAPI的请求对象，用于检查客户端连接状态。
    @returns {EventSourceResponse} 一个服务器发送事件（SSE）的流式响应。
    @raises {HTTPException} 如果处理过程中发生错误，则抛出500异常。
    """
    try:
        # 将Pydantic模型转换为字典，并处理多模态内容，以符合后端工作流的输入格式
        messages = []
        for msg in request.messages:
            message_dict = {"role": msg.role}

            # 处理字符串或内容项列表两种格式的内容
            if isinstance(msg.content, str):
                message_dict["content"] = msg.content
            else:
                # 将内容项列表转换为工作流期望的格式
                content_items = []
                for item in msg.content:
                    if item.type == "text" and item.text:
                        content_items.append({"type": "text", "text": item.text})
                    elif item.type == "image" and item.image_url:
                        content_items.append(
                            {"type": "image", "image_url": item.image_url}
                        )

                message_dict["content"] = content_items

            messages.append(message_dict)

        # 定义一个异步生成器，用于从工作流服务中获取事件并推送到客户端
        async def event_generator():
            try:
                # 异步迭代执行agent工作流，并获取返回的事件
                async for event in run_agent_workflow(
                    messages,
                    request.debug,
                    request.deep_thinking_mode,
                    request.search_before_planning,
                ):
                    # 在发送事件前，检查客户端是否仍然连接
                    if await req.is_disconnected():
                        logger.info("客户端已断开连接，停止工作流")
                        break
                    # 使用yield将事件发送给客户端
                    yield {
                        "event": event["event"],
                        "data": json.dumps(event["data"], ensure_ascii=False),
                    }
            except asyncio.CancelledError:
                logger.info("流处理被取消")
                raise

        # 返回一个EventSourceResponse，它会持续调用event_generator生成事件流
        return EventSourceResponse(
            event_generator(),
            media_type="text/event-stream",
            sep="\n",
        )
    except Exception as e:
        logger.error(f"聊天端点出错: {e}")
        raise HTTPException(status_code=500, detail=str(e))
