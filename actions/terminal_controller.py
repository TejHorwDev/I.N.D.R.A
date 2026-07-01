import subprocess
import os

def terminal_controller(parameters: dict, player=None) -> str:
    """
    Executes raw shell commands on the host OS.
    """
    command = parameters.get("command", "").strip()
    if not command:
        return "No command provided."
    
    timeout = parameters.get("timeout", 60)
    
    try:
                                                 
        shell_cmd = ["powershell", "-Command", command] if os.name == 'nt' else ["bash", "-c", command]
        
        result = subprocess.run(
            shell_cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        
        output = []
        if stdout:
            output.append(f"STDOUT:\n{stdout}")
        if stderr:
            output.append(f"STDERR:\n{stderr}")
            
        if not output:
            return f"Command '{command}' executed successfully with no output."
            
        final_output = "\n".join(output)

        if len(final_output) > 2000:
            final_output = final_output[:2000] + "\n...[TRUNCATED]"
            
        return final_output
        
    except subprocess.TimeoutExpired:
        return f"Command '{command}' timed out after {timeout} seconds."
    except Exception as e:
        return f"Failed to execute command: {e}"
