# -*- coding: utf-8 -*-
"""
PPT Master - Function Calling Schemas
Contains tool schemas in OpenAI (API tools) format and Gemini (FunctionDeclaration) format
for all wrappers defined in `ppt_tools.py`.
"""

# =====================================================================
# OpenAI Tool Schemas (Structured under 'type': 'function')
# =====================================================================
OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "convert_source_to_markdown",
            "description": "Converts a source document (PDF, DOCX, XLSX, PPTX, TXT) or a Web URL to Markdown.",
            "parameters": {
                "type": "object",
                "properties": {
                    "input_path": {
                        "type": "string",
                        "description": "Absolute path to the source file or a web URL (starts with http:// or https://)."
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Optional path for the output Markdown file. If omitted, it will be placed next to the input."
                    }
                },
                "required": ["input_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "init_project",
            "description": "Initializes a new project directory structure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Name of the project."
                    },
                    "format": {
                        "type": "string",
                        "description": "Canvas format. Options: ppt169 (16:9), ppt43 (4:3), xhs (xiaohongshu), story. Default: ppt169."
                    }
                },
                "required": ["project_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "import_sources",
            "description": "Imports converted Markdown and other source materials into the project directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the initialized project directory."
                    },
                    "source_files": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "List of absolute file paths or URLs to import."
                    },
                    "move": {
                        "type": "boolean",
                        "description": "If true, moves the files into the project. If false, copies them. Default: true."
                    }
                },
                "required": ["project_path", "source_files"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_template",
            "description": "Applies layout, brand, or deck templates to the project templates directory. Fuses multiple templates sequentially if provided.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory."
                    },
                    "template_paths": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "List of absolute paths to template directories."
                    }
                },
                "required": ["project_path", "template_paths"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_images",
            "description": "Runs analysis on images in the project directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory."
                    }
                },
                "required": ["project_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "render_latex",
            "description": "Renders LaTeX formula manifest to transparent PNG assets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory."
                    },
                    "manifest_path": {
                        "type": "string",
                        "description": "Optional manifest path. Defaults to <project_path>/images/formula_manifest.json."
                    },
                    "dpi": {
                        "type": "integer",
                        "description": "Render DPI (default: 300)."
                    },
                    "providers": {
                        "type": "string",
                        "description": "Comma-separated provider fallback chain (e.g. 'codecogs,quicklatex,mathpad,wikimedia')."
                    }
                },
                "required": ["project_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_images",
            "description": "Generates AI images from the project manifest file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory."
                    },
                    "manifest_path": {
                        "type": "string",
                        "description": "Optional manifest path. Defaults to <project_path>/images/image_prompts.json."
                    },
                    "render_md": {
                        "type": "boolean",
                        "description": "Whether to also render the markdown preview sidecar. Default: true."
                    }
                },
                "required": ["project_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_preview_server",
            "description": "Launches the browser editor in live preview mode as a background process.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory."
                    },
                    "port": {
                        "type": "integer",
                        "description": "Port to listen on (default: 5050)."
                    },
                    "no_browser": {
                        "type": "boolean",
                        "description": "If true, do not auto-open the browser. Default: false."
                    }
                },
                "required": ["project_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_annotations",
            "description": "Scans SVG files in the project directory for user-submitted edit annotations to discover pending edits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory."
                    }
                },
                "required": ["project_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_svg_quality",
            "description": "Checks the quality of generated SVG files in the project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory."
                    }
                },
                "required": ["project_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "split_speaker_notes",
            "description": "Splits the speaker notes total.md file into separate files per slide.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory."
                    }
                },
                "required": ["project_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_svg_files",
            "description": "Runs SVG post-processing (embeddings, icons, text flattening, rounded rect conversions).",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory."
                    },
                    "compress": {
                        "type": "boolean",
                        "description": "If true, compresses images before embedding. Default: false."
                    },
                    "max_dimension": {
                        "type": "integer",
                        "description": "Downscale images exceeding this dimension on either axis."
                    }
                },
                "required": ["project_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "export_to_pptx",
            "description": "Converts and exports the finalized SVGs into a native PPTX presentation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory."
                    },
                    "transition": {
                        "type": "string",
                        "description": "Slide transition effect (fade, push, wipe, split, strips, cover, random, none). Default: fade."
                    },
                    "animation": {
                        "type": "string",
                        "description": "Per-element entrance animation effect (auto, mixed, fade, none). Default: auto."
                    },
                    "animation_trigger": {
                        "type": "string",
                        "description": "Animation start trigger (on-click, with-previous, after-previous). Default: after-previous."
                    },
                    "no_merge": {
                        "type": "boolean",
                        "description": "If true, disables paragraph merging and keeps strict line-layout fidelity. Default: false."
                    },
                    "svg_snapshot": {
                        "type": "boolean",
                        "description": "If true, additionally exports the SVG snapshot pptx. Default: false."
                    }
                },
                "required": ["project_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "validate_project",
            "description": "Validates the structural integrity of a project directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory."
                    }
                },
                "required": ["project_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_design_spec",
            "description": "Saves the Design Specification (design_spec.md) to the project root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory."
                    },
                    "content": {
                        "type": "string",
                        "description": "Markdown text content of the design specification."
                    }
                },
                "required": ["project_path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_spec_lock",
            "description": "Saves the Execution Contract (spec_lock.md) to the project root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory."
                    },
                    "content": {
                        "type": "string",
                        "description": "Markdown text content of the execution spec lock."
                    }
                },
                "required": ["project_path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_svg_page",
            "description": "Saves a generated SVG page to the svg_output directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory."
                    },
                    "filename": {
                        "type": "string",
                        "description": "Filename for the SVG slide (e.g. '01_cover.svg', '02_why_it_matters.svg')."
                    },
                    "content": {
                        "type": "string",
                        "description": "SVG/XML text content of the page."
                    }
                },
                "required": ["project_path", "filename", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_speaker_notes",
            "description": "Saves the master speaker notes (notes/total.md) to the project directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory."
                    },
                    "content": {
                        "type": "string",
                        "description": "Markdown text content of the speaker notes."
                    }
                },
                "required": ["project_path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Reads the text contents of a file in the project or repository workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute or relative path to the file to read."
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "Lists all files and subdirectories under the specified directory path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dir_path": {
                        "type": "string",
                        "description": "Absolute or relative path to the directory to list."
                    }
                },
                "required": ["dir_path"]
            }
        }
    }
]

# =====================================================================
# Gemini Tool Schemas (Direct parameters schema)
# =====================================================================
def _openai_to_gemini(tool):
    """Converts OpenAI tool declaration to Gemini FunctionDeclaration format."""
    fn = tool["function"]
    
    # Simple conversion of schema keywords
    def convert_schema(schema):
        if not isinstance(schema, dict):
            return schema
        new_schema = {}
        for k, v in schema.items():
            if k == "type" and isinstance(v, str):
                new_schema[k] = v.upper()
            elif k == "items" and isinstance(v, dict):
                new_schema[k] = convert_schema(v)
            elif k == "properties" and isinstance(v, dict):
                new_schema[k] = {pk: convert_schema(pv) for pk, pv in v.items()}
            else:
                new_schema[k] = v
        return new_schema

    return {
        "name": fn["name"],
        "description": fn["description"],
        "parameters": convert_schema(fn["parameters"])
    }

GEMINI_TOOLS = [_openai_to_gemini(t) for t in OPENAI_TOOLS]
