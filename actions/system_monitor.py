                     
                                                                                                                                       
import psutil
import shutil
from typing import Any

def system_monitor(parameters: dict[str, Any], ui_callback, dashboard_callback, send_log_callback, get_memory_callback) -> str:
    """Retrieves system hardware usage stats."""
    action = parameters.get("action", "full_report")
    
    try:
        if action == "full_report":
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = shutil.disk_usage("/")
            
            battery = ""
            if hasattr(psutil, "sensors_battery"):
                bat = psutil.sensors_battery()
                if bat:
                    plugged = "Plugged in" if bat.power_plugged else "On battery"
                    battery = f"\nBattery: {bat.percent}% ({plugged})"
                    
            return (f"System Status:\n"
                    f"CPU: {cpu}%\n"
                    f"RAM: {mem.percent}% ({mem.used // (1024**3)}GB / {mem.total // (1024**3)}GB)\n"
                    f"Disk: {disk.free // (1024**3)}GB free out of {disk.total // (1024**3)}GB"
                    f"{battery}")
        
        elif action == "get_cpu":
            cpu = psutil.cpu_percent(interval=0.5)
            return f"CPU Usage is at {cpu}%"
            
        elif action == "get_ram":
            mem = psutil.virtual_memory()
            return f"RAM Usage is at {mem.percent}%. {mem.used // (1024**3)}GB used, {mem.available // (1024**3)}GB available."
            
        elif action == "get_battery":
            if hasattr(psutil, "sensors_battery"):
                bat = psutil.sensors_battery()
                if bat:
                    plugged = "plugged in" if bat.power_plugged else "on battery"
                    return f"Battery is at {bat.percent}% and is {plugged}."
            return "No battery information available."
            
        elif action == "get_disk":
            disk = shutil.disk_usage("/")
            return f"Main Disk: {disk.free // (1024**3)}GB free out of {disk.total // (1024**3)}GB."
            
        return f"Unknown system_monitor action: {action}"
    except Exception as e:
        return f"Error retrieving system stats: {e}"
