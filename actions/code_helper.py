                     
                                                                                                                                       
import ast
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

                                                         
def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
DESKTOP = Path.home() / "Desktop"
MAX_BUILD_ATTEMPTS = 3
GEMINI_MODEL = "gemini-2.5-flash"
BACKUP_SUFFIX = ".INDRA_backup"
MAX_BACKUPS = 5                        
API_RETRY_ATTEMPTS = 3                                 
API_RETRY_DELAY = 1.5                                              

                                                                                      
LANG_REGISTRY: Dict[str, Dict] = {
    "python": {
        "ext": ".py",
        "interp": [sys.executable],
        "fmt": ["black"],
        "lint": ["flake8"],
        "test": "pytest",
    },
    "py": {
        "ext": ".py",
        "interp": [sys.executable],
        "fmt": ["black"],
        "lint": ["flake8"],
        "test": "pytest",
    },
    "javascript": {
        "ext": ".js",
        "interp": ["node"],
        "fmt": ["prettier", "--write"],
        "lint": ["eslint"],
        "test": "jest",
    },
    "js": {
        "ext": ".js",
        "interp": ["node"],
        "fmt": ["prettier", "--write"],
        "lint": ["eslint"],
        "test": "jest",
    },
    "typescript": {
        "ext": ".ts",
        "interp": ["ts-node"],
        "fmt": ["prettier", "--write"],
        "lint": ["eslint"],
        "test": "jest",
    },
    "ts": {
        "ext": ".ts",
        "interp": ["ts-node"],
        "fmt": ["prettier", "--write"],
        "lint": ["eslint"],
        "test": "jest",
    },
    "html": {
        "ext": ".html",
        "interp": None,
        "fmt": ["prettier", "--write"],
        "lint": [],
        "test": None,
    },
    "css": {
        "ext": ".css",
        "interp": None,
        "fmt": ["prettier", "--write"],
        "lint": [],
        "test": None,
    },
    "java": {
        "ext": ".java",
        "interp": ["java"],
        "fmt": ["google-java-format"],
        "lint": [],
        "test": "junit",
    },
    "cpp": {
        "ext": ".cpp",
        "interp": None,
        "fmt": ["clang-format"],
        "lint": [],
        "test": "gtest",
    },
    "c": {
        "ext": ".c",
        "interp": None,
        "fmt": ["clang-format"],
        "lint": [],
        "test": None,
    },
    "bash": {
        "ext": ".sh",
        "interp": ["bash"],
        "fmt": [],
        "lint": ["shellcheck"],
        "test": None,
    },
    "shell": {
        "ext": ".sh",
        "interp": ["bash"],
        "fmt": [],
        "lint": ["shellcheck"],
        "test": None,
    },
    "powershell": {
        "ext": ".ps1",
        "interp": ["powershell", "-File"],
        "fmt": [],
        "lint": [],
        "test": None,
    },
    "sql": {"ext": ".sql", "interp": None, "fmt": [], "lint": [], "test": None},
    "json": {
        "ext": ".json",
        "interp": None,
        "fmt": ["prettier", "--write"],
        "lint": [],
        "test": None,
    },
    "rust": {
        "ext": ".rs",
        "interp": ["rustc"],
        "fmt": ["rustfmt"],
        "lint": ["clippy"],
        "test": "cargo test",
    },
    "go": {
        "ext": ".go",
        "interp": ["go", "run"],
        "fmt": ["gofmt"],
        "lint": ["golint"],
        "test": "go test",
    },
    "ruby": {
        "ext": ".rb",
        "interp": ["ruby"],
        "fmt": [],
        "lint": ["rubocop"],
        "test": "rspec",
    },
    "php": {
        "ext": ".php",
        "interp": ["php"],
        "fmt": [],
        "lint": ["phpcs"],
        "test": "phpunit",
    },
}

def _lang_info(lang: str) -> Dict:
    """Return registry entry for a language, defaulting to python."""
    return LANG_REGISTRY.get((lang or "python").lower(), LANG_REGISTRY["python"])

                                                       
def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]

def _get_genai_client():
    from google import genai

    return genai.Client(api_key=_get_api_key())

def _generate_content(prompt: str, model: str = GEMINI_MODEL) -> str:
    """Call Gemini with exponential-backoff retry on transient failures."""
    last_exc = None
    for attempt in range(1, API_RETRY_ATTEMPTS + 1):
        try:
            client = _get_genai_client()
            response = client.models.generate_content(model=model, contents=prompt)
            text = response.text
            if not text or not text.strip():
                raise ValueError("Empty response from model.")
            return text
        except Exception as exc:
            last_exc = exc
            err_str = str(exc).lower()
                                                                                      
            if any(
                kw in err_str for kw in ["api_key", "permission", "quota", "invalid"]
            ):
                raise
            if attempt < API_RETRY_ATTEMPTS:
                wait = API_RETRY_DELAY * (2 ** (attempt - 1))
                print(
                    f"[Code] ⚠️  API attempt {attempt} failed ({exc}). Retrying in {wait:.1f}s…"
                )
                time.sleep(wait)
    raise RuntimeError(f"API failed after {API_RETRY_ATTEMPTS} attempts: {last_exc}")

def _multimodal_generate(
    image_bytes: bytes, prompt: str, model: str = GEMINI_MODEL
) -> str:
    """Multimodal call with validation that the image is non-trivial."""
    if not image_bytes or len(image_bytes) < 1024:
        raise ValueError("Screenshot appears empty or corrupt.")
    last_exc = None
    for attempt in range(1, API_RETRY_ATTEMPTS + 1):
        try:
            from google.genai import types

            client = _get_genai_client()
            contents = [
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt,
            ]
            response = client.models.generate_content(model=model, contents=contents)
            text = response.text
            if not text or not text.strip():
                raise ValueError("Empty multimodal response.")
            return text
        except Exception as exc:
            last_exc = exc
            if attempt < API_RETRY_ATTEMPTS:
                time.sleep(API_RETRY_DELAY * attempt)
    raise RuntimeError(f"Multimodal API failed: {last_exc}")

def _clean_code(text: str) -> str:
    """
    Strip ALL markdown code fence variants robustly.
    Handles: ```python, ```py, ```js, ``` (bare), plus leading/trailing whitespace.
    Also strips explanatory lines before/after the fence block.
    """
    if not text:
        return ""
    text = text.strip()
                                                                              
    fence_pattern = re.compile(r"```[a-zA-Z0-9_+-]*\n?(.*?)```", re.DOTALL)
    matches = fence_pattern.findall(text)
    if matches:
                                                                  
        text = max(matches, key=len)
                                         
    text = re.sub(r"^```[a-zA-Z0-9_+-]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()

                                                           
def _resolve_save_path(output_path: str, language: str) -> Path:
    info = _lang_info(language)
    ext = info["ext"]
    if output_path:
        p = Path(output_path)
        return p if p.is_absolute() else DESKTOP / p
    return DESKTOP / f"INDRA_code{ext}"

def _read_file(file_path: str) -> Tuple[str, str]:
    if not file_path:
        return "", "No file path provided."
    p = Path(file_path)
    if not p.exists():
        return "", f"File not found: {file_path}"
    try:
        return p.read_text(encoding="utf-8"), ""
    except UnicodeDecodeError:
        try:
            return p.read_text(encoding="latin-1"), ""
        except Exception as e:
            return "", f"Could not read file (encoding issue): {e}"
    except Exception as e:
        return "", f"Could not read file: {e}"

def _rolling_backup(path: Path) -> None:
    """
    Keep up to MAX_BACKUPS rolling backups: .INDRA_backup.1 (newest) → .INDRA_backup.N (oldest).
    Prevents overwriting the only backup on repeated edits.
    """
    for i in range(MAX_BACKUPS - 1, 0, -1):
        old = Path(str(path) + f"{BACKUP_SUFFIX}.{i}")
        new = Path(str(path) + f"{BACKUP_SUFFIX}.{i+1}")
        if old.exists():
            old.rename(new)
    first = Path(str(path) + f"{BACKUP_SUFFIX}.1")
    shutil.copy2(path, first)

def _save_file(path: Path, content: str) -> str:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            _rolling_backup(path)
        path.write_text(content, encoding="utf-8")
        return f"Saved to: {path}"
    except Exception as e:
        return f"Could not save: {e}"

def _preview(code: str, lines: int = 10) -> str:
    all_lines = code.splitlines()
    preview = "\n".join(all_lines[:lines])
    suffix = (
        f"\n… ({len(all_lines) - lines} more lines)" if len(all_lines) > lines else ""
    )
    return preview + suffix

def _count_lines(text: str) -> int:
    return len(text.splitlines())

                                                                
                                                                 
_ERROR_PATTERNS = [
    (r"(?i)(syntax\s*error|indentation\s*error)", "syntax"),
    (r"(?i)(name\s*error|undefined\s*(variable|reference))", "name"),
    (r"(?i)(type\s*error)", "type"),
    (r"(?i)(import\s*error|module\s*not\s*found)", "import"),
    (r"(?i)(file\s*not\s*found|no\s*such\s*file)", "file"),
    (r"(?i)(permission\s*denied)", "permission"),
    (r"(?i)(connection\s*(refused|error|timed?\s*out))", "network"),
    (r"(?i)(traceback|exception|crash|fatal)", "runtime"),
    (r"(?i)(error|failed|stderr)", "generic"),
]

def _classify_error(output: str) -> Tuple[bool, str]:
    """Returns (has_error, category). Category helps tailor fix prompts."""
    for pattern, category in _ERROR_PATTERNS:
        if re.search(pattern, output):
            return True, category
    return False, "none"

def _has_error(output: str) -> bool:
    has, _ = _classify_error(output)
    return has

                                                                         
def _extract_imports_from_code(code: str, lang: str) -> List[str]:
    """
    Parse actual import statements from source code.
    Python: uses ast for accuracy. Others: regex fallback.
    Returns list of third-party package names (filters stdlib).
    """
    packages = []
    lang = (lang or "python").lower()
    if lang in ("python", "py"):
        try:
            tree = ast.parse(code)
            stdlib = (
                set(sys.stdlib_module_names)
                if hasattr(sys, "stdlib_module_names")
                else set()
            )
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".")[0]
                        if root not in stdlib:
                            packages.append(root)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        root = node.module.split(".")[0]
                        if root not in stdlib:
                            packages.append(root)
        except SyntaxError:
                                                      
            for m in re.finditer(r"^(?:import|from)\s+([\w]+)", code, re.MULTILINE):
                packages.append(m.group(1))
    elif lang in ("javascript", "js", "typescript", "ts"):
        for m in re.finditer(r"""(?:require\(['"]|from\s+['"])([@\w/-]+)""", code):
            pkg = m.group(1)
            if not pkg.startswith("."):
                packages.append(pkg.split("/")[0])
    return list(dict.fromkeys(packages))                                

def _detect_test_framework(code: str, lang: str) -> str:
    """Detect which test framework to use based on existing imports in the file."""
    info = _lang_info(lang)
    default = info.get("test", "pytest")
    patterns = {
        "pytest": r"import pytest|from pytest",
        "unittest": r"import unittest|from unittest",
        "jest": r"from '@testing-library|describe\(|it\(|test\(",
        "mocha": r"require.*mocha|describe\(|it\(",
    }
    for fw, pattern in patterns.items():
        if re.search(pattern, code):
            return fw
    return default

                                                                             
                                       
_INTENT_RULES: List[Tuple[List[str], str, int]] = [
                                        
    (
        [
            "ekrandaki",
            "screen",
            "ekranda",
            "bu hatayı",
            "why am i getting",
            "neden hata",
            "what's wrong",
            "ne yanlış",
            "screenshot",
            "görüntü",
        ],
        "screen_debug",
        10,
    ),
              
    (
        [
            "optimize",
            "refactor",
            "clean up",
            "improve",
            "temizle",
            "iyileştir",
            "daha iyi",
            "make it better",
            "hızlandır",
            "performance",
        ],
        "optimize",
        8,
    ),
          
    (
        [
            "edit",
            "update",
            "modify",
            "change",
            "add",
            "remove",
            "rename",
            "replace",
            "düzenle",
            "değiştir",
            "fix the",
        ],
        "edit",
        7,
    ),
             
    (
        [
            "explain",
            "what does",
            "describe",
            "analyze",
            "açıkla",
            "ne yapıyor",
            "how does",
            "walk me through",
        ],
        "explain",
        7,
    ),
         
    (["run", "execute", "launch", "start", "çalıştır", "test it"], "run", 7),
                   
    (["build", "make it work", "try again", "attempt", "rebuild"], "build", 6),
            
    (["review", "check", "audit", "look at"], "review", 6),
              
    (
        ["security", "vulnerability", "secure", "hack", "penetration"],
        "security_scan",
        6,
    ),
                     
    (["test", "unit test", "write tests", "generate tests"], "generate_tests", 6),
          
    (["document", "docstring", "comment", "annotate", "jsdoc"], "generate_docs", 6),
             
    (["convert", "translate", "port", "migrate"], "convert", 6),
            
    (["format", "prettier", "black", "beautify"], "format", 5),
          
    (["lint", "style check", "flake8", "eslint"], "lint", 5),
         
    (["api", "rest api", "endpoint", "route", "fastapi", "express"], "api_generate", 5),
            
    (["schema", "database", "sql", "table", "migration"], "database_schema", 5),
                   
    (["scaffold", "project setup", "new project", "initialize"], "project_setup", 5),
               
    (["benchmark", "performance test", "profile", "speed"], "benchmark", 5),
                  
    (["dependencies", "requirements", "packages", "deps"], "dependencies", 5),
]

def _detect_intent(description: str, file_path: str, code: str) -> str:
    """
    Score-based intent detection. Returns the highest-scoring intent.
    Falls back to 'edit' if a file_path exists, else 'write'.
    """
    desc = (description or "").lower()
    scores: Dict[str, int] = {}
    for keywords, intent, score in _INTENT_RULES:
        for kw in keywords:
            if kw in desc:
                scores[intent] = scores.get(intent, 0) + score
    if scores:
        best = max(scores, key=lambda k: scores[k])
        print(
            f"[Code] 🤖 Intent scores: {dict(sorted(scores.items(), key=lambda x: -x[1])[:5])}"
        )
        return best
                         
    if file_path and Path(file_path).exists():
        return "edit"
    if code:
        return "explain"
    return "write"

                                                      
def _take_screenshot() -> Optional[Path]:
    try:
        import pyautogui

        screenshot_path = DESKTOP / f"INDRA_debug_{int(time.time())}.png"
        screenshot = pyautogui.screenshot()
        screenshot.save(str(screenshot_path))
                                          
        if screenshot_path.stat().st_size < 1024:
            screenshot_path.unlink(missing_ok=True)
            raise ValueError("Screenshot file is suspiciously small.")
        print(f"[Code] 📸 Screenshot: {screenshot_path}")
        return screenshot_path
    except ImportError:
        print("[Code] ⚠️  pyautogui not installed. Run: pip install pyautogui pillow")
        return None
    except Exception as e:
        print(f"[Code] ⚠️  Screenshot failed: {e}")
        return None

                                                       
def _run_file(path: Path, args: list, timeout: int) -> str:
    info = _lang_info(path.suffix.lstrip("."))
    interp = info.get("interp")
    if not interp:
        return f"No interpreter configured for '{path.suffix}' files."
    cmd = interp + [str(path)] + (args or [])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(path.parent),
        )
        parts = []
        if result.stdout.strip():
            parts.append(f"Output:\n{result.stdout.strip()}")
        if result.stderr.strip():
            parts.append(f"Stderr:\n{result.stderr.strip()}")
        exit_info = f"Exit code: {result.returncode}"
        parts.append(exit_info)
        return "\n\n".join(parts) if parts else "Executed with no output."
    except subprocess.TimeoutExpired:
        return f"⏱  Timed out after {timeout}s."
    except FileNotFoundError:
        tool = interp[0]
        return f"Interpreter not found: '{tool}'. Is it installed and on PATH?"
    except Exception as e:
        return f"Execution error: {e}"

                                                 
def _write(
    description: str, language: str, output_path: str, player=None
) -> Tuple[str, Path]:
    lang = language or "python"
    info = _lang_info(lang)
    test_fw = info.get("test", "pytest")
    prompt = f"""You are an elite {lang} engineer.
Write production-quality, complete, working {lang} code for the task below.

STRICT RULES:
- Output ONLY the raw code. Zero explanation. Zero markdown. Zero backticks.
- Use modern {lang} best practices and idioms.
- Include inline comments only where non-obvious.
- Full error handling with meaningful messages.
- Type hints / type annotations where applicable.
- No placeholder stubs — every function must be fully implemented.
- Code must be immediately runnable without modifications.

Task: {description}

Code:"""
    response = _generate_content(prompt)
    code = _clean_code(response)
    if not code:
        raise ValueError("Model returned empty code.")
    path = _resolve_save_path(output_path, lang)
    _save_file(path, code)
    return code, path

                                                    
def _fix_code(
    code: str, error_output: str, description: str, error_category: str = "generic"
) -> str:
    """
    Category-aware fix prompt — gives the model better context about what went wrong.
    """
    category_hints = {
        "syntax": "Focus on fixing syntax/indentation errors. Ensure all brackets, quotes, colons are balanced.",
        "import": "The error is an import/module issue. Fix missing packages or incorrect import paths.",
        "name": "A variable or function is referenced before definition. Fix name/scope issues.",
        "type": "A type mismatch or incompatible operation. Fix type conversions and argument types.",
        "file": "A file path does not exist. Use proper path handling (pathlib, os.path).",
        "permission": "A permission error. Add appropriate permission checks or use safer alternatives.",
        "network": "A network/connection error. Add retry logic and connection error handling.",
        "runtime": "A runtime exception. Add proper try/except blocks around the failing section.",
        "generic": "Fix all errors to make the code run successfully.",
    }
    hint = category_hints.get(error_category, category_hints["generic"])
    prompt = f"""You are an expert debugger.
Fix the code below so it runs without errors.

TASK GOAL: {description}
ERROR TYPE: {error_category}
HINT: {hint}

ERROR OUTPUT:
{error_output[:3000]}

BROKEN CODE:
{code}

RULES:
- Return ONLY the complete fixed code. No explanation. No backticks. No markdown.
- Do NOT truncate or summarize — return the full file.
- If the fix requires a new import, add it at the top.
- Preserve all working functionality.

FIXED CODE:"""
    result = _clean_code(_generate_content(prompt))
    if not result:
        raise ValueError("Fix attempt returned empty code.")
    return result

                                                 
def _build(
    description, language, output_path, args, timeout, speak=None, player=None
) -> str:
    if not description:
        return "Please describe what you want me to build, sir."
    if player:
        player.write_log("[Code] Build started…")
    lang = language or "python"
    try:
        code, path = _write(description, lang, output_path, player)
        print(f"[Code] ✅ Written: {path}")
    except Exception as e:
        msg = f"Could not write initial code: {e}"
        if speak:
            speak(msg)
        return msg

    last_output = ""
    for attempt in range(1, MAX_BUILD_ATTEMPTS + 1):
        print(f"[Code] 🔄 Attempt {attempt}/{MAX_BUILD_ATTEMPTS}")
        if player:
            player.write_log(f"[Code] Attempt {attempt}/{MAX_BUILD_ATTEMPTS}…")

        last_output = _run_file(path, args, timeout)
        has_err, err_cat = _classify_error(last_output)

        if not has_err:
            plural = "s" if attempt > 1 else ""
            msg = (
                f"Build complete, sir. "
                f"Code is working after {attempt} attempt{plural}. "
                f"Saved to {path}."
            )
            if speak:
                speak(msg)
            return f"{msg}\n\nOutput:\n{last_output}"

        print(f"[Code] ⚠️  Error [{err_cat}] on attempt {attempt}, fixing…")
        if player:
            player.write_log(f"[Code] Fixing [{err_cat}] (attempt {attempt})…")

        try:
            code = _fix_code(code, last_output, description, err_cat)
            _save_file(path, code)
        except Exception as e:
            msg = f"Could not fix code on attempt {attempt}: {e}"
            if speak:
                speak(msg)
            return msg

    msg = (
        f"I was unable to build a working version after {MAX_BUILD_ATTEMPTS} attempts, sir. "
        f"Last error type: [{_classify_error(last_output)[1]}]. "
        f"Last error: {last_output[:300]}"
    )
    if speak:
        speak(msg)
    return f"{msg}\n\nLast code saved to: {path}"

                                                        
def _write_action(description, language, output_path, player) -> str:
    if not description:
        return "Please describe what you want me to write, sir."
    if player:
        player.write_log("[Code] Writing code…")
    try:
        code, path = _write(description, language, output_path, player)
        print(f"[Code] ✅ Written: {path}")
        lines = _count_lines(code)
        return f"Code written ({lines} lines). Saved to: {path}\n\nPreview:\n{_preview(code)}"
    except Exception as e:
        return f"Could not generate code: {e}"

                                                       
def _edit_action(file_path, instruction, player) -> str:
    if not file_path:
        return "Please provide a file path to edit, sir."
    if not instruction:
        return "Please describe what change to make, sir."
    content, err = _read_file(file_path)
    if err:
        return err
    if player:
        player.write_log("[Code] Editing file…")
    prompt = f"""You are an expert code editor.
Apply EXACTLY the following change to the code below.

Change: {instruction}

RULES:
- Return the complete updated file. No explanation. No backticks. No markdown.
- Do NOT remove any existing functionality unless the change explicitly requires it.
- Preserve the original code style and formatting.
- If the change is ambiguous, make the most sensible interpretation.

Original code:
{content}

Updated code:"""
    try:
        response = _generate_content(prompt)
        edited = _clean_code(response)
        if not edited:
            return "Edit returned empty result. File not modified."
    except Exception as e:
        return f"Could not edit code: {e}"
    status = _save_file(Path(file_path), edited)
    orig_lines = _count_lines(content)
    new_lines = _count_lines(edited)
    diff_str = (
        f"+{new_lines - orig_lines}"
        if new_lines >= orig_lines
        else str(new_lines - orig_lines)
    )
    print(f"[Code] ✅ Edited: {file_path} ({orig_lines}→{new_lines} lines, {diff_str})")
    return f"File edited. {status}\nLines: {orig_lines} → {new_lines} ({diff_str})\n\nPreview:\n{_preview(edited)}"

                                                          
def _explain_action(file_path, code, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "Please provide code or a file path to explain, sir."
    if player:
        player.write_log("[Code] Analyzing code…")
    lang_hint = ""
    if file_path:
        suffix = Path(file_path).suffix
        lang_hint = f"Language: {suffix.lstrip('.')}. "
    prompt = f"""You are an expert software engineer and technical writer.
{lang_hint}Explain the following code clearly and precisely.

Structure your explanation as:
1. OVERVIEW — What this code does in 1–2 sentences.
2. HOW IT WORKS — Key logic, algorithms, and data flow (3–5 sentences).
3. IMPORTANT DETAILS — Edge cases, dependencies, or gotchas to be aware of.
4. USAGE EXAMPLE — A one-liner showing how to call/use it (if applicable).

Be concise. No padding.

Code:
{code[:5000]}

Explanation:"""
    return _generate_content(prompt).strip()

                                                      
def _run_action(file_path, args, timeout, player) -> str:
    if not file_path:
        return "Please provide a file path to run, sir."
    p = Path(file_path)
    if not p.exists():
        return f"File not found: {file_path}"
    if player:
        player.write_log(f"[Code] Running {p.name}…")
    start = time.time()
    result = _run_file(p, args, timeout)
    elapsed = time.time() - start
    return f"[Ran in {elapsed:.2f}s]\n{result}"

                                                           
def _optimize_action(file_path, code, language, output_path, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "Please provide code or a file path to optimize, sir."
    if player:
        player.write_log("[Code] Optimizing code…")
    lang = language or "python"
    prompt = f"""You are a principal {lang} engineer conducting a performance and quality optimization pass.

Optimize the following code for:
1. PERFORMANCE — Eliminate unnecessary iterations, use efficient data structures, avoid redundant computation, prefer built-ins.
2. READABILITY — Descriptive names, logical grouping, remove dead/commented code.
3. BEST PRACTICES — Modern {lang} idioms, proper error handling, type hints (if {lang} supports them).
4. MEMORY — Reduce allocations, use generators/lazy evaluation where appropriate.
5. CONCISENESS — Remove redundancy without sacrificing clarity.

Return ONLY the optimized code. No explanation. No backticks.

Original code:
{code[:7000]}

Optimized code:"""
    optimized = _clean_code(_generate_content(prompt))
    if not optimized:
        return "Optimization returned empty result. File not modified."
    save_path = Path(file_path) if file_path else _resolve_save_path(output_path, lang)
    status = _save_file(save_path, optimized)
    orig_lines = _count_lines(code)
    opt_lines = _count_lines(optimized)
    diff = orig_lines - opt_lines
    sign = "−" if diff > 0 else "+"
    print(f"[Code] ✅ Optimized: {save_path}")
    return (
        f"Code optimized. {status}\n"
        f"Lines: {orig_lines} → {opt_lines} ({sign}{abs(diff)} lines)\n\n"
        f"Preview:\n{_preview(optimized)}"
    )

                                                        
def _screen_debug_action(description, file_path, player, speak=None) -> str:
    if player:
        player.write_log("[Code] Capturing screen for analysis…")
    print("[Code] 📸 Capturing screen for debug…")
    screenshot_path = _take_screenshot()
    if not screenshot_path:
        return (
            "Could not take screenshot, sir. Ensure pyautogui and pillow are installed."
        )

    file_content = ""
    if file_path:
        file_content, err = _read_file(file_path)
        if err:
            print(f"[Code] ⚠️  Could not read file: {err}")

    try:
        image_bytes = screenshot_path.read_bytes()
        user_question = (
            description or "What error or problem do you see? How can it be fixed?"
        )
        context = ""
        if file_content:
            context = f"\n\nRelated file content:\n```\n{file_content[:4000]}\n```"

        analysis_prompt = f"""You are an expert programmer analyzing a screenshot to diagnose issues.

User's question: {user_question}{context}

Instructions:
1. Identify and QUOTE any visible error messages exactly.
2. Explain in plain English what is causing the problem.
3. Provide a precise, actionable fix.
4. If code is visible and fixable, provide the corrected version in a single fenced code block.
5. If it's a configuration/environment issue, give step-by-step commands to resolve it.

Be specific. Be actionable."""

        analysis = _multimodal_generate(image_bytes, analysis_prompt)
        print("[Code] ✅ Screen analysis complete")

        try:
            screenshot_path.unlink()
        except Exception:
            pass

        if file_path and file_content:
            code_match = re.search(r"```[a-zA-Z0-9_+-]*\n(.*?)```", analysis, re.DOTALL)
            if code_match:
                fixed_code = code_match.group(1).strip()
                if (
                    len(fixed_code) > 50
                ):                                                      
                    save_path = Path(file_path)
                    _save_file(save_path, fixed_code)
                    analysis += f"\n\n✅ Fixed code saved to: {file_path}"
                    print(f"[Code] ✅ Auto-applied fix to: {file_path}")

        return analysis
    except Exception as e:
        try:
            screenshot_path.unlink()
        except Exception:
            pass
        return f"Screen analysis failed: {e}"

                                                          
def _generate_tests(
    file_path: str, code: str, language: str, output_path: str, player
) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "Please provide code or a file path to generate tests for."
    if player:
        player.write_log("[Code] Generating tests…")
    lang = language or "python"
    framework = _detect_test_framework(code, lang)
    imports_found = _extract_imports_from_code(code, lang)
    prompt = f"""You are an expert {lang} test engineer.
Write comprehensive unit tests using {framework} for the following code.

RULES:
- Use {framework} testing conventions and best practices.
- Cover: happy path, edge cases, boundary values, error/exception cases.
- Each test has a clear, descriptive name that explains what it tests.
- Tests must be independent — no shared mutable state.
- Mock external dependencies (filesystem, network, DB) where needed.
- Return ONLY the test code. No explanation. No backticks.

Known imports in source: {', '.join(imports_found) if imports_found else 'none detected'}

Source code:
{code[:6000]}

Test code:"""
    test_code = _clean_code(_generate_content(prompt))
    if not test_code:
        return "Test generation returned empty result."
                         
    if file_path:
        p = Path(file_path)
        save_path = p.with_name(f"test_{p.stem}{p.suffix}")
    else:
        save_path = _resolve_save_path(output_path or "", lang)
        save_path = save_path.with_stem(save_path.stem + "_test")
    status = _save_file(save_path, test_code)
    return f"Tests generated ({framework}). {status}\n\nPreview:\n{_preview(test_code, 20)}"

                                                       
def _review_code(file_path: str, code: str, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "Please provide code to review."
    if player:
        player.write_log("[Code] Reviewing code…")
    prompt = f"""You are a principal engineer conducting a thorough code review.

Review the following code and provide a structured report using this format:

## Summary
One sentence verdict (e.g., "Solid structure with minor issues" / "Needs significant work").

## 🐛 Bugs & Logic Errors
List each bug with line reference and exact fix. Mark severity: [CRITICAL / HIGH / MEDIUM / LOW]

## 🔒 Security Issues
List any security vulnerabilities with risk level and remediation.

## ⚡ Performance Issues
List inefficiencies with suggested optimizations.

## 📖 Readability & Style
Naming, formatting, complexity concerns.

## ✅ Strengths
What was done well (be specific).

## 🎯 Top 3 Priority Fixes
Numbered list of the most important changes to make first.

Code:
{code[:7000]}

Review:"""
    return _generate_content(prompt).strip()

                                                         
def _security_scan(file_path: str, code: str, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "Please provide code to scan."
    if player:
        player.write_log("[Code] Security scanning…")
    prompt = f"""You are a senior application security engineer (AppSec).
Perform a comprehensive SAST (Static Application Security Testing) scan on the following code.

Check for (but not limited to):
- Injection flaws (SQL, Command, LDAP, XPath)
- Broken authentication / hardcoded credentials / secrets
- Sensitive data exposure (PII, keys in logs/responses)
- Path traversal / insecure file operations
- Insecure deserialization
- Cross-Site Scripting (XSS) / CSRF (if web code)
- Improper error handling leaking internals
- Outdated or insecure cryptographic practices
- Race conditions / TOCTOU
- Unvalidated inputs / missing sanitization

For each finding, provide:
| # | Vulnerability | Location | Risk Level | CVSS-like Score | Fix |
Use table format. Then add a "Remediation Priority" section ranking the top 3 fixes.

Code:
{code[:7000]}

Security Analysis:"""
    return _generate_content(prompt).strip()

                                                    
def _refactor_code(
    file_path: str, code: str, pattern: str, language: str, player
) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "Please provide code to refactor."
    if not pattern:
        pattern = "Improve overall structure, readability, and maintainability using SOLID principles"
    if player:
        player.write_log(f"[Code] Refactoring: {pattern[:60]}…")
    lang = language or "python"
    prompt = f"""You are a senior {lang} engineer performing a targeted refactor.

Refactoring instruction: {pattern}

RULES:
- Preserve ALL existing functionality exactly (no regressions).
- Apply the refactoring pattern cleanly and completely.
- Do not introduce new features.
- Return ONLY the refactored code. No explanation. No backticks.

Original code:
{code[:7000]}

Refactored code:"""
    refactored = _clean_code(_generate_content(prompt))
    if not refactored:
        return "Refactor returned empty result. File not modified."
    save_path = Path(file_path) if file_path else _resolve_save_path("", lang)
    status = _save_file(save_path, refactored)
    orig_lines = _count_lines(code)
    new_lines = _count_lines(refactored)
    return f"Refactored ({pattern[:50]}…). {status}\nLines: {orig_lines} → {new_lines}\n\nPreview:\n{_preview(refactored)}"

                                                   
def _convert_code(
    file_path: str, code: str, source_lang: str, target_lang: str, player
) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "Please provide code to convert."
    if not target_lang:
        return "Please specify the target language (e.g., target_lang='typescript')."
    if not source_lang or source_lang == "guess":
                                           
        source_lang = Path(file_path).suffix.lstrip(".") if file_path else "unknown"
    if player:
        player.write_log(f"[Code] Converting {source_lang} → {target_lang}…")
    prompt = f"""You are an expert polyglot software engineer.

Convert the following {source_lang} code to idiomatic {target_lang}.

RULES:
- Preserve EXACT logic and behavior — this is a 1:1 port.
- Use idiomatic {target_lang} patterns (not literal translation).
- Include all necessary imports/requires for {target_lang}.
- Add type annotations if {target_lang} supports them.
- Handle {target_lang}-specific error patterns properly.
- Return ONLY the {target_lang} code. No explanation. No backticks.

{source_lang} code:
{code[:6000]}

{target_lang} code:"""
    converted = _clean_code(_generate_content(prompt))
    if not converted:
        return "Conversion returned empty result."
    info = _lang_info(target_lang)
    ext = info["ext"]
    save_path = _resolve_save_path("", target_lang)
    status = _save_file(save_path, converted)
    return f"Converted {source_lang} → {target_lang}. {status}\n\nPreview:\n{_preview(converted)}"

                                                         
def _generate_docs(file_path: str, code: str, language: str, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "Please provide code to document."
    if player:
        player.write_log("[Code] Generating documentation…")
    lang = language or (Path(file_path).suffix.lstrip(".") if file_path else "python")
    doc_styles = {
        "python": "Google-style docstrings",
        "javascript": "JSDoc comments",
        "typescript": "TSDoc comments",
        "java": "Javadoc comments",
        "go": "GoDoc comments",
        "rust": "Rustdoc comments",
        "ruby": "YARD comments",
        "php": "PHPDoc comments",
    }
    style = doc_styles.get(
        lang.lower(), "inline comments and function-level documentation"
    )
    prompt = f"""You are an expert {lang} technical writer.
Add comprehensive {style} to every function, class, and module in this code.

RULES:
- Document parameters (name, type, description), return values, and raised exceptions.
- Add a module-level docstring/comment at the top summarizing the file's purpose.
- For complex logic, add inline comments explaining the WHY, not the WHAT.
- Do NOT change any logic — documentation only.
- Return ONLY the fully documented code. No explanation. No backticks.

Code:
{code[:7000]}

Documented code:"""
    doc_code = _clean_code(_generate_content(prompt))
    if not doc_code:
        return "Documentation generation returned empty result."
    save_path = Path(file_path) if file_path else _resolve_save_path("", lang)
    status = _save_file(save_path, doc_code)
    return f"Documentation added ({style}). {status}\n\nPreview:\n{_preview(doc_code)}"

                                                
def _lint_code(file_path: str, player) -> str:
    if not file_path:
        return "Please provide a file path to lint."
    p = Path(file_path)
    if not p.exists():
        return f"File not found: {file_path}"
    if player:
        player.write_log(f"[Code] Linting {p.name}…")
    info = _lang_info(p.suffix.lstrip("."))
    linters = info.get("lint", [])
    if not linters:
        return f"No linter configured for '{p.suffix}' files."
    tool = linters[0]
    try:
        result = subprocess.run(
            [tool, str(p)],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(p.parent),
        )
        output = result.stdout.strip() or result.stderr.strip()
        if not output:
            return f"✅ No linting issues found in {p.name}."
        issue_count = len(output.splitlines())
        return f"🔍 Lint results for {p.name} ({issue_count} issue{'s' if issue_count != 1 else ''}):\n\n{output}"
    except FileNotFoundError:
        return (
            f"Linter '{tool}' not found. Install it:\n"
            f"  Python: pip install flake8\n"
            f"  JS/TS:  npm install -g eslint\n"
            f"  Shell:  apt install shellcheck"
        )
    except subprocess.TimeoutExpired:
        return f"Linting timed out after 15s."
    except Exception as e:
        return f"Linting failed: {e}"

                                                  
def _format_code(file_path: str, player) -> str:
    if not file_path:
        return "Please provide a file path to format."
    p = Path(file_path)
    if not p.exists():
        return f"File not found: {file_path}"
    if player:
        player.write_log(f"[Code] Formatting {p.name}…")
    info = _lang_info(p.suffix.lstrip("."))
    fmt_cmd = info.get("fmt", [])
    if not fmt_cmd:
        return f"No formatter configured for '{p.suffix}' files."
    cmd = fmt_cmd + [str(p)]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15, cwd=str(p.parent)
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            return f"Formatting failed:\n{err}"
        return f"✅ Formatted {p.name} using {fmt_cmd[0]}."
    except FileNotFoundError:
        return (
            f"Formatter '{fmt_cmd[0]}' not found. Install it:\n"
            f"  Python: pip install black\n"
            f"  JS/TS:  npm install -g prettier"
        )
    except subprocess.TimeoutExpired:
        return "Formatting timed out after 15s."
    except Exception as e:
        return f"Formatting failed: {e}"

                                                        
def _extract_dependencies(file_path: str, code: str, language: str, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "Please provide code to extract dependencies from."
    if player:
        player.write_log("[Code] Extracting dependencies…")
    lang = language or (Path(file_path).suffix.lstrip(".") if file_path else "python")

    detected = _extract_imports_from_code(code, lang)

    prompt = f"""You are a {lang} package expert.
The following imports were detected: {', '.join(detected) if detected else 'none detected via static analysis'}.

Analyze the code below and produce the correct dependency file content:
- Python → requirements.txt format (package==version or package>=version)
- JavaScript/TypeScript → JSON object with "dependencies" key only
- Other → plain text list of package names with versions

Include ONLY third-party packages (exclude standard library).
Use the latest stable versions as of your knowledge cutoff.
Return ONLY the dependency file content. No explanation.

Code:
{code[:5000]}"""
    deps = _clean_code(_generate_content(prompt))

    base = Path(file_path).parent if file_path else DESKTOP
    if lang in ("python", "py"):
        out_path = base / "requirements_INDRA.txt"
    elif lang in ("javascript", "js", "typescript", "ts"):
        out_path = base / "package_INDRA.json"
    else:
        out_path = base / "deps_INDRA.txt"

    status = _save_file(out_path, deps)
    detected_str = f"\nStatically detected: {', '.join(detected)}" if detected else ""
    return f"Dependencies extracted. {status}{detected_str}\n\n{deps}"

                                                         
def _project_setup(language: str, project_name: str, player) -> str:
    if not project_name:
        project_name = "my_project"
                   
    project_name = re.sub(r"[^\w-]", "_", project_name).strip("_")
    lang = (language or "python").lower()
    base = DESKTOP / project_name
    if base.exists():
        return f"Project '{project_name}' already exists at {base}."
    try:
        base.mkdir()
        if lang in ("python", "py"):
            (base / "src").mkdir()
            (base / "tests").mkdir()
            (base / "src" / "__init__.py").touch()
            (base / "tests" / "__init__.py").touch()
            (base / "main.py").write_text(
                f'"""Entry point for {project_name}."""\n\n\ndef main():\n    print("Hello from {project_name}!")\n\n\nif __name__ == "__main__":\n    main()\n'
            )
            (base / "requirements.txt").touch()
            (base / "README.md").write_text(
                f"# {project_name}\n\n## Setup\n\n```bash\npip install -r requirements.txt\npython main.py\n```\n"
            )
            (base / ".gitignore").write_text(
                "__pycache__/\n*.pyc\n*.pyo\n.venv/\nvenv/\n.env\n*.egg-info/\ndist/\nbuild/\n"
            )
        elif lang in ("javascript", "js"):
            (base / "src").mkdir()
            (base / "tests").mkdir()
            (base / "src" / "index.js").write_text(
                f'"use strict";\n\n// {project_name} entry point\nconsole.log("Hello from {project_name}!");\n'
            )
            (base / "package.json").write_text(
                json.dumps(
                    {
                        "name": project_name.lower().replace("_", "-"),
                        "version": "1.0.0",
                        "description": "",
                        "main": "src/index.js",
                        "scripts": {"start": "node src/index.js", "test": "jest"},
                        "keywords": [],
                        "author": "",
                        "license": "ISC",
                    },
                    indent=2,
                )
            )
            (base / "README.md").write_text(
                f"# {project_name}\n\n## Setup\n\n```bash\nnpm install\nnode src/index.js\n```\n"
            )
            (base / ".gitignore").write_text("node_modules/\n.env\ndist/\n")
        elif lang in ("typescript", "ts"):
            (base / "src").mkdir()
            (base / "tests").mkdir()
            (base / "src" / "index.ts").write_text(
                f'// {project_name} entry point\nconsole.log("Hello from {project_name}!");\n'
            )
            (base / "tsconfig.json").write_text(
                json.dumps(
                    {
                        "compilerOptions": {
                            "target": "ES2020",
                            "module": "commonjs",
                            "strict": True,
                            "outDir": "./dist",
                            "rootDir": "./src",
                        },
                        "include": ["src/**/*"],
                        "exclude": ["node_modules", "dist"],
                    },
                    indent=2,
                )
            )
            (base / "package.json").write_text(
                json.dumps(
                    {
                        "name": project_name.lower().replace("_", "-"),
                        "version": "1.0.0",
                        "scripts": {
                            "build": "tsc",
                            "start": "node dist/index.js",
                            "dev": "ts-node src/index.ts",
                        },
                        "devDependencies": {
                            "typescript": "^5.0.0",
                            "ts-node": "^10.0.0",
                            "@types/node": "^20.0.0",
                        },
                    },
                    indent=2,
                )
            )
            (base / ".gitignore").write_text("node_modules/\n.env\ndist/\n")
            (base / "README.md").write_text(
                f"# {project_name}\n\n## Setup\n\n```bash\nnpm install\nnpm run dev\n```\n"
            )
        else:
            (base / "main.py").touch()
            (base / "README.md").write_text(f"# {project_name}\n")

        file_count = sum(1 for _ in base.rglob("*") if _.is_file())
        return f"✅ Project '{project_name}' created at {base} ({file_count} files, {lang} template)."
    except Exception as e:
                                  
        if base.exists():
            shutil.rmtree(base, ignore_errors=True)
        return f"Project setup failed: {e}"

                                                       
def _git_diff(file_path: str, player) -> str:
    if not file_path:
        return "Please provide a file path."
    p = Path(file_path)
    if not p.exists():
        return f"File not found: {file_path}"
    try:
        result = subprocess.run(
            ["git", "diff", "--", str(p.name)],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(p.parent),
        )
        diff = result.stdout.strip()
        if not diff:
                             
            result = subprocess.run(
                ["git", "diff", "--cached", "--", str(p.name)],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(p.parent),
            )
            diff = result.stdout.strip()
        return diff if diff else "No changes detected (working tree clean)."
    except FileNotFoundError:
        return "Git not installed or not on PATH."
    except Exception as e:
        return f"git diff failed: {e}"

def _git_commit(file_path: str, message: str, player) -> str:
    if not file_path:
        return "Please provide a file path."
    p = Path(file_path)
    if not p.exists():
        return f"File not found: {file_path}"
                                                  
    if not message:
        try:
                                                                
            diff_result = subprocess.run(
                ["git", "diff", "--cached", "--stat"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(p.parent),
            )
            diff_context = diff_result.stdout.strip() or f"changes to {p.name}"
            prompt = f"""Write a concise git commit message for the following change.
Use Conventional Commits format (feat:, fix:, refactor:, docs:, chore:, etc.).
One line only. Max 72 characters. No period at end.
Change context: {diff_context}
File: {p.name}
Message:"""
            message = _generate_content(prompt).strip().split("\n")[0][:72]
        except Exception:
            message = f"chore: update {p.name}"
    try:
        subprocess.run(
            ["git", "add", str(p)],
            check=True,
            cwd=str(p.parent),
            capture_output=True,
            timeout=10,
        )
        result = subprocess.run(
            ["git", "commit", "-m", message],
            check=True,
            cwd=str(p.parent),
            capture_output=True,
            text=True,
            timeout=15,
        )
        return f'✅ Committed: "{message}"\n{result.stdout.strip()}'
    except subprocess.CalledProcessError as e:
        return f"Commit failed: {e.stderr.strip() or e.stdout.strip()}"
    except Exception as e:
        return f"Commit failed: {e}"

def _git_push(player) -> str:
    try:
        result = subprocess.run(
            ["git", "push"], capture_output=True, text=True, timeout=30
        )
        out = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            return f"Push failed:\n{out}"
        return f"✅ Push successful.\n{out}" if out else "✅ Push successful."
    except subprocess.TimeoutExpired:
        return "Push timed out after 30s. Check your network connection."
    except Exception as e:
        return f"Push failed: {e}"

                                                     
def _benchmark(file_path: str, player) -> str:
    if not file_path:
        return "Please provide a file path."
    p = Path(file_path)
    if not p.exists():
        return f"File not found: {file_path}"
    if player:
        player.write_log(f"[Code] Benchmarking {p.name}…")

    if p.suffix == ".py":
                                                                      
        import tempfile

        profile_script = f"""
import cProfile
import pstats
import io
import time

start = time.perf_counter()
pr = cProfile.Profile()
pr.enable()

# Execute the target script in its own namespace
import runpy
try:
    runpy.run_path(r'{p}', run_name='__main__')
except SystemExit:
    pass

pr.disable()
elapsed = time.perf_counter() - start

s = io.StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
ps.print_stats(15)

print(f"\\n⏱  Total elapsed: {{elapsed:.4f}}s")
print(s.getvalue())
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
            tmp.write(profile_script)
            tmp_path = tmp.name
        try:
            result = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(p.parent),
            )
            out = result.stdout.strip() or result.stderr.strip()
            return f"📊 Benchmark for {p.name}:\n\n{out}"
        except subprocess.TimeoutExpired:
            return "Benchmark timed out after 60s."
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    else:
                                      
        start = time.perf_counter()
        result = _run_file(p, [], 30)
        elapsed = time.perf_counter() - start
        return f"📊 {p.name} completed in {elapsed:.4f}s\n\n{result}"

                                                        
def _api_generate(description: str, language: str, output_path: str, player) -> str:
    if not description:
        return "Please describe the API to generate."
    lang = language or "python"
    if player:
        player.write_log("[Code] Generating API…")
    framework_hint = {
        "python": "FastAPI (with Pydantic models, async where appropriate)",
        "javascript": "Express.js (with middleware, async/await, proper error handling)",
        "typescript": "Express.js with TypeScript (typed request/response, Zod validation)",
        "go": "net/http with gorilla/mux",
        "java": "Spring Boot",
        "ruby": "Sinatra or Rails API mode",
    }.get(lang.lower(), lang)
    prompt = f"""You are a senior backend engineer.
Build a complete REST API using {framework_hint} based on this specification:

{description}

Include:
- All routes with proper HTTP methods (GET/POST/PUT/DELETE/PATCH)
- Request validation and meaningful error responses (400, 404, 422, 500)
- Proper status codes for each endpoint
- Pydantic/Zod/DTO models for request and response bodies
- Basic health check endpoint (GET /health)
- CORS configuration
- Environment variable configuration (not hardcoded secrets)
- Brief inline comments for each route explaining its purpose
- A "# USAGE" comment block at the top explaining how to run the server

Return ONLY the complete, runnable code. No explanation. No backticks."""
    code = _clean_code(_generate_content(prompt))
    if not code:
        return "API generation returned empty result."
    path = _resolve_save_path(output_path, lang)
    status = _save_file(path, code)
    return f"API generated. {status}\n\nPreview:\n{_preview(code, 20)}"

                                                           
def _database_schema(description: str, output_path: str, player) -> str:
    if not description:
        return "Please describe the database schema."
    if player:
        player.write_log("[Code] Generating database schema…")
    prompt = f"""You are a senior database architect.
Design a complete, normalized SQL schema based on this description:

{description}

Include:
- CREATE TABLE statements with appropriate data types
- Primary keys (UUID preferred over serial integers)
- Foreign key constraints with ON DELETE/UPDATE behavior
- Indexes for frequently queried columns and foreign keys
- NOT NULL constraints where appropriate
- created_at / updated_at timestamps with defaults
- A brief comment on each table explaining its purpose
- Sample INSERT statements (3–5 rows per table for reference data)

Use ANSI SQL that is compatible with PostgreSQL.
Return ONLY the SQL. No explanation. No backticks."""
    sql = _clean_code(_generate_content(prompt))
    if not sql:
        return "Schema generation returned empty result."
    path = _resolve_save_path(output_path or "", "sql")
    status = _save_file(path, sql)
    table_count = len(re.findall(r"CREATE\s+TABLE", sql, re.IGNORECASE))
    return f"Schema generated ({table_count} tables). {status}\n\nPreview:\n{_preview(sql, 25)}"

                                                        
def _code_summary(file_path: str, code: str, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "No code provided."
    if player:
        player.write_log("[Code] Summarizing…")
    lines = _count_lines(code)
    prompt = f"""Provide a concise technical summary of this {lines}-line code file.

Structure:
- PURPOSE: What this code does (1 sentence).
- COMPONENTS: Key classes/functions and what each does (bullet list).
- DEPENDENCIES: External packages used.
- COMPLEXITY: Estimated complexity (Simple / Moderate / Complex) and why.

Code: {code[:5000]}

Summary:"""
    return _generate_content(prompt).strip()

                                                
def _undo_edit(file_path: str, player) -> str:
    if not file_path:
        return "No file path provided."
    p = Path(file_path)
                                 
    latest_backup = Path(str(p) + f"{BACKUP_SUFFIX}.1")
    if not latest_backup.exists():
                                            
        old_backup = Path(str(p) + BACKUP_SUFFIX)
        if old_backup.exists():
            latest_backup = old_backup
        else:
            return f"No backup available for {p.name}."
    try:
                                                                           
        if p.exists():
            _rolling_backup(p)
        shutil.copy2(latest_backup, p)
        latest_backup.unlink()
        return f"✅ Reverted {p.name} to previous version."
    except Exception as e:
        return f"Undo failed: {e}"

                                                 
def _batch(actions: List[Dict], player, speak, session_memory) -> str:
    """
    Execute multiple actions in sequence with per-action error isolation.
    One failing action does NOT stop the rest.
    """
    if not actions:
        return "No actions provided for batch execution."
    results = []
    total = len(actions)
    print(f"[Code] 🔄 Batch: {total} actions")
    for idx, act in enumerate(actions, 1):
        action_name = act.get("action", "unknown")
        print(f"[Code] Batch [{idx}/{total}]: {action_name}")
        if player:
            player.write_log(f"[Code] Batch {idx}/{total}: {action_name}…")
        try:
            params = dict(act)                          
            res = code_helper(
                params, player=player, speak=speak, session_memory=session_memory
            )
            results.append(f"[{idx}/{total}] ✅ {action_name}:\n{res}")
        except Exception as e:
            results.append(f"[{idx}/{total}] ❌ {action_name} FAILED: {e}")
    success = sum(1 for r in results if "✅" in r)
    fail = total - success
    header = f"Batch complete: {success}/{total} succeeded, {fail} failed.\n{'─'*50}\n"
    return header + "\n\n".join(results)

                                                          
def _update_session_memory(
    session_memory: Optional[Dict], key: str, value: Any
) -> None:
    """Store action results and context into session memory for cross-action awareness."""
    if session_memory is None:
        return
    if "history" not in session_memory:
        session_memory["history"] = []
    session_memory["history"].append(
        {"key": key, "value": value, "timestamp": time.time()}
    )
    session_memory[key] = value

def _get_session_context(session_memory: Optional[Dict]) -> str:
    """Build a context string from session memory for inclusion in prompts."""
    if not session_memory:
        return ""
    ctx_parts = []
    if "last_file" in session_memory:
        ctx_parts.append(f"Last file worked on: {session_memory['last_file']}")
    if "last_language" in session_memory:
        ctx_parts.append(f"Last language: {session_memory['last_language']}")
    if "last_error" in session_memory:
        ctx_parts.append(
            f"Last error encountered: {session_memory['last_error'][:200]}"
        )
    return "\n".join(ctx_parts) if ctx_parts else ""

                                                         
def code_helper(
    parameters: dict, response=None, player=None, session_memory=None, speak=None
) -> str:
    p = parameters or {}
    action = p.get("action", "auto").lower().strip()
    description = p.get("description", "").strip()
    language = p.get("language", "python").strip()
    output_path = p.get("output_path", "").strip()
    file_path = p.get("file_path", "").strip()
    code = p.get("code", "").strip()
    args = p.get("args", [])
    timeout = int(p.get("timeout", 30))
    instruction = p.get("instruction", "").strip()

    if file_path:
        _update_session_memory(session_memory, "last_file", file_path)
    if language:
        _update_session_memory(session_memory, "last_language", language)

    if action == "auto":
        action = _detect_intent(description, file_path, code)
        print(f"[Code] 🤖 Auto-detected intent: '{action}'")

    if action == "write":
        return _write_action(description, language, output_path, player)

    elif action == "edit":
        return _edit_action(file_path, instruction or description, player)

    elif action == "explain":
        return _explain_action(file_path, code, player)

    elif action == "run":
        result = _run_action(file_path, args, timeout, player)
        if _has_error(result):
            _update_session_memory(session_memory, "last_error", result)
        return result

    elif action == "build":
        return _build(description, language, output_path, args, timeout, speak, player)

    elif action == "optimize":
        return _optimize_action(file_path, code, language, output_path, player)

    elif action == "screen_debug":
        return _screen_debug_action(description, file_path, player, speak)

    elif action in ("generate_tests", "test"):
        return _generate_tests(file_path, code, language, output_path, player)

    elif action in ("review", "code_review"):
        return _review_code(file_path, code, player)

    elif action in ("security_scan", "security"):
        return _security_scan(file_path, code, player)

    elif action == "refactor":
        pattern = p.get("pattern", instruction or description)
        return _refactor_code(file_path, code, pattern, language, player)

    elif action == "convert":
        source_lang = p.get("source_lang", language)
        target_lang = p.get("target_lang", "")
        return _convert_code(file_path, code, source_lang, target_lang, player)

    elif action in ("generate_docs", "document", "docs"):
        return _generate_docs(file_path, code, language, player)

    elif action == "lint":
        return _lint_code(file_path, player)

    elif action == "format":
        return _format_code(file_path, player)

    elif action in ("dependencies", "deps"):
        return _extract_dependencies(file_path, code, language, player)

    elif action in ("project_setup", "scaffold"):
        project_name = p.get("project_name", description or "new_project")
        return _project_setup(language, project_name, player)

    elif action == "git_diff":
        return _git_diff(file_path, player)

    elif action == "git_commit":
        return _git_commit(file_path, p.get("message", ""), player)

    elif action == "git_push":
        return _git_push(player)

    elif action == "benchmark":
        return _benchmark(file_path, player)

    elif action in ("api_generate", "api"):
        return _api_generate(description, language, output_path, player)

    elif action in ("database_schema", "schema"):
        return _database_schema(description, output_path, player)

    elif action in ("code_summary", "summary"):
        return _code_summary(file_path, code, player)

    elif action == "undo":
        return _undo_edit(file_path, player)

    elif action == "batch":
        return _batch(p.get("actions", []), player, speak, session_memory)

    else:
        supported = (
            "write, edit, explain, run, build, optimize, screen_debug, "
            "test, review, security_scan, refactor, convert, docs, lint, format, "
            "dependencies, project_setup, git_diff, git_commit, git_push, "
            "benchmark, api_generate, schema, summary, batch, undo"
        )
        return f"Unknown action: '{action}'. Supported actions: {supported}"
