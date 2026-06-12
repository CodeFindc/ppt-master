# PPT Master - Function Calling 接口说明

该目录 (`FunCall/`) 提供了针对 `ppt-master` 幻灯片生成主要流程的 **Function Calling (函数调用/工具调用)** 封装。它专为**离线局域网 (Offline LAN)** 等无法直接连接公网 API 的环境设计，使本地运行的 LLM (如 Ollama, LM Studio, vLLM 等) 能够通过结构化的 JSON 工具调用来驱动和跑通整个 PPT 生成流水线。

---

## 📂 文件结构说明

- **[`ppt_tools.py`](file:///c:/Users/xsc/Documents/tmp/ppt-master/FunCall/ppt_tools.py)**: 核心工具库。将 `skills/ppt-master/scripts/` 下的各个 Python 脚本包装为标准的 Python 函数，自动处理 Windows 环境下的路径兼容性、环境隔离和执行状态捕捉。
- **[`tool_schemas.py`](file:///c:/Users/xsc/Documents/tmp/ppt-master/FunCall/tool_schemas.py)**: 工具定义 Schema。提供符合 **OpenAI API (Tools)** 规范以及 **Gemini FunctionDeclaration** 规范的结构化 JSON 定义，可直接传给模型。
- **[`run_pipeline.py`](file:///c:/Users/xsc/Documents/tmp/ppt-master/FunCall/run_pipeline.py)**: CLI 流水线运行器。允许在没有 LLM 交互的情况下，通过命令行手动/程序化地执行各个函数封装，方便进行单元测试和流水线断点运行。
- **[`local_agent.py`](file:///c:/Users/xsc/Documents/tmp/ppt-master/FunCall/local_agent.py)**: 本地 Function Calling 智能体示例。展示了如何通过标准的 API 协议连接本地加载的开源 LLM（如 Qwen2.5-Coder、Llama 3.1 等），并在本地通过循环调用工具完成端到端任务。

---

## 🔧 准备工作与环境配置

1. **启用 Python 虚拟环境**：
   确保你的全局或项目虚拟环境已激活，且已安装项目所需的全部依赖项（如 `requirements.txt` 中所列的 `PyMuPDF`、`Pillow`、`Flask` 等）。

2. **配置本地 LLM 环境变量**（仅在运行 `local_agent.py` 时需要）：
   你可以通过环境变量来配置本地大模型接口地址、模型名称以及 API 密钥 (Key)：
   - **Windows PowerShell**:
     ```powershell
     # 配置 API 基础地址 (Endpoint) - 优先读取 LOCAL_LLM_API_BASE，回退读取 OPENAI_API_BASE
     $env:LOCAL_LLM_API_BASE="http://localhost:11434/v1"  # Ollama 默认地址
     # $env:OPENAI_API_BASE="http://10.x.x.x:8000/v1"     # 局域网内其他中转/vLLM 服务地址
     
     # 配置 API 密钥 (Key) - 优先读取 LOCAL_LLM_API_KEY，回退读取 OPENAI_API_KEY
     $env:LOCAL_LLM_API_KEY="sk-your-local-key-here"      # 本地或局域网中转服务的 API 密钥
     
     # 配置模型名称 - 优先读取 LOCAL_LLM_MODEL，回退读取 OPENAI_MODEL
     $env:LOCAL_LLM_MODEL="qwen2.5-coder:14b"             # 本地加载的模型名称
     ```
   - **Windows CMD**:
     ```cmd
     :: 配置 API 基础地址 (Endpoint)
     set LOCAL_LLM_API_BASE=http://localhost:11434/v1
     
     :: 配置 API 密钥 (Key)
     set LOCAL_LLM_API_KEY=sk-your-local-key-here
     
     :: 配置模型名称
     set LOCAL_LLM_MODEL=qwen2.5-coder:14b
     ```

---

## 🚀 运行方式

### 1. 使用 CLI 运行器手动跑通流程 (`run_pipeline.py`)

CLI 运行器将 `ppt_tools.py` 内部的接口直接暴露为子命令。你可以依次运行以下命令测试它们：

```bash
# 步骤 1：转换源文件为 Markdown (例如 PDF 转换为 md)
python FunCall/run_pipeline.py convert C:/Users/xsc/Documents/tmp/source.pdf -o C:/Users/xsc/Documents/tmp/source.md

# 步骤 2：初始化项目
python FunCall/run_pipeline.py init my_project --format ppt169

# 步骤 3：导入转换后的 Markdown 文件至项目源目录
python FunCall/run_pipeline.py import projects/my_project_ppt169_20260608 C:/Users/xsc/Documents/tmp/source.md

# 步骤 4：拷贝/应用规范模板 (如果是自由设计可跳过此步)
python FunCall/run_pipeline.py template projects/my_project_ppt169_20260608 skills/ppt-master/templates/brands/anthropic

# 步骤 5（在 LLM 写入 design_spec.md 和 spec_lock.md 之后）：渲染 LaTeX 公式
python FunCall/run_pipeline.py latex projects/my_project_ppt169_20260608

# 步骤 6：生成 AI 图像 (若 spec_lock.md 中包含 ai 来源的图片)
python FunCall/run_pipeline.py image projects/my_project_ppt169_20260608

# 步骤 7：启动前端实时预览服务
python FunCall/run_pipeline.py preview projects/my_project_ppt169_20260608 --port 5050

# 步骤 8（在 LLM 在 svg_output/ 下生成全部 slide.svg 和 notes/total.md 之后）：进行格式化后处理并导出 PPTX
python FunCall/run_pipeline.py finalize projects/my_project_ppt169_20260608 --compress --transition fade

# 步骤 9：验证项目结构
python FunCall/run_pipeline.py validate projects/my_project_ppt169_20260608
```

### 2. 使用本地大模型进行 Function Calling 交互 (`local_agent.py` - LangGraph 版)

`local_agent.py` 使用 **LangGraph** 重构，将原有的命令式循环升级为基于状态机图（StateGraph）的智能体架构。

运行前请确保已安装 LangGraph 相关依赖：
```bash
pip install -r FunCall/requirements.txt
# 或者单独安装：
pip install langgraph langchain-core langchain-openai
```

确保你的本地模型服务已启动（例如，执行 `ollama run qwen2.5-coder:14b`），然后执行：

```bash
python FunCall/local_agent.py "请将 C:/Users/xsc/Documents/tmp/paper.pdf 转换为 Markdown，并以此初始化一个名为 'paper_summary' 的项目"
```

**智能体 LangGraph 架构设计**：
- **状态（State）**：定义为 `AgentState`，包含对话消息历史列表 `messages`（使用 `add_messages` 增量合并）以及当前执行步骤计数器 `step`。
- **节点（Nodes）**：
  - `agent` 节点：调用本地配置的 `ChatOpenAI` 接口，模型自动通过 `bind_tools` 绑定了所有 PPT 生成工具。
  - `tools` 节点：当模型输出包含工具调用指令时，在此节点循环调用 `ppt_tools.py` 内部对应的本地 Python 工具包装函数，将执行结果返回为 `ToolMessage` 列表。
- **边（Edges）**：
  - 起始于 `agent` 节点，并由条件路由函数 `should_continue` 决定去向：
    - 若包含 `tool_calls` 任务，路由至 `tools` 节点执行工具。
    - 若没有工具调用，说明任务结束，路由至 `END` 终止执行。
  - `tools` 节点执行完毕后，自动有一条单向边连回 `agent` 节点，继续进行下一步推理。

---

## 🌐 FastAPI 服务化接口服务部署

我们进一步将 `FunCall` 工具包和 LangGraph 智能体封装为了一个统一的 **FastAPI Web 服务**，使局域网内的前端应用或其他客户端可以通过标准的 API 和实时流式传输（SSE）来驱动 PPT 的生成和可视化预览编辑。

### 1. 启动服务
在 `FunCall/` 目录下运行 Uvicorn 服务器（默认监听 **`5050`** 端口）：
```bash
# 进入虚拟环境并运行
.\venv\Scripts\python -m uvicorn app:app --port 5050
```

### 2. 核心架构与端点说明

#### 2.1 动态会话与可视化编辑 (`/{session_id}`)
- **路由入口**：访问 `http://127.0.0.1:5050/{session_id}` 会在浏览器设置 `session_id` 的 Cookie，并直接加载内置的可视化 SVG 编辑器。
- **Cookie 自动路由**：随后静态页面发起的所有数据请求（如 `/api/slides`、`/images/pic.png`）都会由后端根据 Cookie 中的 `session_id` 自动定位到对应的项目目录 `projects/{session_id}_*`，从而支持多会话并行编辑，且不需要修改任何前端代码。

#### 2.2 项目初始化与文件导入 API
- **初始化项目**：
  - **URL**: `POST /api/projects/init`
  - **Body**: `{"session_id": "可选_如不传自动生成", "format": "ppt169"}`
  - **说明**: 初始化成功后会在 Response 响应中回写 `session_id` 的 Cookie。
- **上传源文件**：
  - **URL**: `POST /api/projects/import`
  - **Body**: `file` (Multipart Upload)
  - **说明**: 接收用户上传的本地源文件，自动将其存入服务端临时目录并导入至会话对应的项目中。

#### 2.3 流式智能体进度 API (`POST /api/agent/run`)
- **Body**: `{"prompt": "我有一篇产品市场调研报告，请帮我分析并生成一份演示文稿"}`
- **响应格式**: `text/event-stream` (Server-Sent Events)
- **说明**: 拉起后台的 LangGraph 智能体，并通过持久化的 checkpoint (`MemorySaver`) 保证会话记忆，支持多轮对话持续修改。执行的日志进度（如 `[*] Step 1: Querying LLM...`、`[TOOL CALL] Executing...`）会以流式逐行实时推送给前端。

#### 2.4 PPTX 导出与下载
- **导出 PPTX**：`POST /api/projects/export`
- **下载 PPTX**：`GET /api/projects/download`

---

## 🛠️ 如何将工具整合到您自己的代理框架中

如果您使用的是成熟的 Python 代理框架（如 **LangChain**、**AutoGen**、**CrewAI** 等），可以很容易地导入我们的工具和 Schema：

### 1. LangChain / LangGraph 集成示例
```python
from langchain_core.tools import StructuredTool
from FunCall import ppt_tools

# 将本地工具直接包装为 StructuredTool
convert_tool = StructuredTool.from_function(
    func=ppt_tools.convert_source_to_markdown,
    name="convert_source_to_markdown",
    description="Converts a source document or Web URL to Markdown format."
)

# 之后可以将 tool 绑定到你的 ChatModel 上：
# llm_with_tools = model.bind_tools([convert_tool, ...])
```

### 2. 原生 OpenAI SDK 集成示例
```python
from openai import OpenAI
from FunCall import ppt_tools
from FunCall.tool_schemas import OPENAI_TOOLS

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

response = client.chat.completions.create(
    model="qwen2.5-coder:14b",
    messages=[{"role": "user", "content": "初始化一个名称为 test 的 ppt 16:9 项目"}],
    tools=OPENAI_TOOLS,
    tool_choice="auto"
)
```

---

## 🔌 MCP (Model Context Protocol) 智能体服务化调度

本项目在 `FunCall/mcp_agent_server.py` 中实现了**智能体即服务 (Agent-as-a-Service)** 的 MCP 协议封装。它将整个 PPT 协同生成与设计智能体（LangGraph Agent）打包为一个高级的“PPT 制作专家”提供给外部调度。

### 1. 启动 MCP 服务

服务支持三种不同的传输模式（Stdio、SSE HTTP、Streamable HTTP）：

```bash
# 模式 A: Stdio 模式（默认，用于本地 IDE/Claude 客户端）
python FunCall/mcp_agent_server.py

# 模式 B: SSE HTTP 传输模式（用于局域网内跨机调用）
python FunCall/mcp_agent_server.py --transport sse --port 8001

# 模式 C: Streamable HTTP 传输模式（最新推荐，更高效的双向流传输）
python FunCall/mcp_agent_server.py --transport streamable-http --port 8001
```

* **启动参数**：
  * `--transport`：可选择 `stdio`、`sse` 或 `streamable-http`。
  * `--host`：绑定的 IP 地址（默认 `0.0.0.0`，允许局域网远程访问）。
  * `--port`：监听端口（默认 `8001`）。

### 2. 客户端接入配置

#### 本地集成 (例如 Claude Desktop)
在 `%APPDATA%\Claude\claude_desktop_config.json` 中配置：
```json
{
  "mcpServers": {
    "ppt-master-agent": {
      "command": "python",
      "args": [
        "D:/iso/ppt-master/FunCall/mcp_agent_server.py"
      ]
    }
  }
}
```

#### 局域网分布式客户端远程调用 (基于 HTTP SSE)
```python
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

async def main():
    # 对接局域网中运行的 MCP 智能体服务
    async with sse_client("http://192.168.x.x:8001/sse") as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            
            # 一键委托“PPT 智能体”进行生成
            result = await session.call_tool(
                "create_presentation", 
                arguments={
                    "prompt": "帮我生成一份关于人工智能在医疗领域应用的 PPT"
                }
            )
            print("生成任务结果:", result.content)

asyncio.run(main())
```

### 3. 暴露接口规范

* **Tools (工具)**:
  * `create_presentation(prompt, format)`: 自动启动后台 LangGraph 生成完整的演示文稿并返回 PPTX 下载链接。
  * `optimize_presentation_with_annotations(session_id)`: 根据用户在画板上对 SVG 标记的批注直接对 PPT 进行二次重绘和重新排版。
* **Resources (资源)**:
  * `ppt://{session_id}/spec`: 读取对应项目当前的设计规范大纲文件（`design_spec.md`）。
  * `ppt://{session_id}/spec-lock`: 读取对应项目当前的样式物理约束锁文件（`spec_lock.md`）。
