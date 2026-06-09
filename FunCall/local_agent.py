# -*- coding: utf-8 -*-
"""
PPT Master - Local Function Calling Agent (LangGraph Edition)
Demonstrates how to wire the ppt_tools wrappers to a local, offline LLM endpoint
(such as Ollama, LM Studio, or vLLM) using a LangGraph state graph.
"""

import os
import sys
import json
from pathlib import Path
from typing import Annotated, Sequence, TypedDict

# Add current directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ppt_tools
import tool_schemas

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

# ==========================================
# Configuration (Adjust for your local LAN environment)
# ==========================================
# If using Ollama, the default endpoint is http://localhost:11434/v1
# If using LM Studio, it's typically http://localhost:1234/v1
# If using vLLM, it depends on your custom server setup
API_BASE_URL = os.environ.get("LOCAL_LLM_API_BASE") or os.environ.get("OPENAI_API_BASE", "http://localhost:11434/v1")
MODEL_NAME = os.environ.get("LOCAL_LLM_MODEL") or os.environ.get("OPENAI_MODEL", "qwen2.5-coder:14b")
API_KEY = os.environ.get("LOCAL_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY", "not-needed-for-local")

# Map of tool names to actual functions in ppt_tools.py
TOOL_FUNCTION_MAP = {
    "convert_source_to_markdown": ppt_tools.convert_source_to_markdown,
    "init_project": ppt_tools.init_project,
    "import_sources": ppt_tools.import_sources,
    "apply_template": ppt_tools.apply_template,
    "analyze_images": ppt_tools.analyze_images,
    "render_latex": ppt_tools.render_latex,
    "generate_images": ppt_tools.generate_images,
    "start_preview_server": ppt_tools.start_preview_server,
    "check_annotations": ppt_tools.check_annotations,
    "check_svg_quality": ppt_tools.check_svg_quality,
    "split_speaker_notes": ppt_tools.split_speaker_notes,
    "finalize_svg_files": ppt_tools.finalize_svg_files,
    "export_to_pptx": ppt_tools.export_to_pptx,
    "validate_project": ppt_tools.validate_project,
    "save_design_spec": ppt_tools.save_design_spec,
    "save_spec_lock": ppt_tools.save_spec_lock,
    "save_svg_page": ppt_tools.save_svg_page,
    "save_speaker_notes": ppt_tools.save_speaker_notes,
    "read_file": ppt_tools.read_file,
    "list_dir": ppt_tools.list_dir,
}

def build_tools():
    """Build LangChain StructuredTools from our schemas and functions."""
    tools_list = []
    for tool_schema in tool_schemas.OPENAI_TOOLS:
        name = tool_schema["function"]["name"]
        description = tool_schema["function"]["description"]
        func = TOOL_FUNCTION_MAP.get(name)
        if func:
            tools_list.append(StructuredTool.from_function(
                func=func,
                name=name,
                description=description
            ))
    return tools_list

# ==========================================
# LangGraph Agent State
# ==========================================
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    step: int

# ==========================================
# Nodes & Router
# ==========================================
# Initialize the local LLM using ChatOpenAI
model = ChatOpenAI(
    base_url=API_BASE_URL,
    api_key=API_KEY,
    model=MODEL_NAME,
    temperature=0.1,
)

tools_list = build_tools()
model_with_tools = model.bind_tools(tools_list)

def call_model(state: AgentState):
    """Query the local LLM model."""
    step = state.get("step", 1)
    print(f"\n[*] Step {step}: Querying LLM...")
    
    messages = state["messages"]
    try:
        response = model_with_tools.invoke(messages)
    except Exception as e:
        print(f"[-] Connection Error: {e}")
        print(f"    Please verify that your local LLM server is running at: {API_BASE_URL}")
        print(f"    and that the model '{MODEL_NAME}' is pulled/loaded.")
        sys.exit(1)
        
    return {"messages": [response], "step": step + 1}

# Known path keys in our tool schemas to normalize for comparison
PATH_KEYS = {
    "project_path",
    "input_path",
    "output_path",
    "manifest_path",
    "source_files",
    "template_paths",
    "file_path",
    "dir_path"
}

def normalize_tool_args(args):
    """Normalize file paths (slashes, case, absolute status) for robust equivalence comparison."""
    if not isinstance(args, dict):
        return args
    normalized = {}
    for k, v in args.items():
        if k in PATH_KEYS:
            if isinstance(v, str):
                normalized[k] = ppt_tools.normalize_path(v)
            elif isinstance(v, list):
                normalized[k] = [ppt_tools.normalize_path(item) if isinstance(item, str) else item for item in v]
            else:
                normalized[k] = v
        else:
            normalized[k] = v
    return normalized

def check_tool_has_succeeded(messages, tool_name, tool_args):
    """Search history to see if this tool has successfully executed with equivalent arguments."""
    normalized_args = normalize_tool_args(tool_args)
    for i in range(len(messages)):
        msg = messages[i]
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc["name"] == tool_name:
                    tc_norm_args = normalize_tool_args(tc["args"])
                    if tc_norm_args == normalized_args:
                        tc_id = tc["id"]
                        # Find corresponding ToolMessage
                        for j in range(i + 1, len(messages)):
                            t_msg = messages[j]
                            if isinstance(t_msg, ToolMessage) and t_msg.tool_call_id == tc_id:
                                try:
                                    res = json.loads(t_msg.content)
                                    if res.get("success") is True:
                                        return res
                                except Exception:
                                    pass
    return None

def call_tools(state: AgentState):
    """Execute requested tool calls using ppt_tools wrappers."""
    messages = state["messages"]
    last_message = messages[-1]
    
    tool_messages = []
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return {"messages": tool_messages}
        
    print(f"[+] Model requested {len(last_message.tool_calls)} tool call(s).")
    
    for tool_call in last_message.tool_calls:
        name = tool_call["name"]
        args = tool_call["args"]
        call_id = tool_call["id"]
        
        print(f"\n[TOOL CALL] Executing: {name}")
        print(f"            Args: {json.dumps(args, indent=2, ensure_ascii=False)}")
        
        # Loop prevention check: if the tool has already run successfully with the same arguments, prevent it from running again
        prev_success = check_tool_has_succeeded(messages, name, args)
        if prev_success:
            print(f"[LOOP DETECTED] Tool '{name}' has already succeeded previously.")
            warning_msg = (
                f"Error: Tool '{name}' has already been successfully executed with equivalent arguments. "
                f"Previous result: {json.dumps(prev_success, ensure_ascii=False)}. "
                f"Do not call '{name}' again with the same arguments. "
                f"You must proceed to the next step in the workflow (e.g. writing design_spec.md/spec_lock.md, "
                f"generating slides, or exporting)."
            )
            tool_messages.append(ToolMessage(
                content=json.dumps({"success": False, "error": warning_msg}, ensure_ascii=False),
                tool_call_id=call_id,
                name=name
            ))
            continue
            
        func = TOOL_FUNCTION_MAP.get(name)
        if not func:
            error_res = {"success": False, "error": f"Tool '{name}' is not registered."}
            tool_messages.append(ToolMessage(
                content=json.dumps(error_res, ensure_ascii=False),
                tool_call_id=call_id,
                name=name
            ))
            continue
            
        try:
            result = func(**args)
            
            # Print a short summary of the execution
            status = "Success" if result.get("success") else "Failed"
            print(f"[TOOL RESULT] Status: {status}")
            if not result.get("success"):
                error_msg = result.get('error') or result.get('stderr')
                if not error_msg and result.get('stdout'):
                    stdout = result.get('stdout', '')
                    error_lines = [l for l in stdout.splitlines() if '[ERROR]' in l]
                    error_msg = "\n".join(error_lines) if error_lines else stdout.strip()
                print(f"              Error: {error_msg}")
                
            tool_messages.append(ToolMessage(
                content=json.dumps(result, ensure_ascii=False),
                tool_call_id=call_id,
                name=name
            ))
        except Exception as e:
            print(f"[TOOL ERROR] Exception raised: {e}")
            tool_messages.append(ToolMessage(
                content=json.dumps({"success": False, "error": str(e)}, ensure_ascii=False),
                tool_call_id=call_id,
                name=name
            ))
            
    return {"messages": tool_messages}

def should_continue(state: AgentState):
    """Determine whether to route to tools or end execution."""
    messages = state["messages"]
    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END

# ==========================================
# Graph Compilation
# ==========================================
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", call_tools)

workflow.set_entry_point("agent")
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "tools": "tools",
        END: END
    }
)
workflow.add_edge("tools", "agent")

app = workflow.compile()

# ==========================================
# Run Loop
# ==========================================
def run_agent_loop(prompt: str):
    """Main execution loop for the LangGraph agent."""
    print(f"[*] Starting agent with model: {MODEL_NAME}")
    print(f"[*] Target Endpoint: {API_BASE_URL}")
    print("=" * 60)
    
    print("[*] State Graph Structure:")
    try:
        print(app.get_graph().draw_ascii())
    except Exception as e:
        print(f"    (Could not draw ASCII graph: {e})")
    print("=" * 60)
    
    system_prompt = (
        "You are the PPT Master Strategist and Executor. You coordinate and generate presentation decks.\n"
        "You have access to a set of local tools to run the pipeline steps.\n"
        "Workflow Order:\n"
        "1. Convert documents if needed (convert_source_to_markdown).\n"
        "   - Note: If the source document is already a Markdown file (.md or .markdown), do NOT call convert_source_to_markdown. Proceed directly to initializing the project and importing sources.\n"
        "2. Initialize the project (init_project). Only call this ONCE per project. If a project is already initialized, do not call it again.\n"
        "3. Import source documents (import_sources). Only call this ONCE per project. Ensure you pass the correct unconverted or converted Markdown files.\n"
        "4. Write design specification (save_design_spec) and execution contract (save_spec_lock).\n"
        "5. Render LaTeX formulas if manifest exists (render_latex).\n"
        "6. Generate AI images if manifest exists (generate_images).\n"
        "7. Start the preview server (start_preview_server).\n"
        "8. Generate SVG slides page-by-page (save_svg_page).\n"
        "9. Save speaker notes (save_speaker_notes).\n"
        "10. Finalize SVGs, split notes, and export to PPTX (finalize_svg_files, split_speaker_notes, export_to_pptx).\n"
        "\n"
        "Rules & Guidelines:\n"
        "- Execute tools step-by-step. Do not loop or re-call initialization/import/conversion tools once they have succeeded.\n"
        "- If a tool output indicates success (including 'No conversion needed' or 'already exists'), immediately move to the next workflow step instead of calling it again.\n"
        "- If you call a tool and receive an error message saying that the tool has already been successfully executed, you MUST stop calling that tool and proceed to the next logical step in the workflow.\n"
        "- If a tool call fails with a real error, read the error message carefully and fix the arguments instead of blindly retrying.\n"
        "\n"
        "Handling User Annotations & Post-Export Edits:\n"
        "- If the user asks to apply annotations/edits (e.g., 'apply my annotations', '应用注解', '开始应用'), do the following:\n"
        "  1. Call check_annotations to discover all pending edits on the slides.\n"
        "  2. For each annotation, use read_file to load the target SVG content, locate the element by its element_id, modify its text/color/style/layout in the SVG markup per the instruction, remove the 'data-edit-target' and 'data-edit-annotation' attributes from that element, and save the updated content back using save_svg_page.\n"
        "  3. After editing all targeted elements, run finalize_svg_files and export_to_pptx to compile and re-export the updated presentation."
    )
    
    initial_state = {
        "messages": [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt)
        ],
        "step": 1
    }
    
    config = {"recursion_limit": 50}
    
    # Run graph execution stream
    for event in app.stream(initial_state, config=config):
        for node_name, output in event.items():
            if node_name == "agent":
                last_msg = output["messages"][-1]
                if not last_msg.tool_calls:
                    print("\n[+] Agent Completed Task / Response:")
                    print(last_msg.content)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python local_agent.py \"<instruction>\"")
        print("Example:")
        print("  python local_agent.py \"Please convert c:/path/to/paper.pdf and create a project named 'my_paper'\"")
        sys.exit(1)
        
    user_instruction = sys.argv[1]
    run_agent_loop(user_instruction)
