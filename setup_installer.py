import os
import sys
import win32com.client
from pathlib import Path

def create_installer():
    base_dir = Path(__file__).resolve().parent
    exe_path = base_dir / "dist" / "INDRA" / "INDRA.exe"
    
    if not exe_path.exists():
        # Try checking for onefile output
        exe_path = base_dir / "dist" / "INDRA.exe"
        if not exe_path.exists():
            print("ERROR: INDRA.exe not found! Please build it first.")
            return
        
    shell = win32com.client.Dispatch("WScript.Shell")
    
    # 1. Desktop Shortcut
    desktop_dir = Path(shell.SpecialFolders("Desktop"))
    desktop_lnk = desktop_dir / "INDRA.lnk"
    
    shortcut = shell.CreateShortCut(str(desktop_lnk))
    shortcut.Targetpath = str(exe_path)
    shortcut.WorkingDirectory = str(exe_path.parent)
    shortcut.IconLocation = str(exe_path)
    shortcut.WindowStyle = 1 # Normal
    shortcut.Save()
    
    # 2. Startup Shortcut
    startup_dir = Path(shell.SpecialFolders("Startup"))
    startup_lnk = startup_dir / "INDRA.lnk"
    
    startup_shortcut = shell.CreateShortCut(str(startup_lnk))
    startup_shortcut.Targetpath = str(exe_path)
    startup_shortcut.WorkingDirectory = str(exe_path.parent)
    startup_shortcut.IconLocation = str(exe_path)
    startup_shortcut.WindowStyle = 1
    startup_shortcut.Save()
    
    print(f"Successfully installed INDRA as a standalone Desktop Application!")
    print(f"Desktop Icon created at: {desktop_lnk}")
    print(f"Auto-Start App registered at: {startup_lnk}")

if __name__ == "__main__":
    create_installer()
