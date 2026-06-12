# -*- coding: utf-8 -*-
"""
FunCall - MCP (Model Context Protocol) Agent-as-a-Service Server
Wraps the entire LangGraph Agent loop as a single high-level MCP Tool,
allowing other external agents to request and generate PPT presentations.
"""

import sys
import os
import json
import uuid
import time
from pathlib import Path
from mcp.server.fastmcp import FastMCP

# Resolve path to import app.py and ppt_tools.py
FUN_CALL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(FUN_CALL_DIR))

try:
    from app import agent_app, get_or_create_session_project_path, SYSTEM_PROMPT
except ImportError as e:
    print(f"[-] Failed to import core agent components from app.py: {e}")
    sys.exit(1)

# Initialize FastMCP Server
mcp = FastMCP("PPT-Generation-Agent")

# ==========================================
# 1. MCP Tools (High-Level Actions)
# ==========================================

@mcp.tool()
async def create_presentation(prompt: str, format: str = "ppt169") -> str:
    """
    委托『PPT制作专家智能体』从头设计并生成一份全新的 PowerPoint 演示文稿（PPTX）。
    该工具会自动串联执行：文档分析 -> 项目初始化 -> 风格规范生成 -> 图像/公式绘制 -> 逐页SVG渲染 -> 后处理与PPTX导出。
    
    :param prompt: PPT 主题说明、幻灯片制作大纲或者文档路径（如 C:/path/to/report.pdf/md 或 Web 链接）。
    :param format: 画布版式（可选：ppt169 16:9比例，ppt43 4:3比例，xhs 小红书，story 故事）。
    :return: 任务执行状态，包含 session_id、项目物理路径和最终 PPTX 下载链接。
    """
    # 1. Generate a unique session_id for directory isolation & state tracking
    session_id = str(uuid.uuid4())
    
    # 2. Build LangGraph execution config
    config = {
        "configurable": {
            "thread_id": session_id,
        },
        "recursion_limit": 100
    }
    
    # 3. Formulate initial agent message state
    from langchain_core.messages import SystemMessage, HumanMessage
    initial_state = {
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ],
        "step": 1
    }
    
    print(f"[*] MCP Server: Delegating task to internal LangGraph. Session: {session_id}")
    
    try:
        # Run LangGraph streaming in background
        async for event in agent_app.astream(initial_state, config=config):
            for node_name, output in event.items():
                print(f"    [Node: {node_name}] processed.")
    except Exception as e:
        return json.dumps({
            "success": False,
            "session_id": session_id,
            "error": f"Internal LangGraph failed: {str(e)}"
        }, ensure_ascii=False)
        
    # 4. Resolve the project path and check generated exports
    actual_project_path = get_or_create_session_project_path(session_id, format)
    export_dir = actual_project_path / "exports"
    
    pptx_files = []
    if export_dir.exists():
        pptx_files = sorted(export_dir.glob("*.pptx"), key=lambda f: f.stat().st_mtime, reverse=True)
        
    if pptx_files:
        final_pptx_name = pptx_files[0].name
        # Match download API in app.py
        download_url = f"http://127.0.0.1:5050/api/projects/download?filename={final_pptx_name}"
        return json.dumps({
            "success": True,
            "session_id": session_id,
            "project_path": str(actual_project_path).replace("\\", "/"),
            "pptx_filename": final_pptx_name,
            "download_url": download_url,
            "message": "PPT generated successfully! You can download the native PPTX via the download_url."
        }, ensure_ascii=False)
    else:
        return json.dumps({
            "success": False,
            "session_id": session_id,
            "project_path": str(actual_project_path).replace("\\", "/"),
            "error": "LangGraph finished execution but no PPTX file was found in exports/."
        }, ensure_ascii=False)

@mcp.tool()
async def optimize_presentation_with_annotations(session_id: str) -> str:
    """
    根据用户在画板上对 SVG 元素添加的修改标注（Annotations），委托『PPT制作专家智能体』对 PPT 进行重绘与排版二次优化。
    大模型会自动识别标注，在后台修改对应的 SVG 并重新编译导出全新的 PPTX 文件。
    
    :param session_id: 之前成功生成 PPT 时返回的唯一会话 ID (session_id)。
    :return: 优化后的任务状态与重新导出的 PPTX 下载链接。
    """
    # Use the same session_id to load conversation checkpoint & project sandbox
    config = {
        "configurable": {
            "thread_id": session_id,
        },
        "recursion_limit": 100
    }
    
    from langchain_core.messages import HumanMessage
    initial_state = {
        "messages": [
            HumanMessage(content="请根据我刚才在右侧添加的标注，优化当前这页幻灯片的布局排版")
        ]
    }
    
    print(f"[*] MCP Server: Optimizing PPT with annotations. Session: {session_id}")
    
    try:
        async for event in agent_app.astream(initial_state, config=config):
            for node_name, output in event.items():
                print(f"    [Node: {node_name}] processed.")
    except Exception as e:
        return json.dumps({
            "success": False,
            "session_id": session_id,
            "error": f"Internal LangGraph failed during optimization: {str(e)}"
        }, ensure_ascii=False)
        
    actual_project_path = get_or_create_session_project_path(session_id)
    export_dir = actual_project_path / "exports"
    
    pptx_files = []
    if export_dir.exists():
        pptx_files = sorted(export_dir.glob("*.pptx"), key=lambda f: f.stat().st_mtime, reverse=True)
        
    if pptx_files:
        final_pptx_name = pptx_files[0].name
        download_url = f"http://127.0.0.1:5050/api/projects/download?filename={final_pptx_name}"
        return json.dumps({
            "success": True,
            "session_id": session_id,
            "project_path": str(actual_project_path).replace("\\", "/"),
            "pptx_filename": final_pptx_name,
            "download_url": download_url,
            "message": "PPT optimized and re-exported successfully!"
        }, ensure_ascii=False)
    else:
        return json.dumps({
            "success": False,
            "session_id": session_id,
            "error": "Optimization completed but no new PPTX file was found in exports/."
        }, ensure_ascii=False)

# ==========================================
# 2. MCP Resources (Exposing internal documents)
# ==========================================

@mcp.resource("ppt://{session_id}/spec")
def get_project_spec(session_id: str) -> str:
    """读取指定项目当前的 Design Specification (design_spec.md) 规划说明书。"""
    try:
        project_path = get_or_create_session_project_path(session_id)
        spec_file = project_path / "design_spec.md"
        if spec_file.exists():
            return spec_file.read_text(encoding="utf-8")
        return "Design specification not found yet. The PPT might still be generating."
    except Exception as e:
        return f"Error reading design spec: {e}"

@mcp.resource("ppt://{session_id}/spec-lock")
def get_project_spec_lock(session_id: str) -> str:
    """读取指定项目当前的 Execution Contract (spec_lock.md) 结构锁定配置。"""
    try:
        project_path = get_or_create_session_project_path(session_id)
        spec_lock_file = project_path / "spec_lock.md"
        if spec_lock_file.exists():
            return spec_lock_file.read_text(encoding="utf-8")
        return "Execution lock (spec_lock.md) not found yet."
    except Exception as e:
        return f"Error reading spec lock: {e}"

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="FunCall MCP Agent-as-a-Service Server")
    parser.add_argument("--sse", action="store_true", help="Run in SSE transport mode")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to for SSE (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8001, help="Port to listen on for SSE (default: 8001)")
    
    args = parser.parse_args()
    
    if args.sse:
        print(f"[*] Starting FunCall MCP Agent-as-a-Service server on SSE: http://{args.host}:{args.port}", file=sys.stderr)
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.settings.transport_security = None  # Disable DNS Rebinding Protection for remote/LAN access
        mcp.run(transport="sse")
    else:
        print("[*] Starting FunCall MCP Agent-as-a-Service server on stdio...", file=sys.stderr)
        mcp.run(transport="stdio")
