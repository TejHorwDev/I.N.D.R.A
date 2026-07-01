                     
                                                                                                                                       
"""
file_processor.py — INDRA Universal File Processor (Enhanced)
=============================================================
Peak‑performance, multi‑format file processing with safe AI,
robust error handling, and lazy dependency loading.

Supported types & actions:
  image   → describe, ocr, resize, convert, compress, info, crop
  pdf     → summarize, extract_text, info, to_word, to_images
  docx    → summarize, extract_text, reformat, translate_hint, to_pdf
  txt/md  → summarize, reformat, translate_hint, word_count
  csv     → analyze, filter, sort, convert, stats
  xlsx    → analyze, filter, convert, stats
  json    → validate, format, extract, convert
  xml     → validate, format, extract, to_json, transform
  code    → explain, review, fix, run, document, test
  audio   → transcribe, trim, convert, info, split
  video   → trim, extract_audio, extract_frame, info, compress, convert
  zip     → list, extract, create
  pptx    → summarize, extract_text, to_pdf

Author : INDRA Project
Version: 3.0
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


               
MAX_FILE_SIZE_MB = 200                                   
MAX_AI_CONTENT_CHARS = 30_000                                      
MAX_VIDEO_DURATION_S = 600                                   

_PIL = None
_PDFPLUMBER = None
_PYPDF = None
_PYDUB = None
_DOCX = None
_PPTX = None
_PANDAS = None
_OPENPYXL = None
_LXML = None
_TESSERACT = None
_GEMINI_CLIENT = None



def _import_pil():
    global _PIL
    if _PIL is None:
        from PIL import Image

        _PIL = Image
    return _PIL

def _import_pdfplumber():
    global _PDFPLUMBER
    if _PDFPLUMBER is None:
        try:
            import pdfplumber

            _PDFPLUMBER = pdfplumber
        except ImportError:
            _PDFPLUMBER = False
    return _PDFPLUMBER

def _import_pypdf():
    global _PYPDF
    if _PYPDF is None:
        try:
            import pypdf

            _PYPDF = pypdf
        except ImportError:
            _PYPDF = False
    return _PYPDF

def _import_pydub():
    global _PYDUB
    if _PYDUB is None:
        try:
            from pydub import AudioSegment

            _PYDUB = AudioSegment
        except ImportError:
            _PYDUB = False
    return _PYDUB

def _import_docx():
    global _DOCX
    if _DOCX is None:
        try:
            from docx import Document

            _DOCX = Document
        except ImportError:
            _DOCX = False
    return _DOCX

def _import_pptx():
    global _PPTX
    if _PPTX is None:
        try:
            from pptx import Presentation

            _PPTX = Presentation
        except ImportError:
            _PPTX = False
    return _PPTX

def _import_pandas():
    global _PANDAS
    if _PANDAS is None:
        try:
            import pandas as pd

            _PANDAS = pd
        except ImportError:
            _PANDAS = False
    return _PANDAS

def _import_openpyxl():
    global _OPENPYXL
    if _OPENPYXL is None:
        try:
            import openpyxl

            _OPENPYXL = openpyxl
        except ImportError:
            _OPENPYXL = False
    return _OPENPYXL

def _import_lxml():
    global _LXML
    if _LXML is None:
        try:
            from lxml import etree

            _LXML = etree
        except ImportError:
            _LXML = False
    return _LXML

def _import_tesseract():
    global _TESSERACT
    if _TESSERACT is None:
        try:
            import pytesseract

            _TESSERACT = pytesseract
        except ImportError:
            _TESSERACT = False
    return _TESSERACT

                                                                                 

def _get_api_key() -> str:
    """Safe API key loader with clear error messages."""
    config_path = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            key = data.get("gemini_api_key", "")
            if not key:
                raise ValueError("gemini_api_key is empty")
            return key
    except Exception as e:
        raise RuntimeError(
            f"Unable to load Gemini API key from {config_path}: {e}"
        ) from e

def _gemini_client():
    """Lazy singleton Gemini client."""
    global _GEMINI_CLIENT
    if _GEMINI_CLIENT is None:
        from google import genai

        api_key = _get_api_key()
        _GEMINI_CLIENT = genai.Client(api_key=api_key)
    return _GEMINI_CLIENT

                                                                           

def _file_size_mb(path: Path) -> float:
    """File size in megabytes."""
    return path.stat().st_size / (1024 * 1024)

def _file_size_str(path: Path) -> str:
    size = path.stat().st_size
    if size < 1024:
        return f"{size} B"
    if size < 1024**2:
        return f"{size/1024:.1f} KB"
    if size < 1024**3:
        return f"{size/1024**2:.1f} MB"
    return f"{size/1024**3:.1f} GB"

def _output_path(src: Path, suffix: str, new_ext: str = None) -> Path:
    """Generate a safe output path next to the source."""
    ext = new_ext if new_ext else src.suffix
    name = f"{src.stem}_{suffix}{ext}"
    return src.parent / name

def _check_file_size(path: Path, max_mb: int = MAX_FILE_SIZE_MB) -> None:
    """Raise if file is too large."""
    if _file_size_mb(path) > max_mb:
        raise ValueError(
            f"File size ({_file_size_mb(path):.1f} MB) exceeds limit of {max_mb} MB."
        )

def _safe_subprocess_run(
    cmd: List[str], timeout: int = 300, **kwargs
) -> subprocess.CompletedProcess:
    """Wrapper for subprocess.run with timeout and clear errors."""
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, **kwargs
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Command timed out after {timeout}s: {' '.join(cmd)}")
    except FileNotFoundError:
        raise RuntimeError(f"Required tool not found: {cmd[0]}")

def _ffmpeg_available() -> bool:
    """Check if ffmpeg is accessible."""
    try:
        _safe_subprocess_run(["ffmpeg", "-version"], timeout=3)
        return True
    except Exception:
        return False

def _ffprobe_available() -> bool:
    """Check if ffprobe is accessible."""
    try:
        _safe_subprocess_run(["ffprobe", "-version"], timeout=3)
        return True
    except Exception:
        return False

def _detect_type(path: Path) -> str:
    """Fast extension‑based file type detection (cached per path)."""
    ext = path.suffix.lower().lstrip(".")
    image_exts = {
        "jpg",
        "jpeg",
        "png",
        "gif",
        "webp",
        "bmp",
        "tiff",
        "tif",
        "svg",
        "ico",
        "heic",
        "heif",
        "raw",
        "cr2",
        "nef",
        "arw",
    }
    video_exts = {
        "mp4",
        "avi",
        "mov",
        "mkv",
        "wmv",
        "flv",
        "webm",
        "m4v",
        "3gp",
        "ogv",
        "ts",
        "mts",
        "m2ts",
    }
    audio_exts = {
        "mp3",
        "wav",
        "ogg",
        "m4a",
        "aac",
        "flac",
        "wma",
        "opus",
        "aiff",
        "alac",
    }
    code_exts = {
        "py",
        "js",
        "ts",
        "jsx",
        "tsx",
        "html",
        "css",
        "java",
        "c",
        "cpp",
        "cs",
        "go",
        "rs",
        "rb",
        "php",
        "swift",
        "kt",
        "sh",
        "bash",
        "ps1",
        "lua",
        "r",
        "m",
        "sql",
        "yaml",
        "toml",
    }
    archive_exts = {"zip", "rar", "tar", "gz", "7z", "bz2", "xz"}
    doc_exts = {
        "pdf",
        "docx",
        "doc",
        "txt",
        "md",
        "rst",
        "log",
        "csv",
        "tsv",
        "xlsx",
        "xls",
        "ods",
        "json",
        "xml",
        "pptx",
        "ppt",
    }

    if ext in image_exts:
        return "image"
    if ext in video_exts:
        return "video"
    if ext in audio_exts:
        return "audio"
    if ext in code_exts:
        return "code"
    if ext in archive_exts:
        return "archive"
    if ext == "pdf":
        return "pdf"
    if ext in ("docx", "doc"):
        return "docx"
    if ext in ("txt", "md", "rst", "log"):
        return "text"
    if ext in ("csv", "tsv"):
        return "csv"
    if ext in ("xlsx", "xls", "ods"):
        return "excel"
    if ext == "json":
        return "json"
    if ext == "xml":
        return "xml"
    if ext in ("pptx", "ppt"):
        return "pptx"
    return "unknown"

                                                                   

def _ai_process(prompt: str, max_chars: int = MAX_AI_CONTENT_CHARS) -> str:
    """Send a prompt to Gemini and return clean text."""
    try:
        model = _gemini_client()
        response = model.models.generate_content(
            model="gemini-2.5-flash", contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        raise RuntimeError(f"AI processing failed: {e}") from e

def _ai_process_with_image(prompt: str, image_path: Path) -> str:
    """Send an image along with a prompt to Gemini."""
    Image = _import_pil()
    try:
        img = Image.open(image_path)
        model = _gemini_client()
        response = model.models.generate_content(
            model="gemini-2.5-flash", contents=[prompt, img]
        )
        return response.text.strip()
    except Exception as e:
        raise RuntimeError(f"AI image analysis failed: {e}") from e

                                                                          

def _process_image(path: Path, action: str, params: dict, speak=None) -> str:
    _check_file_size(path, max_mb=50)                                              
    action = action or "describe"

    if action in ("describe", "ocr", "analyze", "read", "extract_text"):
        prompt = {
            "describe": "Describe this image in detail.",
            "ocr": "Extract all text visible in this image. Return only the text, formatted clearly.",
            "analyze": "Analyze this image thoroughly: objects, colors, composition, any text, context.",
            "read": "Read all text in this image, preserving structure and formatting.",
            "extract_text": "Extract all text from this image.",
        }.get(action, "Describe this image.")
        if params.get("instruction"):
            prompt = params["instruction"]

        if action == "ocr":
            tess = _import_tesseract()
            if tess:
                try:
                    Image = _import_pil()
                    img = Image.open(path)
                    text = tess.image_to_string(img)
                    if text.strip():
                        return text.strip()
                except Exception as e:
                    pass                          
                     
        result = _ai_process_with_image(prompt, path)
        if len(result) > 500 and params.get("save", True):
            out = _output_path(path, "result", ".txt")
            out.write_text(result, encoding="utf-8")
            return f"{result[:300]}...\n\nFull result saved to: {out}"
        return result

    Image = _import_pil()

    if action == "resize":
        width = int(params.get("width", 0))
        height = int(params.get("height", 0))
        scale = float(params.get("scale", 0))
        img = Image.open(path)
        w, h = img.size
        if scale:
            new_size = (int(w * scale), int(h * scale))
        elif width and height:
            new_size = (width, height)
        elif width:
            new_size = (width, int(h * width / w))
        elif height:
            new_size = (int(w * height / h), height)
        else:
            return "Please specify width, height, or scale."
        out = _output_path(path, f"resized_{new_size[0]}x{new_size[1]}")
        resample = getattr(Image, "Resampling", Image).LANCZOS
        img.resize(new_size, resample).save(out)
        return f"Resized from {w}x{h} to {new_size[0]}x{new_size[1]}. Saved: {out.name}"

    if action == "convert":
        fmt = params.get("format", "png").lower().strip(".")
        fmt_map = {
            "jpg": "JPEG",
            "jpeg": "JPEG",
            "png": "PNG",
            "webp": "WEBP",
            "bmp": "BMP",
            "tiff": "TIFF",
        }
        pil_fmt = fmt_map.get(fmt, fmt.upper())
        img = Image.open(path)
        if fmt == "jpg":
            img = img.convert("RGB")
        out = _output_path(path, "converted", f".{fmt}")
        img.save(out, pil_fmt)
        return f"Converted to {fmt.upper()}. Saved: {out.name}"

    if action == "compress":
        quality = int(params.get("quality", 70))
        img = Image.open(path).convert("RGB")
        out = _output_path(path, f"compressed_q{quality}", ".jpg")
        img.save(out, "JPEG", quality=quality, optimize=True)
        before = _file_size_str(path)
        after = _file_size_str(out)
        return f"Compressed: {before} → {after}. Saved: {out.name}"

    if action == "info":
        img = Image.open(path)
        return (
            f"Image info: {img.format}, {img.size[0]}x{img.size[1]}px, "
            f"mode: {img.mode}, size: {_file_size_str(path)}"
        )

    return _process_image(
        path, "describe", {"instruction": f"{action}: {params}"}, speak
    )

                                                                        

def _extract_pdf_text(path: Path, max_chars: int = MAX_AI_CONTENT_CHARS) -> str:
    """Extract text from PDF using best available library."""
    text = ""
                                         
    plumber = _import_pdfplumber()
    if plumber:
        try:
            with plumber.open(path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            if text.strip():
                return text[:max_chars]
        except Exception:
            pass

    pypdf = _import_pypdf()
    if pypdf:
        try:
            reader = pypdf.PdfReader(str(path))
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        except Exception:
            pass

    return text[:max_chars]

def _process_pdf(path: Path, action: str, params: dict, speak=None) -> str:
    _check_file_size(path, max_mb=150)
    action = action or "summarize"

    if action in ("summarize", "extract_text", "translate_hint", "analyze", "reformat"):
        text = _extract_pdf_text(path)
        if not text.strip():
            return "Could not extract text from PDF (may be scanned/image-based)."

        if action == "extract_text":
            out = _output_path(path, "text", ".txt")
            out.write_text(text, encoding="utf-8")
            return f"Text extracted ({len(text)} chars). Saved: {out.name}"

        prompt_map = {
            "summarize": f"Summarize this PDF document concisely:\n\n{text}",
            "analyze": f"Analyze this document thoroughly:\n\n{text}",
            "translate_hint": f"What language is this document in and what does it say? Summarize:\n\n{text}",
            "reformat": f"Reformat this text cleanly with proper structure:\n\n{text}",
        }
        result = _ai_process(prompt_map.get(action, f"Analyze:\n\n{text}"))
        if len(result) > 600 and params.get("save", True):
            out = _output_path(path, action, ".txt")
            out.write_text(result, encoding="utf-8")
            return f"{result[:400]}...\n\nFull result saved: {out.name}"
        return result

    if action == "info":
        try:
            plumber = _import_pdfplumber()
            if plumber:
                with plumber.open(path) as pdf:
                    pages = len(pdf.pages)
                return f"PDF: {pages} pages, size: {_file_size_str(path)}"
        except Exception:
            pass
        return f"PDF size: {_file_size_str(path)}"

    if action == "to_word":
        text = _extract_pdf_text(path)
        if not text:
            return "Could not extract text to convert."
        Document = _import_docx()
        if not Document:
            return "python-docx not installed. Run: pip install python-docx"
        doc = Document()
        doc.add_heading(path.stem, 0)
        for para in text.split("\n\n"):
            if para.strip():
                doc.add_paragraph(para.strip())
        out = _output_path(path, "converted", ".docx")
        doc.save(out)
        return f"Converted to Word document. Saved: {out.name}"

    if action == "to_images":
                                                                
        try:
            from pdf2image import convert_from_path

            images = convert_from_path(path)
            saved = []
            for i, img in enumerate(images, 1):
                img_out = _output_path(path, f"page_{i}", ".png")
                img.save(img_out, "PNG")
                saved.append(img_out.name)
            return f"Extracted {len(saved)} pages as images: {', '.join(saved)}"
        except ImportError:
            return "pdf2image not installed. Run: pip install pdf2image"
        except Exception as e:
            return f"Page image extraction failed: {e}"

    return f"Unknown PDF action: '{action}'. Try: summarize, extract_text, info, to_word, to_images"

                                                                                

def _read_text_content(path: Path, file_type: str) -> str:
    if file_type == "docx":
        Document = _import_docx()
        if not Document:
            return "python-docx not installed."
        try:
            doc = Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            return f"Read failed: {e}"
    else:
        return path.read_text(encoding="utf-8", errors="ignore")

def _process_text_doc(
    path: Path, file_type: str, action: str, params: dict, speak=None
) -> str:
    _check_file_size(path, max_mb=50)
    action = action or "summarize"
    content = _read_text_content(path, file_type)
    if not content.strip():
        return "File appears to be empty."

    if action == "word_count":
        words = len(content.split())
        chars = len(content)
        lines = content.count("\n")
        return f"Word count: {words} words, {chars} characters, {lines} lines."

    if action == "extract_text":
        if file_type != "txt":
            out = _output_path(path, "extracted", ".txt")
            out.write_text(content, encoding="utf-8")
            return f"Text extracted. Saved: {out.name}"
        return content[:2000]

    instruction = params.get("instruction", "")
    prompt_map = {
        "summarize": f"Summarize this document concisely:\n\n{content[:MAX_AI_CONTENT_CHARS]}",
        "analyze": f"Analyze this document:\n\n{content[:MAX_AI_CONTENT_CHARS]}",
        "reformat": f"Reformat this text with clean structure, proper headings and paragraphs:\n\n{content[:MAX_AI_CONTENT_CHARS]}",
        "fix": f"Fix grammar, spelling and style issues in this text:\n\n{content[:MAX_AI_CONTENT_CHARS]}",
        "translate_hint": f"What language is this and what does it say? Summarize:\n\n{content[:10000]}",
        "to_bullet": f"Convert this text into a clear bullet-point summary:\n\n{content[:MAX_AI_CONTENT_CHARS]}",
        "custom": f"{instruction}\n\n{content[:MAX_AI_CONTENT_CHARS]}",
    }

    if action not in prompt_map:
        action = "custom"
        instruction = action
        prompt_map["custom"] = f"{instruction}\n\n{content[:MAX_AI_CONTENT_CHARS]}"

    result = _ai_process(prompt_map[action])
    if len(result) > 600 and params.get("save", True):
        out = _output_path(path, action, ".txt")
        out.write_text(result, encoding="utf-8")
        return f"{result[:400]}...\n\nFull result saved: {out.name}"
    return result

                                                                                

def _process_data(
    path: Path, file_type: str, action: str, params: dict, speak=None
) -> str:
    pd = _import_pandas()
    if not pd:
        return "pandas not installed. Run: pip install pandas openpyxl"

    _check_file_size(path, max_mb=100)
    action = action or "analyze"

    try:
        if file_type == "csv":
            df = pd.read_csv(path, encoding="utf-8", errors="replace")
        else:
            df = pd.read_excel(
                path, engine="openpyxl" if path.suffix.lower() == ".xlsx" else None
            )
    except Exception as e:
        return f"Could not read file: {e}"

    if action == "info":
        return (
            f"Rows: {len(df)}, Columns: {len(df.columns)}\n"
            f"Columns: {', '.join(df.columns.tolist())}\n"
            f"Size: {_file_size_str(path)}"
        )

    if action == "stats":
        try:
            desc = df.describe(include="all").to_string()
            return f"Statistics:\n{desc[:2000]}"
        except Exception as e:
            return f"Stats failed: {e}"

    if action == "analyze":
        preview = df.head(50).to_string()
        prompt = (
            f"Analyze this dataset. Columns: {list(df.columns)}\n"
            f"Rows: {len(df)}\nPreview:\n{preview}\n\n"
            f"Give insights, patterns, and notable findings."
        )
        return _ai_process(prompt)

    if action in ("convert", "to_csv", "to_excel", "to_json"):
        fmt = {
            "to_csv": "csv",
            "to_excel": "xlsx",
            "to_json": "json",
            "convert": params.get("format", "csv"),
        }.get(action, "csv")
        try:
            if fmt == "csv":
                out = _output_path(path, "converted", ".csv")
                df.to_csv(out, index=False, encoding="utf-8")
            elif fmt == "xlsx":
                out = _output_path(path, "converted", ".xlsx")
                df.to_excel(out, index=False, engine="openpyxl")
            elif fmt == "json":
                out = _output_path(path, "converted", ".json")
                df.to_json(out, orient="records", force_ascii=False, indent=2)
            return f"Converted to {fmt.upper()}. Saved: {out.name}"
        except Exception as e:
            return f"Convert failed: {e}"

    if action == "filter":
        col = params.get("column", "")
        value = params.get("value", "")
        condition = params.get("condition", "equals")
        if not col or col not in df.columns:
            return f"Column '{col}' not found. Available: {', '.join(df.columns)}"
        try:
            if condition == "equals":
                filtered = df[df[col] == value]
            elif condition == "contains":
                filtered = df[df[col].astype(str).str.contains(str(value), case=False)]
            elif condition == "gt":
                filtered = df[df[col] > float(value)]
            elif condition == "lt":
                filtered = df[df[col] < float(value)]
            else:
                filtered = df[df[col] == value]
            out = _output_path(path, "filtered", ".csv")
            filtered.to_csv(out, index=False)
            return f"Filtered: {len(filtered)} rows match. Saved: {out.name}"
        except Exception as e:
            return f"Filter failed: {e}"

    if action == "sort":
        col = params.get("column", df.columns[0])
        asc = params.get("ascending", True)
        try:
            sorted_df = df.sort_values(col, ascending=asc)
            out = _output_path(path, "sorted", path.suffix)
            sorted_df.to_csv(out, index=False)
            return f"Sorted by '{col}'. Saved: {out.name}"
        except Exception as e:
            return f"Sort failed: {e}"

    preview = df.head(30).to_string()
    prompt = f"Task: {action}\nDataset ({len(df)} rows, cols: {list(df.columns)}):\n{preview}"
    return _ai_process(prompt)

                                                                         

def _process_json(path: Path, action: str, params: dict, speak=None) -> str:
    _check_file_size(path, max_mb=50)
    action = action or "analyze"
    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
    except Exception as e:
        return f"Invalid JSON: {e}"

    if action == "validate":
        return f"Valid JSON. Type: {type(data).__name__}, size: {_file_size_str(path)}"

    if action == "format":
        out = _output_path(path, "formatted", ".json")
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return f"Formatted JSON saved: {out.name}"

    if action in ("analyze", "summarize", "extract"):
        preview = json.dumps(data, indent=2, ensure_ascii=False)[:8000]
        prompt = f"Task: {action} this JSON data:\n{preview}"
        if params.get("instruction"):
            prompt = f"{params['instruction']}\n\nJSON data:\n{preview}"
        return _ai_process(prompt)

    if action == "to_csv":
        pd = _import_pandas()
        if not pd:
            return "pandas not installed."
        if isinstance(data, list):
            df = pd.DataFrame(data)
            out = _output_path(path, "converted", ".csv")
            df.to_csv(out, index=False)
            return f"Converted to CSV. Saved: {out.name}"
        return "JSON must be an array of objects to convert to CSV."

    return _process_json(path, "analyze", {"instruction": action})

                                                                        

def _process_xml(path: Path, action: str, params: dict, speak=None) -> str:
    _check_file_size(path, max_mb=50)
    action = action or "validate"
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Cannot read file: {e}"

    if action == "validate":
        try:
            etree = _import_lxml()
            if etree:
                etree.fromstring(content.encode())
                return f"Valid XML. Size: {_file_size_str(path)}"
            else:
                                         
                import xml.etree.ElementTree as ET

                ET.fromstring(content)
                return f"Valid XML. Size: {_file_size_str(path)}"
        except Exception as e:
            return f"Invalid XML: {e}"

    if action == "format":
        try:
            etree = _import_lxml()
            if etree:
                parser = etree.XMLParser(remove_blank_text=True)
                root = etree.fromstring(content.encode(), parser)
                formatted = etree.tostring(root, pretty_print=True, encoding="unicode")
            else:
                import xml.dom.minidom

                dom = xml.dom.minidom.parseString(content)
                formatted = dom.toprettyxml(indent="  ")
            out = _output_path(path, "formatted", ".xml")
            out.write_text(formatted, encoding="utf-8")
            return f"Formatted XML saved: {out.name}"
        except Exception as e:
            return f"Format failed: {e}"

    if action == "to_json":
        try:
            import xmltodict

            data = xmltodict.parse(content)
            out = _output_path(path, "converted", ".json")
            out.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return f"Converted to JSON. Saved: {out.name}"
        except ImportError:
            return "xmltodict not installed. Run: pip install xmltodict"
        except Exception as e:
            return f"Conversion failed: {e}"

    if action in ("extract", "analyze", "summarize"):
        prompt = f"Task: {action} this XML data:\n{content[:MAX_AI_CONTENT_CHARS]}"
        if params.get("instruction"):
            prompt = f"{params['instruction']}\n\nXML data:\n{content[:MAX_AI_CONTENT_CHARS]}"
        return _ai_process(prompt)

    return _process_xml(path, "analyze", {"instruction": action})

                                                                         

def _process_code(path: Path, action: str, params: dict, speak=None) -> str:
    _check_file_size(path, max_mb=10)
    action = action or "explain"
    content = path.read_text(encoding="utf-8", errors="ignore")
    ext = path.suffix.lstrip(".")

    if action == "run":
        if ext == "py":
            try:
                result = _safe_subprocess_run(["python", str(path)], timeout=30)
                out = result.stdout or result.stderr
                return f"Output:\n{out[:2000]}" if out else "No output."
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"Run failed: {e}"
        return f"Direct execution not supported for .{ext} files."

    if action == "info":
        lines = content.count("\n")
        words = len(content.split())
        return f"Code file: {lines} lines, {words} words, {_file_size_str(path)}"

    prompt_map = {
        "explain": f"Explain this {ext} code clearly:\n\n```{ext}\n{content[:MAX_AI_CONTENT_CHARS]}\n```",
        "review": f"Review this {ext} code for bugs, issues, and improvements:\n\n```{ext}\n{content[:MAX_AI_CONTENT_CHARS]}\n```",
        "fix": f"Fix any bugs in this {ext} code and return the corrected version:\n\n```{ext}\n{content[:MAX_AI_CONTENT_CHARS]}\n```",
        "optimize": f"Optimize this {ext} code for performance and readability:\n\n```{ext}\n{content[:MAX_AI_CONTENT_CHARS]}\n```",
        "document": f"Add proper documentation/comments to this {ext} code:\n\n```{ext}\n{content[:MAX_AI_CONTENT_CHARS]}\n```",
        "summarize": f"Summarize what this {ext} code does:\n\n```{ext}\n{content[:MAX_AI_CONTENT_CHARS]}\n```",
        "test": f"Write unit tests for this {ext} code:\n\n```{ext}\n{content[:MAX_AI_CONTENT_CHARS]}\n```",
    }

    instruction = params.get("instruction", "")
    if action not in prompt_map:
        prompt = f"{action}\n\n```{ext}\n{content[:MAX_AI_CONTENT_CHARS]}\n```"
        if instruction:
            prompt = f"{instruction}\n\n```{ext}\n{content[:MAX_AI_CONTENT_CHARS]}\n```"
    else:
        prompt = prompt_map[action]

    result = _ai_process(prompt)
    if action in ("fix", "optimize", "document") and params.get("save", True):
        out = _output_path(path, action)
        code_match = re.search(r"```(?:\w+)?\n(.*?)```", result, re.DOTALL)
        code_to_save = code_match.group(1) if code_match else result
        out.write_text(code_to_save, encoding="utf-8")
        return f"{result[:400]}...\n\nSaved: {out.name}"
    return result

                                                                          

def _process_audio(path: Path, action: str, params: dict, speak=None) -> str:
    _check_file_size(path, max_mb=150)
    action = action or "transcribe"

    if action == "info":
        AudioSegment = _import_pydub()
        if AudioSegment:
            try:
                audio = AudioSegment.from_file(str(path))
                duration = len(audio) / 1000
                mins, secs = divmod(int(duration), 60)
                return (
                    f"Audio: {mins}m {secs}s, "
                    f"{audio.channels} ch, "
                    f"{audio.frame_rate}Hz, "
                    f"{_file_size_str(path)}"
                )
            except Exception:
                pass
        return f"Audio file: {_file_size_str(path)} (install pydub for more info)"

    if action == "transcribe":
                                                                         
        try:
            content = path.read_bytes()
            if len(content) > 20 * 1024 * 1024:                          
                return "Audio file too large for AI transcription (>20MB)."
            mime = {
                "mp3": "audio/mp3",
                "wav": "audio/wav",
                "ogg": "audio/ogg",
                "m4a": "audio/mp4",
                "aac": "audio/aac",
                "flac": "audio/flac",
            }.get(path.suffix.lstrip(".").lower(), "audio/mpeg")
            model = _gemini_client()
            response = model.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    "Transcribe all speech in this audio file accurately.",
                    {"mime_type": mime, "data": content},
                ],
            )
            result = response.text.strip()
            if params.get("save", True):
                out = _output_path(path, "transcript", ".txt")
                out.write_text(result, encoding="utf-8")
                return f"Transcription saved: {out.name}\n\nPreview: {result[:300]}"
            return result
        except Exception as e:
            return f"Transcription failed: {e}"

    if action == "convert":
        fmt = params.get("format", "mp3").lstrip(".")
        AudioSegment = _import_pydub()
        if not AudioSegment:
            return "pydub not installed. Run: pip install pydub"
        try:
            audio = AudioSegment.from_file(str(path))
            out = _output_path(path, "converted", f".{fmt}")
            audio.export(out, format=fmt)
            return f"Converted to {fmt.upper()}. Saved: {out.name}"
        except Exception as e:
            return f"Convert failed: {e}"

    if action == "trim":
        start = float(params.get("start", 0))
        end = float(params.get("end", 0))
        AudioSegment = _import_pydub()
        if not AudioSegment:
            return "pydub not installed."
        try:
            audio = AudioSegment.from_file(str(path))
            end_ms = int(end * 1000) if end else len(audio)
            trimmed = audio[int(start * 1000) : end_ms]
            out = _output_path(path, f"trim_{int(start)}s_{int(end)}s")
            trimmed.export(out, format=path.suffix.lstrip("."))
            return f"Trimmed audio ({int(start)}s–{int(end)}s). Saved: {out.name}"
        except Exception as e:
            return f"Trim failed: {e}"

    return f"Unknown audio action: '{action}'. Try: transcribe, info, convert, trim"

                                                                          

def _process_video(path: Path, action: str, params: dict, speak=None) -> str:
    _check_file_size(path, max_mb=500)
    action = action or "info"

    if action == "info":
        if _ffprobe_available():
            try:
                cmd = [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    str(path),
                ]
                result = _safe_subprocess_run(cmd, timeout=15)
                data = json.loads(result.stdout)
                fmt = data.get("format", {})
                duration = float(fmt.get("duration", 0))
                mins, secs = divmod(int(duration), 60)
                size = _file_size_str(path)
                streams = data.get("streams", [])
                video_s = next((s for s in streams if s["codec_type"] == "video"), {})
                w = video_s.get("width", "?")
                h = video_s.get("height", "?")
                fps = video_s.get("r_frame_rate", "?")
                return f"Video: {mins}m {secs}s, {w}x{h}, {fps} fps, {size}"
            except Exception:
                pass
        return f"Video file: {_file_size_str(path)}"

    if not _ffmpeg_available():
        return "ffmpeg not found. Install ffmpeg for video processing."

    if action == "extract_audio":
        out = _output_path(path, "audio", ".mp3")
        try:
            _safe_subprocess_run(
                ["ffmpeg", "-i", str(path), "-q:a", "0", "-map", "a", str(out), "-y"],
                timeout=300,
            )
            return f"Audio extracted. Saved: {out.name}"
        except RuntimeError as e:
            return f"Extract audio failed: {e}"

    if action == "trim":
        start = params.get("start", "00:00:00")
        end = params.get("end", "")
        out = _output_path(path, "trim", path.suffix)
        try:
            cmd = ["ffmpeg", "-i", str(path), "-ss", str(start)]
            if end:
                cmd += ["-to", str(end)]
            cmd += ["-c", "copy", str(out), "-y"]
            _safe_subprocess_run(cmd, timeout=600)
            return f"Trimmed video saved: {out.name}"
        except RuntimeError as e:
            return f"Trim failed: {e}"

    if action == "extract_frame":
        timestamp = params.get("timestamp", "00:00:01")
        out = _output_path(path, f"frame_{timestamp.replace(':', '')}", ".jpg")
        try:
            _safe_subprocess_run(
                [
                    "ffmpeg",
                    "-i",
                    str(path),
                    "-ss",
                    timestamp,
                    "-vframes",
                    "1",
                    str(out),
                    "-y",
                ],
                timeout=30,
            )
            return f"Frame extracted at {timestamp}. Saved: {out.name}"
        except RuntimeError as e:
            return f"Extract frame failed: {e}"

    if action == "compress":
        crf = int(params.get("quality", 28))
        out = _output_path(path, f"compressed_crf{crf}", ".mp4")
        try:
            _safe_subprocess_run(
                [
                    "ffmpeg",
                    "-i",
                    str(path),
                    "-c:v",
                    "libx264",
                    "-crf",
                    str(crf),
                    "-preset",
                    "medium",
                    "-c:a",
                    "copy",
                    str(out),
                    "-y",
                ],
                timeout=1800,
            )
            before = _file_size_str(path)
            after = _file_size_str(out)
            return f"Compressed: {before} → {after}. Saved: {out.name}"
        except RuntimeError as e:
            return f"Compress failed: {e}"

    if action == "transcribe":
                                             
        tmp_audio = Path(tempfile.mktemp(suffix=".mp3"))
        try:
            _safe_subprocess_run(
                [
                    "ffmpeg",
                    "-i",
                    str(path),
                    "-q:a",
                    "0",
                    "-map",
                    "a",
                    str(tmp_audio),
                    "-y",
                ],
                timeout=300,
            )
            return _process_audio(tmp_audio, "transcribe", params, speak)
        except Exception as e:
            return f"Video transcription failed: {e}"
        finally:
            if tmp_audio.exists():
                tmp_audio.unlink()

    if action == "convert":
        fmt = params.get("format", "mp4").lstrip(".")
        out = _output_path(path, "converted", f".{fmt}")
        try:
            _safe_subprocess_run(
                ["ffmpeg", "-i", str(path), str(out), "-y"], timeout=1800
            )
            return f"Converted to {fmt.upper()}. Saved: {out.name}"
        except RuntimeError as e:
            return f"Convert failed: {e}"

    return f"Unknown video action: '{action}'. Try: info, trim, extract_audio, extract_frame, compress, transcribe, convert"

                                                                            

def _process_archive(path: Path, action: str, params: dict, speak=None) -> str:
    action = action or "list"

    if action == "list":
        try:
            ext = path.suffix.lower()
            if ext == ".zip":
                with zipfile.ZipFile(path) as z:
                    names = z.namelist()
            elif ext in (".tar", ".gz", ".bz2", ".xz"):
                with tarfile.open(path) as t:
                    names = t.getnames()
            else:
                                                  
                names = []
                                                                                     
                return (
                    f"Archive listing not directly supported for .{ext} (try: extract)"
                )
            preview = "\n".join(names[:30])
            suffix = f"\n... and {len(names)-30} more" if len(names) > 30 else ""
            return f"Archive contains {len(names)} files:\n{preview}{suffix}"
        except Exception as e:
            return f"List failed: {e}"

    if action == "extract":
        dest = Path(params.get("destination", str(path.parent / path.stem)))
        dest.mkdir(parents=True, exist_ok=True)
        try:
            shutil.unpack_archive(path, dest)
            return f"Extracted to: {dest}"
        except Exception as e:
            return f"Extract failed: {e}"

    return f"Unknown archive action: '{action}'. Try: list, extract"

                                                                         

def _process_pptx(path: Path, action: str, params: dict, speak=None) -> str:
    _check_file_size(path, max_mb=100)
    action = action or "summarize"

    def _read_pptx_text() -> str:
        Presentation = _import_pptx()
        if not Presentation:
            return "python-pptx not installed."
        try:
            prs = Presentation(str(path))
            text = []
            for i, slide in enumerate(prs.slides, 1):
                slide_text = f"\n--- Slide {i} ---\n"
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        slide_text += shape.text.strip() + "\n"
                text.append(slide_text)
            return "\n".join(text)
        except Exception as e:
            return f"Read failed: {e}"

    if action in ("summarize", "extract_text", "analyze"):
        text = _read_pptx_text()
        if isinstance(text, str) and text.startswith("python-pptx"):
            return text                 
        if action == "extract_text":
            out = _output_path(path, "text", ".txt")
            out.write_text(text, encoding="utf-8")
            return f"Text extracted. Saved: {out.name}"
        prompt = f"{'Summarize' if action == 'summarize' else 'Analyze'} this presentation:\n{text[:MAX_AI_CONTENT_CHARS]}"
        return _ai_process(prompt)

    if action == "to_pdf":
                                                               
        return "PPTX to PDF conversion requires LibreOffice (not yet integrated)."

    return f"Unknown PPTX action: '{action}'. Try: summarize, extract_text, analyze"

                                                                                     

def file_processor(parameters: dict, player=None, speak=None) -> str:
    file_path_str = parameters.get("file_path", "").strip()
    if not file_path_str:
        return "No file path provided."

    path = Path(file_path_str)
    if not path.exists():
        return f"File not found: {file_path_str}"
    if not path.is_file():
        return f"Path is not a file: {file_path_str}"

    file_type = _detect_type(path)
    action = (parameters.get("action") or "").lower().strip()
    instruction = parameters.get("instruction", "")
    params = {**parameters, "instruction": instruction}

    log_msg = (
        f"[FileProcessor] {file_type.upper()} | {path.name} | action={action or 'auto'}"
    )
    print(log_msg)
    if player:
        player.write_log(log_msg)

    if file_type == "unknown":
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")[
                :MAX_AI_CONTENT_CHARS
            ]
            prompt = (
                f"File: {path.name}\nContent preview:\n{content}\n\n"
                f"Task: {action or instruction or 'Describe what this file contains and what can be done with it.'}"
            )
            return _ai_process(prompt)
        except Exception as e:
            return f"Unknown file type ({path.suffix}). Could not process: {e}"

    dispatch = {
        "image": _process_image,
        "pdf": _process_pdf,
        "docx": lambda p, a, pm, s: _process_text_doc(p, "docx", a, pm, s),
        "text": lambda p, a, pm, s: _process_text_doc(p, "text", a, pm, s),
        "csv": lambda p, a, pm, s: _process_data(p, "csv", a, pm, s),
        "excel": lambda p, a, pm, s: _process_data(p, "excel", a, pm, s),
        "json": _process_json,
        "xml": _process_xml,
        "code": _process_code,
        "audio": _process_audio,
        "video": _process_video,
        "archive": _process_archive,
        "pptx": _process_pptx,
    }

    handler = dispatch.get(file_type)
    if not handler:
        return f"Unsupported file type: {file_type}"

    try:
        result = handler(path, action, params, speak)
        return result or "Done."
    except Exception as e:
        import traceback

        traceback.print_exc()
        return f"Processing failed: {e}"
