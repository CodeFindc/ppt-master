# -*- coding: utf-8 -*-
"""
PPT Master - Pipeline Runner CLI
A utility script to run the ppt-master pipeline steps sequentially using the Function Calling wrappers.
Useful for testing, debugging, and executing without a live LLM in offline LAN environments.
"""

import os
import sys
import argparse
from pathlib import Path

# Add parent directory to sys.path so we can import ppt_tools
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ppt_tools

def handle_convert(args):
    print(f"[*] Converting source content: {args.input}...")
    res = ppt_tools.convert_source_to_markdown(args.input, args.output)
    if res["success"]:
        print("[+] Conversion successful!")
        if res.get("stdout"):
            print(res["stdout"])
    else:
        print(f"[-] Conversion failed: {res.get('error') or res.get('stderr')}")
        sys.exit(1)

def handle_init(args):
    print(f"[*] Initializing project: {args.name} (Format: {args.format})...")
    res = ppt_tools.init_project(args.name, args.format)
    if res["success"]:
        project_path = res.get("project_path")
        print(f"[+] Project initialized successfully at: {project_path}")
    else:
        print(f"[-] Initialization failed: {res.get('error') or res.get('stderr')}")
        sys.exit(1)

def handle_import(args):
    print(f"[*] Importing sources into: {args.project_path}...")
    move_files = not args.copy
    res = ppt_tools.import_sources(args.project_path, args.sources, move=move_files)
    if res["success"]:
        print("[+] Sources imported successfully!")
        if res.get("stdout"):
            print(res["stdout"])
    else:
        print(f"[-] Import failed: {res.get('error') or res.get('stderr')}")
        sys.exit(1)

def handle_template(args):
    print(f"[*] Applying templates to: {args.project_path}...")
    res = ppt_tools.apply_template(args.project_path, args.templates)
    if res["success"]:
        print(f"[+] Templates applied successfully! Message: {res.get('message')}")
    else:
        print(f"[-] Failed to apply templates: {res.get('error')}")
        sys.exit(1)

def handle_latex(args):
    print(f"[*] Rendering LaTeX formulas for: {args.project_path}...")
    res = ppt_tools.render_latex(args.project_path, args.manifest, args.dpi, args.providers)
    if res["success"]:
        print("[+] LaTeX rendering successful!")
        if res.get("stdout"):
            print(res["stdout"])
    else:
        print(f"[-] LaTeX rendering failed: {res.get('error') or res.get('stderr')}")
        sys.exit(1)

def handle_image(args):
    print(f"[*] Generating AI images for: {args.project_path}...")
    res = ppt_tools.generate_images(args.project_path, args.manifest, render_md=True)
    if res["success"]:
        print("[+] Image generation complete!")
        if res.get("stdout"):
            print(res["stdout"])
    else:
        print(f"[-] Image generation failed: {res.get('error') or res.get('stderr')}")
        sys.exit(1)

def handle_preview(args):
    print(f"[*] Starting preview server for: {args.project_path} on port {args.port}...")
    res = ppt_tools.start_preview_server(args.project_path, args.port, args.no_browser)
    if res["success"]:
        print(f"[+] Preview server started!")
        print(f"    URL: {res.get('url')}")
        print(f"    PID: {res.get('pid')}")
        print("    Press Ctrl+C to exit this runner (preview server runs in background).")
    else:
        print(f"[-] Failed to start preview server: {res.get('error') or res.get('message')}")
        sys.exit(1)

def handle_finalize(args):
    print(f"[*] Finalizing project: {args.project_path}...")
    
    # 1. Split speaker notes
    print("    [1/3] Splitting speaker notes...")
    notes_res = ppt_tools.split_speaker_notes(args.project_path)
    if not notes_res["success"]:
        print(f"    [-] Notes splitting failed: {notes_res.get('error') or notes_res.get('stderr')}")
        sys.exit(1)
        
    # 2. Post-process SVGs
    print("    [2/3] Post-processing SVG files...")
    svg_res = ppt_tools.finalize_svg_files(args.project_path, args.compress, args.max_dimension)
    if not svg_res["success"]:
        print(f"    [-] SVG finalization failed: {svg_res.get('error') or svg_res.get('stderr')}")
        sys.exit(1)
        
    # 3. Export to PPTX
    print("    [3/3] Exporting to PPTX...")
    export_res = ppt_tools.export_to_pptx(
        args.project_path,
        transition=args.transition,
        animation=args.animation,
        animation_trigger=args.animation_trigger,
        no_merge=args.no_merge,
        svg_snapshot=args.svg_snapshot
    )
    
    if export_res["success"]:
        print("[+] Finalization and export complete!")
        if export_res.get("stdout"):
            print(export_res["stdout"])
    else:
        print(f"[-] Export failed: {export_res.get('error') or export_res.get('stderr')}")
        sys.exit(1)

def handle_validate(args):
    print(f"[*] Validating project: {args.project_path}...")
    res = ppt_tools.validate_project(args.project_path)
    if res["success"]:
        print("[+] Project validation complete!")
        if res.get("stdout"):
            print(res["stdout"])
    else:
        print(f"[-] Validation failed: {res.get('error') or res.get('stderr')}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="PPT Master - Function Calling Pipeline CLI Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Pipeline command to execute")

    # convert
    p_convert = subparsers.add_parser("convert", help="Convert source document or URL to Markdown")
    p_convert.add_argument("input", help="Path to input file or web URL")
    p_convert.add_argument("-o", "--output", help="Optional output Markdown path")
    p_convert.set_defaults(func=handle_convert)

    # init
    p_init = subparsers.add_parser("init", help="Initialize a new project")
    p_init.add_argument("name", help="Name of the project")
    p_init.add_argument("--format", default="ppt169", choices=["ppt169", "ppt43", "xhs", "story"], help="Canvas format (default: ppt169)")
    p_init.set_defaults(func=handle_init)

    # import
    p_import = subparsers.add_parser("import", help="Import source files into a project")
    p_import.add_argument("project_path", help="Path to project directory")
    p_import.add_argument("sources", nargs="+", help="Source files or URLs to import")
    p_import.add_argument("--copy", action="store_true", help="Copy instead of move")
    p_import.set_defaults(func=handle_import)

    # template
    p_template = subparsers.add_parser("template", help="Apply templates to a project")
    p_template.add_argument("project_path", help="Path to project directory")
    p_template.add_argument("templates", nargs="+", help="Absolute paths to template directories")
    p_template.set_defaults(func=handle_template)

    # latex
    p_latex = subparsers.add_parser("latex", help="Render LaTeX formulas declared in the manifest")
    p_latex.add_argument("project_path", help="Path to project directory")
    p_latex.add_argument("--manifest", help="Optional manifest path")
    p_latex.add_argument("--dpi", type=int, default=300, help="Render DPI (default: 300)")
    p_latex.add_argument("--providers", help="Comma-separated provider chain")
    p_latex.set_defaults(func=handle_latex)

    # image
    p_image = subparsers.add_parser("image", help="Generate AI images declared in the manifest")
    p_image.add_argument("project_path", help="Path to project directory")
    p_image.add_argument("--manifest", help="Optional manifest path")
    p_image.set_defaults(func=handle_image)

    # preview
    p_preview = subparsers.add_parser("preview", help="Start the live preview editor server")
    p_preview.add_argument("project_path", help="Path to project directory")
    p_preview.add_argument("--port", type=int, default=5050, help="Port to listen on (default: 5050)")
    p_preview.add_argument("--no-browser", action="store_true", help="Do not auto-open browser")
    p_preview.set_defaults(func=handle_preview)

    # finalize
    p_finalize = subparsers.add_parser("finalize", help="Split notes, finalize SVGs, and export to PPTX")
    p_finalize.add_argument("project_path", help="Path to project directory")
    p_finalize.add_argument("--compress", action="store_true", help="Compress images during finalization")
    p_finalize.add_argument("--max-dimension", type=int, help="Downscale images exceeding this size")
    p_finalize.add_argument("-t", "--transition", default="fade", help="Slide transition effect (default: fade)")
    p_finalize.add_argument("-a", "--animation", default="auto", help="Per-element animation effect (default: auto)")
    p_finalize.add_argument("--animation-trigger", default="after-previous", help="Animation trigger (default: after-previous)")
    p_finalize.add_argument("--no-merge", action="store_true", help="Disable paragraph merging")
    p_finalize.add_argument("--svg-snapshot", action="store_true", help="Additionally export SVG snapshot pptx")
    p_finalize.set_defaults(func=handle_finalize)

    # validate
    p_validate = subparsers.add_parser("validate", help="Validate project structure")
    p_validate.add_argument("project_path", help="Path to project directory")
    p_validate.set_defaults(func=handle_validate)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
