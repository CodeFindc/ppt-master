# -*- coding: utf-8 -*-
"""
PPT Master - Function Calling Wrappers
This module wraps the scripts under `skills/ppt-master/scripts/` into structured Python
functions to enable step-by-step pipeline execution via Function Calling.
"""

import os
import sys
import shutil
import subprocess
import time
import json
import urllib.parse
from pathlib import Path

# Resolve paths dynamically
REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / 'skills' / 'ppt-master'
SCRIPTS_DIR = SKILLS_DIR / 'scripts'

def normalize_path(path_str: str) -> str:
    """Normalize file paths, stripping file:/// URIs and unquoting URL encodings."""
    if not isinstance(path_str, str) or not path_str:
        return path_str
    
    # Check for file:/// or file:// URIs
    if path_str.startswith("file:///"):
        if sys.platform == 'win32':
            path_str = path_str[8:]  # file:///C:/... -> C:/...
        else:
            path_str = path_str[7:]  # file:///... -> /...
    elif path_str.startswith("file://"):
        path_str = path_str[7:]
        
    # Unquote URL-encoded characters (like %20 -> space)
    path_str = urllib.parse.unquote(path_str)
    
    # Return a clean resolved absolute path string
    try:
        return str(Path(path_str).resolve())
    except Exception:
        # Fallback to simple path resolution if resolve fails
        return os.path.abspath(path_str)

def get_env():
    """Build environment dictionary with PYTHONPATH set correctly."""
    env = os.environ.copy()
    python_path = [str(SCRIPTS_DIR)]
    if "PYTHONPATH" in env:
        python_path.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(python_path)
    return env

def run_script(script_relative_path: str, args: list) -> dict:
    """Helper to run a python script in the repository using subprocess."""
    script_path = SCRIPTS_DIR / script_relative_path
    if not script_path.exists():
        return {
            "success": False,
            "error": f"Script not found at: {script_path}",
            "stdout": "",
            "stderr": ""
        }
    
    cmd = [sys.executable, str(script_path)] + [str(a) for a in args]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=get_env()
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "stdout": "",
            "stderr": ""
        }

# ==========================================
# 1. Source Conversion
# ==========================================
def convert_source_to_markdown(input_path: str, output_path: str = None) -> dict:
    """
    Converts a source document (PDF, DOCX, XLSX, PPTX, TXT) or a URL to Markdown.
    
    Parameters:
    - input_path: Absolute path to the source file or a web URL.
    - output_path: Optional path for the output Markdown file. If omitted, it will be placed next to the input.
    """
    is_url = input_path.startswith("http://") or input_path.startswith("https://")
    
    if is_url:
        args = [input_path]
        if output_path:
            args.extend(["-o", output_path])
        return run_script("source_to_md/web_to_md.py", args)
        
    input_path = normalize_path(input_path)
    if output_path:
        output_path = normalize_path(output_path)
        
    path_obj = Path(input_path)
    if not path_obj.exists():
        return {
            "success": False,
            "error": f"Source file does not exist: {input_path}"
        }
        
    suffix = path_obj.suffix.lower()
    
    # If the file is already a markdown file, return success directly
    if suffix in {".md", ".markdown"}:
        return {
            "success": True,
            "stdout": f"[OK] File is already in Markdown format: {input_path}",
            "stderr": "",
            "markdown_path": str(input_path),
            "message": "File is already in Markdown format. No conversion needed."
        }
        
    script_map = {
        ".pdf": "source_to_md/pdf_to_md.py",
        ".docx": "source_to_md/doc_to_md.py",
        ".doc": "source_to_md/doc_to_md.py",
        ".xlsx": "source_to_md/excel_to_md.py",
        ".xlsm": "source_to_md/excel_to_md.py",
        ".pptx": "source_to_md/ppt_to_md.py",
        ".ppt": "source_to_md/ppt_to_md.py",
        ".txt": "source_to_md/doc_to_md.py",
        ".html": "source_to_md/doc_to_md.py",
        ".epub": "source_to_md/doc_to_md.py",
    }
    
    script = script_map.get(suffix)
    if not script:
        # Fall back to doc_to_md for other text formats
        script = "source_to_md/doc_to_md.py"
        
    args = [input_path]
    if output_path:
        args.extend(["-o", output_path])
        
    return run_script(script, args)

# ==========================================
# 2. Project Init & Import
# ==========================================
def init_project(project_name: str, format: str = "ppt169") -> dict:
    """
    Initializes a new project directory structure.
    
    Parameters:
    - project_name: Name of the project.
    - format: Canvas format. Options: ppt169 (16:9), ppt43 (4:3), xhs (xiaohongshu), story. Default: ppt169.
    """
    # Check if the project directory already exists to make this tool idempotent
    date_str = time.strftime("%Y%m%d")
    folder_name = f"{project_name}_{format}_{date_str}"
    project_path = str(REPO_ROOT / "projects" / folder_name)
    if os.path.exists(project_path):
        return {
            "success": True,
            "returncode": 0,
            "stdout": f"[OK] Project already exists: {project_path}",
            "stderr": "",
            "project_path": project_path,
            "message": "Project directory already exists and is ready to use. Do not initialize again. Proceed to import_sources or writing the design spec."
        }

    args = ["init", project_name, "--format", format]
    result = run_script("project_manager.py", args)
    
    if result["success"]:
        # Parse output to find project path
        # Example output: "Project created: <path>"
        lines = result["stdout"].splitlines()
        project_path = None
        for line in lines:
            if "Project created:" in line:
                project_path = line.split("Project created:")[-1].strip()
                break
        
        if not project_path:
            # Fallback to look up in local projects folder
            date_str = time.strftime("%Y%m%d")
            # The project folder name format: <name>_<format>_<date>
            # (matches project_manager.py logic)
            folder_name = f"{project_name}_{format}_{date_str}"
            project_path = str(REPO_ROOT / "projects" / folder_name)
            
        result["project_path"] = project_path
        
    return result

def import_sources(project_path: str, source_files: list, move: bool = True) -> dict:
    """
    Imports converted Markdown and other source materials into the project directory.
    
    Parameters:
    - project_path: Path to the initialized project directory.
    - source_files: List of file paths or URLs to import.
    - move: If True, moves the files into the project. If False, copies them. Default: True.
    """
    project_path = normalize_path(project_path)
    source_files = [normalize_path(f) for f in source_files]
    
    args = ["import-sources", project_path] + source_files
    if move:
        args.append("--move")
    else:
        args.append("--copy")
        
    return run_script("project_manager.py", args)

# ==========================================
# 3. Template Application
# ==========================================
def apply_template(project_path: str, template_paths: list) -> dict:
    """
    Applies layout, brand, or deck templates to the project templates directory.
    If multiple template paths are provided, they will be copied sequentially.
    
    Parameters:
    - project_path: Path to the project directory.
    - template_paths: List of absolute paths to template directories.
    """
    project_path = normalize_path(project_path)
    template_paths = [normalize_path(p) for p in template_paths]
    
    proj_path_obj = Path(project_path)
    if not proj_path_obj.exists():
        return {
            "success": False,
            "error": f"Project directory not found: {project_path}"
        }
        
    dest_dir = proj_path_obj / "templates"
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    copied = []
    errors = []
    
    for t_path in template_paths:
        t_path_obj = Path(t_path)
        if not t_path_obj.exists() or not t_path_obj.is_dir():
            errors.append(f"Template path not found or not a directory: {t_path}")
            continue
            
        try:
            # Copy all files from template directory to project templates
            for item in t_path_obj.iterdir():
                dest_item = dest_dir / item.name
                if item.is_dir():
                    if dest_item.exists():
                        shutil.rmtree(dest_item)
                    shutil.copytree(item, dest_item)
                else:
                    shutil.copy2(item, dest_item)
            copied.append(t_path)
        except Exception as e:
            errors.append(f"Failed to copy template {t_path}: {e}")
            
    if errors and not copied:
        return {
            "success": False,
            "error": "; ".join(errors)
        }
        
    return {
        "success": True,
        "message": f"Successfully applied templates: {copied}",
        "errors": errors if errors else None
    }

# ==========================================
# 4. Image Processing & LaTeX
# ==========================================
def analyze_images(project_path: str) -> dict:
    """
    Runs analysis on images in the project directory.
    
    Parameters:
    - project_path: Path to the project directory.
    """
    project_path = normalize_path(project_path)
    images_dir = Path(project_path) / "images"
    if not images_dir.exists():
        return {
            "success": False,
            "error": f"Images directory not found in project: {images_dir}"
        }
    return run_script("analyze_images.py", [str(images_dir)])

def render_latex(project_path: str, manifest_path: str = None, dpi: int = 300, providers: str = None) -> dict:
    """
    Renders LaTeX formula manifest to transparent PNG assets.
    
    Parameters:
    - project_path: Path to the project directory.
    - manifest_path: Optional manifest path. Defaults to <project_path>/images/formula_manifest.json.
    - dpi: Render DPI (default: 300).
    - providers: Comma-separated provider fallback chain (e.g. "codecogs,quicklatex,mathpad,wikimedia").
    """
    project_path = normalize_path(project_path)
    if manifest_path:
        manifest_path = normalize_path(manifest_path)
        
    args = [project_path, "--dpi", str(dpi)]
    if manifest_path:
        args.extend(["--manifest", manifest_path])
    if providers:
        args.extend(["--providers", providers])
        
    return run_script("latex_render.py", args)

def generate_images(project_path: str, manifest_path: str = None, render_md: bool = True) -> dict:
    """
    Generates AI images from the project manifest file.
    
    Parameters:
    - project_path: Path to the project directory.
    - manifest_path: Optional manifest path. Defaults to <project_path>/images/image_prompts.json.
    - render_md: Whether to also render the markdown preview sidecar. Default: True.
    """
    project_path = normalize_path(project_path)
    if manifest_path:
        manifest_path = normalize_path(manifest_path)
        
    proj_path_obj = Path(project_path)
    manifest = manifest_path if manifest_path else str(proj_path_obj / "images" / "image_prompts.json")
    
    if not Path(manifest).exists():
        return {
            "success": False,
            "error": f"Image prompts manifest not found: {manifest}"
        }
        
    # Step 1: Run image generation
    res = run_script("image_gen.py", ["--manifest", manifest])
    
    # Step 2: Render markdown preview if requested
    if render_md:
        run_script("image_gen.py", ["--render-md", manifest])
        
    return res

# ==========================================
# 5. Live Preview Server
# ==========================================
def pid_exists(pid: int) -> bool:
    """Checks whether a process with the given PID exists (without external dependencies)."""
    if sys.platform == 'win32':
        import ctypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_INFORMATION = 0x0400
        handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    else:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        else:
            return True

def start_preview_server(project_path: str, port: int = 5050, no_browser: bool = False) -> dict:
    """
    Launches the live browser editor in live preview mode as a background process.
    
    Parameters:
    - project_path: Path to the project directory.
    - port: Port to listen on (default: 5050).
    - no_browser: If True, do not auto-open the browser.
    """
    project_path = normalize_path(project_path)
    project_path_obj = Path(project_path).resolve()
    lock_file = project_path_obj / '.live_preview.lock'
    
    # Check if already running
    if lock_file.exists():
        try:
            lock_data = json.loads(lock_file.read_text(encoding='utf-8'))
            pid = lock_data.get('pid')
            running_port = lock_data.get('port')
            if pid and pid_exists(pid):
                return {
                    "success": True,
                    "message": "Preview server is already running for this project.",
                    "url": f"http://127.0.0.1:{running_port}",
                    "pid": pid,
                    "port": running_port,
                    "already_running": True
                }
        except Exception:
            # Stale lock, proceed to launch
            pass

    script_path = SCRIPTS_DIR / 'svg_editor' / 'server.py'
    if not script_path.exists():
        return {
            "success": False,
            "error": f"Preview server script not found: {script_path}"
        }

    cmd = [sys.executable, str(script_path), str(project_path_obj), "--live", "--port", str(port)]
    if no_browser:
        cmd.append("--no-browser")
        
    try:
        creationflags = 0
        if sys.platform == 'win32':
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            
        # Write output logs to project directory
        log_file_path = project_path_obj / '.live_preview_server.log'
        log_file = open(log_file_path, 'w', encoding='utf-8')
        
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            stdout=log_file,
            stderr=log_file,
            creationflags=creationflags,
            env=get_env()
        )
        
        # Let the server bind the port
        time.sleep(1.5)
        
        return {
            "success": True,
            "message": f"Started preview server in background. Logs are written to {log_file_path.name}",
            "url": f"http://127.0.0.1:{port}",
            "pid": proc.pid,
            "port": port,
            "already_running": False
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to start preview server: {e}"
        }

# ==========================================
# 6. Quality Checks & Post-processing
# ==========================================
def check_annotations(project_path: str) -> dict:
    """
    Scans the project SVG files for user-submitted edit annotations.
    
    Parameters:
    - project_path: Path to the project directory.
    """
    project_path = normalize_path(project_path)
    return run_script("check_annotations.py", [project_path])

def check_svg_quality(project_path: str) -> dict:
    """
    Checks the quality of the generated SVG files.
    
    Parameters:
    - project_path: Path to the project directory.
    """
    project_path = normalize_path(project_path)
    return run_script("svg_quality_checker.py", [project_path])

def split_speaker_notes(project_path: str) -> dict:
    """
    Splits the speaker notes total.md file into separate files per slide.
    
    Parameters:
    - project_path: Path to the project directory.
    """
    project_path = normalize_path(project_path)
    return run_script("total_md_split.py", [project_path])

def finalize_svg_files(project_path: str, compress: bool = False, max_dimension: int = None) -> dict:
    """
    Runs SVG post-processing (embeddings, icons, text flattening, rounded rect conversions).
    
    Parameters:
    - project_path: Path to the project directory.
    - compress: If True, compresses images before embedding.
    - max_dimension: Downscale images exceeding this dimension on either axis.
    """
    project_path = normalize_path(project_path)
    args = [project_path]
    if compress:
        args.append("--compress")
    if max_dimension:
        args.extend(["--max-dimension", str(max_dimension)])
        
    return run_script("finalize_svg.py", args)

def export_to_pptx(project_path: str, transition: str = "fade", animation: str = "auto", 
                   animation_trigger: str = "after-previous", no_merge: bool = False, 
                   svg_snapshot: bool = False) -> dict:
    """
    Converts and exports the finalized SVGs into native PPTX presentations.
    
    Parameters:
    - project_path: Path to the project directory.
    - transition: Slide transitions (e.g. fade, push, wipe, split, strips, cover, random, none). Default: fade.
    - animation: Per-element entrance animations (e.g. auto, mixed, fade, none). Default: auto.
    - animation_trigger: Animation start trigger (on-click, with-previous, after-previous). Default: after-previous.
    - no_merge: If True, disables paragraph merging and keeps strict line-layout fidelity. Default: False.
    - svg_snapshot: If True, additionally exports the SVG snapshot pptx. Default: False.
    """
    project_path = normalize_path(project_path)
    args = [
        project_path,
        "-t", transition,
        "-a", animation,
        "--animation-trigger", animation_trigger
    ]
    if no_merge:
        args.append("--no-merge")
    if svg_snapshot:
        args.append("--svg-snapshot")
        
    return run_script("svg_to_pptx.py", args)

def validate_project(project_path: str) -> dict:
    """
    Validates structural integrity of a project directory.
    
    Parameters:
    - project_path: Path to the project directory.
    """
    project_path = normalize_path(project_path)
    return run_script("project_manager.py", ["validate", project_path])

# ==========================================
# 7. File Writing Helpers (Agent Outputs)
# ==========================================
def save_design_spec(project_path: str, content: str) -> dict:
    """
    Saves the Design Specification (design_spec.md) to the project root.
    
    Parameters:
    - project_path: Path to the project directory.
    - content: Markdown text content of the design specification.
    """
    try:
        project_path = normalize_path(project_path)
        dest_file = Path(project_path) / "design_spec.md"
        dest_file.write_text(content, encoding="utf-8")
        return {
            "success": True,
            "message": f"Successfully saved design specification to {dest_file}",
            "file_path": str(dest_file)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def save_spec_lock(project_path: str, content: str) -> dict:
    """
    Saves the Execution Contract (spec_lock.md) to the project root.
    
    Parameters:
    - project_path: Path to the project directory.
    - content: Markdown text content of the execution spec lock.
    """
    try:
        project_path = normalize_path(project_path)
        dest_file = Path(project_path) / "spec_lock.md"
        dest_file.write_text(content, encoding="utf-8")
        return {
            "success": True,
            "message": f"Successfully saved execution lock (spec_lock.md) to {dest_file}",
            "file_path": str(dest_file)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def save_svg_page(project_path: str, filename: str, content: str) -> dict:
    """
    Saves a generated SVG page to the svg_output directory.
    
    Parameters:
    - project_path: Path to the project directory.
    - filename: Filename for the SVG slide (e.g. "01_cover.svg" or "02_why_it_matters.svg").
    - content: SVG/XML text content of the page.
    """
    try:
        project_path = normalize_path(project_path)
        svg_dir = Path(project_path) / "svg_output"
        svg_dir.mkdir(parents=True, exist_ok=True)
        
        # Validate filename to prevent path traversal
        if "/" in filename or "\\" in filename or ".." in filename:
            raise ValueError("Filename cannot contain directory separators or path traversals.")
            
        # Automatically escape raw ampersands to prevent XML parse errors
        import re
        content = re.sub(r'&(?!(amp|lt|gt|quot|apos|#[0-9]+|#x[0-9a-fA-F]+);)', '&amp;', content)
            
        dest_file = svg_dir / filename
        dest_file.write_text(content, encoding="utf-8")
        return {
            "success": True,
            "message": f"Successfully saved SVG slide to {dest_file}",
            "file_path": str(dest_file)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def save_speaker_notes(project_path: str, content: str) -> dict:
    """
    Saves the master speaker notes (notes/total.md) to the project directory.
    
    Parameters:
    - project_path: Path to the project directory.
    - content: Markdown text content of the speaker notes.
    """
    try:
        project_path = normalize_path(project_path)
        notes_dir = Path(project_path) / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)
        
        dest_file = notes_dir / "total.md"
        dest_file.write_text(content, encoding="utf-8")
        return {
            "success": True,
            "message": f"Successfully saved speaker notes to {dest_file}",
            "file_path": str(dest_file)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def read_file(file_path: str) -> dict:
    """
    Reads the text contents of a file in the project or repository.
    
    Parameters:
    - file_path: Absolute or relative path to the file.
    """
    try:
        norm_path = normalize_path(file_path)
        path_obj = Path(norm_path)
        if not path_obj.exists():
            return {"success": False, "error": f"File does not exist: {file_path}"}
        if not path_obj.is_file():
            return {"success": False, "error": f"Path is a directory, not a file: {file_path}"}
            
        content = path_obj.read_text(encoding="utf-8", errors="replace")
        return {
            "success": True,
            "content": content,
            "file_path": str(path_obj)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def list_dir(dir_path: str) -> dict:
    """
    Lists files and directories under a specified directory path.
    
    Parameters:
    - dir_path: Absolute or relative path to the directory.
    """
    try:
        norm_path = normalize_path(dir_path)
        path_obj = Path(norm_path)
        if not path_obj.exists():
            return {"success": False, "error": f"Directory does not exist: {dir_path}"}
        if not path_obj.is_dir():
            return {"success": False, "error": f"Path is a file, not a directory: {dir_path}"}
            
        items = []
        for item in path_obj.iterdir():
            items.append({
                "name": item.name,
                "is_dir": item.is_dir(),
                "size_bytes": item.stat().st_size if item.is_file() else None
            })
        return {
            "success": True,
            "items": items,
            "directory_path": str(path_obj)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
