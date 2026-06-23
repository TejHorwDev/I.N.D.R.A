import psutil
import subprocess

def system_diagnostics(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    Runs system diagnostics like battery health, ping tests, or internet speed tests.
    """
    action = parameters.get("action", "battery").lower()
    
    if action == "battery":
        if not hasattr(psutil, "sensors_battery"):
            return "Battery monitoring is not supported on this device."
        battery = psutil.sensors_battery()
        if battery is None:
            return "No battery detected (desktop mode)."
            
        percent = battery.percent
        plugged = "Plugged In" if battery.power_plugged else "Not Plugged In"
        
        return f"Battery Status: {percent}% ({plugged})"
        
    elif action == "speedtest":
        try:
            import speedtest as _st_mod
            st = _st_mod.Speedtest()
            st.get_best_server()
            download = st.download() / 1_000_000
            upload = st.upload() / 1_000_000
            ping = st.results.ping
            return f"Speed Test Results:\nDownload: {download:.2f} Mbps\nUpload: {upload:.2f} Mbps\nPing: {ping:.2f} ms"
        except ImportError:
            return "Speed test module is unavailable in this build."
        except Exception as e:
            return f"Failed to run speed test: {e}"
            
    elif action == "ping":
        target = parameters.get("target", "8.8.8.8")
        try:
            # -n 2 for faster execution on Windows
            result = subprocess.run(["ping", "-n", "2", target], capture_output=True, text=True, timeout=5)
            return f"Ping results for {target}:\n{result.stdout}"
        except Exception as e:
            return f"Failed to ping {target}: {e}"
            
    elif action == "wifi":
        try:
            result = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True)
            return f"Wi-Fi Status:\n{result.stdout}"
        except Exception as e:
            return f"Failed to fetch Wi-Fi status: {e}"
            
    else:
        return f"Unknown diagnostics action: {action}"
