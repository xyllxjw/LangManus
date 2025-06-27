from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import create_tool_calling_agent

from src.tools.search import tavily_tool
from src.tools.file_management import list_files_tool, read_file_tool, write_file_tool
from src.tools.python_repl import python_repl_tool
from src.tools.browser import browse_tool, close_browser_tool, create_browser_tool
from src.prompts.template import apply_prompt_template
from src.config.agents import AGENT_LLM_MAP
from src.agents.llm import get_llm_by_type


def create_agent(agent_type: str, tools: list):
    """
    一个通用的Agent创建工厂函数。

    @param {str} agent_type - Agent的类型（例如 'researcher', 'coder'）。
                              这个类型用于从配置中获取对应的LLM和Prompt。
    @param {list} tools - 一个包含该Agent可以使用的工具的列表。
    @returns {AgentExecutor} 一个创建好的、可执行的Agent实例。
    """
    # 1. 根据Agent类型获取对应的Prompt模板
    prompt = ChatPromptTemplate.from_messages(
        apply_prompt_template(agent_type, {"messages": []})
    )
    # 2. 根据Agent类型获取对应的LLM实例
    llm = get_llm_by_type(AGENT_LLM_MAP[agent_type])
    # 3. 使用LangChain的create_tool_calling_agent方法创建Agent
    #    这个Agent被设计为能够理解并调用工具。
    return create_tool_calling_agent(llm, tools, prompt)


# 创建研究员Agent，为其配备搜索引擎工具
research_agent = create_agent(
    "researcher",
    [tavily_tool],
)

# 创建程序员Agent，为其配备文件操作和Python代码执行工具
coder_agent = create_agent(
    "coder",
    [list_files_tool, read_file_tool, write_file_tool, python_repl_tool],
)

# 创建浏览器Agent，为其配备完整的浏览器操作工具集
browser_agent = create_agent(
    "browser",
    [create_browser_tool, browse_tool, close_browser_tool],
)
