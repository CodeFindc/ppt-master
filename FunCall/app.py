# -*- coding: utf-8 -*-
"""
PPT Master - FastAPI Service (LangGraph Edition)
Serves the web UI and provides API endpoints for running the LangGraph agent
and managing slide previews / edits dynamically based on session_id.
"""

import os
import sys
import json
import uuid
import time
import shutil
import re
import html
import asyncio
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Annotated, Sequence, TypedDict, Optional, List

from fastapi import FastAPI, Cookie, Response, Request, HTTPException, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Add parent directory to path to resolve sibling imports
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ppt_tools
import tool_schemas

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

# ==========================================
# Paths Resolution
# ==========================================
REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills" / "ppt-master"
SCRIPTS_DIR = SKILLS_DIR / "scripts"
SVG_EDITOR_DIR = SCRIPTS_DIR / "svg_editor"
FINALIZE_DIR = SCRIPTS_DIR / "svg_finalize"
STATIC_DIR = SVG_EDITOR_DIR / "static"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(SVG_EDITOR_DIR) not in sys.path:
    sys.path.insert(0, str(SVG_EDITOR_DIR))
if str(FINALIZE_DIR) not in sys.path:
    sys.path.insert(0, str(FINALIZE_DIR))

from annotations import (
    assign_temp_ids,
    is_editable_attr,
    parse_annotations,
    promote_tspan_to_text,
    set_annotation,
    set_attributes,
    set_text,
    strip_unused_temp_ids,
)
from embed_icons import (
    parse_use_element,
    resolve_icon_path,
    extract_paths_from_icon,
    generate_icon_group,
)

_ICONS_DIR = REPO_ROOT / 'skills' / 'ppt-master' / 'templates' / 'icons'
_USE_ICON_PATTERN = re.compile(r'<use\s+[^>]*data-icon="[^"]*"[^>]*/>')

# ==========================================
# Configuration (Local LAN Environment)
# ==========================================
API_BASE_URL = os.environ.get("LOCAL_LLM_API_BASE") or os.environ.get("OPENAI_API_BASE", "http://localhost:11434/v1")
MODEL_NAME = os.environ.get("LOCAL_LLM_MODEL") or os.environ.get("OPENAI_MODEL", "qwen2.5-coder:14b")
API_KEY = os.environ.get("LOCAL_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY", "not-needed-for-local")

# ==========================================
# Memory Stores for Web Editor
# ==========================================
# Mapped by session_id: {session_id: {filename: {element_id: annotation_text}}}
session_annotations = {}
# Mapped by session_id: {session_id: {filename: list_of_pending_edit_records}}
session_pending_edits = {}

# ==========================================
# Path Mapping Helper
# ==========================================
def resolve_project_path(session_id: str) -> Path:
    """Scan projects directory to find the folder corresponding to this session_id."""
    projects_dir = REPO_ROOT / "projects"
    if projects_dir.exists():
        for item in projects_dir.iterdir():
            if item.is_dir() and item.name.startswith(session_id):
                return item
    raise HTTPException(
        status_code=404, 
        detail=f"No initialized project directory found starting with session: {session_id}."
    )

def _safe_svg_path(svg_dir: Path, name: str) -> Optional[Path]:
    if "/" in name or "\\" in name or ".." in name:
        return None
    svg_file = (svg_dir / name).resolve()
    if not str(svg_file).startswith(str(svg_dir.resolve())):
        return None
    return svg_file

# ==========================================
# SVG Helper Constants and Functions
# ==========================================
import logging
import threading
logger = logging.getLogger("app")

_EDIT_LOG_NAME = '.live_edits.jsonl'
_UNSAFE_COLOR_RE = re.compile(r'[;:@\\]|url\s*\(', re.IGNORECASE)
_SAFE_ATTR_NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_.:-]*$')
_MAX_ATTR_VALUE_LEN = 256
_MAX_EDIT_TEXT_LEN = 5000
_ADDABLE_BATCH_ATTRS = frozenset({
    'fill', 'stroke', 'opacity',
    'font-size', 'font-family', 'font-weight', 'text-anchor',
    'x', 'y',
})

def _xml_attr(value: object) -> str:
    """Escape a value for safe insertion into generated preview SVG markup."""
    return html.escape(str(value), quote=True)

def _inline_icons(content: str) -> tuple[str, list[dict]]:
    """Replace <use data-icon="..."/> with rendered <g> for browser preview.

    Returns (rewritten_content, warnings). Each warning is
    ``{"icon": <name>, "reason": <str>}`` so the frontend can surface
    "icon X not found" to the user instead of silently dropping it.
    """
    warnings: list[dict] = []
    matches = list(_USE_ICON_PATTERN.finditer(content))
    if not matches:
        return content, warnings
    new_content = content
    for match in reversed(matches):
        use_str = match.group(0)
        icon_name: str = ''
        try:
            attrs = parse_use_element(use_str)
            icon_name = str(attrs.get('icon') or '')
            if not icon_name:
                warnings.append({'icon': '', 'reason': 'missing data-icon attribute'})
                continue
            icon_path, _ = resolve_icon_path(icon_name, _ICONS_DIR)
            color = str(attrs.get('fill', '#000000'))
            elements, style, base_size = extract_paths_from_icon(icon_path, color)
        except Exception as exc:
            warnings.append({'icon': icon_name, 'reason': f'{type(exc).__name__}: {exc}'})
            logger.warning('icon inline failed: name=%r reason=%s', icon_name, exc)
            continue
        if not elements:
            warnings.append({'icon': icon_name, 'reason': 'no renderable paths in icon'})
            continue
        replacement = generate_icon_group(attrs, elements, style, base_size)
        id_match = re.search(r'\bid="([^"]+)"', use_str)
        if id_match:
            preview_attrs = [
                f'id="{_xml_attr(id_match.group(1))}"',
                f'data-icon="{_xml_attr(icon_name)}"',
            ]
            for key in ('x', 'y', 'width', 'height'):
                if key in attrs:
                    preview_attrs.append(f'data-use-{key}="{_xml_attr(attrs[key])}"')
            if 'transform' in attrs:
                preview_attrs.append('data-use-has-transform="1"')
            replacement = replacement.replace(
                '<g ', f'<g {" ".join(preview_attrs)} ', 1,
            )
        new_content = new_content[:match.start()] + replacement + new_content[match.end():]
    return new_content, warnings

def _is_safe_color(value: str) -> bool:
    return len(value) < _MAX_ATTR_VALUE_LEN and not _UNSAFE_COLOR_RE.search(value)

def _validate_edit_attrs(attrs: dict, existing_attrs: set[str]) -> Optional[str]:
    """Return an error string if any attr/value is disallowed, else None."""
    for key, value in attrs.items():
        if not isinstance(key, str) or not _SAFE_ATTR_NAME_RE.match(key):
            return f'invalid attribute name: {key}'
        if not is_editable_attr(key):
            return f'attribute not editable: {key}'
        if key not in existing_attrs and key != 'transform' and key not in _ADDABLE_BATCH_ATTRS:
            return f'attribute does not exist on element: {key}'
        if value is None:
            if key not in existing_attrs:
                return f'attribute does not exist on element: {key}'
            continue
        if not isinstance(value, str):
            return f'value must be a string: {key}'
        if len(value) > _MAX_ATTR_VALUE_LEN:
            return f'value too long: {key}'
        if key in ('fill', 'stroke', 'color', 'stop-color', 'flood-color', 'lighting-color'):
            if not _is_safe_color(value):
                return f'unsafe color value: {key}'
        if key == 'transform' and re.search(r'nan|inf', value, re.IGNORECASE):
            return f'invalid transform value: {key}'
        if any(c in value for c in '<>"'):
            return f'invalid value: {key}'
        if re.search(r'javascript\s*:|data\s*:|url\s*\(', value, re.IGNORECASE):
            return f'unsafe value: {key}'
    return None

def _append_edit_log(project_path: Path, record: dict) -> None:
    """Append one applied edit record (old→new) to the project's history.

    The on-disk JSONL is the durable trail the user can review to see exactly
    what changed. Un-applied staged edits stay in memory only.
    """
    try:
        with open(project_path / _EDIT_LOG_NAME, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + '\n')
    except OSError as exc:
        logger.warning('edit log append failed: %s', exc)

def _find_by_id(root: ET.Element, element_id: str) -> Optional[ET.Element]:
    for elem in root.iter():
        if elem.get('id') == element_id:
            return elem
    return None

def _apply_edit_record(root: ET.Element, record: dict) -> tuple[bool, Optional[str]]:
    element_id = record.get('element_id')
    if not isinstance(element_id, str):
        return False, 'invalid-record'
    promote = record.get('promote_tspan')
    if promote:
        if not isinstance(promote, dict):
            return False, 'invalid-promote'
        ok, reason = promote_tspan_to_text(
            root,
            element_id,
            str(promote.get('x') or ''),
            str(promote.get('y') or ''),
        )
        if not ok:
            return ok, reason
    if 'text' in record:
        ok, reason = set_text(root, element_id, str(record.get('text') or ''))
        if not ok:
            return ok, reason
    attrs = record.get('attrs')
    if attrs:
        ok, reason = set_attributes(root, element_id, attrs)
        if not ok:
            return ok, reason
    return True, None

def _apply_edit_records(root: ET.Element, records: list[dict]) -> tuple[bool, Optional[str]]:
    for record in records:
        ok, reason = _apply_edit_record(root, record)
        if not ok:
            return ok, reason
    return True, None

def _edit_signature(record: dict) -> tuple:
    """Identity used to coalesce consecutive staged edits.

    Two edits fold together only when they touch the exact same element and the
    exact same field set (text flag + sorted attr keys). 'Nudge fill 5×'
    collapses to one undo step; 'change fill then font-size' stays two.
    """
    attr_keys = tuple(sorted((record.get('attrs') or {}).keys()))
    promote_keys = tuple(sorted((record.get('promote_tspan') or {}).keys()))
    return (record.get('element_id'), 'text' in record, attr_keys, promote_keys)

def _coalesce_into(prev: dict, cur: dict) -> None:
    """Fold cur's new values into prev, keeping prev's original old values.

    Callers guarantee matching signatures, so prev and cur carry the same
    (kind, key) change set; only the 'new' side advances. prev's 'old' is the
    value from before the first edit in the run, which is what undo and the
    edit log should report.
    """
    if 'text' in cur:
        prev['text'] = cur['text']
    if cur.get('attrs'):
        merged = dict(prev.get('attrs') or {})
        merged.update(cur['attrs'])
        prev['attrs'] = merged
    if cur.get('promote_tspan'):
        prev['promote_tspan'] = cur['promote_tspan']
    old_by_field = {(c['kind'], c['key']): c['old'] for c in prev['changes']}
    prev['changes'] = [
        {
            'kind': c['kind'], 'key': c['key'],
            'old': old_by_field.get((c['kind'], c['key']), c['old']),
            'new': c['new'],
        }
        for c in cur['changes']
    ]


# ==========================================
# Tool mapping
# ==========================================
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
# LangGraph Agent State & Setup
# ==========================================
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    step: int

# Initialize LLM & Bind tools
model = ChatOpenAI(
    base_url=API_BASE_URL,
    api_key=API_KEY,
    model=MODEL_NAME,
    temperature=0.1,
)
tools_list = build_tools()
model_with_tools = model.bind_tools(tools_list)

# ==========================================
# Logs Streaming & Task Queue Helpers
# ==========================================
def serialize_message(msg: BaseMessage) -> dict:
    """Format a LangChain Message object into a JSON-compatible dictionary."""
    kind = type(msg).__name__
    role = "user"
    if isinstance(msg, AIMessage):
        role = "assistant"
    elif isinstance(msg, SystemMessage):
        role = "system"
    elif isinstance(msg, ToolMessage):
        role = "tool"
        
    result = {
        "role": role,
        "type": kind,
        "content": getattr(msg, "content", ""),
    }
    
    msg_id = getattr(msg, "id", None)
    if msg_id:
        result["id"] = msg_id
        
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        tc_serialized = []
        for tc in tool_calls:
            tc_serialized.append({
                "name": tc.get("name"),
                "args": tc.get("args"),
                "id": tc.get("id")
            })
        result["tool_calls"] = tc_serialized
    if isinstance(msg, ToolMessage):
        result["name"] = msg.name
        result["tool_call_id"] = msg.tool_call_id
        
    return result

def agent_log(msg: str, config = None):
    """Output log lines both to console and safely queue them to client SSE stream."""
    print(msg)
    if config and "configurable" in config:
        log_queue = config["configurable"].get("log_queue")
        loop = config["configurable"].get("loop")
        if log_queue is not None and loop is not None:
            # Safe queue push from any thread back to asyncio main thread
            loop.call_soon_threadsafe(log_queue.put_nowait, {"type": "log", "content": msg})

# ==========================================
# Loop checks helper
# ==========================================
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

# ==========================================
# Graph Nodes & Router
# ==========================================
def call_model(state: AgentState, config: RunnableConfig = None):
    """Query the local LLM model."""
    step = state.get("step", 1)
    agent_log(f"\n[*] Step {step}: Querying LLM...", config)
    
    messages = state["messages"]
    try:
        response = model_with_tools.invoke(messages, config)
    except Exception as e:
        err_msg = (
            f"[-] Connection Error: {e}\n"
            f"    Please verify that your local LLM server is running at: {API_BASE_URL}\n"
            f"    and that the model '{MODEL_NAME}' is pulled/loaded."
        )
        agent_log(err_msg, config)
        raise e
        
    return {"messages": [response], "step": step + 1}

def get_or_create_session_project_path(session_id: str, format: str = "ppt169") -> Path:
    """Scan projects directory to find the folder corresponding to this session_id.
    If none exists, return the path that will be created.
    """
    projects_dir = REPO_ROOT / "projects"
    if projects_dir.exists():
        for item in projects_dir.iterdir():
            if item.is_dir() and item.name.startswith(session_id):
                return item
    
    date_str = time.strftime("%Y%m%d")
    return projects_dir / f"{session_id}_{format}_{date_str}"

def sanitize_session_paths(args, session_id: str):
    """Recursively traverse arguments and replace any path segments under 'projects/'
    with the correct session-specific project directory name.
    """
    actual_project_path = get_or_create_session_project_path(session_id)
    session_project_dir_name = actual_project_path.name
    
    # Match projects/folder_name or projects\folder_name
    pattern = re.compile(r'projects([/\\])([^/\\]+)')
    
    def replace_match(match):
        separator = match.group(1)
        old_folder = match.group(2)
        # If it already starts with session_id, don't change it
        if old_folder.startswith(session_id):
            return match.group(0)
        return f"projects{separator}{session_project_dir_name}"

    if isinstance(args, dict):
        for k, v in args.items():
            if isinstance(v, str):
                args[k] = pattern.sub(replace_match, v)
            elif isinstance(v, list):
                args[k] = [pattern.sub(replace_match, item) if isinstance(item, str) else sanitize_session_paths(item, session_id) for item in v]
            elif isinstance(v, dict):
                args[k] = sanitize_session_paths(v, session_id)
    elif isinstance(args, list):
        for i, v in enumerate(args):
            if isinstance(v, str):
                args[i] = pattern.sub(replace_match, v)
            elif isinstance(v, list) or isinstance(v, dict):
                args[i] = sanitize_session_paths(v, session_id)
    return args

def call_tools(state: AgentState, config: RunnableConfig = None):
    """Execute requested tool calls using ppt_tools wrappers."""
    messages = state["messages"]
    last_message = messages[-1]
    
    tool_messages = []
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return {"messages": tool_messages}
        
    agent_log(f"[+] Model requested {len(last_message.tool_calls)} tool call(s).", config)
    
    for tool_call in last_message.tool_calls:
        name = tool_call["name"]
        args = tool_call["args"]
        call_id = tool_call["id"]
        
        # Intercept and rewrite arguments to enforce session-based directory isolation
        session_id = None
        if config and "configurable" in config:
            session_id = config["configurable"].get("thread_id")
            
        if session_id:
            if name == "init_project":
                args["project_name"] = session_id
                agent_log(f"[SESSION ENFORCER] Overriding init project name to session: {session_id}", config)
            else:
                args = sanitize_session_paths(args, session_id)
                if "project_path" in args:
                    actual_path = get_or_create_session_project_path(session_id)
                    old_path = args["project_path"]
                    args["project_path"] = str(actual_path).replace("\\", "/")
                    agent_log(f"[SESSION ENFORCER] Overriding project_path from '{old_path}' to '{args['project_path']}'", config)
        
        agent_log(f"\n[TOOL CALL] Executing: {name}", config)
        agent_log(f"            Args: {json.dumps(args, indent=2, ensure_ascii=False)}", config)
        
        # Loop prevention check
        prev_success = check_tool_has_succeeded(messages, name, args)
        if prev_success:
            agent_log(f"[LOOP DETECTED] Tool '{name}' has already succeeded previously.", config)
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
            
            status = "Success" if result.get("success") else "Failed"
            agent_log(f"[TOOL RESULT] Status: {status}", config)
            if not result.get("success"):
                error_msg = result.get('error') or result.get('stderr')
                if not error_msg and result.get('stdout'):
                    stdout = result.get('stdout', '')
                    error_lines = [l for l in stdout.splitlines() if '[ERROR]' in l]
                    error_msg = "\n".join(error_lines) if error_lines else stdout.strip()
                agent_log(f"              Error: {error_msg}", config)
                
            tool_messages.append(ToolMessage(
                content=json.dumps(result, ensure_ascii=False),
                tool_call_id=call_id,
                name=name
            ))
        except Exception as e:
            agent_log(f"[TOOL ERROR] Exception raised: {e}", config)
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

# Compile the LangGraph agent with checkpoint saving for multiround对话
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", call_tools)

workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
workflow.add_edge("tools", "agent")

memory = MemorySaver()
agent_app = workflow.compile(checkpointer=memory)

# ==========================================
# FastAPI Application setup
# ==========================================
app = FastAPI(title="PPT Master Service Portal")

# CORS Settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static mounting of the existing visual editor
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

SYSTEM_PROMPT = (
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

# ==========================================
# HTML Editor Routing Controllers
# ==========================================
@app.get("/")
def index_redirect():
    """UX Redirect: auto-generate UUID session_id on visit."""
    new_session_id = str(uuid.uuid4())
    return RedirectResponse(url=f"/{new_session_id}")

@app.get("/{session_id}")
def serve_editor(session_id: str, response: Response):
    """Sets Cookie mapping path / to session_id and returns React app or fallback index.html."""
    response.set_cookie(key="session_id", value=session_id, path="/")
    
    # Check if compiled React app exists
    react_index = REPO_ROOT / "FunCall" / "FunCall_ui" / "dist" / "index.html"
    if react_index.exists():
        return FileResponse(str(react_index))
        
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Editor index.html not found.")
    return FileResponse(str(index_file))

# ==========================================
# Image / Asset serving based on Cookie Session
# ==========================================
@app.get("/images/{filename}")
def serve_image(filename: str, session_id: str = Cookie(None)):
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id Cookie.")
    project_path = resolve_project_path(session_id)
    images_dir = project_path / "images"
    target_file = (images_dir / filename).resolve()
    if not str(target_file).startswith(str(images_dir.resolve())):
        raise HTTPException(status_code=403, detail="Access denied.")
    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    return FileResponse(str(target_file))

@app.get("/assets/{filename}")
def serve_asset(filename: str, session_id: str = Cookie(None)):
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id Cookie.")
    project_path = resolve_project_path(session_id)
    assets_dir = project_path / "assets"
    target_file = (assets_dir / filename).resolve()
    if not str(target_file).startswith(str(assets_dir.resolve())):
        raise HTTPException(status_code=403, detail="Access denied.")
    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status_code=404, detail="Asset not found.")
    return FileResponse(str(target_file))

# ==========================================
# Editor API Endpoints (Flask Compatibility)
# ==========================================
@app.get("/api/config")
def get_config():
    return {"live": True}

@app.get("/api/slides")
def get_slides(session_id: str = Cookie(None)):
    if not session_id:
        return {"slides": []}
    try:
        project_path = resolve_project_path(session_id)
    except HTTPException:
        return {"slides": []}
    
    svg_dir = project_path / "svg_output"
    if not svg_dir.exists():
        return {"slides": []}
        
    slides = []
    annotations = session_annotations.setdefault(session_id, {})
    for svg_file in sorted(svg_dir.glob("*.svg")):
        path_str = str(svg_file)
        try:
            mtime = svg_file.stat().st_mtime
        except OSError:
            continue
            
        ok = True
        error_msg = None
        disk_count = 0
        try:
            tree = ET.parse(path_str)
            disk_count = len(parse_annotations(tree.getroot()))
        except ET.ParseError as exc:
            ok = False
            error_msg = f"XML parse error: {exc}"
            
        mem_count = len(annotations.get(svg_file.name, {}))
        annotation_count = max(disk_count, mem_count)
        
        slides.append({
            "name": svg_file.name,
            "annotated": annotation_count > 0,
            "annotation_count": annotation_count,
            "ok": ok,
            "error": error_msg,
            "mtime": mtime
        })
    return {"slides": slides}

@app.get("/api/slide/{name}")
def get_slide(name: str, session_id: str = Cookie(None)):
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id Cookie.")
    project_path = resolve_project_path(session_id)
    svg_dir = project_path / "svg_output"
    
    svg_file = _safe_svg_path(svg_dir, name)
    if svg_file is None:
        raise HTTPException(status_code=400, detail="Invalid slide name")
    if not svg_file.exists():
        raise HTTPException(status_code=404, detail="Slide not found")
        
    try:
        mtime = svg_file.stat().st_mtime
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to stat SVG: {exc}")
        
    pending_edits = session_pending_edits.setdefault(session_id, {}).get(name) or []
    
    try:
        tree = ET.parse(str(svg_file))
        root = tree.getroot()
    except ET.ParseError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse SVG: {exc}")
        
    assign_temp_ids(root)
    if pending_edits:
        ok, reason = _apply_edit_records(root, pending_edits)
        if not ok:
            raise HTTPException(status_code=500, detail=f"Failed to apply pending edits: {reason}")
            
    disk_annotations = parse_annotations(root)
    id_to_tag = {}
    for elem in root.iter():
        eid = elem.get("id")
        if eid:
            tag = elem.tag
            if "}" in tag:
                tag = tag.split("}", 1)[1]
            id_to_tag[eid] = tag
            
    content = ET.tostring(root, encoding="unicode", xml_declaration=False)
    content, warnings = _inline_icons(content)
    
    mem_annotations = session_annotations.setdefault(session_id, {}).get(name, {})
    merged = {}
    for ann in disk_annotations:
        merged[ann["element_id"]] = ann["annotation"]
    merged.update(mem_annotations)
    
    annotations_list = [
        {
            "element_id": eid,
            "tag": id_to_tag.get(eid, ""),
            "annotation": ann_text
        }
        for eid, ann_text in merged.items()
    ]
    
    return {
        "name": name,
        "content": content,
        "annotations": annotations_list,
        "warnings": warnings,
        "mtime": mtime,
        "undo_depth": len(pending_edits)
    }

@app.post("/api/slide/{name}/annotate")
def post_annotate(name: str, request_data: dict, session_id: str = Cookie(None)):
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id Cookie.")
    element_id = request_data.get("element_id")
    annotation = request_data.get("annotation")
    
    if element_id is None or annotation is None:
        raise HTTPException(status_code=400, detail="Missing element_id or annotation")
    if not isinstance(element_id, str) or not isinstance(annotation, str):
        raise HTTPException(status_code=400, detail="element_id and annotation must be strings")
    if len(element_id) > 200:
        raise HTTPException(status_code=400, detail="element_id too long")
    if len(annotation) > 10000:
        raise HTTPException(status_code=400, detail="annotation too long")
        
    annotations = session_annotations.setdefault(session_id, {})
    slide_anns = annotations.setdefault(name, {})
    slide_anns[element_id] = annotation
    return {"status": "ok", "annotations_count": len(slide_anns)}

@app.delete("/api/slide/{name}/annotate/{element_id}")
def delete_annotate(name: str, element_id: str, session_id: str = Cookie(None)):
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id Cookie.")
    annotations = session_annotations.setdefault(session_id, {})
    slide_anns = annotations.setdefault(name, {})
    if element_id in slide_anns:
        del slide_anns[element_id]
    return {"status": "ok", "annotations_count": len(slide_anns)}

@app.post("/api/slide/{name}/edit")
def post_edit(name: str, request_data: dict, session_id: str = Cookie(None)):
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id Cookie.")
    project_path = resolve_project_path(session_id)
    svg_dir = project_path / "svg_output"
    
    svg_file = _safe_svg_path(svg_dir, name)
    if svg_file is None:
        raise HTTPException(status_code=400, detail="Invalid slide name")
    if not svg_file.exists():
        raise HTTPException(status_code=404, detail="Slide not found")
        
    element_id = request_data.get("element_id")
    if not isinstance(element_id, str) or not element_id or len(element_id) > 200:
        raise HTTPException(status_code=400, detail="Missing or invalid element_id")
        
    new_text = request_data.get("text")
    attrs = request_data.get("attrs")
    promote = request_data.get("promote_tspan")
    
    if new_text is None and not attrs and not promote:
        raise HTTPException(status_code=400, detail="Nothing to edit (no text or attrs)")
        
    if new_text is not None:
        if not isinstance(new_text, str) or len(new_text) > _MAX_EDIT_TEXT_LEN:
            raise HTTPException(status_code=400, detail="Invalid or too-long text")
    if attrs is not None:
        if not isinstance(attrs, dict):
            raise HTTPException(status_code=400, detail="attrs must be an object")
    if promote is not None:
        if not isinstance(promote, dict):
            raise HTTPException(status_code=400, detail="promote_tspan must be an object")
        for key in ('x', 'y'):
            value = promote.get(key)
            if not isinstance(value, str) or not re.fullmatch(r'-?\d+(?:\.\d+)?', value):
                raise HTTPException(status_code=400, detail=f"invalid promote_tspan.{key}")
                
    try:
        tree = ET.parse(str(svg_file))
        root = tree.getroot()
    except ET.ParseError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse SVG: {exc}")
        
    assign_temp_ids(root)
    pending = session_pending_edits.setdefault(session_id, {}).setdefault(name, [])
    ok, reason = _apply_edit_records(root, pending)
    if not ok:
        raise HTTPException(status_code=500, detail=f"Failed to replay pending edits: {reason}")
        
    target = _find_by_id(root, element_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Element not found")
    if attrs is not None:
        attr_err = _validate_edit_attrs(attrs, set(target.attrib.keys()))
        if attr_err:
            raise HTTPException(status_code=400, detail=attr_err)
            
    changes = []
    staged = {"element_id": element_id}
    if new_text is not None:
        old_text = target.text or ''
        ok, reason = set_text(root, element_id, new_text)
        if not ok:
            raise HTTPException(status_code=404 if reason == 'not-found' else 400, detail=f"Text edit failed: {reason}")
        changes.append({"kind": "text", "key": None, "old": old_text, "new": new_text})
        staged["text"] = new_text
    if attrs:
        old_attrs = {k: target.get(k) for k in attrs}
        ok, reason = set_attributes(root, element_id, attrs)
        if not ok:
            raise HTTPException(status_code=404 if reason == 'not-found' else 400, detail=f"Attribute edit failed: {reason}")
        for k, v in attrs.items():
            changes.append({"kind": "attr", "key": k, "old": old_attrs[k], "new": v})
        staged["attrs"] = attrs
    if promote:
        tag = target.tag.split("}", 1)[1] if "}" in target.tag else target.tag
        old_state = {
            "tag": tag,
            "x": target.get("x"),
            "y": target.get("y"),
            "dy": target.get("dy"),
            "transform": target.get("transform"),
        }
        ok, reason = promote_tspan_to_text(root, element_id, promote["x"], promote["y"])
        if not ok:
            raise HTTPException(status_code=404 if reason == 'not-found' else 400, detail=f"Tspan promotion failed: {reason}")
        changes.append({
            "kind": "structure",
            "key": "promote-tspan",
            "old": old_state,
            "new": {"tag": "text", "x": promote["x"], "y": promote["y"]}
        })
        staged["promote_tspan"] = promote
        
    staged["changes"] = changes
    if pending and _edit_signature(pending[-1]) == _edit_signature(staged):
        _coalesce_into(pending[-1], staged)
    else:
        pending.append(staged)
    return {"status": "ok", "undo_depth": len(pending)}

@app.post("/api/slide/{name}/undo")
def post_undo(name: str, session_id: str = Cookie(None)):
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id Cookie.")
    stack = session_pending_edits.setdefault(session_id, {}).get(name) or []
    if not stack:
        return {"status": "empty", "undo_depth": 0}
    stack.pop()
    return {"status": "ok", "undo_depth": len(stack)}

@app.post("/api/save-all")
def save_all(session_id: str = Cookie(None)):
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id Cookie.")
    project_path = resolve_project_path(session_id)
    svg_dir = project_path / "svg_output"
    
    annotations = session_annotations.setdefault(session_id, {})
    pending_edits = session_pending_edits.setdefault(session_id, {})
    
    filenames = sorted(set(annotations.keys()) | set(pending_edits.keys()))
    modified = []
    
    for filename in filenames:
        anns = annotations.get(filename, {})
        edits = pending_edits.get(filename, [])
        
        svg_file = _safe_svg_path(svg_dir, filename)
        if svg_file is None or not svg_file.exists():
            continue
            
        try:
            tree = ET.parse(str(svg_file))
            root = tree.getroot()
        except ET.ParseError:
            continue
            
        assign_temp_ids(root)
        ok, reason = _apply_edit_records(root, edits)
        if not ok:
            raise HTTPException(status_code=400, detail=f"Failed to apply edits in {filename}: {reason}")
            
        # Clear existing annotations
        for elem in root.iter():
            elem.attrib.pop('data-edit-target', None)
            elem.attrib.pop('data-edit-annotation', None)
            
        # Set new annotations
        for element_id, annotation_text in anns.items():
            set_annotation(root, element_id, annotation_text)
            
        # Strip unused transient ids
        annotated_ids = set(anns.keys())
        strip_unused_temp_ids(root, annotated_ids)
        
        # Write back to disk
        tree.write(str(svg_file), encoding='UTF-8', xml_declaration=True)
        
        # Append to log
        ts = time.time()
        for edit in edits:
            for chg in edit.get('changes', []):
                _append_edit_log(project_path, {
                    'ts': ts, 'file': filename, 'element_id': edit.get('element_id'),
                    'action': 'edit', 'kind': chg.get('kind'), 'key': chg.get('key'),
                    'old': chg.get('old'), 'new': chg.get('new'),
                })
        modified.append(filename)
        
    # Clear session cache
    session_annotations[session_id] = {}
    session_pending_edits[session_id] = {}
    
    return {"status": "ok", "files_modified": modified}

@app.post("/api/shutdown")
def shutdown():
    return {"status": "ok"}

# ==========================================
# Project HTTP Control APIs
# ==========================================
@app.post("/api/projects/init")
def init_project(request_data: dict, response: Response):
    """Initializes a new project based on session_id and drops Cookie."""
    session_id = request_data.get("session_id")
    format = request_data.get("format", "ppt169")
    
    if not session_id:
        session_id = str(uuid.uuid4())
        
    res = ppt_tools.init_project(project_name=session_id, format=format)
    if res.get("success"):
        response.set_cookie(key="session_id", value=session_id, path="/")
        return {
            "success": True,
            "session_id": session_id,
            "project_path": res.get("project_path"),
            "message": "Project initialized successfully."
        }
    else:
        raise HTTPException(status_code=500, detail=res.get("error") or res.get("stderr"))

@app.post("/api/projects/import")
def import_file(file: UploadFile = File(...), session_id: str = Cookie(None)):
    """Receives file upload temporarily and imports it into the session project."""
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id Cookie.")
    project_path = resolve_project_path(session_id)
    
    temp_dir = Path("temp_uploads")
    temp_dir.mkdir(exist_ok=True)
    temp_file_path = temp_dir / file.filename
    
    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        res = ppt_tools.import_sources(
            project_path=str(project_path),
            source_files=[str(temp_file_path)],
            move=True
        )
        if not res.get("success"):
            raise HTTPException(status_code=500, detail=res.get("error") or res.get("stderr"))
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_file_path.exists():
            temp_file_path.unlink()

@app.post("/api/projects/export")
def export_pptx(request_data: dict, session_id: str = Cookie(None)):
    """Export finalized slides to native PPTX presentation."""
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id Cookie.")
    project_path = resolve_project_path(session_id)
    
    transition = request_data.get("transition", "fade")
    animation = request_data.get("animation", "auto")
    no_merge = request_data.get("no_merge", False)
    
    # Run finalize_svg_files and export_to_pptx sequentially
    try:
        # Step 1: Finalize SVGs
        fin_res = ppt_tools.finalize_svg_files(project_path=str(project_path))
        if not fin_res.get("success"):
            raise HTTPException(status_code=500, detail=f"SVG Finalize failed: {fin_res.get('error') or fin_res.get('stderr')}")
            
        # Step 2: Split speaker notes
        split_res = ppt_tools.split_speaker_notes(project_path=str(project_path))
        
        # Step 3: Export PPTX
        exp_res = ppt_tools.export_to_pptx(
            project_path=str(project_path),
            transition=transition,
            animation=animation,
            no_merge=no_merge
        )
        return exp_res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects/download")
def download_deck(session_id: str = Cookie(None)):
    """Finds and downloads the latest exported pptx file."""
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id Cookie.")
    project_path = resolve_project_path(session_id)
    exports_dir = project_path / "exports"
    if not exports_dir.exists():
        raise HTTPException(status_code=404, detail="No exports folder found.")
        
    pptx_files = sorted(exports_dir.glob("*.pptx"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not pptx_files:
        raise HTTPException(status_code=404, detail="No exported PPTX file found.")
        
    return FileResponse(
        str(pptx_files[0]), 
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=pptx_files[0].name
    )

# ==========================================
# LangGraph Agent SSE Streaming Runner API
# ==========================================
@app.get("/api/agent/history")
def get_agent_history(session_id: str = Cookie(None)):
    """Retrieves current chat history for the active session from checkpointer."""
    if not session_id:
        return {"messages": []}
    
    config = {
        "configurable": {
            "thread_id": session_id
        }
    }
    
    try:
        state = agent_app.get_state(config)
    except Exception as e:
        return {"messages": []}
        
    if not state.values or not state.values.get("messages"):
        return {"messages": []}
        
    messages = state.values.get("messages", [])
    serialized_messages = [serialize_message(msg) for msg in messages]
    return {"messages": serialized_messages}

@app.post("/api/agent/run")
async def run_agent(request_data: dict, session_id: str = Cookie(None)):
    """Runs the LangGraph agent, streaming updates in line-delimited NDJSON."""
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id Cookie.")
    prompt = request_data.get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="Missing prompt in request body.")
        
    config = {
        "configurable": {
            "thread_id": session_id,
        },
        "recursion_limit": 50
    }
    
    # Determine initial input
    state = agent_app.get_state(config)
    if not state.values or not state.values.get("messages"):
        initial_input = {
            "messages": [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=prompt)
            ],
            "step": 1
        }
    else:
        # Update the existing SystemMessage to the latest SYSTEM_PROMPT so that historical sessions get new tools/rules
        messages = list(state.values["messages"])
        if messages and isinstance(messages[0], SystemMessage):
            msg_id = getattr(messages[0], "id", None)
            if msg_id:
                try:
                    agent_app.update_state(config, {"messages": [SystemMessage(content=SYSTEM_PROMPT, id=msg_id)]})
                except Exception as e:
                    logger.warning("Failed to update system prompt in historical state: %s", e)
        initial_input = {
            "messages": [
                HumanMessage(content=prompt)
            ]
        }
        
    async def ndjson_generator():
        try:
            async for event in agent_app.astream(initial_input, config=config, stream_mode="updates"):
                formatted_event = {
                    "session_id": session_id
                }
                for node_name, update in event.items():
                    msgs = update.get("messages", [])
                    serialized_msgs = [serialize_message(msg) for msg in msgs]
                    formatted_event[node_name] = {"messages": serialized_msgs}
                
                yield json.dumps(formatted_event, ensure_ascii=False) + "\n"
        except Exception as e:
            logger.exception("Error during agent execution: %s", e)
            yield json.dumps({"error": str(e)}, ensure_ascii=False) + "\n"
            
    return StreamingResponse(ndjson_generator(), media_type="application/x-ndjson")
