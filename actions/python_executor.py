import sys
import io
import traceback
from contextlib import redirect_stdout, redirect_stderr

def python_executor(parameters: dict, player=None) -> str:
    """
    Instantly executes arbitrary Python code and returns the output.
    """
    code = parameters.get("code", "").strip()
    if not code:
        return "No code provided."

    # Capture stdout and stderr
    f_stdout = io.StringIO()
    f_stderr = io.StringIO()
    
    # We use a shared dictionary for local and global variables
    exec_globals = {}
    
    try:
        with redirect_stdout(f_stdout), redirect_stderr(f_stderr):
            exec(code, exec_globals)
        
        out = f_stdout.getvalue().strip()
        err = f_stderr.getvalue().strip()
        
        result = []
        if out:
            result.append(f"STDOUT:\n{out}")
        if err:
            result.append(f"STDERR:\n{err}")
            
        if not result:
            return "Code executed successfully with no output."
            
        final_output = "\n".join(result)
        if len(final_output) > 2000:
            return final_output[:2000] + "\n...[TRUNCATED]"
        return final_output
        
    except Exception as e:
        err_trace = traceback.format_exc()
        return f"Exception during execution:\n{err_trace}"
