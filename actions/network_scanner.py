import socket
import subprocess
import os

def network_scanner(parameters: dict, player=None) -> str:
    """
    Scans the local network for connected devices.
    """
    action = parameters.get("action", "arp").strip()
    
    if action == "arp":
        try:
            # Use arp -a to get local network devices
            result = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=10)
            return result.stdout.strip() or "No ARP entries found."
        except Exception as e:
            return f"Failed to run arp scan: {e}"
            
    elif action == "ping_sweep":
        base_ip = parameters.get("base_ip", "192.168.1").strip()
        found = []
        # Ping a small subnet quickly to find hosts
        try:
            for i in range(1, 255):
                ip = f"{base_ip}.{i}"
                if os.name == 'nt':
                    res = subprocess.run(["ping", "-n", "1", "-w", "100", ip], capture_output=True, text=True)
                    if "TTL=" in res.stdout:
                        found.append(ip)
                else:
                    res = subprocess.run(["ping", "-c", "1", "-W", "1", ip], capture_output=True, text=True)
                    if "ttl=" in res.stdout.lower():
                        found.append(ip)
            if not found:
                return "No devices found on ping sweep."
            return "Active IPs found:\n" + "\n".join(found)
        except Exception as e:
            return f"Failed during ping sweep: {e}"
            
    return f"Unknown action: {action}"
