import streamlit as st
import requests
import json

# --- 配置 ---
API_URL = "http://localhost:8000/api/chat/stream"
USER_AVATAR = "🧑‍💻"
BOT_AVATAR = "🤖"

# --- 页面设置 ---
st.set_page_config(
    page_title="LangManus 聊天机器人",
    page_icon=BOT_AVATAR,
    layout="wide"
)
st.title("LangManus 聊天机器人")
st.write("一个基于多智能体（Multi-Agent）的AI聊天应用。")

# --- 会话状态管理 ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- UI 渲染 ---
# 显示历史消息
for message in st.session_state.messages:
    avatar = USER_AVATAR if message["role"] == "user" else BOT_AVATAR
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])

# 获取用户输入
if prompt := st.chat_input("请输入您的问题..."):
    # 1. 将用户消息添加到会话历史并显示
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(prompt)

    # 2. 准备请求数据
    api_payload = {
        "messages": [{"role": "user", "content": prompt}],
        "debug": True
    }
    
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream'
    }

    # 3. 创建一个空的助手消息占位符
    with st.chat_message("assistant", avatar=BOT_AVATAR):
        message_placeholder = st.empty()
        full_response = ""
        event_type = ""
        try:
            # 使用 requests.post(stream=True) 并手动解析事件流
            # 这移除了 sseclient 和 httpx，以最简单、最可靠的方式处理与异步后端的通信
            with requests.post(API_URL, json=api_payload, headers=headers, stream=True) as response:
                response.raise_for_status()
                
                for line in response.iter_lines():
                    if not line:
                        continue
                    
                    line_str = line.decode('utf-8')
                    
                    if line_str.startswith("event:"):
                        event_type = line_str.split(":", 1)[1].strip()
                    elif line_str.startswith("data:"):
                        data_str = line_str.split(":", 1)[1].strip()
                        if not data_str:
                            continue
                        try:
                            data = json.loads(data_str)
                            if event_type == "message":
                                delta = data.get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    full_response += content
                                    message_placeholder.markdown(full_response + "▌")
                            elif event_type == "tool_call":
                                tool_name = data.get('tool_name', 'unknown_tool')
                                tool_args = data.get('tool_input', {})
                                tool_info = f"**Tool Call:** `{tool_name}({json.dumps(tool_args)})`"
                                full_response += f"\n\n{tool_info}\n\n"
                                message_placeholder.markdown(full_response)
                            elif event_type == "tool_call_result":
                                tool_name = data.get('tool_name', 'unknown_tool')
                                tool_result = data.get('tool_result', '')
                                if not isinstance(tool_result, str):
                                    tool_result = json.dumps(tool_result, indent=2)
                                result_info = f"**Tool Result for `{tool_name}`:**\n```\n{tool_result}\n```"
                                full_response += f"\n\n{result_info}\n\n"
                                message_placeholder.markdown(full_response)
                            elif event_type == "error":
                                st.error(f"An error occurred: {data.get('error', data_str)}")
                                break
                        except json.JSONDecodeError:
                            # 容错处理：如果JSON解析失败，我们就认为这是后端出错前发送的原始文本
                            # 直接追加并显示，然后中断
                            full_response += f"\n\n```\n{data_str}\n```\n"
                            message_placeholder.markdown(full_response)
                            break
            
            message_placeholder.markdown(full_response)
            if full_response and not any(msg.get("content") == full_response for msg in st.session_state.messages if msg["role"] == "assistant"):
                 st.session_state.messages.append({"role": "assistant", "content": full_response})

        except requests.exceptions.ChunkedEncodingError:
            # 这个错误通常在后端提前关闭连接时发生，是我们的主要目标
            # 我们在这里保存已收到的内容，而不是显示错误
            message_placeholder.markdown(full_response)
            if full_response and not any(msg.get("content") == full_response for msg in st.session_state.messages if msg["role"] == "assistant"):
                 st.session_state.messages.append({"role": "assistant", "content": full_response})
        except requests.exceptions.RequestException as e:
            if full_response:
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            st.error(f"无法连接到API: {e}")
        except Exception as e:
            if full_response:
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            st.error(f"发生未知错误: {e}")