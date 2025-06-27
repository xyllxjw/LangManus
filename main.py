"""
Entry point script for the LangGraph Demo.
"""

from src.workflow import run_agent_workflow
from langchain_core.messages import BaseMessage

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        user_query = " ".join(sys.argv[1:])
    else:
        user_query = input("Enter your query: ")

    result = run_agent_workflow(user_input=user_query, debug=True)

    # Print the conversation history
    print("\n\n=== Conversation History ===")
    if result and "messages" in result:
        for message in result["messages"]:
            if isinstance(message, BaseMessage):
                # Handle LangChain message objects
                role = message.type.capitalize()
                content = message.content
            elif isinstance(message, dict):
                # Handle dictionary-based messages
                role = message.get("role", "Unknown").capitalize()
                content = message.get("content", "")
            else:
                # Handle any other unexpected types gracefully
                role = "Unknown"
                content = str(message)

            print(f"--- {role} ---\n{content}\n")
    else:
        print("No conversation history found.")
