# LangManus 项目结构与工作流程深度解析

本文档旨在对 LangManus 项目进行全面的分析，包括其源代码结构、核心功能实现流程、以及多Agent协作机制，以帮助开发者快速理解和上手该项目。

---

## 一、 项目源代码结构 (`src`目录)

项目的核心逻辑全部位于`src`目录中，其子目录结构清晰，职责分明：

-   **`api/`**: 包含项目的Web服务入口。
    -   `app.py`: 基于**FastAPI**框架，定义了项目唯一的API端点`/api/chat/stream`，并使用服务器发送事件（SSE）实现对客户端的流式响应。

-   **`service/`**: 包含项目的核心业务服务。
    -   `workflow_service.py`: 定义了`run_agent_workflow`函数，这是工作流的**主驱动器**。它负责调用LangGraph图，处理执行过程中产生的各类事件，并将其格式化后传递给API层。

-   **`graph/`**: 定义了整个工作流的核心——**计算图**。
    -   `builder.py`: 使用**LangGraph**库来构建一个状态图（StateGraph），在图中注册所有的Agent节点，并指定工作流的入口。
    -   `nodes.py`: **项目最核心的逻辑文件**。定义了图中每一个节点（即每一个Agent）的具体行为和其内部的路由逻辑。
    -   `types.py`: 定义了贯穿整个工作流的共享`State`对象的数据结构，以及`supervisor`（监督员）决策时所依赖的`Router`数据结构。

-   **`agents/`**: 包含所有Agent的创建和配置。
    -   `agents.py`: 通过一个通用的`create_agent`工厂函数，创建了项目中所有具体的Agent实例（如`research_agent`, `coder_agent`等），并为它们绑定了各自可以使用的工具。
    -   `llm.py`: 封装了对不同类型大型语言模型（LLM）的调用逻辑。

-   **`tools/`**: 定义了可供Agents使用的各种工具。
    -   例如 `search.py`, `file_management.py`, `python_repl.py`等，分别封装了搜索引擎、文件操作、Python代码执行等能力。

-   **`prompts/`**: 管理所有Agent在与LLM交互时使用的提示（Prompt）模板。
    -   `template.py`: 提供了应用Prompt模板的功能。
    -   各种`.md`文件: 存储了不同角色的具体Prompt内容。

-   **`config/`**: 存放项目的各类配置信息。
    -   `agents.py`: 定义了Agent类型与所使用的LLM模型之间的映射关系。
    -   `env.py`: 管理环境变量。

---

## 二、 核心功能实现流程

本项目的核心是一个基于LangGraph构建的多Agent协作系统。其工作流程精巧地通过一个**监督员-执行者**（Supervisor-Executor）循环模式来完成复杂任务。

### 流程图示

```mermaid
graph TD
    A[用户请求<br/>/api/chat/stream] --> B(api/app.py);
    B --> C(service/run_agent_workflow);
    C --> D{LangGraph图<br/>开始执行};

    subgraph "工作流循环 (由Supervisor驱动)"
        D --> E[coordinator_node<br/>(协调员/入口)];
        E -->|"handoff_to_planner"| F[planner_node<br/>(规划师)];
        F --> G[supervisor_node<br/>(监督员/决策中枢)];
        G -->|"分派任务"| H[research_node<br/>(研究员)];
        G -->|"分派任务"| I[code_node<br/>(程序员)];
        G -->|"分派任务"| J[browser_node<br/>(浏览器)];
        G -->|"分派任务"| K[reporter_node<br/>(报告员)];
        H -- "完成, 交回控制权" --> G;
        I -- "完成, 交回控制权" --> G;
        J -- "完成, 交回控制权" --> G;
        K -- "完成, 交回控制权" --> G;
        G -->|"FINISH"| L{结束};
    end

    E --> |"无需规划"| L;

    subgraph "事件流 (实时反馈)"
        D -- "产生事件流" --> C;
        C -- "格式化事件" --> B;
        B -- "SSE流式响应" --> A;
    end

    style G fill:#f9f,stroke:#333,stroke-width:2px
    style E fill:#ccf,stroke:#333,stroke-width:2px
```

### 流程详解

1.  **启动 (API层)**:
    -   用户通过HTTP POST请求访问`/api/chat/stream`端点。
    -   `api/app.py`接收请求，调用`service/workflow_service.py`中的`run_agent_workflow`函数，并将用户消息和配置传入。

2.  **驱动 (Service层)**:
    -   `run_agent_workflow`函数启动预先构建好的LangGraph图的执行（通过`graph.astream_events`）。
    -   它异步地监听图执行过程中产生的所有事件（如节点开始/结束，工具调用，LLM流式输出等）。
    -   它将这些原始事件转换成统一格式的JSON，并通过SSE流实时地`yield`回API层。

3.  **入口与规划 (Graph层)**:
    -   图从`coordinator_node`（协调员）开始。该节点负责与用户进行初步沟通，判断任务是否需要一个详细的计划。
    -   如果需要，它会将控制权交给`planner_node`（规划师）。
    -   规划师可能会先调用**搜索引擎工具**进行信息搜集，然后调用一个强大的LLM来生成一份结构化（JSON格式）的详细行动计划，并将其存入共享的`State`中。
    -   规划完成后，控制权被移交给`supervisor_node`（监督员）。

4.  **监督-执行循环 (Graph层核心)**:
    -   **决策**: `supervisor_node`是整个工作流的**大脑和指挥中枢**。它查看共享`State`中的所有信息（用户原始需求、历史消息、完整计划等），然后调用一个专门用于决策的LLM，来决定**下一步应该由哪个Agent执行任务**。
    -   **分派**: 监督员根据LLM的决策，将流程`goto`到指定的执行者节点（如`research_node`, `code_node`等）。
    -   **执行**: 被选中的Agent节点（如`research_node`）被激活。它调用自己的LLM和绑定的工具（如搜索引擎），完成分配给它的具体任务，并将执行结果（如研究报告）更新回共享的`State`中。
    -   **交回**: 执行节点完成任务后，**无条件地将控制权交还给`supervisor_node`**。
    -   **循环**: 流程回到第1步（决策），监督员再次根据更新后的状态进行下一步决策。这个"**决策 -> 分派 -> 执行 -> 交回**"的循环会一直持续，直到任务被完全分解和执行。

5.  **结束**:
    -   当监督员的决策LLM认为计划中的所有步骤都已完成，它会返回一个特殊的指令`FINISH`。
    -   `supervisor_node`捕获到这个指令，将流程导向图的终点`__end__`，整个工作流优雅地结束。

---

## 三、 总结

LangManus是一个设计精良、高度模块化的多Agent协作框架。其核心优势在于：

-   **清晰的责任分离**: Supervisor负责宏观决策，Executor（各类Agent）负责具体执行，使得系统逻辑清晰，易于扩展。
-   **动态与灵活**: 工作流的路径不是预先固定的，而是由Supervisor在运行时根据上下文动态决定的，这使得系统能够灵活应对复杂和多变的任务。
-   **状态管理**: 通过一个集中式的`State`对象在图中传递信息，确保了所有Agent都能访问到最新的上下文，协同工作。
-   **实时反馈**: 基于FastAPI的SSE技术，将后端Agent的每一步思考和执行过程都实时地反馈给前端，提供了极佳的用户体验。

该项目是学习和实践高级Agent系统（如`agent-of-thought`或`multi-agent-collaboration`）的一个优秀范例。 